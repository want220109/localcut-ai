@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0.venv-win\Scripts\python.exe" (
  echo Copy the ENTIRE update into your ORIGINAL LocalCut-AI folder first.
  echo Keep .venv-win, node_modules, vendor and your user data.
  pause
  exit /b 1
)
echo LocalCut AI 0.2.0 - YouTube and Instagram subtitle update
echo Close LocalCut AI normally before continuing.
echo Reuses existing build tools. No paid API, model download or public publication.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-local-test.ps1" -UpdateExisting
set "LOCALCUT_UPDATE_EXIT=%ERRORLEVEL%"
echo.
echo Check windows-results\RESULT.txt for the actual Windows update/test result.
pause
exit /b %LOCALCUT_UPDATE_EXIT%
