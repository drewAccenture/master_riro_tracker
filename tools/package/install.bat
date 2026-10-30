@echo off
rem Install or upgrade RIRO Tracker for this Windows user. No admin rights (ADR-006).
rem Only app\ and app.prev\ are replaced. data\, edge_profile\ and logs\ are never touched.
rem RIRO_INSTALL_TEST=1 (tests only): no shortcuts and no app start.
setlocal
set "TARGET=%LOCALAPPDATA%\RIROTracker"
set "SOURCE=%~dp0app"

if not exist "%SOURCE%\pythonw.exe" (
    echo The package is incomplete: app\pythonw.exe is missing. Unzip the whole package first.
    pause
    exit /b 1
)

echo Checking that RIRO Tracker is not running...
rem Any program started from the installed app folder counts, whatever its window title (old versions too).
powershell -NoProfile -Command ^
  "$app = (Join-Path $env:TARGET 'app') + '\';" ^
  "$running = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($app, [StringComparison]::OrdinalIgnoreCase) };" ^
  "if ($running) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo RIRO Tracker, or an older version of it, is still running.
    echo Close it, or restart the PC, then run install.bat again. Nothing was changed.
    pause
    exit /b 1
)

if not exist "%TARGET%" mkdir "%TARGET%"
if exist "%TARGET%\app.prev" (
    echo Removing the version before last...
    rmdir /s /q "%TARGET%\app.prev"
)
if exist "%TARGET%\app.prev" (
    echo The folder "%TARGET%\app.prev" could not be removed. A file in it is in use.
    echo Restart the PC, then run install.bat again. The installed version was not changed.
    pause
    exit /b 1
)
if exist "%TARGET%\app" (
    echo Keeping the current version as app.prev...
    move "%TARGET%\app" "%TARGET%\app.prev" >nul
)
if exist "%TARGET%\app" (
    echo The current version could not be moved aside. A file in it is in use.
    echo Close RIRO Tracker or restart the PC, then run install.bat again. The installed version was not changed.
    pause
    exit /b 1
)

echo Copying the new version. This can take a few minutes...
robocopy "%SOURCE%" "%TARGET%\app" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo The copy failed. The previous version is kept in "%TARGET%\app.prev".
    if not exist "%TARGET%\app\pythonw.exe" if exist "%TARGET%\app.prev" (
        rmdir /s /q "%TARGET%\app" 2>nul
        move "%TARGET%\app.prev" "%TARGET%\app" >nul
    )
    pause
    exit /b 1
)

if "%RIRO_INSTALL_TEST%"=="1" (
    echo Test install finished: no shortcuts, app not started.
    exit /b 0
)

echo Creating the shortcuts...
powershell -NoProfile -Command ^
  "$shell = New-Object -ComObject WScript.Shell;" ^
  "foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {" ^
  "  $link = $shell.CreateShortcut((Join-Path $folder 'Master RIRO Tracker.lnk'));" ^
  "  $link.TargetPath = Join-Path $env:LOCALAPPDATA 'RIROTracker\app\pythonw.exe';" ^
  "  $link.Arguments = '-m riro';" ^
  "  $link.WorkingDirectory = Join-Path $env:LOCALAPPDATA 'RIROTracker\app';" ^
  "  $link.Save() }"

echo Master RIRO Tracker is installed. Starting it now.
start "" /d "%TARGET%\app" "%TARGET%\app\pythonw.exe" -m riro
exit /b 0
