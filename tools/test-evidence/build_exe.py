"""Test Evidence ツール群を PyInstaller で exe 化するビルドスクリプト.

使い方:
    pip install pyinstaller
    python build_exe.py

出力:
    dist/test-evidence/  にすべての exe が生成される
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DIST_DIR = BASE_DIR / "dist" / "test-evidence"
BUILD_DIR = BASE_DIR / "build"

# ビルド対象と設定
TARGETS = [
    {
        "script": "evidence_runner.py",
        "name": "evidence-runner",
        "hidden_imports": [
            "playwright",
            "playwright.async_api",
            "playwright._impl",
            "playwright._impl._api_types",
            "playwright._impl._connection",
            "playwright._impl._driver",
            "playwright._impl._transport",
            "openpyxl",
            "PIL",
            "yaml",
            "csv",
            "json",
            "gen_spec",
            "project_config",
        ],
        "datas": [
            ("project_config.py", "."),
            ("gen_spec.py", "."),
            ("text2spec.py", "."),
        ],
        "collect_all": ["playwright"],
    },
    {
        "script": "gen_spec.py",
        "name": "gen-spec",
        "hidden_imports": [
            "openpyxl",
            "yaml",
            "text2spec",
        ],
        "datas": [
            ("text2spec.py", "."),
        ],
        "collect_all": [],
    },
    {
        "script": "record2spec.py",
        "name": "record2spec",
        "hidden_imports": [
            "yaml",
        ],
        "datas": [],
        "collect_all": [],
    },
    {
        "script": "text2spec.py",
        "name": "text2spec",
        "hidden_imports": [
            "yaml",
            "openpyxl",
        ],
        "datas": [],
        "collect_all": [],
    },
    {
        "script": "create_template.py",
        "name": "create-template",
        "hidden_imports": [
            "openpyxl",
        ],
        "datas": [],
        "collect_all": [],
    },
]


def build_target(target: dict) -> bool:
    """1つのターゲットをビルドする."""
    script = target["script"]
    name = target["name"]
    print(f"\n{'='*60}")
    print(f"  Building: {script} -> {name}.exe")
    print(f"{'='*60}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        f"--name={name}",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
    ]

    for imp in target["hidden_imports"]:
        cmd.extend(["--hidden-import", imp])

    for src, dest in target["datas"]:
        sep = ";" if sys.platform == "win32" else ":"
        cmd.extend(["--add-data", f"{src}{sep}{dest}"])

    for pkg in target.get("collect_all", []):
        cmd.extend(["--collect-all", pkg])

    cmd.append(script)

    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        print(f"  FAILED: {name}")
        return False
    print(f"  OK: {name}.exe")
    return True


def copy_extras():
    """サンプル・設定ファイルをdistにコピーする."""
    extras = [
        ("examples", "examples"),
    ]
    for src, dest in extras:
        src_path = BASE_DIR / src
        dest_path = DIST_DIR / dest
        if src_path.exists():
            if src_path.is_dir():
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(src_path, dest_path)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dest_path)
            print(f"  Copied: {src} -> {dest}")


def create_install_browsers_script():
    """Playwright ブラウザインストール用スクリプトを生成する."""
    bat_content = """@echo off
echo ============================================
echo  Playwright ブラウザのインストール
echo ============================================
echo.
echo Chromium ブラウザをダウンロードします...
echo （初回のみ必要です。数分かかる場合があります）
echo.

cd /d "%~dp0"
cd evidence-runner
evidence-runner.exe --version >nul 2>&1

:: Playwright CLI経由でインストール
python -m playwright install chromium 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [INFO] Python環境が見つからないため、手動インストールが必要です。
    echo.
    echo 以下のコマンドを実行してください:
    echo   pip install playwright
    echo   playwright install chromium
    echo.
) else (
    echo.
    echo ブラウザのインストールが完了しました！
)

echo.
pause
"""
    sh_content = """#!/bin/bash
echo "============================================"
echo "  Playwright ブラウザのインストール"
echo "============================================"
echo ""
echo "Chromium ブラウザをダウンロードします..."
echo "（初回のみ必要です。数分かかる場合があります）"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python3 -m playwright install chromium 2>/dev/null
if [ $? -ne 0 ]; then
    python -m playwright install chromium 2>/dev/null
    if [ $? -ne 0 ]; then
        echo ""
        echo "[INFO] Python環境が見つからないため、手動インストールが必要です。"
        echo ""
        echo "以下のコマンドを実行してください:"
        echo "  pip install playwright"
        echo "  playwright install chromium"
        echo ""
    fi
fi

echo ""
echo "ブラウザのインストールが完了しました！"
"""
    bat_path = DIST_DIR / "install-browsers.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"  Created: install-browsers.bat")

    sh_path = DIST_DIR / "install-browsers.sh"
    sh_path.write_text(sh_content, encoding="utf-8")
    os.chmod(sh_path, 0o755)
    print(f"  Created: install-browsers.sh")


def create_readme():
    """配布用READMEを生成する."""
    content = """# Test Evidence Pro - 実行ファイル版

## セットアップ（初回のみ）

### 1. ブラウザのインストール

テスト実行にはChromiumブラウザが必要です。

**Windows:**
```
install-browsers.bat
```

**macOS/Linux:**
```
./install-browsers.sh
```

または手動で:
```
pip install playwright
playwright install chromium
```

## 使い方

### テスト実行（メインツール）
```
evidence-runner/evidence-runner.exe spec.xlsx -c config.yaml -o output.xlsx
```

### テスト定義 → Excel変換
```
gen-spec/gen-spec.exe test_spec.yaml -o spec.xlsx
```

### Playwright録画 → YAML変換
```
record2spec/record2spec.exe recorded.py -o test_spec.yaml
```

### プレーンテキスト → YAML/Excel変換
```
text2spec/text2spec.exe test.txt -o test_spec.yaml
```

### Excelテンプレート生成
```
create-template/create-template.exe
```

## オプション一覧

evidence-runner の主なオプション:
  -c, --config FILE          プロジェクト設定YAMLファイル
  -o, --output FILE          出力先Excelファイル
  --sheets SHEET1 SHEET2     実行するシートの指定
  --headed                   ブラウザを表示して実行
  --dry-run                  書式チェックのみ（ブラウザ不使用）
  --verify-selectors         セレクタの事前検証
  --json-report FILE         JSON形式のレポート出力

## ファイル構成

```
test-evidence/
├── evidence-runner/     テスト実行エンジン
├── gen-spec/            Excel仕様書生成
├── record2spec/         Playwright録画変換
├── text2spec/           テキスト定義変換
├── create-template/     テンプレート生成
├── examples/            サンプルファイル
├── install-browsers.bat ブラウザインストール (Windows)
├── install-browsers.sh  ブラウザインストール (macOS/Linux)
└── README.txt           このファイル
```
"""
    readme_path = DIST_DIR / "README.txt"
    readme_path.write_text(content, encoding="utf-8")
    print(f"  Created: README.txt")


def main():
    """メインビルド処理."""
    print("=" * 60)
    print("  Test Evidence - exe ビルド")
    print("=" * 60)

    # PyInstaller の存在確認
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: PyInstaller がインストールされていません。")
        print("  pip install pyinstaller")
        sys.exit(1)

    # 出力ディレクトリ準備
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 各ターゲットをビルド
    results = []
    for target in TARGETS:
        ok = build_target(target)
        results.append((target["name"], ok))

    # 追加ファイル
    print(f"\n{'='*60}")
    print("  追加ファイルのコピー")
    print(f"{'='*60}")
    copy_extras()
    create_install_browsers_script()
    create_readme()

    # 結果サマリ
    print(f"\n{'='*60}")
    print("  ビルド結果")
    print(f"{'='*60}")
    all_ok = True
    for name, ok in results:
        status = "OK" if ok else "FAILED"
        print(f"  {name:.<30} {status}")
        if not ok:
            all_ok = False

    print(f"\n  出力先: {DIST_DIR.resolve()}")

    if not all_ok:
        print("\n  一部のビルドが失敗しました。")
        sys.exit(1)
    else:
        print("\n  すべてのビルドが完了しました！")


if __name__ == "__main__":
    main()
