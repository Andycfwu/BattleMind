# Acceptance packaging repair and zero-battle readiness

2026-09-11. This is a packaging/preflight repair following
[the failed replacement](ACCEPTANCE-LIVE-REPLACEMENT-RESULTS.md),
[the deadline repair](ACCEPTANCE-PREFLIGHT-REPAIR.md), and the unchanged
[recording contract](ACCEPTANCE-RECORDING.md). Historical ledgers, specifications,
results, checkpoints, exclusions and the original engine are preserved.

## Root cause and repair

The old builder used `shutil.copytree` on pnpm's `node_modules`. On Windows it
dereferenced junctions. The original `sockjs` resolves inside
`.pnpm/sockjs@0.3.24/node_modules/sockjs`; the copied alias became an ordinary
`node_modules/sockjs` directory. Node then searched different ancestor directories
for transitive dependencies. `faye-websocket` bytes existed in the copied store,
but were inaccessible from the actual requiring package. Ten required dependency
edges failed: seven under `mysql2` and three under `sockjs`. Loading `sockjs` also
failed. The original resolves all required edges. This was a layout defect, not a
request to add a new or latest package.

`acceptance_build.py` now uses pnpm **11.19.0**, Node **24.19.0** and the unchanged
lock. It retains production-only, no-optional, ignored lifecycle scripts and frozen
lock safeguards. `--package-import-method=copy` gives the derived install separate
file contents while pnpm constructs its own internal links. Only the existing
explicit esbuild platform setup runs, then `node build`. Subprocesses are bounded
at 120 seconds each within a 300-second build deadline. No original-tree files or
package links are reused as writable dependencies.

An initial fresh packaging attempt, `.local/pokemon-showdown-acceptance-v2-r4`,
stopped after install because Windows cp1252 could not encode pnpm's checkmark in
the build log. It is preserved. Logging was corrected to UTF-8 before building
`.local/pokemon-showdown-acceptance-v2-r5`. Neither build command starts a server.

Build schema `bm-acceptance-build-2` adds package-manager provenance, a physical
dependency-file inventory and an internal link-target inventory. Link targets
must exist inside that install. The strict v1 byte verifier remains available for
historical builds; a successful v1 integrity check does not imply readiness.
The old r3 build is preserved and still fails operational resolution as expected.
The new r5 build has **662 physical dependency files and 41 links**. Every source
and compiled file in its 2,142-file build inventory matches the failed r3 build.
Package versions and resolved required dependency edges match the original.
Instrumentation source, patch, evidence schema, policy features, sampling,
commitment/exclusion rules, game rules and RNG calls are unchanged.

| Identity | Value |
|---|---|
| Upstream commit | `2f5b273925862ac242b419086c1e7a8868b51da1` |
| New build ID | `b2b0a1b1bdc30749a38e3c6ae3beea27ea03387d75dda0afe4e7ba7051d1b19a` |
| Build manifest SHA-256 | `41ec777dc02811d55c8b8c3762d24e6e5ee41c488bc3077ad3d2b1fc69d1a813` |
| Patch SHA-256 | `84c4c66dfdf4a165b8e17f54c5b32a455a5715a8b7daaae02bb7a3d1c40214d3` |
| Lock SHA-256 | `af01112eb887fd8d1985425e61f9f7d80400512fa52073055320dc6a663ff251` |

Actual build commands, each using a fresh directory:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B -m battlemind.acceptance_build --output .local/pokemon-showdown-acceptance-v2-r4
# Failed only at log encoding; retained, not resumed.
.\.venv\Scripts\python.exe -B -m battlemind.acceptance_build --output .local/pokemon-showdown-acceptance-v2-r5
```

Each successful build uses these commands **in its own derived working directory**:

```powershell
pnpm install --prod --no-optional --ignore-scripts --frozen-lockfile --package-import-method=copy --registry=https://registry.npmjs.org
node node_modules/esbuild/install.js
node build
```

## Operational and reporting boundaries

`scripts/inspect-acceptance-runtime.cjs` uses `createRequire` from the absolute
`pokemon-showdown` entry, verifies its real cwd, walks required dependency edges
and loads `sockjs`. Optional packages omitted by the declared installation are
reported explicitly. It does not bind sockets or start a server.
`acceptance_readiness.py` additionally verifies the writable private recording
directory/session and launches a supervised zero-battle server worker. The real
entry must load and send the normal `challstr` WebSocket handshake. The inherited
reviewed config binds only `127.0.0.1`; occupied ports are rejected, never taken
over. Cleanup tracks owned processes, including failed startups.

Future live preflight invokes this before the first game phase. All prior runtime,
model, patch, source, team and dependency-byte checks remain; readiness is an
additional result. New helper source hashes are explicitly included in the freeze.
The consumed 48-game command/configuration is not repointed or made reusable.

The replacement's 187.048110s supplemental inspection/authoring occurred **after**
its harness closed, outside the unused reporting worker. Those historical times
are not rewritten. Future mandatory reporting now runs on failures as well as
successes in the reserved 60-second supervised worker: at most 50s for full audits
and 10s for counts/Markdown. The parent retains 20s cleanup/constant-size closure.
If a worker blocks, it is terminated and counts may be explicitly unavailable;
closure never performs another log/archive scan. Read-only reports cannot extend
closed clocks. Optional forensic work is not invoked by closure and requires its
own declared offline budget. The separate targeted integrity analysis in this
repair used **53.876313s of an explicit 60s**, not a live-run allocation.

## Frozen zero-battle probe specification

Offline verification before this freeze: **105 focused tests passed in 3.04s**;
the final offline suite **374 passed, 14 integration tests deselected in 9.43s**.
The first full-suite pass attempt recorded one failure (372 passed): a new synthetic
build fixture omitted the official config directory. The fixture was corrected;
production build behavior did not change. All failed and passing outputs are
retained. The fixtures exercise copied identical bytes with broken resolution,
actual cwd/entry, link tampering, UTF-8 build logging, installed package-manager
arguments, failed readiness before requests, occupied ports, bounded startup
cleanup, report deadlines, zero-request accounting and sealed ledgers. Existing
acceptance-schema and policy-isolation tests remain included. No test games ran.

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_acceptance_readiness.py tests/test_acceptance_build.py tests/test_acceptance_preflight.py tests/test_acceptance_live.py tests/test_acceptance.py
.\.venv\Scripts\python.exe -B -m pytest -q -m 'not integration'
git diff --check
```

[`configs/acceptance-zero-battle-readiness.json`](../configs/acceptance-zero-battle-readiness.json)
is the machine-readable specification. This document and all listed source files
are hashed **before** startup. Its sole command has zero planned/reserved/requested
games, one permitted startup probe, no retries/resume, and a 120-second aggregate
ceiling: 90s integrity/lifecycle, 10s mandatory reporting, 20s cleanup/closure.
This deliberately schedules only one of the user's maximum two probes. A second
is never automatic and could occur only after a concrete first-probe defect is
repaired, using a separately recorded remaining allocation. Unused time cannot
authorize games or another successful probe.

Critical inputs are explicit: all 4,049 original-engine/wrapper runtime inventory
files; the existing manifest's 74 project files; six named new source/spec files;
the exact c0, V4 and V5 artifacts; the full r5 build/physical files/link inventory;
and the same four legal teams. No historical archive scan is involved. The
freeze/checked-I/O artifacts name every file actually validated. Strict retained
model loaders run again. A fresh exclusive output and single-use ledger precede
work; integrity failure prevents startup. An occupied port, failed dependency
resolution, config/model mismatch, unexpected file/binding, timeout or cleanup
failure stops the probe. No retries, game reservations or policy calls exist in
this diagnostic.

After loading/handshake the server is closed. Expected private output is session
and path-check metadata only: there must be no battle/end/acceptance records.
Mandatory machine and Markdown reports are produced under the reserved deadline,
including failure paths. Later documentation links these sealed results without
extending their clocks or making supplemental forensic work part of that budget.

Run once **only after the offline suite passes**:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B diagnostics/acceptance_zero_battle.py
```

Fresh output: `runs/acceptance-zero-battle-readiness-20260911`. Actual results and
times belong to its `ledger.json`, `report.json`, `REPORT.md`, `verification.json`,
`readiness/lifecycle.json`, worker records and source freeze. This pre-start
specification will remain unchanged after collection; results are linked separately.

## Retained controls and limits

`runs/acceptance-packaging-repair-20260911/integrity-and-controls.json` records
strict c0/V4/V5 loading; verification of all 4,049 retained runtime hashes and both
r3/r5 build manifests; equal patch/source/compiled files; equal resolved versions;
and unchanged ASTs for patch construction, match collection, replay, recording
factories and isolation auditing. Changed historical project hashes belong only
to packaging, preflight/reporting and their tests. The original 24 games therefore
remain relevant restricted-pool controls for the same engine/runtime, teams,
policies and recording design. They are not new games and cannot demonstrate
identical trajectories, normalized acceptance or instrumented behavior. Unmatched
old/new timing is descriptive, not a controlled instrumentation-overhead estimate.

The repair artifacts preserve baseline files/hashes, both resolution diagnostics,
build console failures/success and offline test outputs. The original failed
attempt and replacement ledgers remain sealed. No historical conclusion changes.
Readiness alone leaves request/attempt/acceptance/commitment linkage, public versus
private isolation during real decisions, completeness and all battle normalization
cases unverified live. Eligibility remains unchanged.

## Proposed follow-up — not authorized or executed

Propose **24 instrumented-only games**, no new original games, in a fresh
`runs/acceptance-instrumented-only-1` with its own frozen spec and single-use ledger.
Use the same c0/random policies, seed 260911, Gen 1 OU four-team schedule (all six
pairs × four assignments/sides), concurrency one, 300-turn/60-second per-game
limits, exact matching, warning/exclusion rules and conservative 66s reservation
guard. Suggested ceiling: **420s** = 100s integrity/readiness, 240s collection,
60s mandatory replay/isolation/preservation/report, 20s cleanup. No borrowing,
retries, resume or supplementary games. Reserve all allocations before work.

Freeze the new r5 manifest plus current source and exact input list; do not reuse
the consumed 48-game configuration or ledger. Reuse its original 24 games solely
as retained controls with provenance checks. Report instrumented normalization
coverage actually observed; unencountered cases remain unverified. Any blocking
integrity or cleanup error stops. A separate implementation/review and explicit
authorization are required; this repair does not add a runnable battle follow-up.
