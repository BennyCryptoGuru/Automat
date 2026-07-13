$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-PythonExecutable {
    $commands = @(
        @{ Command = "py"; Arguments = @("-3") },
        @{ Command = "python"; Arguments = @() },
        @{ Command = "python3"; Arguments = @() }
    )

    foreach ($candidate in $commands) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }
        try {
            $path = & $candidate.Command @($candidate.Arguments) -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path -LiteralPath $path.Trim())) {
                return $path.Trim()
            }
        } catch {
            continue
        }
    }
    return $null
}

function Install-WithWinget([string]$Id, [string]$Name) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Windows Package Manager (winget) is missing. Install App Installer from Microsoft Store and run install.bat again."
    }
    Write-Step "Installing $Name"
    & winget.exe install --id $Id --exact --source winget --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        throw "Installing package $Name with winget failed (code $LASTEXITCODE)."
    }
}

function Remove-VenvSafely {
    $root = (Resolve-Path ".").Path
    $venv = Join-Path $root ".venv"
    if (-not (Test-Path -LiteralPath $venv)) {
        return
    }
    $resolved = (Resolve-Path -LiteralPath $venv).Path
    if (-not $resolved.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete .venv outside the Automat folder: $resolved"
    }
    Write-Step "Removing transferred or damaged .venv environment"
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Test-VenvUsable {
    if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
        return $false
    }
    try {
        $output = & ".venv\Scripts\python.exe" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $output) {
            return $false
        }
        return $true
    } catch {
        return $false
    }
}

Write-Host "Automat - dependency installation" -ForegroundColor Magenta
Write-Host "Folder: $PSScriptRoot"

$python = Get-PythonExecutable
if (-not $python) {
    Install-WithWinget "Python.Python.3.13" "Python 3.13"
    $python = Get-PythonExecutable
    if (-not $python) {
        $possible = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
        if ($possible) { $python = $possible.FullName }
    }
}
if (-not $python) {
    throw "Python could not be found even after installation. Restart Windows and run install.bat again."
}

$versionText = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$versionParts = $versionText.Split(".")
if ([int]$versionParts[0] -lt 3 -or ([int]$versionParts[0] -eq 3 -and [int]$versionParts[1] -lt 10)) {
    throw "Automat requires Python 3.10 or newer. Found: $versionText"
}
Write-Host "Python: $python ($versionText)" -ForegroundColor Green

if ((Test-Path -LiteralPath ".venv") -and -not (Test-VenvUsable)) {
    Remove-VenvSafely
}

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Write-Step "Creating isolated Python environment .venv"
    & $python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Creating .venv failed." }
}

$venvPython = (Resolve-Path ".venv\Scripts\python.exe").Path
& $venvPython -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Step "Adding pip to .venv"
    & $venvPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw "Installing pip through ensurepip failed." }
}

Write-Step "Updating pip"
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Updating pip failed." }

Write-Step "Installing Python dependencies"
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Installing requirements.txt failed." }

$browserPaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$browser = $browserPaths | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $browser) {
    Install-WithWinget "Google.Chrome" "Google Chrome"
    $browser = $browserPaths | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $browser) {
    throw "Google Chrome was not found. Install Chrome and run install.bat again."
}
Write-Host "Chrome: $browser" -ForegroundColor Green

New-Item -ItemType Directory -Force -Path "data", "data\screenshots" | Out-Null

Write-Step "Verifying installation"
& $venvPython -c "import flask, selenium, PIL, waitress; print('Python dependencies are OK.')"
if ($LASTEXITCODE -ne 0) { throw "Python dependency check failed." }

Write-Host "`nAutomat installation completed successfully." -ForegroundColor Green
Write-Host "Selenium Manager downloads a compatible ChromeDriver automatically on the first browser start."
