# Wrapper invoked by Task Scheduler: runs one profile's bot cycle and
# appends output to a per-profile log file, so scheduled runs are visible
# even though Task Scheduler itself doesn't capture console output.
param(
    [Parameter(Mandatory = $true)][string]$Profile
)

# This machine's Claude Code app runs in an app-container sandbox that
# transparently redirects %LOCALAPPDATA% to a hidden real path when accessed
# from inside the container. Task Scheduler runs OUTSIDE the container, so it
# needs the real underlying path directly, not the virtualized one.
$py = "C:\Users\ariff\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\PythonEmbed312\python.exe"
$root = "C:\Users\ariff\OneDrive\Documents\Downloads\luno_bot"
$logFile = Join-Path $root "logs\task_$Profile.log"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n=== $timestamp ===" -Encoding utf8

try {
    # Read directly from the registry rather than relying on process env
    # inheritance - a value set via `setx` isn't visible to already-running
    # processes or new ones spawned from a stale cached logon environment
    # (observed on this machine) until this is done explicitly.
    foreach ($name in @("LUNO_API_KEY_ID", "LUNO_API_SECRET", "EMAIL_SMTP_HOST",
                         "EMAIL_SMTP_PORT", "EMAIL_USERNAME", "EMAIL_APP_PASSWORD", "EMAIL_TO")) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
        if ($value) { Set-Item -Path "env:$name" -Value $value }
    }

    if (-not (Test-Path $py)) {
        throw "Python not found at $py"
    }

    Set-Location $root
    $output = & $py main.py --profile $Profile 2>&1 | Out-String
    Add-Content -Path $logFile -Value $output -Encoding utf8
}
catch {
    Add-Content -Path $logFile -Value "WRAPPER ERROR: $($_.Exception.Message)`n$($_.ScriptStackTrace)" -Encoding utf8
}
