@echo off
chcp 65001 >/dev/null 2>&1
echo OSCタイマー を起動します...
echo.
cd /d "%~dp0"
python main.py %*
if %errorlevel% neq 0 (
    echo.
    echo [エラー] ツールの起動に失敗しました。
    echo   setup.bat を先に実行してください。
)
pause
