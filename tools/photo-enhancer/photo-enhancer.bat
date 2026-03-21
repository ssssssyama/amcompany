@echo off
echo 物件写真AIエンハンサー
echo.
python "%~dp0enhance.py" %*
if errorlevel 1 pause
