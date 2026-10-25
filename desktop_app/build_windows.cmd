@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
if errorlevel 1 (
  echo Build failed. Please read the error above.
  pause
  exit /b 1
)
echo Build succeeded. Open the dist folder.
pause
