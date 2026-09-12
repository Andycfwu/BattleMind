# Instrumented-only verification — functional success, partial coverage

2026-09-11. The single authorized run completed **24/24 instrumented games**. All **1,697 decisions** passed frozen-policy replay and exact request-to-attempt-to-acceptance-to-commitment validation. The policy-isolation and preservation audits passed. **Clamp continuation and Struggle were not encountered and remain unverified live.** No follow-up ran.

The predeclared [specification](ACCEPTANCE-INSTRUMENTED-ONLY.md) and machine configuration remain unchanged. Historical failed attempts, original labels/unknowns, checkpoints and exclusions were preserved. No training, policy change, eligibility change, retry, commit, push or deployment occurred.

## Actual collection and coverage

Planned/reserved/requested/recorded/completed: **24/24/24/24/24**. Never requested and missing requested records: **0/0**. Frozen c0 won 24, random won 0, draws 0; the completed-game denominator is 24. Caps, timeouts, crashes, cancellations, invalid-action incidents and experiment/integrity failures were all zero. These are restricted-pool functional outcomes, not a strength experiment.

| Validated committed category | Decisions |
|---|---:|
| Ordinary move | 1110 |
| Voluntary switch | 344 |
| Forced replacement | 155 |
| Wrap locked-move continuation | 1 |
| Gen 1 fight branch | 61 |
| Recharge locked-move branch | 26 |
| Clamp continuation | 0 |
| Struggle | 0 |

All 1,697 attempts are committed; none are unknown, rejected or accepted-but-uncommitted in this new run. The 48 separate client streams, 24 room streams and 24 simulator streams were validated with clean seals, exact identities, hashes and commitment indices against official end logs. The six unordered team pairs each received their complete four-game assignment/challenger block.

**No sampled semantic ID was observed being rewritten into a different accepted move.** The 88 branch observations (61 fight, 26 Recharge, one Wrap) validate those paths and their linkage; they do not exercise the many-to-one or semantic-rewrite discrepancies that motivated earlier exclusions. The Wrap example is match 12, p2, rqid 57, exact commitment index 55. Private per-attempt examples are in `verification.json` and the corresponding acceptance reports.

Functional recording passed for the observed schedule. Target coverage is incomplete because Clamp continuation was absent; optional Struggle was also absent. Rejection/undo/reconnect/duplicate cases remain offline-only. No unobserved case is marked passed, and no extra game was used to fill coverage. Acceptance/commitment does not prove execution or effect.

## Isolation and historical reference

The unchanged isolation audit mutated disposable private acceptance/end-log copies from match 0, covering 33 observer snapshots. Private validation rejected the mutations while policy replay, predictor probabilities, permitted public memory and spectator projection stayed identical. This is a concrete boundary test, not a universal security proof.

The new legacy label audit passed: 1,697 decisions/labels across 24 battles, with 1,697 verified intended choices and zero unknown intended choices. Opponent-target eligibility still has two unknown cases; that separate target contract was not relaxed. Public execution evidence reports 957 move announcements, 499 observed switches, 107 not-announced actions and 134 prevented/engine-wait records. None of these categories is substituted for acceptance.

The retained original **24 games were not rerun**. Preflight reproduced all **1,641** original decisions through the frozen checkpoint, audited their original labels, compared scientific/runtime/model/team/config hashes, and hashed the original run directory before/after collection. Its four unknown intended choices remain unknown. Packaging and the instrumented-only reader import are outside policy mathematics; the underlying collector and audit function bodies remain unchanged. The original run-manifest identity is `02677f406fd059bf68a27773620b5a19b07223c58ee50043a17fbd2832413ff2`.

Two recognized Wrap/Clamp trailing-annotation warnings were retained; zero unexpected warnings occurred. Private recording never entered policy features or viewer routes. Historical V6 acceptance and previous learning conclusions remain unchanged.

## Time, overhead and cleanup

| Measurement | Seconds |
|---|---:|
| Preflight, including reference audit and operational readiness | 16.520215 / 100 |
| Instrumented collection, per-match audits and shutdown | 18.175183 / 240 |
| Preservation/isolation/coverage/hashing and mandatory reporting | 9.490372 / 60 |
| Ledger-accounted total | 44.188811 / 420 |
| Full externally measured invocation | 44.300102 / 420 |

Ledger-defined overhead was 26.013628s. Direct per-match acceptance validation totaled 2.099067s. All phase/aggregate overrun counters were zero, and the outer watchdog did not fire. Mandatory reports were written before the ledger sealed; later reads do not extend or rewrite it.

The original phase took 11.282825s versus 18.175183s here. Different trajectories, 1,641 versus 1,697 decisions, recording/auditing work and machine conditions prevent treating this as a causal instrumentation-overhead estimate. Equal 24–0 outcomes do not establish engine equivalence.

Sampled Python CPU: 7.671875s; peak Python RSS: 113,655,808 bytes. Sum of sampled server-process RSS peaked at 447,270,912 bytes; last sampled server CPU: 3.984375s. Sampling every 0.1s can miss peaks/final CPU work and RSS sums can include shared pages.

The hashed artifact inventory totals 73,210,708 bytes, including 35,353,861 bytes under the private acceptance directory. This excludes active I/O/console logs and later closure files; it is not total disk usage.

Every owned server/worker process exited, and no listener remained on port 8000. A bounded read-only publication check independently confirmed cleanup and unchanged frozen source hashes; it did not run another audit or archive scan. No unrelated process was terminated.

## Commands, tests and artifacts

The missing `read_chain` import was reproduced offline (one failing regression), then fixed before freezing. All existing function/class ASTs remained identical. **381 offline tests passed, 14 integration tests were deselected in 10.54s**; 83 focused tests passed in 2.29s, and the final seven targeted tests passed in 0.31s. Test games: zero. Whitespace/source review passed; no historical training integration suite ran.

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B -m pytest -q -m 'not integration'
.\.venv\Scripts\python.exe -B diagnostics/acceptance_instrumented_only.py --output runs/acceptance-instrumented-only-1
```

The collection command was invoked exactly once with an external 420s watchdog. Read saved reports without collecting, auditing or rewriting clocks:

```powershell
.\.venv\Scripts\python.exe -B diagnostics/acceptance_instrumented_only.py --output runs/acceptance-instrumented-only-1 --report
```

- `runs/acceptance-instrumented-only-1/`: frozen specification/source/inputs, single-use ledger, reference audit/hashes, operational readiness, private streams, match audits, isolation copies, `verification.json`, `report.json`, `REPORT.md`, artifact hashes/sizes and cleanup records.
- `runs/acceptance-instrumented-only-preparation-20260911/`: pre-fix source, failing/passing tests, exact import diff, source review, actual invocation/PID/watchdog timing and publication checks.
- New orchestration/configuration: `diagnostics/acceptance_instrumented_only.py`, `configs/acceptance-instrumented-only.json`, `configs/acceptance-instrumented-only-inputs.json`, and focused offline tests. Existing `acceptance_live_verify.py` changed only by importing the strict reader.

| Artifact | SHA-256 |
|---|---|
| `configs/acceptance-instrumented-only.json` | `d7170470120faf81520308e3855583a948059798c5cfc49f263a89af4acb375c` |
| `docs/ACCEPTANCE-INSTRUMENTED-ONLY.md` | `8aaf69cabf7daac652d1fb272e24a2960c9b7b98620e116736bed457a6fe6666` |
| `runs/acceptance-instrumented-only-1/ledger.json` | `40547b056f10d5b24ea07a586a4af1b75bb218485e810af111ed9f53aad6af98` |
| `runs/acceptance-instrumented-only-1/freeze.json` | `f874fa22975c34a6d4a577a7d1fc33a6539898ca8532a3070e275eeb867d1996` |
| `runs/acceptance-instrumented-only-1/report.json` | `28d024c82fec10c851d6c6ff6ddc2c25198ec673be87422a6dc9d0f7170f4b07` |
| `runs/acceptance-instrumented-only-1/verification.json` | `e3767851b5869e6aa533b6d755fad28712ccc777000ad5b917c57feeab805390` |
| `runs/acceptance-instrumented-only-1/artifact-hashes.json` | `3bc1621bdcb35561bb5e76cd941f617b8d5e96e7ec6182211d7d6723c6f7a83a` |
| `runs/acceptance-instrumented-only-1/instrumented/run.json` | `18e135646c0832173ebc2d1b6c258bed712998ddf9770596900aafe174fa5782` |

**Supported conclusion:** the opt-in recorder works end to end for all 1,697 observed decisions under this bounded fixed-team schedule, with preserved policy isolation and exact commitments. Normalization coverage is partial, and no semantic-rewrite case was observed. This does not validate historical uncertain trajectories, justify relaxing exclusions, prove engine equivalence, or establish better battle play. No follow-up is executed or authorized by this result.
