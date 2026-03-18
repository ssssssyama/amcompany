@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
python gui.py
if %errorlevel% neq 0 (
    echo.
    echo [エラー] 起動に失敗しました。
    echo   setup.bat を先に実行してください。
    pause
)
