@echo off
rem Remove the RIRO Tracker program and its shortcuts. Data, logs and the app's Edge sign-in are kept.
setlocal
set "TARGET=%LOCALAPPDATA%\RIROTracker"

powershell -NoProfile -Command ^
  "foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {" ^
  "  Remove-Item -LiteralPath (Join-Path $folder 'Master RIRO Tracker.lnk') -ErrorAction SilentlyContinue }"

if exist "%TARGET%\app" rmdir /s /q "%TARGET%\app"
if exist "%TARGET%\app.prev" rmdir /s /q "%TARGET%\app.prev"

echo Master RIRO Tracker is removed.
echo Your data, logs and the app's Edge sign-in are kept in "%TARGET%".
echo To remove them too, delete that folder.
pause
exit /b 0
