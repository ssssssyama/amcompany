@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   テクスチャ高画質化ツール セットアップ
echo ========================================
echo.
echo ※ GPU推奨（NVIDIA CUDA / AMD ROCm）
echo   CPUでも動作しますが低速です。
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
echo パッケージをインストール中...
echo （PyTorchのダウンロードに数分かかる場合があります）
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [エラー] パッケージのインストールに失敗しました。
    echo.
    echo AMD GPUの場合は以下を手動実行してください:
    echo   pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.1
    echo   pip install realesrgan opencv-python Pillow
    pause
    exit /b 1
)

echo.
echo [OK] セットアップ完了！
echo   run.bat に画像ファイルをドラッグ＆ドロップして起動してください。
pause
