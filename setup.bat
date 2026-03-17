@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   AM Company ツール セットアップ
echo ========================================
echo.

REM Pythonの確認
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [エラー] Pythonが見つかりません。
    echo.
    echo Pythonをインストールしてください:
    echo   https://www.python.org/downloads/
    echo.
    echo インストール時に「Add Python to PATH」に
    echo チェックを入れるのを忘れないでください。
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] Python %PYVER% が見つかりました
echo.

REM 基本パッケージのインストール
echo --- VRChatツール用パッケージをインストール中 ---
pip install python-osc Pillow
if %errorlevel% neq 0 (
    echo [エラー] パッケージのインストールに失敗しました。
    echo   管理者として実行してみてください。
    pause
    exit /b 1
)
echo.
echo [OK] VRChatツール用のセットアップが完了しました！
echo.

REM オプション: AI系ツール
echo ========================================
echo   追加オプション
echo ========================================
echo.
echo AI系ツール（足音生成・テクスチャ高画質化）も
echo 使いますか？（GPUが必要です）
echo.
set /p AI_CHOICE="インストールする場合は y を入力: "

if /i "%AI_CHOICE%"=="y" (
    echo.
    echo --- AI系パッケージをインストール中 ---
    echo （数分かかる場合があります）
    pip install -r requirements-upscaler.txt
    echo.
    echo [OK] テクスチャ高画質化ツールのセットアップ完了
    echo.
    echo 足音生成ツールも使う場合は別途以下を実行してください:
    echo   pip install -r requirements-footstep.txt
)

echo.
echo ========================================
echo   セットアップ完了！
echo ========================================
echo.
echo ツールを起動するには:
echo   python launcher.py
echo.
echo または各ツールフォルダの .bat ファイルを
echo ダブルクリックしてください。
echo.
pause
