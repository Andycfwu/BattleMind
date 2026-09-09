# Dot-source for this terminal only. Prefer user-installed tools, then Codex bundles.
$runtimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
foreach ($entry in @('node\bin', 'native\git\cmd', 'bin\fallback')) {
    $candidate = Join-Path $runtimeRoot $entry
    if (Test-Path -LiteralPath $candidate) { $env:PATH = "$candidate;$env:PATH" }
}
