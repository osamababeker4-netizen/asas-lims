@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo       نظام مختبر أساس - LIMS V7.2.0
echo   المشاريع + المختبر + البرنامج الميداني
echo ========================================
echo.
if "%LIMS_BOOTSTRAP_PASSWORD%"=="" (
  echo قبل اول تشغيل فقط عيّن متغير البيئة LIMS_BOOTSTRAP_PASSWORD
  echo إلى كلمة مرور قوية من 12 حرفاً أو أكثر. لن يحفظها البرنامج في Git.
  echo.
)
python server.py
if errorlevel 1 (
  echo.
  echo تعذر تشغيل النظام. راجع رسالة الخطأ أعلاه وتحقق من Python وإعداد كلمة المرور الأولية.
  pause
)

