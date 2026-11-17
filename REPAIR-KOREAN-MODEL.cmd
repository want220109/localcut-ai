@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
if not exist "%~dp0.venv-win\Scripts\python.exe" (
  echo Copy this file, the models folder and the scripts folder into the ORIGINAL LocalCut-AI folder.
  echo The .venv-win folder created by your previous test must be present.
  pause
  exit /b 1
)
echo LocalCut AI - Korean model download repair
echo Close LocalCut AI normally before continuing. No installer rebuild is needed.
echo Reuses the existing cache and downloads missing model files only.
echo No paid API and no video/audio/transcript upload.
echo.
"%~dp0.venv-win\Scripts\python.exe" "%~dp0scripts\repair-speech-model.py" --model small
set "LOCALCUT_REPAIR_EXIT=%ERRORLEVEL%"
echo.
echo Read model-repair-results\RESULT.txt for the actual result.
pause
exit /b %LOCALCUT_REPAIR_EXIT%
