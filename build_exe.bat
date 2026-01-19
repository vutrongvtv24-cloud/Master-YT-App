
@echo off
chcp 65001 > nul
echo ====================================================
echo      BUILDING MASTER_YTB V6.4 PREMIUM TO EXE
echo ====================================================
echo.

echo 1. Kiem tra thu vien can thiet...
pip install pyinstaller cryptography google-generativeai sqlite-utils yt-dlp PyQt6 google-api-python-client pandas openpyxl

echo.
echo 2. Bat dau build EXE...
echo Vui long doi khoang 1-3 phut...
echo.

pyinstaller --noconfirm --onefile --windowed --icon "resources/logo.ico" --name "Master_YTB_V6.4" --add-data "resources;resources" main_app.py

echo.
echo ====================================================
echo                 BUILD COMPLETE!
echo File EXE nam trong thu muc 'dist'
echo ====================================================
pause
