@echo off
chcp 65001 >nul 2>&1
echo ============================================
echo   闇バイト通報支援ツール を起動します...
echo ============================================
echo.
cd /d "%~dp0"
python main.py %*
if %errorlevel% neq 0 (
    echo.
    echo [エラー] ツールの起動に失敗しました。
    echo Python がインストールされているか確認してください。
    echo.
)
pause
