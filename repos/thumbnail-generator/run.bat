@echo off
chcp 65001 >nul 2>&1
echo サムネイル生成ツール を起動します...
echo.
cd /d "%~dp0"
python generate.py %*
if %errorlevel% neq 0 (
    echo.
    echo [エラー] ツールの起動に失敗しました。
    echo   setup.bat を先に実行してください。
)
pause
