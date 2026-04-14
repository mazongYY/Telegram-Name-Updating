$ErrorActionPreference = "Stop"

$projectRoot = "F:\Project\Telegram-Name-Updating"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$scriptPath = Join-Path $projectRoot "tg_username_update.py"
$configPath = Join-Path $projectRoot "config.local.json"
$logDir = Join-Path $projectRoot "logs"
$launcherLogPath = Join-Path $logDir "telegram-name-updating-launcher.log"
$stdoutLogPath = Join-Path $logDir "telegram-name-updating.out.log"
$stderrLogPath = Join-Path $logDir "telegram-name-updating.err.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -like "*tg_username_update.py*" -and
    $_.CommandLine -like "*config.local.json*"
}

if ($existing) {
    Add-Content -Path $launcherLogPath -Value ("{0} | already running, skip" -f (Get-Date -Format "s"))
    exit 0
}

Add-Content -Path $launcherLogPath -Value ("{0} | starting process" -f (Get-Date -Format "s"))

Start-Process `
    -FilePath $pythonExe `
    -ArgumentList @($scriptPath, "--config", $configPath) `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutLogPath `
    -RedirectStandardError $stderrLogPath `
    -WindowStyle Hidden
