@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0package.json" (
  echo Please extract the entire ZIP before running this file.
  pause
  exit /b 1
)
echo LocalCut AI - Windows local build and test
echo No paid API, GitHub login or public publication is used.
echo Keep this window open until the test finishes.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-local-test.ps1"
set "LOCALCUT_TEST_EXIT=%ERRORLEVEL%"
echo.
if "%LOCALCUT_TEST_EXIT%"=="0" (
  echo Finished. Read windows-results\RESULT.txt for the verified test results.
) else (
  echo Test stopped. Read windows-results\RESULT.txt or the error above.
)
pause
exit /b %LOCALCUT_TEST_EXIT%
