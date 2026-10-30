# Build dist\RIROTracker_<version>.zip: embeddable Python + pinned packages + src\riro + install scripts (ADR-006).
# Usage: powershell -File tools\build_package.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
Set-Location $root

$PythonVersion = '3.13.17'
$EmbedName = "python-$PythonVersion-embed-amd64.zip"
$EmbedUrl = "https://www.python.org/ftp/python/$PythonVersion/$EmbedName"
# From the python.org release page, checked 2026-10-27 against a download.
$EmbedSha256 = '9E35319BFFEDAB8B36AD44D8F377CB4F1733BCEC257A0B6D04D94F01486DDB38'

function Assert-Ok([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $Step (exit code $LASTEXITCODE)"
        exit 1
    }
}

$main = Get-Content -Encoding UTF8 (Join-Path $root 'src\riro\__main__.py') -Raw
if ($main -notmatch 'APP_VERSION = "([^"]+)"') { throw 'APP_VERSION not found in src\riro\__main__.py' }
$version = $Matches[1]

$build = Join-Path $root 'build'
$cache = Join-Path $build 'cache'
$wheels = Join-Path $build 'wheels'
$stage = Join-Path $build "RIROTracker_$version"
$app = Join-Path $stage 'app'
$dist = Join-Path $root 'dist'
$zip = Join-Path $dist "RIROTracker_$version.zip"

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force $cache, $wheels, $app, $dist | Out-Null

Write-Host "== embeddable Python $PythonVersion"
$embed = Join-Path $cache $EmbedName
if (-not (Test-Path $embed)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $EmbedUrl -OutFile $embed
}
$hash = (Get-FileHash -Algorithm SHA256 $embed).Hash
if ($hash -ne $EmbedSha256) {
    Remove-Item -LiteralPath $embed -Force
    throw "SHA-256 mismatch for $EmbedName (got $hash). Download deleted."
}
Expand-Archive -LiteralPath $embed -DestinationPath $app

# Search path: the stdlib zip, the app folder (holds riro\), site-packages. "import site" handles .pth files.
$pth = Get-ChildItem -LiteralPath $app -Filter 'python*._pth' | Select-Object -First 1
$zipName = (Get-ChildItem -LiteralPath $app -Filter 'python3*.zip' | Select-Object -First 1).Name
Set-Content -LiteralPath $pth.FullName -Encoding ASCII -Value @($zipName, '.', 'Lib\site-packages', 'import site')

Write-Host '== packages (requirements.txt, exact pins)'
# proxy-tools has no wheel on PyPI: build it here first (constraints.md).
& $py -m pip wheel --no-deps --wheel-dir $wheels 'proxy-tools==0.1.0'
Assert-Ok 'pip wheel proxy-tools'
& $py -m pip install --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.13 `
    --implementation cp --find-links $wheels --target (Join-Path $app 'Lib\site-packages') -r requirements.txt
Assert-Ok 'pip install'

Write-Host '== app code'
Copy-Item -LiteralPath (Join-Path $root 'src\riro') -Destination (Join-Path $app 'riro') -Recurse
Get-ChildItem -LiteralPath $app -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root 'tools\package\install.bat'), (Join-Path $root 'tools\package\uninstall.bat') -Destination $stage
# US-16: the report shows which build she runs. riro\build.txt = "<git short commit> <yyyy-mm-dd>", package only.
try { $commit = (& git rev-parse --short=10 HEAD) } catch { $commit = $null }
if (-not $commit) { Write-Host 'FAIL: git rev-parse (is git installed, and is this the repo folder?)'; exit 1 }
$commit = "$commit".Trim()
Set-Content -LiteralPath (Join-Path $app 'riro\build.txt') -Encoding ASCII -Value "$commit $(Get-Date -Format 'yyyy-MM-dd')"

Write-Host '== import check with the packaged Python'
& (Join-Path $app 'python.exe') -c 'import riro.__main__, webview, openpyxl, websocket, clr_loader'
Assert-Ok 'import check'
Write-Host 'imports OK'

Write-Host "== zip"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip
Write-Host "OK: $zip"
exit 0
