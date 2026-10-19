@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install --target .vendor -r requirements.txt
pause
