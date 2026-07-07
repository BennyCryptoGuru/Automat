$ErrorActionPreference = "Stop"
$logPath = Join-Path $PSScriptRoot "cleanup_profiles.admin.log"
trap {
    ($_ | Out-String) | Set-Content -LiteralPath $logPath -Encoding UTF8
    exit 1
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class PendingDelete {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool MoveFileEx(string existingFile, string newFile, int flags);
}
"@

$root = Join-Path $PSScriptRoot "data"
$root = (Resolve-Path -LiteralPath $root).Path
$principal = "$env:USERDOMAIN\$env:USERNAME"

Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match "^(brave|BraveCrashHandler|BraveCrashHandler64|chrome|chromedriver|python|pythonw)$" } |
    Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

$targets = Get-ChildItem -LiteralPath $root -Directory -Force | Where-Object {
    ($_.Name -eq "browser-profile" -or $_.Name -like "browser-profile-recovered-*") -and
    $_.Name -ne "browser-profile-main"
}
$scheduled = 0

function Remove-OrSchedule([string]$Path) {
    try {
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
    } catch {
        if (-not [PendingDelete]::MoveFileEx($Path, $null, 4)) {
            throw "Nelze odstranit ani naplanovat: $Path (Win32 $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))"
        }
        $script:scheduled++
    }
}

function Reset-DirectoryAcl([string]$Path) {
    $security = New-Object System.Security.AccessControl.DirectorySecurity
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $security.SetOwner($currentUser)
    $security.SetAccessRuleProtection($true, $false)
    $inheritance = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
    $propagation = [System.Security.AccessControl.PropagationFlags]::None
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    foreach ($sidText in @($currentUser.Value, "S-1-5-18", "S-1-5-32-544")) {
        $sid = New-Object System.Security.Principal.SecurityIdentifier($sidText)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $sid,
            [System.Security.AccessControl.FileSystemRights]::FullControl,
            $inheritance,
            $propagation,
            $allow
        )
        [void]$security.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $security
}

foreach ($target in $targets) {
    if (-not $target.FullName.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Neplatna cesta: $($target.FullName)"
    }
    & icacls.exe $target.FullName /setowner $principal /T /C /Q | Out-Null
    & icacls.exe $target.FullName /grant "${principal}:(OI)(CI)F" /T /C /Q | Out-Null
    $directories = Get-ChildItem -LiteralPath $target.FullName -Recurse -Directory -Force
    Reset-DirectoryAcl $target.FullName
    $directories | ForEach-Object { Reset-DirectoryAcl $_.FullName }
    $directories | Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object { Remove-OrSchedule $_.FullName }
    Remove-OrSchedule $target.FullName
}

$remaining = Get-ChildItem -LiteralPath $root -Directory -Force | Where-Object {
    $_.Name -eq "browser-profile" -or $_.Name -like "browser-profile-recovered-*"
}

if ($remaining -and $scheduled -eq 0) {
    throw "Nektere stare profily se nepodarilo odstranit: $($remaining.Name -join ', ')"
}

$message = if ($scheduled) {
    "Data profilu byla odstranena. Zbyvajici prazdne adresare budou odstraneny po restartu Windows: $scheduled"
} else {
    "Stare profily byly odstraneny: $($targets.Count)"
}
Write-Host $message -ForegroundColor Green
$message | Set-Content -LiteralPath $logPath -Encoding UTF8

if ([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value -eq "S-1-5-18") {
    Unregister-ScheduledTask -TaskName "AutomatCleanupOldProfiles" -Confirm:$false -ErrorAction SilentlyContinue
}
