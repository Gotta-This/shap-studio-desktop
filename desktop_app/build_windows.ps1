param([switch]$SkipTests, [switch]$RequireInstaller)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_OPENGL = 'software'
$env:MPLBACKEND = 'Agg'

function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)." }
}

$BasePython = (Get-Command python -ErrorAction Stop).Source
$Version = & $BasePython -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")'
Assert-Exit 'Check Python'
if ($Version.Trim() -ne '3.12') { throw 'Build requires Python 3.12 x64. GitHub Actions sets it up automatically.' }
$Bits = & $BasePython -c 'import struct;print(struct.calcsize("P")*8)'
if ($Bits.Trim() -ne '64') { throw 'Build requires 64-bit Python.' }
& $BasePython -m venv .venv-win
Assert-Exit 'Create build environment'
$Python = Join-Path $PSScriptRoot '.venv-win\Scripts\python.exe'
& $Python -m pip install --disable-pip-version-check -r requirements-windows.txt
Assert-Exit 'Install dependencies'
& $Python prepare_assets.py
Assert-Exit 'Prepare verified offline font assets'
if (-not $SkipTests) {
    & $Python -m unittest discover -s tests -v
    Assert-Exit 'Unit and export tests'
}
& $Python -m PyInstaller --noconfirm --clean SHAPStudio.spec
Assert-Exit 'Package Windows app'
$Exe = Join-Path $PSScriptRoot 'dist\SHAPStudio\SHAPStudio.exe'
if (-not (Test-Path $Exe)) { throw 'Packaged EXE is missing.' }

function Run-Packaged([string]$Flag, [string]$Destination, [string]$Marker) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $Process = Start-Process -FilePath $Exe -ArgumentList @($Flag, ('"' + $Destination + '"')) -PassThru
    if (-not $Process.WaitForExit(300000)) {
        Stop-Process -Id $Process.Id -Force
        throw "Packaged app $Flag timed out."
    }
    $Process.Refresh()
    if ($Process.ExitCode -ne 0) { throw "Packaged app $Flag failed (exit $($Process.ExitCode))." }
    $MarkerPath = Join-Path $Destination $Marker
    if (-not (Test-Path $MarkerPath)) { throw "Packaged app did not write $MarkerPath." }
    $Report = Get-Content -LiteralPath $MarkerPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $Report.passed) { throw "Packaged verification failed: $MarkerPath" }
}

Run-Packaged '--self-test' (Join-Path $PSScriptRoot 'verification\windows_packaged') 'self_test_passed.json'
Run-Packaged '--ui-verify' (Join-Path $PSScriptRoot 'verification\windows_ui') 'ui_verification.json'
$Modules = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'verification\windows_ui\four_module_verification.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Modules.passed) { throw 'Independent module UI and export verification failed.' }
& $Python verify_ui_exports.py (Join-Path $PSScriptRoot 'verification\windows_ui')
Assert-Exit 'Independently verify SVG colors, embedded glyphs and stroke widths'
Compress-Archive -Path 'dist\SHAPStudio' -DestinationPath 'dist\SHAPStudio-Windows-x64.zip' -Force
Get-FileHash 'dist\SHAPStudio-Windows-x64.zip' -Algorithm SHA256 |
    Format-List | Out-File 'dist\SHAPStudio-Windows-x64.sha256.txt' -Encoding utf8
$Compilers = @(Get-ChildItem -Path (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup *\ISCC.exe') -ErrorAction SilentlyContinue)
if ($Compilers.Count -gt 0) {
    & $Compilers[-1].FullName windows_installer.iss
    Assert-Exit 'Create setup installer'
} elseif ($RequireInstaller) {
    throw 'Inno Setup compiler is required but was not found.'
}
Write-Host 'Windows portable app and packaged UI verification completed.'
