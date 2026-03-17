@echo off
chcp 65001 >nul 2>&1
echo サムネイル生成ツール
echo.
cd /d "%~dp0"

echo 全商品のサムネイルを一括生成しますか？
set /p CHOICE="y で一括生成、n で個別指定: "

if /i "%CHOICE%"=="y" (
    python generate.py --all
) else (
    set /p TITLE="商品タイトルを入力: "
    set /p SUBTITLE="サブタイトル（なければEnter）: "
    python generate.py --title "%TITLE%" --subtitle "%SUBTITLE%"
)

if %errorlevel% neq 0 (
    echo.
    echo [エラー] 処理に失敗しました。
    echo   setup.bat を先に実行してください。
)
echo.
pause
