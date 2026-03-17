@echo off
chcp 65001 >nul 2>&1
echo OSCタイマー を起動します...
echo.
echo 使い方:
echo   このファイルをダブルクリック → 対話モードで起動
echo.
echo モードを選んでください:
echo   1. カウントダウン
echo   2. ストップウォッチ
echo   3. ポモドーロ
echo.
cd /d "%~dp0"
set /p MODE="番号を入力: "

if "%MODE%"=="1" (
    set /p MINUTES="何分カウントダウンしますか？: "
    python main.py countdown %MINUTES%
) else if "%MODE%"=="2" (
    python main.py stopwatch
) else if "%MODE%"=="3" (
    python main.py pomodoro
) else (
    echo 不明な選択です。
)
pause
