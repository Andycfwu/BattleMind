param([Parameter(Mandatory=$true)][string]$Run)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$state = Get-Content -LiteralPath (Join-Path $Run 'service.json') -Raw | ConvertFrom-Json
if ($state.schema_version -ne 'v7-service-1' -or $state.url -notmatch '^http://127\.0\.0\.1:[0-9]+$') {
    throw 'Unsupported local service record'
}
Invoke-RestMethod -Method Post -Uri ($state.url + '/api/stop') -ContentType 'application/json' -Headers @{'X-BattleMind-Token'=$state.token} -Body '{}'
