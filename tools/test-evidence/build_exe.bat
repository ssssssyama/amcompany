@echo off
echo ============================================
echo  Test Evidence - exe ビルド
echo ============================================
echo.

:: PyInstaller がなければインストール
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller をインストールしています...
    pip install pyinstaller
    echo.
)

:: ビルド実行
cd /d "%~dp0"
python build_exe.py

echo.
if %errorlevel% equ 0 (
    echo ビルド完了！ dist\test-evidence フォルダを確認してください。
) else (
    echo ビルドに失敗しました。エラーメッセージを確認してください。
)
echo.
pause
