@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   テストエビデンス自動化ツール セットアップ
echo ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [エラー] Pythonが見つかりません。
    echo   https://www.python.org/downloads/ からインストールしてください。
    echo   「Add Python to PATH」にチェックを入れてください。
    pause
    exit /b 1
)

echo [OK] Pythonが見つかりました
echo.
echo --- Pythonパッケージをインストール中 ---
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [エラー] パッケージのインストールに失敗しました。
    pause
    exit /b 1
)

echo.
echo --- Playwrightブラウザをインストール中 ---
playwright install chromium
if %errorlevel% neq 0 (
    echo [エラー] Playwrightのインストールに失敗しました。
    pause
    exit /b 1
)

echo.
echo [OK] セットアップ完了！
echo.
echo 使い方:
echo   python evidence_runner.py テスト仕様書.xlsx
echo.
echo 詳しくはREADME.mdを参照してください。
pause
