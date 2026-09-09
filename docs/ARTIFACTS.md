# Reproducibility and the V7 local bundle

Code alone can run the original transparent baselines after pinned environment
setup. A source-only clone does **not** contain the ignored V4 model, historical
V5 checkpoint, datasets, experiment evidence or viewer assets. It cannot reproduce
historical checkpoints without retained inputs. V7 supplies a deliberately small
local demonstration closure, not a replacement for the full research archive.

## Release artifact

- `runs/v7-release-bundle.zip`: 1,962,355 bytes; SHA-256
  `808282811b87da04062534447e11eee6c2be1fb6e717b76b12eac286bf883a45`.
- Extracted payload: 157 files / 8,813,930 bytes, plus manifest.
- Manifest SHA-256: `fdb3bd642a4ea854a50fc35ffe3005a6a51e21497ea378dd3c36309e0a43220c`.
- Original V4 predictor: `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`.
- Selected V5 checkpoint: `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e`.

The original predictor/checkpoint are copied verbatim. The bundle includes seven
public replay projections (normal, choice change, freeze cap, four chronological
memory encounters), pinned offline renderer/assets/notices/corresponding source,
and the minimal V6 observer-owned four-encounter audit prefix. That prefix retains
its own pre-decision snapshots and journal so the unchanged public replay auditor
can check all 98 decisions and updates. It is offline audit input, **not served
by HTTP**. It contains no other-player journal, private end log, committed labels,
engine RNG or full training dataset. No service tokens or accounts are included.

## Import on a fresh checkout

Keep a retained copy of the zip alongside this source. Do not upload models or
change repository visibility. With the existing pinned Python environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m battlemind bundle-import --source PATH_TO_RETAINED_ZIP --output runs/MY_IMPORTED_BUNDLE
.\.venv\Scripts\python.exe -m battlemind bundle-verify --bundle runs/MY_IMPORTED_BUNDLE
.\scripts\start-demo.ps1 -Bundle runs/MY_IMPORTED_BUNDLE -Output runs/MY_FRESH_DEMO
```

Recorded-only playback needs Python, the source, and the bundle; no server or
network download is needed at viewing time. Fresh live battles also need the
pinned official engine setup and Node bundle described in README. The import
does not install runtimes, clone Showdown, fit anything, or regenerate artifacts.

`bundle-import` validates inside an isolated temporary directory before creating
the fresh destination. It bounds archive size/member count, rejects traversal,
duplicate members, symlinks, extra files, unsupported schemas and hash mismatch.
The exact allowed closure excludes arbitrary bundled content. It then runs the
existing V4/V5 compatibility loaders and chronological memory replay. Malformed
models or incompatible scoring code fail; hashes are never rewritten to fit.

## Build a local export from the full retained workspace

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe scripts/setup-viewer.py
.\.venv\Scripts\python.exe -m battlemind demo-prepare --output runs/FRESH_BUNDLE
.\.venv\Scripts\python.exe -m battlemind bundle-export --source runs/FRESH_BUNDLE --output runs/FRESH_BUNDLE.zip
```

Setup downloads only the pinned ~2.9 MB renderer closure if absent; subsequent
setup validates cached bytes and compiled output. `--freeze` is a developer-only
first asset-freeze operation and refuses an existing pin. Ordinary setup never
silently updates hosted sprites. The portable zip contains all runtime assets and
the corresponding sources/notices, so imported viewing needs no download.

`demo-prepare` intentionally requires the selected original historical recordings.
It fails when evidence is absent; it does not create stand-in replays. A minimal
bundle cannot rebuild the full evidence catalog because full historical experiments
are intentionally excluded. Run `evidence` in the retained archive for that task.

## What is reproducible

The same frozen snapshot and compatible parameters reproduce numeric prediction,
memory update, scores and choice. Isolated import reproduced all 98 observer
decisions in the four-game prefix, including 37 with different individual versus
no-memory probabilities. The original V4 and V5 content hashes remained unchanged.

Policy/schedule seeds are recorded but do not control Showdown RNG. A new battle
may differ. Repeating V4 fitting needs the retained audited development dataset;
even identical coefficients may have different provenance bytes. Repeating V5
uses stochastic outcomes and cannot promise the selected checkpoint hash. Existing
regeneration commands are documented in ADAPTATION/POLICY-LEARNING; running them
is a separately authorized experiment, not V7 setup.

Hash checking detects corruption and incompatibility, not malicious rewriting of
every artifact and manifest by a local editor. Historical full-source audits still
require their historical code. Generated bundles, runs, datasets and models stay
ignored. Preliminary development bundles have older renderer pins and are retained
only as development output; the release artifact above is the supported import.
