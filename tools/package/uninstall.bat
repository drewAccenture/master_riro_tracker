@echo off
rem Remove the RIRO Tracker program and its shortcuts. Data, logs and the app's Edge sign-in are kept.
rem RIRO_INSTALL_TEST=1 (tests only): the shortcuts are not touched.
setlocal
set "TARGET=%LOCALAPPDATA%\RIROTracker"

if not "%RIRO_INSTALL_TEST%"=="1" (
    echo Removing the shortcuts...
    powershell -NoProfile -Command ^
      "foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {" ^
      "  Remove-Item -LiteralPath (Join-Path $folder 'Master RIRO Tracker.lnk') -ErrorAction SilentlyContinue }"
)

echo Removing the program files. This can take a minute...
if exist "%TARGET%\app" rmdir /s /q "%TARGET%\app"
if exist "%TARGET%\app.prev" rmdir /s /q "%TARGET%\app.prev"

if exist "%TARGET%\app" goto :not_removed
if exist "%TARGET%\app.prev" goto :not_removed

echo Master RIRO Tracker is removed.
echo Your data, logs and the app's Edge sign-in are kept in "%TARGET%".
echo To remove them too, delete that folder.
pause
exit /b 0

:not_removed
echo Some program files could not be removed. A file is in use.
echo Close RIRO Tracker or restart the PC, then run uninstall.bat again.
pause
exit /b 1
