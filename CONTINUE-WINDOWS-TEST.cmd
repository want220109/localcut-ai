@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0package.json" (
  echo Copy this file and the scripts folder into your ORIGINAL LocalCut-AI folder.
  echo It must be next to package.json and the release folder created by the previous run.
  pause
  exit /b 1
)
echo LocalCut AI - continue installation and test
echo Reuses the installer already built on this PC. No full rebuild or paid API.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-local-test.ps1" -ResumeInstall
set "LOCALCUT_TEST_EXIT=%ERRORLEVEL%"
echo.
echo Read windows-results\RESULT.txt for the actual result, or the error above.
pause
exit /b %LOCALCUT_TEST_EXIT%
