@echo off
rem Install or upgrade RIRO Tracker for this Windows user. No admin rights (ADR-006).
rem Only app\ and app.prev\ are replaced. data\, edge_profile\ and logs\ are never touched.
setlocal
set "TARGET=%LOCALAPPDATA%\RIROTracker"
set "SOURCE=%~dp0app"

if not exist "%SOURCE%\pythonw.exe" (
    echo The package is incomplete: app\pythonw.exe is missing. Unzip the whole package first.
    pause
    exit /b 1
)
tasklist /fi "imagename eq pythonw.exe" /v 2>nul | find /i "Master RIRO Tracker" >nul
if not errorlevel 1 (
    echo Please close Master RIRO Tracker first, then run install.bat again.
    pause
    exit /b 1
)

if not exist "%TARGET%" mkdir "%TARGET%"
if exist "%TARGET%\app.prev" rmdir /s /q "%TARGET%\app.prev"
if exist "%TARGET%\app" move "%TARGET%\app" "%TARGET%\app.prev" >nul
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
