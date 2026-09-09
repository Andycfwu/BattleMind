# BattleMind V7 — evidence and local demonstration

V7 is implemented and its bounded functional checks pass. It adds a read-only
evidence catalog, safe portable artifacts and a local animated viewer. It does
**not** establish competitive strength or complete V6 acceptance. No new
performance benchmark, model fitting, policy optimization or adaptation collection
ran. V7 is the final planned milestone.

The pre-V7 status is preserved byte-for-byte in
[MILESTONE6-REPAIR.md](MILESTONE6-REPAIR.md), SHA-256
`cd6e9590e617701aca4089c68a029a465446790ca4bf43757c0527a85dbc5b29`.
All V1–V6 experiment files and required original models remain unchanged.

## Watch locally

```powershell
.\scripts\start-demo.ps1 -Bundle runs/v7-release-bundle -Output runs/MY_FRESH_DEMO
# Open http://127.0.0.1:8765
# Stop in another terminal, or Ctrl+C in the first:
.\scripts\stop-demo.ps1 -Run runs/MY_FRESH_DEMO
```

The script loads `scripts/env.ps1`. Default allowance: two games, concurrency one,
300 aggregate run seconds, 75 seconds per run, 60 per match and 300 turns. The
service stops after 30 minutes. `-Games 0` permits recorded-only viewing.
Live policies: random, MaxBasePower, V2 heuristic, frozen V4 logistic and selected
V5 learned-score. V6 is demonstrated through four chronological recordings;
live cross-encounter adaptation is unsupported.

The official renderer shows Pokémon, public HP/status, moves, switches, turns,
English logs and outcomes. Controls include Play/Pause, four speeds, turn step,
reset and paused go-to-turn. Simulation often finishes before animation and is
labeled delayed playback. Controls cannot affect policy observations or actions.
Examples include a normal battle, V5 score-driven choice change, historical
freeze cap and V6 encounters with visible reset/history cutoffs. Explanations
use actual own-player post-encounter numeric records.

Viewer and managed games use 127.0.0.1:8765/8000. All assets are local; audio,
account client, CDN, remote fonts, telemetry and replay upload are absent. Models,
private logs and memory-audit inputs are not HTTP routes. All verification
services are stopped. See [V7.md](V7.md) for boundaries and controls.

## Retained conclusions

[Readable report](../runs/v7-evidence-release/REPORT.md) and
[catalog](../runs/v7-evidence-release/catalog.json) cover nine scopes. Terminal
counts were recomputed from every retained battle row and compared to saved cell
summaries. **12,010 historical manifest entries match**, with zero catalog
inconsistencies. V1/V2 lack a scope-wide frozen artifact manifest; their current
hashes establish identity, not an invented historical freeze. Full metric/exclusion,
arm/target, phase, resource, policy/model/team and uncertainty records remain in
the catalog. Mixed A/B totals are accounting, not a cross-version ranking.

Catalog SHA-256:
`d88854df26e76b8b4b6479dc4749022e0bbdb068081d2523f08fffa27af525b7`.
Integrity, retained semantic replay coverage and current source compatibility are
different. Historical full-source audits still require historical code. They were
not weakened. Original scientific V4/V5 loaders and minimal V6 replay pass today.

| Version | Supported conclusion | Limit |
|---|---|---|
| V1 | 20 real local legal matches; immutable decision records | Pipeline check; predates verified commitment labels |
| V2 | Transparent heuristic, validated four-team pool and conservative labels | Restricted baselines, no broad strength estimate |
| V3 | Counts affected decisions | Brier .204089 versus constant .200732: worse estimates |
| V4 | Logistic Brier .078675 versus constant .125640 and fair counts .118878 on 7,377 eligible final examples | Improved prediction on its declared mixture; battle benefit inconclusive |
| V5 | 840 completed games, two nonzero outcome-driven updates with archived self-play | Selected 104/38/2 versus initial 98/43/3 over 144 final games each; reward-difference interval [-.048611, .125000] includes regression |
| V6 first | Memory worked technically | **96 completed development games; development budget exhausted; zero final games** |
| V6 repair | Accounting fixed; 144 development complete | Final: 252 requested, 251 completed, one cap, 324 never requested; only one full final group |

Both V6 attempts remain incomplete. Repair probability metrics cover 248 games
from complete final cells: individual Brier .073545 versus none .083232 and pooled
.083774; log loss .254239 versus .263770/.268022. Partial losses do not establish
adaptation benefit. Individual **switch-active log loss worsened**, four-group
uncertainty is unavailable, and stopped live-arm schedules are unequal. The cap
exposed a frozen heuristic that stayed with frozen Zapdos despite a healthy legal
replacement. Cleanup is not a win. Nothing was tuned or retried. Full details and
original accounting limitations remain in [MILESTONE6-REPAIR.md](MILESTONE6-REPAIR.md).

## Portable artifacts

[ARTIFACTS.md](ARTIFACTS.md) documents import/export and the minimal closure.
`runs/v7-release-bundle.zip` is **1,962,355 bytes**, containing 157 payload files /
8,813,930 bytes plus manifest: seven public recordings, original V4/V5 JSON,
local renderer/source/notices and a four-encounter observer-owned V6 audit prefix.
No credentials, other-player journal, private end log, simulator RNG or full
training dataset is bundled.

| Artifact | SHA-256 |
|---|---|
| Original V4 / bundled predictor | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| Selected V5 / bundled checkpoint | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |
| Release manifest | `fdb3bd642a4ea854a50fc35ffe3005a6a51e21497ea378dd3c36309e0a43220c` |
| Release ZIP | `808282811b87da04062534447e11eee6c2be1fb6e717b76b12eac286bf883a45` |

Import into isolated temporary directories and `runs/v7-release-imported` passed
existing loaders/hash checks and unchanged memory replay: **98 decisions across
four encounters**, including **37** individual-versus-none probability changes.
Playback order does not update memory. This prefix demonstrates the mechanism,
not a representative adaptation win rate.

A source-only clone can set up transparent baseline games but lacks ignored
models, checkpoints, records and assets. Recorded viewing requires the bundle
and pinned Python; fresh live games also require pinned Node/Showdown. Historical
fitting requires retained inputs. Policy seeds do not control engine randomness
or reproduce historical trajectories.

## Actual verification

[V7-VERIFICATION.md](V7-VERIFICATION.md) and `configs/v7-verification.json`
predeclared **three** fresh functional games, below the user's eight-game ceiling,
and 300 aggregate run seconds. This allocation is consumed.

- **160 unit tests passed**, 13 integration tests deselected, in **4.69s**.
  Existing information/label/memory/budget/checkpoint checks remain included.
  New tests cover public HP/private mutation isolation, event alignment, terminal
  states, explanations, safe import, budgets, zero-example reporting and a
  spectator failure after a completed battle.
- **One real integration workflow passed**, at
  `runs/integration-v7-0d640e66da`: learned-score/MaxBasePower, seed 71901,
  1/1 completed, 39/39 verified commitments, **5.195113s** including preflight/audit.
- **Two browser-launched games completed**, at
  `runs/v7-demo-verification/live-1` and `live-2`: learned-score/MaxBasePower and
  heuristic/random, seeds 71001/71002. **2/2 complete**, 120/120 commitments
  verified, **11.070167s** including bundle/preflight/audit work.
- Combined: **3 requested, 3 complete; A wins 3, B wins 0, draws 0; 159/159
  commitments verified**. Zero caps, invalid actions, timeouts, crashes,
  cancellations, missing records, server errors or wrapper warnings.
  **16.265280 / 300 seconds used**. This unbalanced sample is functional only.
- Game resource samples: summed Python CPU .328125s; summed last server CPU
  samples 8.625s; maximum sampled RSS 91,189,248 bytes Python / 452,493,312 bytes
  server. Sampling every .1s is not exact lifetime/browser/offline-audit usage.
- Browser checks reached completed turn 37 and capped turn 300. Paused seek 3 →
  next 4 → previous 3 passed, alongside images/HP/status, moves/logs, pacing,
  reset, explanations and memory cutoffs. Final page errors, broken displayed
  images and CSP-blocked remote requests were zero.
- Actual HTTP checks rejected private/model/trace/path endpoints, hostile
  Host/Origin, unknown policies and invalid tokens. Zero-game budget denial
  left the ledger unchanged. Expected negative 400/403/404/409 responses are
  tests, not battle failures. `runs/v7-final-viewer-check` allowed/requested zero
  games. Stop commands succeeded; no listener remains on 8000/8765.

The documented launcher itself was also exercised with zero games:
`scripts/start-demo.ps1 -Bundle runs/v7-release-bundle -Output runs/v7-launch-script-check -Games 0`.
Its local page returned HTTP 200; `scripts/stop-demo.ps1 -Run runs/v7-launch-script-check`
stopped it with zero requests. Final process inspection found no managed Showdown
Node process. These playback/startup checks add no battle-run time.

[Verification JSON](../runs/v7-verification.json) records resource/count/source
hashes, unchanged scientific files, bundle compatibility and cleanup.
[HTTP verification](../runs/v7-http-verification-final.json) is separate. The
spectator-error accounting branch uses an explicit offline failure fixture; the
already verified normal path was not rerun to consume extra games.

Development issues are retained: early local effect-image paths and scene cleanup
needed fixes, verified through zero-game playback. The first readable catalog
formatter failed on a zero-example `None` metric; a regression now displays it
as unavailable. That partial output remains in `runs/v7-evidence`; release output
is separate. Preliminary bundles have older renderer pins and are not supported
release imports. No V1–V6 evidence or scientific rules changed.

## Exact main commands run

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe scripts/setup-viewer.py
.\.venv\Scripts\python.exe -m battlemind demo-prepare --output runs/v7-release-bundle
.\.venv\Scripts\python.exe -m battlemind bundle-export --source runs/v7-release-bundle --output runs/v7-release-bundle.zip
.\.venv\Scripts\python.exe -m battlemind bundle-import --source runs/v7-release-bundle.zip --output runs/v7-release-imported
.\.venv\Scripts\python.exe -m pytest -q
# Already run once: one real game, no training integrations.
.\.venv\Scripts\python.exe -m pytest -q -s -m integration tests/test_v7_integration.py
# Already run with two explicit browser launches, then stopped:
.\.venv\Scripts\python.exe -m battlemind demo-serve --bundle runs/v7-demo-imported --output runs/v7-demo-verification --games 2 --seconds 1800
.\scripts\stop-demo.ps1 -Run runs/v7-demo-verification
# Final UI/assets: recorded playback only.
.\.venv\Scripts\python.exe -m battlemind demo-serve --bundle runs/v7-release-imported --recordings runs/v7-demo-verification/public --output runs/v7-final-viewer-check --games 0 --seconds 1800
.\.venv\Scripts\python.exe scripts/verify-viewer.py --run runs/v7-final-viewer-check --output runs/v7-http-verification-final.json
.\scripts\stop-demo.ps1 -Run runs/v7-final-viewer-check
.\.venv\Scripts\python.exe -m battlemind evidence --output runs/v7-evidence-release
.\.venv\Scripts\python.exe .local/verify-v7-final.py
git -c core.safecrlf=false -c core.autocrlf=false diff --check
```

Renderer pin: official client `afa9d4ae645923e42fc8f587080c6bf3d13de2fc`;
2,913,473 downloaded bytes. Runtime pins remain Python 3.14.3, Node 24.19.0,
poke-env 0.16.1, NumPy 2.5.2 and Showdown
`2f5b273925862ac242b419086c1e7a8868b51da1`. Existing esbuild 0.25.12 builds the
renderer subset. No intentional dependency change was needed.

[INTERVIEW.md](INTERVIEW.md) traces one frozen observation to one legal action
and separates engine, recorder, learner, memory, viewer and evaluation.
[ATTRIBUTION.md](ATTRIBUTION.md) credits official components and standard methods.
Scores remain approximate, effective stats/hidden destinations remain unknown,
and historical animations omit unretained annotations. No public ladder, human
profiling, external replays, hosted service, live adaptation demo, performance
guarantee or next version was added. No commit, push, upload or deployment occurred.
