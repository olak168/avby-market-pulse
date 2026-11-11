<#
.SYNOPSIS
    Refresh the AV.BY Market Pulse dataset from cars.av.by.

.DESCRIPTION
    Runs the scraper with the project virtualenv (falls back to the `py` launcher),
    appends a timestamped log to logs/update-YYYY-MM-DD.log, and keeps the last 30 logs.
    The scraper writes atomically, so a failed run never corrupts data/cars.json.

    Normally invoked by Windows Task Scheduler every day at 13:00.
    Register it with: scripts\register-schedule.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\update-dashboard.ps1

.EXAMPLE
    # quick smoke test into a throwaway file
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\update-dashboard.ps1 -Pages 2 -Out "$env:TEMP\avby-test.json"

.EXAMPLE
    # also rebuild docs/ so the GitHub Pages copy matches the new snapshot
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\update-dashboard.ps1 -Build
#>
[CmdletBinding()]
param(
    [int]$Pages = 50,
    [double]$Delay = 0.35,
    [string]$Out = '',
    [switch]$Build
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$LogDir = Join-Path $ProjectRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ('update-{0}.log' -f (Get-Date -Format 'yyyy-MM-dd'))

function Write-Log {
    param([string]$Message)
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

# Prevent overlapping runs (manual + scheduled) without leaving stale lock files.
$mutex = New-Object System.Threading.Mutex($false, 'Local\AVBY-MarketPulse-Update')
if (-not $mutex.WaitOne(0)) {
    Write-Log 'Another update is already running; skipping this run.'
    exit 0
}

try {
    $python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = 'py' }

    $dataFile = if ($Out) { $Out } else { Join-Path $ProjectRoot 'data\cars.json' }

    Write-Log ('Update started: pages={0}, delay={1}s, python={2}' -f $Pages, $Delay, $python)

    $scraperArgs = @('-m', 'scraper.cli', '--pages', $Pages, '--delay', $Delay)
    if ($Out) { $scraperArgs += @('--out', $Out) }

    $output = & $python @scraperArgs 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object { Write-Log ([string]$_) }

    if ($code -ne 0) { throw ('scraper exited with code {0}' -f $code) }

    $json = Get-Content -LiteralPath $dataFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $sizeKb = [math]::Round((Get-Item -LiteralPath $dataFile).Length / 1KB)
    Write-Log ('Update finished: {0} cars, {1} KB, scraped_at={2}' -f $json.count, $sizeKb, $json.scraped_at)

    if ($Build -and -not $Out) {
        Write-Log 'Rebuilding docs/ for GitHub Pages ...'
        $buildOutput = & $python (Join-Path $ProjectRoot 'scripts\build-static.py') 2>&1
        $buildCode = $LASTEXITCODE
        $buildOutput | ForEach-Object { Write-Log ([string]$_) }
        if ($buildCode -ne 0) { throw ('build-static exited with code {0}' -f $buildCode) }
    }

    # Keep the log directory small.
    Get-ChildItem -LiteralPath $LogDir -Filter 'update-*.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 30 |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
catch {
    Write-Log ('ERROR: ' + $_.Exception.Message)
    exit 1
}
finally {
    try { $mutex.ReleaseMutex() } catch { }
    $mutex.Dispose()
}
