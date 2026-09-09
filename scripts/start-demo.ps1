param(
    [string]$Bundle = "runs/v7-release-bundle",
    [string]$Output = ("runs/demo-" + (Get-Date -Format "yyyyMMdd-HHmmss-ffff")),
    [int]$Port = 8765,
    [int]$Games = 2
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. .\scripts\env.ps1
Write-Host "Stop with Ctrl+C, or scripts/stop-demo.ps1 -Run $Output in another terminal."
& .\.venv\Scripts\python.exe -m battlemind demo-serve --bundle $Bundle --output $Output --port $Port --games $Games
exit $LASTEXITCODE
