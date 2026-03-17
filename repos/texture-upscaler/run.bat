@echo off
chcp 65001 >nul 2>&1
echo テクスチャ高画質化ツール
echo.
echo 使い方: 画像ファイルをこのバッチファイルに
echo ドラッグ＆ドロップしてください。
echo.
cd /d "%~dp0"

if "%~1"=="" (
    set /p FILEPATH="画像ファイルのパスを入力: "
    python upscale.py "%FILEPATH%"
) else (
    echo 処理中: %~1
    python upscale.py "%~1"
)

if %errorlevel% neq 0 (
    echo.
    echo [エラー] 処理に失敗しました。
    echo   setup.bat を先に実行してください。
)
echo.
pause
