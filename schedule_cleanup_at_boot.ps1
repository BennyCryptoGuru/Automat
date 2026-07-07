$ErrorActionPreference = "Stop"

$cleanupScript = Join-Path $PSScriptRoot "cleanup_old_profiles.ps1"
if (-not (Test-Path -LiteralPath $cleanupScript)) {
    throw "Cleanup script nebyl nalezen: $cleanupScript"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$cleanupScript`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "AutomatCleanupOldProfiles" `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Jednorazove odstraneni starych profilu Automatu pred spustenim Codexu" `
    -Force | Out-Null

"Naplanovano: AutomatCleanupOldProfiles" |
    Set-Content -LiteralPath (Join-Path $PSScriptRoot "cleanup_schedule.log") -Encoding UTF8
