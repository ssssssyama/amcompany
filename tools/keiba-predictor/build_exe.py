"""PyInstallerでkeiba_gui.pyをexe化するビルドスクリプト

使い方:
  pip install pyinstaller
  python build_exe.py

出力:
  dist/JRA競馬予想ツール.exe  (ワンファイル実行形式)
"""

import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "JRA競馬予想ツール",
    # アイコン（あれば）
    # "--icon", "icon.ico",
    # 同梱データ
    "--add-data", f"sample_data{os.pathsep}sample_data",
    # 同梱モジュール（main.py から遅延 import されるものを含む）
    "--hidden-import", "main",
    "--hidden-import", "data_manager",
    "--hidden-import", "feature_engine",
    "--hidden-import", "predictor",
    "--hidden-import", "formatter",
    "--hidden-import", "scraper",
    "--hidden-import", "database",
    "--hidden-import", "backtester",
    "--hidden-import", "bet_optimizer",
    "--hidden-import", "common",
    "--hidden-import", "common.error_handler",
    # scikit-learn（MLモデル使用時に必要）
    "--hidden-import", "sklearn",
    "--hidden-import", "sklearn.ensemble",
    "--hidden-import", "sklearn.preprocessing",
    # パス追加
    "--paths", SCRIPT_DIR,
    "--paths", os.path.join(SCRIPT_DIR, ".."),
    # エントリーポイント
    "keiba_gui.py",
]

print("=" * 60)
print("  JRA競馬予想ツール — exe ビルド")
print("=" * 60)
print()
print("実行コマンド:")
print(f"  {' '.join(cmd)}")
print()

result = subprocess.run(cmd)

if result.returncode == 0:
    exe_path = os.path.join(SCRIPT_DIR, "dist", "JRA競馬予想ツール.exe")
    print()
    print("=" * 60)
    print(f"  ビルド成功!")
    print(f"  出力: {exe_path}")
    print()
    print("  ※ dist フォルダの exe をダブルクリックで起動できます")
    print("  ※ data/ フォルダ(DB)は exe と同じ場所に配置してください")
    print("=" * 60)
else:
    print()
    print("ビルドに失敗しました。上記のエラーを確認してください。")
    sys.exit(1)
