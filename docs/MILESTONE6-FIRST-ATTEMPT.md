# BattleMind V6 — memory works; final acceptance is incomplete

V6's public-memory mechanism, frozen three-arm scoring, chronological replay and
tests are implemented. **The single declared experiment stopped on its development
wall budget: 96 requested games completed, but the 144-game development schedule
did not finish and no final games ran.** This is partial acceptance evidence, not
a completed V6 performance experiment. No retry, budget increase or borrowing from
final occurred. Improvement remains unverified by final evaluation.

The original V5 status is preserved **byte-for-byte** in
[MILESTONE5.md](MILESTONE5.md): actual outcome-driven updates, reproducible frozen
checkpoints and inconclusive battle improvement. V4/V3 evidence remains in
[MILESTONE4.md](MILESTONE4.md) and [MILESTONE3.md](MILESTONE3.md). This workspace had
uncommitted V5 work at inspection, based on HEAD
`4b47dc412450c68d73c1268f6b80672251030c23`; that work was preserved. No commit, push,
deployment, external data ingestion or additional self-play experiment was made.

## What is implemented

- `opponent_memory.py`: observer-only public evidence, forced/ambiguous/missing
  exclusions, immutable numeric summaries and opaque session routing. Each completed
  encounter with at least four admitted proxies contributes one mean residual.
- `adaptation.py`: no-memory, pooled and individual probabilities over the same
  frozen V4 predictor and selected V5 scorer. All three shadow predictions and
  choices are computed on each identical snapshot; only the assigned arm plays.
- `memory_runtime.py`: freezes the summary for an entire battle, exports only the
  observer's public data after completion and updates only that observer's manager.
  No private label, end log, opposing journal or reward drives memory.
- `memory_audit.py`: rebuilds memory chronologically and reproduces probabilities,
  scores and choices without reading privileged labels/end logs. The existing
  private commitment audit remains separate and unchanged.
- `adaptation_ledger.py`, `adaptation_experiment.py`, `adaptation_report.py`: single-use
  phase reservations, interleaved repeated encounters, explicit resets, disjoint
  partitions, frozen artifact checks and honest partial-result accounting.
- CLI: `adaptation-run --output FRESH` and read-only
  `adaptation-report --experiment PATH --audit`. Resume is unsupported. Ordinary
  frozen V5 checkpoint battles remain available through the prior CLI.

No original V2/V3/V4/V5 scorer, adapter, snapshot schema, predictor, label recorder,
team fixture, dependency lock or server configuration changed. Poke-env 0.16.1's
installed request/message source was read; private hook bodies remain unchanged.
Package 0.6.0 retains Python 3.14.3, Node 24.19.0, NumPy 2.5.2 and Showdown commit
`2f5b273925862ac242b419086c1e7a8868b51da1`. All games used concurrency 1 and services
on 127.0.0.1; cleanup left no listener on port 8000. No dependency changes were needed.

## Required artifacts and preservation

Both original inputs passed their current compatibility loaders before V6 work
and again after collection. Their unchanged copies are `predictor.json` and
`checkpoint.json` inside `runs/v6-acceptance/` and the relevant cell directories.

| Original retained input | SHA-256 |
|---|---|
| `models/v4-supervised.json` | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| `runs/v5-acceptance/selected.json` | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |

V5 parameters stay (-.32986111111111105, .32986111111111105,
.32986111111111105, .32986111111111105). No coefficients, preprocessing, features
or score parameters were fitted or updated in V6.

`runs/v6-verification.json` verifies every retained artifact manifest: V3 acceptance
667 files, V4 development 668, V4 acceptance 1,330, V5 acceptance 3,917, V6 1,064;
**zero hash mismatches**. It also checks unchanged prior scoring/data/config source
and the preserved V5 status hash
`17cdf778ec9c97a4efea15a6c17d1f56b2575d2bfc3df7da3103051d1f683c19`.
Historical full-source freeze audits require the code that actually ran; V6 additions
naturally change that whole-source manifest. The stricter historical audit was not
weakened. Checkpoint compatibility and historical file preservation are separate checks.

Source-only clones lack ignored historical models, checkpoints and their training
inputs. [ADAPTATION.md](ADAPTATION.md) documents the existing regeneration commands
and why they cannot promise the same historical V5 checkpoint. Missing inputs cause
a clear failure, never silent retraining/substitution. Generated files remain ignored.

## Specification, allocation and actual stop

[V6-EXPERIMENT.md](V6-EXPERIMENT.md) and `configs/v6-experiment.json` were written
before reported games and stayed frozen. Their hashes are respectively
`07a73b4311ad630a317c90ae52de2ad6cd4229a8235a5287126d1f36f1a1ce3d` and
`a777ade5904f669161603fe0ca760913c6e131c080883fffd85e45c31e1b22b6`.

| Phase | Allocated games / wall | Actually requested / completed | Actual use |
|---|---:|---:|---|
| Development, one group | 144 / 180s | **96 / 96** | Collection stopped at 165.731s |
| Final, four fresh groups, reserved first | 576 / 600s | **0 / 0** | Never entered; all allocation unused |
| Freeze/report/hash overhead | 0 / 120s | 0 / 0 | Included in total below |
| Total | **720 / 900s** | **96 / 96** | **181.465s including initial reporting/hashing** |

Stop message: `ValueError: Adaptation game/wall budget exhausted; no borrowing final allocation`.
The guard requires at least 15 seconds before reserving another four-game cell.
At 165.731 seconds, the remaining development allocation was below that threshold.
There was **one experiment-level budget stop and no failed battle**. Forty-eight
development slots and all 576 final slots were never requested; they are neither
completed games nor ordinary losses. The ledger is consumed; no retry/resume is allowed.

The allocation underestimated the cost of 36 separate four-game lifecycles. The
24 completed cells took 132.535 seconds of run wall, of which 37.949 seconds were
battle time. Another 33.196 seconds before the stop were outside run wall, including
preflight validation and repeated audit/hash checks. The 94.586-second difference
inside runs includes startup/shutdown, recording and public-memory work. These are
accounting differences, not a detailed profiler. The budget was not sufficient for
this implementation's declared development schedule, let alone a meaningful final
comparison; the experiment did not proceed to final despite unused aggregate time.

**Preserved reporting limitations:** repeated `finish()` on a failed phase leaves its
clock active during post-stop reporting/hashing. Thus the original summary records
165.731s at collection stop, while the finalized ledger/read-only report charges
181.450s to the failed development phase. No games ran during that difference;
total experiment wall is 181.465s. The frozen files are retained unchanged and
`runs/v6-development-review.json` explains both values. The empty final-arm grid also
retains planned 192-game-per-arm denominators; use `phases.final.requested_games=0`
for actual requests, not that grid's planned unrecorded slots. These limitations and
the unexercised full final workflow remain follow-up work, not hidden successes.

## Exploratory development probability results

All values below come from the **same 2,222 eligible observer snapshots**, including
265 switches and 1,957 moves, across the partial development group. Each snapshot's
three shadow memories belong solely to its generating observer's earlier public
encounters. Shadows did not control play. No final examples exist.

| Shadow probability | Brier | Log loss |
|---|---:|---:|
| No memory | .083013 | .263727 |
| Pooled | .084411 | .271000 |
| Individual | **.072807** | **.249753** |

Individual minus no-memory: Brier **-.010206**, log loss **-.013974**.
Individual minus pooled: Brier **-.011604**, log loss **-.021248**.
These are descriptive development differences, not final conclusions.

| Generating arm (eligible snapshots) | Brier: none / pooled / individual |
|---|---|
| No-memory live arm (731) | .082629 / .083920 / .073850 |
| Pooled live arm (677) | .089282 / .090486 / .075152 |
| Individual live arm (814) | .078145 / .079799 / .069920 |

| Target (eligible snapshots / switches) | Brier: none / pooled / individual | Log loss: none / pooled / individual |
|---|---|---|
| MaxBasePower (801 / 0) | .058316 / .052343 / .038441 | .218936 / .200579 / .155935 |
| switch-active (1,421 / 265) | .096935 / .102487 / .092178 | .288975 / .310696 / .302637 |

Individual history improved aggregate Brier in this sample, but **worsened log loss
against switch-active versus no memory**. Residual correction is coarse: it can
raise probability on too many non-switch states while reducing larger switch errors.
Pooled history mixes incompatible behavior; the zero-switch target pulls its
correction down even for the switching target. Neither observation establishes
generalization beyond these fixed bots.

On the 126 first-session-encounter examples, individual exactly equals no memory
(Brier .136257). Pooled Brier is .151470 because it may already hold the other
session's evidence. On 2,096 later examples, none/pooled/individual Brier is
.079812/.080379/.068993. Sparse-history fallback covers 274 examples and exactly
preserves base prediction there; 1,948 examples have supported individual adjustment.
Calibration bin support and complete arm-by-target, cold/later and fallback
breakdowns are in `runs/v6-development-review.json`.

Only **one incomplete independent group** ran, with no counterbalanced final groups.
There is no useful independent-group uncertainty estimate. The planned bootstrap
returns unavailable; no turn-level or individual-battle intervals are substituted.
The partial development analysis did not change rules, opponents or reporting criteria.

## Exploratory live battle results and choice effects

Each arm completed 32 games: four of six unordered team-pair blocks against both
fixed targets, with both assignments and challenger sides within every block.
The full 24-games-per-target schedule was not completed. Simulator randomness was
not controlled or matched across arms.

| Live arm | MaxBasePower W/L/D (16 each) | switch-active W/L/D (16 each) | Overall W/L/D (32 each) |
|---|---:|---:|---:|
| No memory | 16/0/0 | 13/1/2 | **29/1/2** |
| Pooled | 13/3/0 | 13/3/0 | **26/6/0** |
| Individual | 16/0/0 | 15/1/0 | **31/1/0** |

Observed completed win rates are 90.625%, 81.250% and 96.875%. These are a small,
partial development comparison with shared memory and no final confirmation, not
evidence of improved battle strength. Two extra individual wins cannot establish
causality or statistical improvement.

On **3,643 identical observer snapshots**, individual changed probability relative
to base on 3,196 (87.73%) but changed the chosen action on only **6 (0.165%)**.
Individual versus pooled differed on five; pooled versus none differed on one.
Five of the six individual/no-memory differences occurred on the live individual
arm, and one was a shadow on the pooled arm. These are choice differences, not
counterfactual wins.

Concrete trace: `development/g0/individual-p0-vs-switch-active`, match 2,
`m2:a:r51`, turn 21. Two earlier supported individual encounters give residual sum
.335305; the correction is .335305/(8+2)=.033531. Base p=.078583 becomes .112113,
while pooled p=.054508. The frozen V5 scale gives Psychic score **70.881**, just
above switch:4 at **70.385**, so individual plays Psychic; both other shadows switch.
This uses public/anonymous switch-destination utility, not the opponent's hidden bench
or exact damage. Full scores and references remain in the observer journal and review.

## Public evidence, labels, failures and resources

Of 96 completed encounters, **89** supplied the minimum four proxies and updated
memory. There were **1,184 admitted public proxies**, including 178 switch proxies.
All 1,184 aligned to eligible private evaluation targets with **zero disagreement
in this sample**. That is not proof that the proxy always identifies intended choice.
It covers only **53.29%** of eligible observer snapshots and 178/265 (**67.17%**)
of eligible switches; 87 eligible switches were skipped. Selection bias is material.

| Public skip reason | Observations |
|---|---:|
| Public lock/copy/charge context | 646 |
| No publicly possible alternative | 496 |
| Opponent unknown or engine-related status | 389 |
| Observer engine or uncertain request | 333 |
| Observer forced request | 304 |
| Ambiguous or engine event | 195 |
| Missing announcement | 96 |

The separate private probability exclusions were 473 forced replacements, 504
engine actions and 613 requests without a meaningful switch/move choice. Across
both players, **7,455/7,455** attempted choices had verified commitments, zero unknown
commitments/eligibility, and 5,033 paired eligible opponent targets. V6's probability
population is the narrower 2,222 observer-a/target-b rows, not both perspectives.
Unknown mismatch suffix logic and Wrap/Clamp warning handling remain unchanged.

**Zero** invalid actions, caps, timeouts, crashes, cancellations, missing requested
games, server crash reports, recognized annotation warnings or unexpected warnings
occurred in this experiment. A stopped experiment is still a failure to finish its
schedule. Cleanup forfeits never contributed wins.

Summed per-run Python CPU: **28.469s**. Sum of managed-server last CPU samples:
**67.031s**. Maximum sampled RSS: Python **173.61 MiB**, server **431.53 MiB**.
These are per-run 0.1-second resource samples, not exact lifetime peaks or a CPU
profile of all offline audits. Later read-only audits/verification are outside the
collection clock and collect no games.

## Verification and actual artifacts

- **126 unit tests passed**; hidden-state isolation, immutable bounds/cold start,
  identical-evidence arms, chronological cutoffs, forced/ambiguous/unannounced
  evidence, resets/key renaming, budget exhaustion and incomplete updates are covered.
- **11 integration tests passed** in **86.90s**, including all prior tests.
  Test-game allocation was **45 requested**: 43 completed, one deliberate cap and
  one deliberate timeout. Those two checks are expected exclusions, never wins.
- The new V6 test used **8 of those 45 games**, in
  `runs/integration-v6-395fedd2d1/encounters-0` and `encounters-1`. It rebuilt 285
  decisions across repeated encounters, admitted 99 proxies in seven supported
  encounters and verified later prediction changes. Mutating copied private labels
  and engine evidence left public replay identical while private auditing failed.
- Existing pins, all four legal teams and the local server passed doctor; editable
  installation and `pip check` passed. No dependency download/change was needed.
- The acceptance CLI audit reproduced **3,643 decisions, 96 encounters and 24 private
  cell audits**, with zero overlapping battle identities, no unverified recorded
  cell and **1,064 matching artifact hashes**. `audit.ok=true` applies to recorded
  partial data. CLI exits **1** because `status=failed`, not because replay failed.

Main artifacts:

- `runs/v6-acceptance/`: frozen spec/source/config, original dependency copies,
  single-use ledger, all 24 cells, shadow predictions/decisions, public updates,
  summary and artifact hashes. `final-freeze.json` and final runs are absent.
- `runs/v6-development-review.json`: read-only partial development breakdown,
  complete calibration support, selection bias, changed-choice traces and timing
  interpretation. It adds no games and leaves the experiment files unchanged.
- `runs/v6-verification.json`: preserved historical files, current checkpoint/source
  compatibility, actual CLI audit and no remaining server listener.
- `.local/v6-doctor.json`, `.local/v6-integration-console.log`,
  `.local/v6-acceptance-console.log`, `.local/v6-cli-audit.json`: actual command output.

Exact main commands run from project root:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json > .local/v6-doctor.json
.\.venv\Scripts\python.exe -m pytest -q -m integration > .local/v6-integration-console.log 2>&1
.\.venv\Scripts\python.exe .local/test-v6-report.py
.\.venv\Scripts\python.exe -m battlemind adaptation-run --output runs/v6-acceptance > .local/v6-acceptance-console.log 2>&1
.\.venv\Scripts\python.exe -m battlemind adaptation-report --experiment runs/v6-acceptance --audit > .local/v6-cli-audit.json
.\.venv\Scripts\python.exe .local/verify-v6.py
git -c core.safecrlf=false diff --check
```

`test-v6-report.py` is an offline check on copies of the eight integration games,
explicitly a partial test fixture, with **zero extra games** and no acceptance metrics.
`verify-v6.py` is also read-only with respect to all original runs. Its new review
annotates the failed-phase timing issue; it does not repair or overwrite evidence.
Do not rerun `adaptation-run` or invoke training to replace required artifacts.

## What can be defended

Frozen supervised prediction is V4's learned coefficient/preprocessing artifact.
Prior self-play policy learning is V5's actual outcome-driven score update.
Pooled behavioral adjustment uses an observer's earlier public encounters across
sessions. Individual adaptation uses only that observer's evidence for the current
synthetic session. V6 implements the last two without changing the first two.

The residual/shrinkage and clustered-resampling ideas are standard. BattleMind's
contribution is the explicit permitted-evidence boundary, conservative proxy,
immutable summary, identity routing outside features, shared scorer, matched-snapshot
shadow evaluation, chronological audit and preserved failed experiment. It does not
claim a novel learning algorithm, exact battle simulation or individual human modeling.

1. **Does memory update and affect later predictions? Yes.** Public-only evidence,
   actual cross-encounter updates and changed later predictions/choices are verified.
2. **Does individual history improve probability estimates? In this partial
   development sample, aggregate Brier/log loss improved; final improvement is
   unverified.** Log loss regressed against switch-active versus no memory.
3. **Does it change decisions and improve play? Decisions changed; battle benefit
   remains inconclusive.** The final schedule did not run, and six shadow choice
   differences cannot explain or establish counterfactual wins.
4. **What limits the claim?** A biased public proxy, missed/unannounced actions,
   correlated repeated encounters, one incomplete group, two fixed synthetic bots,
   four restricted teams, coarse action scores and insufficient per-cell wall budget.
   No unseen-opponent, held-out-team, human, or within-battle-learning claim follows.

The single next milestone is **V7 — consolidated, reproducible benchmarks and a
clear demonstration of the supported V1–V6 claims**. It must retain V6's incomplete
acceptance status. Completing a replacement V6 final experiment or changing its
budget requires a new request; no additional collection or V7 work was performed.
