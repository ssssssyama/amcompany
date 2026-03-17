@echo off
chcp 65001 >/dev/null 2>&1
echo ========================================
echo   おみくじBot セットアップ
echo ========================================
echo.

python --version >/dev/null 2>&1
if %errorlevel% neq 0 (
    echo [エラー] Pythonが見つかりません。
    echo   https://www.python.org/downloads/ からインストールしてください。
    echo   「Add Python to PATH」にチェックを入れてください。
    pause
    exit /b 1
)

echo [OK] Pythonが見つかりました
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [エラー] パッケージのインストールに失敗しました。
    pause
    exit /b 1
)

echo.
echo [OK] セットアップ完了！
echo   run.bat をダブルクリックして起動してください。
pause
