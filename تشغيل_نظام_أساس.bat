@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo      نظام مختبر أساس - LIMS
 echo     البرنامج الميداني + المختبر
 echo ========================================
echo.
python server.py
if errorlevel 1 (
  echo.
  echo تعذر تشغيل Python. جرّب تثبيت Python أو تشغيل: py server.py
  pause
)
