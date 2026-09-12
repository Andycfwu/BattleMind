# Instrumented engine readiness — passed, zero battles

2026-09-11. The packaging/preflight repair and its pre-start specification are in
[ACCEPTANCE-PACKAGING-REPAIR.md](ACCEPTANCE-PACKAGING-REPAIR.md). That frozen
document is unchanged after startup. The [failed replacement](ACCEPTANCE-LIVE-REPLACEMENT-RESULTS.md)
still records **24 completed original-engine games and zero requested instrumented
games**. Neither consumed experiment was resumed, repaired or overwritten.

## Observed lifecycle

Exactly **one** startup probe ran, using the fresh pinned-pnpm build
`.local/pokemon-showdown-acceptance-v2-r5`. **Zero games** were planned, reserved,
requested or completed. No policy was called, trained or made eligible.

| Measurement | Seconds |
|---|---:|
| Integrity checks, source freeze, lifecycle and preservation worker | 13.140131 |
| Server startup through initial successful handshake | 3.782073 |
| Complete server lifecycle, including additional handshake and cleanup | 3.830639 |
| Server shutdown and cleanup check | 0.038129 |
| Mandatory machine/Markdown reporting worker | 0.546298 |
| Final ledger closure | 0.000744 |
| Ledger-accounted diagnostic total | **13.690135 / 120** |

Lifecycle rows are contained within the integrity/lifecycle phase, not added to
its duration. Phase/aggregate overruns and integrity failures were zero. The
ledger starts at the diagnostic's main entry; interpreter/import bootstrap was
not separately timed. No second probe was needed or run.

The actual official server entry loaded from its derived working directory and
sent the normal Showdown `challstr` WebSocket response. Its log shows a single
listener at **127.0.0.1:8000**, with ordinary lobby/staff restoration and no startup
error. All captured owned server/worker processes exited; both the lifecycle check
and a later independent read-only check found no remaining owned PID or listener.
No unrelated process was terminated. Private outputs contain session/path-check
metadata only; no acceptance chains or battle end logs were created.

Across 58 process samples, the largest individual server-process RSS was
388,866,048 bytes (about 371 MiB). The sum of each observed process's last sampled
CPU time was 1.9375s. These sampled figures can miss peaks and final CPU work;
they are not a complete allocation trace or an instrumentation-overhead estimate.

## Validation and unchanged science

- **374 offline tests passed; 14 integration tests were deselected**, in 9.43s.
  An earlier focused run passed 105 tests. No battle/training integration suite ran.
- Both original and failed-derived byte inventories remained valid. The failure
  was reproduced independently: copied package bytes still hashed correctly,
  while ten required resolution edges and the `sockjs` load failed. The repaired
  build has no required resolution failure and matches original dependency versions.
- Strict original c0, V4 predictor and selected V5 loaders passed. The new derived
  build retained all 2,142 source/compiled file hashes from r3, the exact reviewed
  patch and lock. Its 662 physical package files and 41 internal links are separately
  inventoried. Old manifest schema v1 remains strictly loadable for historical
  integrity audits; new schema v2 does not convert that into a readiness claim.
- Patch construction, collection, probability replay, recorder factories and
  isolation-audit function ASTs remained identical. Policy, observation, acceptance
  evidence and eligibility code did not change. No poke-env hook was modified.
- The preflight freshly checked the explicit original/wrapper runtime inventory,
  current source, configuration, required models and derived build. The probe
  freeze precedes server startup. Frozen source and model hashes matched afterward.
- The selected historical files, including both consumed ledgers, earlier closure,
  old build manifest and design/results documents, matched their before hashes.
  This was targeted preservation verification, not a full historical archive scan.

The first packaging command stopped on a Windows log-encoding error after pinned
installation; its fresh r4 directory and console are retained. UTF-8 logging was
fixed, then a separate r5 build succeeded before any startup probe. A new synthetic
test initially lacked the official config directory; the fixture was fixed before
the final offline suite. These failures are retained and were not battle failures.

## Reporting and artifacts

Mandatory probe reporting completed inside its **10-second** reserved worker.
The separately repaired live harness gives full audits 50 of its reporting 60s,
reserving ten for counts/Markdown and 20 outside reporting for cleanup/closure.
Failure paths run reporting too; blocked reporters cannot trigger an unbounded
closure log scan. Missing outcomes remain unavailable. Closed ledgers stay sealed.
The earlier 187.048110s supplemental authoring overrun remains historical evidence.

A separate **15-second** read-only post-check used **0.254294s** for named source
and historical hashes, compact probe records, PID/listener checks and changed-file
whitespace checks. It did not extend the sealed probe's clocks. Engineering
documentation is separate from its automated mandatory report; no supplemental
archive investigation was launched. `git diff --check` and explicit no-index
checks of the changed untracked files passed. Generated builds and runs remain ignored.

Actual probe command, invoked once after the passing offline suite:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B diagnostics/acceptance_zero_battle.py
```

- `runs/acceptance-zero-battle-readiness-20260911/`: single-use ledger,
  specification, freeze, exact checked-file I/O records, lifecycle/resource samples,
  private metadata, cleanup records and the timed `report.json` / `REPORT.md`.
- `runs/acceptance-packaging-repair-20260911/`: before copies/hashes, original and
  broken/repaired resolution diagnostics, build logs, failed/passing tests,
  `integrity-and-controls.json`, pre-probe review, diff and final `result.json`.
- Modified existing implementation: `src/battlemind/acceptance_build.py` and
  `diagnostics/acceptance_live_verify.py`; their focused tests were updated.
  New helpers are `scripts/inspect-acceptance-runtime.cjs`,
  `diagnostics/acceptance_readiness.py`, `diagnostics/acceptance_zero_battle.py`,
  the zero-battle specification and `tests/test_acceptance_readiness.py`.

| Artifact | SHA-256 |
|---|---|
| Frozen probe specification | `d43848197d28c32bc2739bfb5a9e79874a75751b542a538429d3e202209d4dd2` |
| Frozen repair/design document | `574cc740b5bf5992b38610d93c554c019c3fc12df18903514971497c8512c156` |
| Probe ledger | `b3c64f99e634727a078422468147a776a3d281ac83050e0e5b52d7d0de816868` |
| Probe freeze | `a665b74b21aa6cdcf90549760adcdd97b9d681ba3cac4d66ae4a259d1c10a817` |
| Probe report | `0ec2ba517ea56925f56ad5d4f9e5da5e408963f29a5645520aae6d476a6446ed` |
| New build manifest | `41ec777dc02811d55c8b8c3762d24e6e5ee41c488bc3077ad3d2b1fc69d1a813` |

## What this supports

The repaired dependency layout, server loading, normal handshake, loopback binding
and cleanup are verified. Required preflight scope is sufficient to catch the
identified packaging failure before future game requests. Reporting has bounded
failure handling, with offline deadline/immutability regressions.

The retained original 24 games remain relevant controls because their runtime,
configuration, policy/team and scientific source hashes are preserved. They do not
match simulator randomness or certify instrumented behavior. There is **no live
request-bound acceptance or normalization evidence yet**, including ordinary moves,
voluntary/forced switches, Wrap, Clamp, fight, Recharge or Struggle. No exclusion
or eligibility change is justified by this lifecycle probe alone.

The single proposed next action is the separately authorized **24 instrumented-only
games / 420 seconds** described in the frozen repair note. It needs its own fresh
specification, input freeze, reviewed harness configuration and ledger. Do not
repeat the successful original-engine games. That follow-up was not implemented
as a runnable battle command or executed here.
