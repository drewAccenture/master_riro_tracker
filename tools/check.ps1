# Local checks: format, lint, unit tests. Replaces the Claude Code hooks that org policy blocks (ADR-008).
# Usage: powershell -File tools\check.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host "FAIL: $py not found. Create the project venv first."
    exit 1
}
Set-Location $root

function Invoke-Step {
    param([string]$Name, [string[]]$StepArgs, [int[]]$OkCodes, [int]$TimeoutSec)
    Write-Host "== $Name"
    $outFile = $null
    $errFile = $null
    $p = $null
    try {
        # Created inside try so the finally block also covers an interrupt between the two calls
        $outFile = [System.IO.Path]::GetTempFileName()
        $errFile = [System.IO.Path]::GetTempFileName()
        $p = Start-Process -FilePath $py -ArgumentList $StepArgs -NoNewWindow -PassThru `
            -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        $null = $p.Handle  # keeps ExitCode readable after the process ends
        if (-not $p.WaitForExit($TimeoutSec * 1000)) {
            $p.Kill()
            $p.WaitForExit()
            Get-Content -Encoding UTF8 -Path $outFile, $errFile | ForEach-Object { Write-Host $_ }
            Write-Host "FAIL: $Name (timed out after $TimeoutSec s)"
            exit 1
        }
        $code = $p.ExitCode
        Get-Content -Encoding UTF8 -Path $outFile, $errFile | ForEach-Object { Write-Host $_ }
    } finally {
        # On Ctrl+C the child may still be running and holding the files open
        if ($p -and -not $p.HasExited) {
            try { $p.Kill(); $p.WaitForExit() } catch { }
        }
        foreach ($f in @($outFile, $errFile)) {
            if ($f) { Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue }
        }
    }
    if ($OkCodes -notcontains $code) {
        Write-Host "FAIL: $Name (exit code $code)"
        exit $code
    }
    Write-Host "OK: $Name (exit code $code)"
}

Invoke-Step -Name 'ruff format' -StepArgs @('-m', 'ruff', 'format', 'src', 'tests') -OkCodes @(0) -TimeoutSec 60
Invoke-Step -Name 'ruff check' -StepArgs @('-m', 'ruff', 'check', 'src', 'tests') -OkCodes @(0) -TimeoutSec 60
Invoke-Step -Name 'pytest unit' -StepArgs @('-m', 'pytest', 'tests\unit', '-q') -OkCodes @(0, 5) -TimeoutSec 120  # 5 = no tests collected
Write-Host 'ALL CHECKS PASSED'
exit 0
