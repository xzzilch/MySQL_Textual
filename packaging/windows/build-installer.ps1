$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$compiler = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
$installerScript = Join-Path $PSScriptRoot "sqltui.iss"
$outputDirectory = Join-Path $root "dist\installer"

if (-not (Test-Path $compiler)) {
    throw "Inno Setup 6 compiler not found at '$compiler'. Install Inno Setup 6 first."
}
if (-not (Test-Path (Join-Path $root "dist\SQLTUI\SQLTUI.exe"))) {
    throw "Application bundle not found. Run packaging\build.py first."
}

New-Item -ItemType Directory -Force $outputDirectory | Out-Null
& $compiler $installerScript
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Built $outputDirectory\SQLTUI-Setup-x64.exe"
