param([switch]$Elevated)

$ErrorActionPreference = "Continue"
$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$dataRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "data"))
$logPath = Join-Path $projectRoot "smazat_stare_profily.log"

if (-not $Elevated) {
    $arguments = @(
        "-NoProfile"
        "-ExecutionPolicy", "Bypass"
        "-File", ('"{0}"' -f $scriptPath)
        "-Elevated"
    )
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments
    exit
}

Start-Transcript -LiteralPath $logPath -Force | Out-Null
Write-Host "Ukoncuji procesy, ktere mohou drzet stare profily..."
Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match '^(Codex|chrome|brave|chromedriver|python|BraveCrashHandler|BraveCrashHandler64)$' } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

if (-not $dataRoot.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Bezpecnostni kontrola cesty selhala: $dataRoot"
}

$targets = Get-ChildItem -LiteralPath $dataRoot -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "browser-profile" -or $_.Name -like "browser-profile-recovered-*" }

foreach ($target in $targets) {
    $fullPath = [IO.Path]::GetFullPath($target.FullName)
    if (-not $fullPath.StartsWith($dataRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Warning "Preskakuji neocekavanou cestu: $fullPath"
        continue
    }

    Write-Host "Odstranuji $fullPath"
    & takeown.exe /F $fullPath /R /A 2>&1 | Out-Null
    & icacls.exe $fullPath /inheritance:e /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /T /C /Q 2>&1 | Out-Null
    Remove-Item -LiteralPath $fullPath -Recurse -Force -ErrorAction SilentlyContinue
}

$remaining = @(Get-ChildItem -LiteralPath $dataRoot -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "browser-profile" -or $_.Name -like "browser-profile-recovered-*" })

if ($remaining.Count -eq 0) {
    Write-Host "Hotovo. Vsechny stare profily byly odstraneny." -ForegroundColor Green
} else {
    Write-Host "Windows stale blokuje $($remaining.Count) prazdnych profilu." -ForegroundColor Red
    Write-Host "V takovem pripade je nutne odstraneni v nouzovem rezimu Windows."
}

Stop-Transcript | Out-Null
Write-Host "Log: $logPath"
Read-Host "Stisknete Enter pro zavreni"
