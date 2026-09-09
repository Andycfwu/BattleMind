$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. "$PSScriptRoot\env.ps1"
$versions = Get-Content configs/versions.json | ConvertFrom-Json
$serverDir = Join-Path (Get-Location) '.local\pokemon-showdown'
if (-not (Test-Path -LiteralPath $serverDir)) {
    git clone --no-checkout --depth 1 https://github.com/smogon/pokemon-showdown.git $serverDir
    if ($LASTEXITCODE -ne 0) { throw 'Showdown clone failed' }
    git -C $serverDir fetch --depth 1 origin $versions.showdown_commit
    if ($LASTEXITCODE -ne 0) { throw 'Pinned commit fetch failed' }
    git -C $serverDir checkout --detach $versions.showdown_commit
    if ($LASTEXITCODE -ne 0) { throw 'Pinned checkout failed' }
}
$actual = git -C $serverDir rev-parse HEAD
if ($actual -ne $versions.showdown_commit) { throw 'Existing checkout has another commit; preserve it and inspect manually.' }
git -C $serverDir diff --quiet
if ($LASTEXITCODE -ne 0) { throw 'Existing Showdown source has modifications; preserve and inspect manually.' }
$configTarget = Join-Path $serverDir 'config\config.js'
if (Test-Path -LiteralPath $configTarget) {
    $expected = (Get-FileHash configs/showdown.config.js).Hash
    if ((Get-FileHash $configTarget).Hash -ne $expected) {
        throw 'Existing server config differs. Inspect it, then explicitly copy configs/showdown.config.js before rerunning.'
    }
} else { Copy-Item configs/showdown.config.js $configTarget }
Copy-Item configs/showdown-pnpm-lock.yaml (Join-Path $serverDir 'pnpm-lock.yaml')
Push-Location $serverDir
try {
    if ((pnpm --version) -ne $versions.pnpm) { throw 'Use the pinned pnpm version from configs/versions.json.' }
    pnpm install --prod --no-optional --ignore-scripts --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Server dependency install failed' }
    # Install only esbuild's small platform executable, avoiding native database builds.
    node node_modules/esbuild/install.js
    if ($LASTEXITCODE -ne 0) { throw 'esbuild platform setup failed' }
    node build
    if ($LASTEXITCODE -ne 0) { throw 'Showdown build failed' }
} finally { Pop-Location }
