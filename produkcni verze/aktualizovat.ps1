param(
    [string]$TargetPath = ""
)

$ErrorActionPreference = "Stop"
$SourcePath = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ([string]::IsNullOrWhiteSpace($TargetPath)) {
    $TargetPath = $SourcePath
}
$TargetPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TargetPath)

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Remove-DirectoryInside([string]$Root, [string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $rootPath = (Resolve-Path -LiteralPath $Root).Path
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Odmitam smazat cestu mimo cilovou slozku: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Get-AutomatProcessIds {
    $ids = @()
    try {
        $ids += Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess
    } catch {
    }
    $escapedTarget = [regex]::Escape($TargetPath)
    $ids += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match $escapedTarget -or
                $_.CommandLine -match "AutomatBrowserStudio" -or
                ($_.CommandLine -match "run\.py" -and $_.Name -match "python")
            )
        } |
        Select-Object -ExpandProperty ProcessId
    return $ids | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique
}

function Stop-AutomatIfRunning {
    $ids = @(Get-AutomatProcessIds)
    if (-not $ids.Count) {
        Write-Host "Automat prave nebezi."
        return
    }
    foreach ($id in $ids) {
        try {
            Write-Host "Ukoncuji bezici Automat PID $id"
            Stop-Process -Id $id -Force -ErrorAction Stop
        } catch {
            Write-Warning "Proces PID $id se nepodarilo ukoncit pres Stop-Process: $($_.Exception.Message)"
            & taskkill.exe /PID $id /F /T | Out-Null
        }
    }
    $deadline = (Get-Date).AddSeconds(12)
    do {
        Start-Sleep -Milliseconds 300
        $stillListening = @(Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue)
    } while ($stillListening.Count -and (Get-Date) -lt $deadline)
    if ($stillListening.Count) {
        throw "Port 5000 je stale obsazeny. Zavrete Automat rucne a spustte aktualizaci znovu."
    }
}

function Start-AutomatHidden {
    $launcher = Join-Path $TargetPath "start_hidden.vbs"
    if (-not (Test-Path -LiteralPath $launcher)) {
        Write-Warning "Skryty launcher nebyl nalezen: $launcher"
        return
    }
    Write-Step "Spoustim Automat skryte"
    Start-Process -FilePath "wscript.exe" -ArgumentList @("`"$launcher`"") -WorkingDirectory $TargetPath -WindowStyle Hidden
}

Write-Host "Automat - aktualizace" -ForegroundColor Magenta
Write-Host "Zdroj: $SourcePath"
Write-Host "Cil:   $TargetPath"

New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null

Write-Step "Zastavuji bezici Automat"
Stop-AutomatIfRunning

if (-not ([string]::Equals($SourcePath, $TargetPath, [System.StringComparison]::OrdinalIgnoreCase))) {
    Write-Step "Kopiruji soubory programu"
    $itemsToCopy = @(
        "automat",
        "install.bat",
        "install.ps1",
        "aktualizovat.bat",
        "aktualizovat.ps1",
        "requirements.txt",
        "run.py",
        "watchdog.py",
        "watchdog_hidden.ps1",
        "watchdog_hidden.vbs",
        "pridat_watchdog_po_prihlaseni.bat",
        "pridat_watchdog_po_prihlaseni.ps1",
        "odebrat_watchdog_po_prihlaseni.bat",
        "start.bat",
        "start_hidden.ps1",
        "start_hidden.vbs",
        "README.md",
        "NAVOD_WATCHDOG_AUTORUN.txt",
        ".gitignore",
        "smazat_profily_nouzovy_rezim.bat",
        "smazat_vsechny_profily_nouzovy_rezim.bat"
    )
    foreach ($item in $itemsToCopy) {
        $source = Join-Path $SourcePath $item
        if (-not (Test-Path -LiteralPath $source)) { continue }
        $target = Join-Path $TargetPath $item
        if ((Get-Item -LiteralPath $source).PSIsContainer) {
            & robocopy $source $target /MIR /XD "__pycache__" ".pytest_cache" /XF "*.pyc" /NFL /NDL /NJH /NJS /NP | Out-Null
            if ($LASTEXITCODE -gt 7) { throw "Kopirovani slozky $item selhalo (robocopy $LASTEXITCODE)." }
        } else {
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }
}

Write-Step "Cistim stare docasne soubory a nepouzivane profily"
Remove-DirectoryInside $TargetPath (Join-Path $TargetPath "__pycache__")
Remove-DirectoryInside $TargetPath (Join-Path $TargetPath ".pytest_cache")
Get-ChildItem -LiteralPath (Join-Path $TargetPath "data") -Directory -Filter "browser-profile*" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-DirectoryInside $TargetPath $_.FullName }

Write-Step "Overuji zavislosti"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $TargetPath "install.ps1")
if ($LASTEXITCODE -ne 0) { throw "Instalace nebo aktualizace zavislosti selhala." }

Write-Host "`nAktualizace je hotova." -ForegroundColor Green
Write-Host "Databaze, screenshoty a prihlasovaci profily v data zustaly zachovane."
Start-AutomatHidden
