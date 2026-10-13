@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0StartTrainer.ps1" %*
set "TrainerExitCode=%ERRORLEVEL%"
if not "%TrainerExitCode%"=="0" (
  echo.
  echo Startup or session failed. Read the message above and the Logs folder.
  pause
)
exit /b %TrainerExitCode%
