"""デモアプリ - タスク管理システム（Flask + SQLite）.

テストエビデンス自動化ツールの動作確認用バックエンド。
DB検証機能のテストも可能にするため、全操作をSQLiteに永続化する。
"""

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, g, jsonify, request, send_file

app = Flask(__name__)

DB_PATH = Path(__file__).parent / "demo.db"


# ---------------------------------------------------------------------------
# DB接続ヘルパー
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def hash_password(password: str) -> str:
    """簡易パスワードハッシュ（デモ用）."""
    return hashlib.sha256(password.encode()).hexdigest()


# ---------------------------------------------------------------------------
# DDL: テーブル作成
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- 部署マスタ
CREATE TABLE IF NOT EXISTS departments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ユーザー
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    display_name    TEXT    NOT NULL,
    email           TEXT    NOT NULL,
    department_id   INTEGER REFERENCES departments(id),
    role            TEXT    NOT NULL DEFAULT 'member'
                        CHECK (role IN ('admin', 'manager', 'member')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ログイン履歴
CREATE TABLE IF NOT EXISTS login_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    login_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    ip_address  TEXT,
    success     INTEGER NOT NULL DEFAULT 1
);

-- タスク
CREATE TABLE IF NOT EXISTS tasks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    description      TEXT    DEFAULT '',
    priority         TEXT    NOT NULL DEFAULT '中'
                        CHECK (priority IN ('高', '中', '低')),
    status           TEXT    NOT NULL DEFAULT '未着手'
                        CHECK (status IN ('未着手', '進行中', '完了')),
    assigned_user_id INTEGER REFERENCES users(id),
    created_by       INTEGER NOT NULL REFERENCES users(id),
    due_date         TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- タスクコメント
CREATE TABLE IF NOT EXISTS task_comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    body        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

SEED_SQL = """
-- 部署マスタ
INSERT OR IGNORE INTO departments (id, name) VALUES
    (1, '開発部'),
    (2, '営業部'),
    (3, '総務部');

-- ユーザー（パスワードはSHA-256ハッシュ）
INSERT OR IGNORE INTO users (id, username, password_hash, display_name, email, department_id, role) VALUES
    (1, 'admin',    '{admin_hash}',    '管理者',       'admin@example.com',    1, 'admin'),
    (2, 'testuser', '{testuser_hash}', 'テストユーザー', 'testuser@example.com', 1, 'member'),
    (3, 'tanaka',   '{tanaka_hash}',   '田中太郎',     'tanaka@example.com',   2, 'manager'),
    (4, 'suzuki',   '{suzuki_hash}',   '鈴木花子',     'suzuki@example.com',   3, 'member');

-- 初期タスク
INSERT OR IGNORE INTO tasks (id, title, description, priority, status, assigned_user_id, created_by, due_date) VALUES
    (1, 'プロジェクト計画書の作成', '第2四半期のプロジェクト計画書を作成する', '高', '未着手', 2, 1, '2026-04-15'),
    (2, 'デザインレビュー',         'UI/UXデザインのレビューを実施',          '中', '進行中', 2, 1, '2026-03-25'),
    (3, '議事録の整理',             '先週の会議議事録を整理して共有',          '低', '完了',   3, 2, '2026-03-10');

-- 初期コメント
INSERT OR IGNORE INTO task_comments (id, task_id, user_id, body) VALUES
    (1, 1, 1, 'Q2の計画書はテンプレートを使ってください'),
    (2, 2, 2, 'モバイル対応のデザインも含めてレビューお願いします');
"""


def init_db():
    """データベースを初期化する（テーブル作成 + シードデータ投入）."""
    db = sqlite3.connect(str(DB_PATH))
    db.executescript(SCHEMA_SQL)

    seed = SEED_SQL.format(
        admin_hash=hash_password("admin123"),
        testuser_hash=hash_password("password123"),
        tanaka_hash=hash_password("tanaka123"),
        suzuki_hash=hash_password("suzuki123"),
    )
    try:
        db.executescript(seed)
    except sqlite3.IntegrityError:
        pass  # 既にデータがある場合はスキップ
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# API: 認証
# ---------------------------------------------------------------------------

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "")
    ip = request.remote_addr

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        (username,),
    ).fetchone()

    if user and user["password_hash"] == hash_password(password):
        db.execute(
            "INSERT INTO login_history (user_id, ip_address, success) VALUES (?, ?, 1)",
            (user["id"], ip),
        )
        db.commit()
        return jsonify({
            "success": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "email": user["email"],
                "role": user["role"],
                "department_id": user["department_id"],
            },
        })

    # ログイン失敗の記録
    if user:
        db.execute(
            "INSERT INTO login_history (user_id, ip_address, success) VALUES (?, ?, 0)",
            (user["id"], ip),
        )
        db.commit()

    return jsonify({"success": False, "error": "ユーザー名またはパスワードが正しくありません"}), 401


# ---------------------------------------------------------------------------
# API: タスク CRUD
# ---------------------------------------------------------------------------

@app.route("/api/tasks", methods=["GET"])
def api_list_tasks():
    db = get_db()
    rows = db.execute("""
        SELECT t.*, u.display_name AS assigned_name, c.display_name AS creator_name
        FROM tasks t
        LEFT JOIN users u ON t.assigned_user_id = u.id
        LEFT JOIN users c ON t.created_by = c.id
        ORDER BY t.id
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    data = request.get_json()
    db = get_db()
    cur = db.execute(
        """INSERT INTO tasks (title, description, priority, status, assigned_user_id, created_by, due_date)
           VALUES (?, ?, ?, '未着手', ?, ?, ?)""",
        (
            data["title"],
            data.get("description", ""),
            data.get("priority", "中"),
            data.get("assigned_user_id"),
            data["created_by"],
            data.get("due_date"),
        ),
    )
    db.commit()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(task)), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def api_update_task(task_id):
    data = request.get_json()
    db = get_db()
    fields = []
    values = []
    for key in ("title", "description", "priority", "status", "assigned_user_id", "due_date"):
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if not fields:
        return jsonify({"error": "更新項目がありません"}), 400

    fields.append("updated_at = datetime('now', 'localtime')")
    values.append(task_id)
    db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        return jsonify({"error": "タスクが見つかりません"}), 404
    return jsonify(dict(task))


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# API: タスクコメント
# ---------------------------------------------------------------------------

@app.route("/api/tasks/<int:task_id>/comments", methods=["GET"])
def api_list_comments(task_id):
    db = get_db()
    rows = db.execute("""
        SELECT tc.*, u.display_name
        FROM task_comments tc
        JOIN users u ON tc.user_id = u.id
        WHERE tc.task_id = ?
        ORDER BY tc.created_at
    """, (task_id,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/tasks/<int:task_id>/comments", methods=["POST"])
def api_create_comment(task_id):
    data = request.get_json()
    db = get_db()
    cur = db.execute(
        "INSERT INTO task_comments (task_id, user_id, body) VALUES (?, ?, ?)",
        (task_id, data["user_id"], data["body"]),
    )
    db.commit()
    comment = db.execute("""
        SELECT tc.*, u.display_name
        FROM task_comments tc
        JOIN users u ON tc.user_id = u.id
        WHERE tc.id = ?
    """, (cur.lastrowid,)).fetchone()
    return jsonify(dict(comment)), 201


# ---------------------------------------------------------------------------
# API: ユーザー・部署
# ---------------------------------------------------------------------------

@app.route("/api/users", methods=["GET"])
def api_list_users():
    db = get_db()
    rows = db.execute("""
        SELECT u.id, u.username, u.display_name, u.email, u.role, u.is_active,
               d.name AS department_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        ORDER BY u.id
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/departments", methods=["GET"])
def api_list_departments():
    db = get_db()
    rows = db.execute("SELECT * FROM departments ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# API: ログイン履歴
# ---------------------------------------------------------------------------

@app.route("/api/login-history", methods=["GET"])
def api_login_history():
    db = get_db()
    rows = db.execute("""
        SELECT lh.*, u.username, u.display_name
        FROM login_history lh
        JOIN users u ON lh.user_id = u.id
        ORDER BY lh.login_at DESC
        LIMIT 50
    """).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# API: DB初期化（テスト用）
# ---------------------------------------------------------------------------

@app.route("/api/reset-db", methods=["POST"])
def api_reset_db():
    """DBを初期状態にリセットする（テスト用）."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    return jsonify({"success": True, "message": "DBを初期化しました"})


# ---------------------------------------------------------------------------
# フロントエンド配信
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_file("app.html")


# ---------------------------------------------------------------------------
# 起動
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print(f"DB: {DB_PATH}")
    print("http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
