# V6 accounting repaired; replacement acceptance blocked by a turn cap

The two accounting defects are fixed and regression-tested. The one separately
authorized replacement **did not complete acceptance**: development finished
144/144 games, then final stopped with **251 completed, one capped and 324 never
requested games** out of its 576-game allocation. No retry, resumed allocation,
scientific tuning or extra collection was performed.

The first attempt remains unchanged: **96 completed development games; development
budget exhausted; zero final games**. Its full incomplete status is preserved in
[MILESTONE6-FIRST-ATTEMPT.md](MILESTONE6-FIRST-ATTEMPT.md), SHA-256
`3f3a1a3057578a7d3ad3aa7aa93fe9a7cfca9950842404a106e6d65f52212163`.
All V1–V5 evidence remains intact, including [MILESTONE5.md](MILESTONE5.md).
The workspace was clean at inspection, HEAD `e64f26e` (V6). No commit, push,
deployment, dependency change, retraining, frontend or V7 implementation occurred.

## Repairs and what stayed frozen

`adaptation_ledger.py` now records a stopped phase once and clears its active clock.
Repeated finish/finalize calls do not extend it. Setup, collection-stop, reporting/
audit, overhead and total durations use distinct monotonic boundaries. Read-only
reporting cannot write or advance a ledger. A separate post-run verification records
its own bounded duration without changing the closed ledger.

`v6-budget-2` / `v6-report-2` separate planned capacity, irrevocable cell reservations,
runner-dispatched requests, recorded/started/completed games and never-started slots.
An untouched final arm has zero actual requests and zero missing requested records;
planned slots are not losses. Partial dispatched records retain unknown start status.
Experiment failure is distinct from completed-game outcomes. Schema details and
the unchanged old-format limitations are in [SCHEMA.md](SCHEMA.md).

Only four production files changed: `adaptation_ledger.py`, `adaptation_report.py`,
`adaptation_experiment.py` and `cli.py`. The original runner/server lifecycle, hooks,
preflight checks, warning handling, public-memory extraction and private recorder
are unchanged. No shared-server reuse, caching or relaxed validation was introduced.
The report also enforces the original requirement for **complete** independent
groups before producing group-bootstrap intervals.

All scientific components stayed frozen: V4 predictor/preprocessing/features, selected
V5 vector, proxy filters, shrinkage/clipping/support, three arms, targets, four teams,
seeds/order/sides, resets and metric/eligibility definitions. The replacement validator
compares scientific configuration and original source hashes. The schedule and metric
functions also pass source comparisons. Read-only replay under repaired accounting
reproduced **all 3,643 original observer decisions, candidate scores, probabilities
and 96 memory updates exactly**, recorded in `runs/v6-repair-equivalence.json`.

Both required originals passed compatibility/hash checks before and after work:

| Artifact | SHA-256 |
|---|---|
| `models/v4-supervised.json` | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| `runs/v5-acceptance/selected.json` | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |

Copies in the replacement and each cell retain these hashes. No source-only clone
can recreate these historical ignored inputs without retaining them and their inputs;
[ADAPTATION.md](ADAPTATION.md) retains regeneration commands and limitations.
Pinned Python 3.14.3, Node 24.19.0, poke-env 0.16.1, NumPy 2.5.2 and Showdown
`2f5b273925862ac242b419086c1e7a8868b51da1` remain unchanged. Services stayed on
127.0.0.1 with concurrency 1. No hooks were modified in this repair.

## Replacement specification, feasibility and actual accounting

[V6-ACCEPTANCE-REPAIR.md](V6-ACCEPTANCE-REPAIR.md) and
`configs/v6-acceptance-repair.json` were written and frozen before collection.
Their SHA-256 hashes are respectively
`eb88547f8224556616fdf1fa485a457ee9f998c21c3320717769dd627fabb511` and
`cc6b43e44503cb57fbb3e8e6b32acec18d306c0507cd6429bdae638aadb46720`.
The original specification and original `runs/v6-acceptance` files were not edited.

Original timing projected about 248.60 seconds for development and 994.39 for final,
including repeated startup/shutdown, memory/recording, preflight and audit/hash work.
That explained why the first 180-second development allocation failed. The replacement
used the authorized 420/1,080-second phase allocations and 300-second overhead reserve,
without changing infrastructure. Development actually finished faster than projected;
**the replacement stopped on a battle cap, not on wall exhaustion**.

| Phase | Planned | Reserved / requested | Completed | Capped | Never requested | Actual phase wall / allocation |
|---|---:|---:|---:|---:|---:|---:|
| Development | 144 | 144 / 144 | 144 | 0 | 0 | 230.213s / 420s |
| Final | 576 | 252 / 252 | 251 | 1 | 324 | 428.446s / 1,080s |
| **Total** | **720** | **396 / 396** | **395** | **1** | **324** | **658.659s of phase work** |

All 396 dispatched games have records and started. There are zero reserved-but-
undispatched cells, missing requested records or unknown starts. The 324 untouched
slots are explicitly never requested/never started, not missing results or losses.

Collection stopped at **658.686s**, with **.027557s setup**. Initial reporting,
replay and bulk hashing took **74.018813s**, giving **732.705108s** measured experiment
time. Subsequent read-only CLI, preservation, hash and supplemental replay verification
took **136.016413s**. Combined measured work: **868.721521s**, with total overhead/
verification **210.062782s of 300s**, within the 1,800-second ceiling. These sum
monotonic work durations; intervening narration/document writing and tiny final
ledger/summary/manifest writes are outside those samples. Repeated reporting left
phase clocks and finalized ledger bytes unchanged.

## Exact stop and remaining blocker

The blocking cell is
`runs/v6-acceptance-repair/final/g1/none-p4-vs-switch-active`, **match 2** (zero-based),
team indices a=1/b=3. The battle log records `truncated`, `winner=null`,
`Turn cap 300 reached`, with boundary turn 301. Last policy choices were at turn 300.
The cleanup terminal messages say a lost/b won; **neither becomes a genuine win or
draw in the experiment**. The other three games in that already requested cell
completed; no later cell was requested.

The public sequence repeatedly announces that both active Pokémon cannot move
because they are frozen. Observer a has only its frozen Exeggutor left. The fixed
switch-active opponent stays with frozen Zapdos despite a healthy, legal Victreebel
replacement. In its own saved snapshot the legal choices are `engine:fight` and
`switch:3`. Its unchanged heuristic scores them **0** and **-1000**, respectively,
because the approximate switch gain is **-55.51**, below its fixed zero threshold.
It therefore keeps choosing the engine action. This exposes a frozen heuristic
limitation in evaluating a frozen active Pokémon, not an invalid action, wrapper
failure or license to change the opponent after observing the result.

The capped encounter admitted zero memory proxies, was update-ineligible and retained
identical pre/post memory digests. Its evidence is preserved separately; none of its
observed prefix was used to update memory. The next scheduled encounter within the
already dispatched cell used the same pre-cap summary. No later cell consumed the
incomplete comparison. Full diagnostic evidence is in `runs/v6-repair-cap-review.json`.

Final group 0 completed 144/144 games. Group 1 requested 108 and completed 107,
with the cap; its remaining 36 slots and all 288 slots for groups 2/3 were never
requested. Only **one complete independent final group** exists. The predeclared
four-group acceptance cannot pass. Both the original and replacement allocations
are consumed and non-resumable; no second replacement is authorized.

## Partial final probability evidence — not a completed confirmation

The experiment report includes 62 fully completed final cells (248 games) in the
probability sample. The entire last incomplete four-game cell is flagged and excluded
from these metrics, including its three completed games. Those completed outcomes
remain visible in battle accounting. Supplemental audits verify all four retained
records without adding them back to the frozen comparison or changing the report.

All three shadow probabilities are evaluated on the **same 5,964 eligible observer
snapshots**, containing **670 switches and 5,294 moves**. They use each generating
observer's own earlier public evidence; original-attempt and replacement-development
rows are excluded from these final metrics.

| Probability source | Brier | Log loss |
|---|---:|---:|
| No memory | .083232 | .263770 |
| Pooled | .083774 | .268022 |
| Individual | **.073545** | **.254239** |

Individual-minus-none differences: Brier **-.009687**, log loss **-.009530**.
Individual-minus-pooled: **-.010229**, **-.013783**. These are partial-sample
descriptive differences; the incomplete four-group schedule prevents a final claim.

| Generating live arm (eligible examples) | Brier: none / pooled / individual |
|---|---|
| No memory (1,975) | .085055 / .085708 / .075245 |
| Pooled (1,791) | .085244 / .086124 / .073961 |
| Individual (2,198) | .079954 / .080121 / .071677 |

| Target (examples / switches) | Brier: none / pooled / individual | Log loss: none / pooled / individual |
|---|---|---|
| MaxBasePower (1,870 / 0) | .071988 / .066439 / .044469 | .246362 / .232851 / .170462 |
| switch-active (4,094 / 670) | .088368 / .091692 / .086825 | .271721 / .284087 / .292506 |

Individual history improves aggregate losses in the recorded sample, but **worsens
switch-active log loss versus both no memory and pooled history**. The single
additive residual correction is a coarse adjustment, not uniformly better calibration.
There was no tuning on this finding.

Cold-start individual and no-memory predictions are identical on 253 examples
(Brier .115261). Pooled cold-start Brier is .124266 because it may already hold
the other target's evidence. On 5,711 later examples, none/pooled/individual Brier
is .081813/.081980/.071697. Individual sparse-history fallback covers 679 examples;
5,285 have supported adjustment. Complete arm-by-target, group, fallback and
calibration support is in `summary.json` and `runs/v6-repair-analysis.json`.

Individual calibration bins illustrate remaining error:

| Probability bin | Support | Mean prediction | Observed switch fraction |
|---|---:|---:|---:|
| [0,.2) | 4,359 | .082595 | .022941 |
| [.2,.4) | 1,102 | .279161 | .254083 |
| [.4,.6) | 358 | .479035 | .519553 |
| [.6,.8) | 115 | .674839 | .652174 |
| [.8,1] | 30 | .885246 | .966667 |

The planned 1,000-resample group bootstrap is unavailable: four complete independent
groups are required and only one exists. No turn-level or independent-battle interval
is substituted. In probability interval objects, `groups: 0` means no group samples
were supplied below that four-group gate; it does not mean no final games ran.
Four groups would itself provide limited uncertainty resolution; this partial result
supports still less inference.

## Partial live outcomes, decisions and evidence coverage

| Live arm | Requested / completed | MaxBasePower W/L/D | switch-active W/L/D | Overall W/L/D |
|---|---:|---:|---:|---:|
| No memory | 84 / 83 | 38/2/0 (40) | 32/11/0 (43), plus one cap | **70/13/0** |
| Pooled | 80 / 80 | 39/1/0 (40) | 29/11/0 (40) | **68/12/0** |
| Individual | 88 / 88 | 43/1/0 (44) | 35/9/0 (44) | **78/10/0** |

Completed win rates are 84.34%, 85.00% and 88.64%, but schedules/exposure are
unequal after the stop. In the sole complete group, W/L/D is 40/8/0, 42/6/0 and
46/2/0 (48 each). Neither table establishes a battle improvement. Engine randomness
is not matched, and changed choices do not establish counterfactual wins.

On 8,915 observer snapshots from eligible complete final cells, individual changed
probabilities relative to base on 7,651, but changed choices on only **14 (.157%)**.
Individual versus pooled differed on 15, pooled versus none on three. The individual/
none differences occur on five no-memory, seven pooled and two individual live-arm
snapshots. The scorer often keeps the same action despite changed probabilities.

The complete final cells contain 248 encounters, of which 232 supplied minimum
memory support. **3,364 proxies** were admitted, including 459 switches, with zero
disagreements against eligible private labels in this sample. Admission covers only
**56.41%** of eligible snapshots and **68.51%** of eligible switches; 211 eligible
switches were skipped. MaxBasePower admission is 922/1,870; switch-active 2,442/4,094.
Agreement on this selected proxy subset does not establish unbiased coverage.

Final public skips: lock/copy/charge context 1,528; no public alternative 860;
opponent unknown/engine status 829; observer engine/uncertain request 798; observer
forced request 789; ambiguous/engine event 468; missing announcement 279.
Private probability exclusions: 1,188 forced replacements, 1,099 engine actions and
1,063 requests without a meaningful choice. These counts exclude the flagged cell.
Its public/private evidence remains available in supplemental verification.

## Audits, failures and resources

Across all 396 requested games: **29,226/29,226** attempts have verified intended
commitments, zero unknown commitments/eligibility and 20,354 paired eligible targets
across both perspectives. No invalid actions, timeouts, crashes, cancellations,
missing requested rows or unexpected warnings occurred. There is **one cap**,
one experiment-level stop and **two recognized Wrap/Clamp warnings**, retained intact.

The frozen experiment report replays 13,869 observer decisions/392 encounters and
98 complete private cell audits. It deliberately has `audit.ok=false` with the last
incomplete cell flagged, so the CLI returns **1**. That is not disguised as passed
acceptance. Read-only supplemental replay reconstructs **all 14,308 observer decisions
and all 396 encounters**, and the flagged cell's private audit verifies all 882
labels/decisions. Its cap remains ineligible. Integrity verification can pass while
the declared performance experiment remains incomplete.

All **4,364 replacement artifact hashes** match, with complete manifest coverage.
There is zero overlap between original/replacement or replacement development/final
battle identities. Two final reset groups actually started; groups 2/3 never started.
All completed cells preserve their four-game team/side schedules; the full final
schedule did not complete. No server listener remains on port 8000.

Historical checks also confirm 667 V3 acceptance, 668 V4 development, 1,330 V4 final,
3,917 V5 acceptance and 1,064 original V6 files with zero mismatches. Full historical
source-freeze checks still require their original code; they were not weakened.
The original V6 full audit passed before source edits, and its permitted-data replay
passed after accounting edits.

Summed per-run Python CPU is **106.328s**; managed-server last CPU samples sum to
**263.203s**. Sampled maximum RSS is **159.137 MiB Python / 432.164 MiB server**.
These are 0.1-second per-run samples, not exact lifetime peaks or CPU accounting for
all later offline verification. Phase/overhead wall measurements are reported above.

## Tests, commands and artifact paths

**133 unit tests passed** in .81s; focused adaptation/accounting tests were 27/27.
**10 selected integration tests passed** in 80.83s. The separate test budget was
**37 games: 35 completed, one deliberate timeout, one deliberate cap**. No test
outcome is part of either acceptance attempt. The V4 new-training and V5 self-play
integration scenarios were excluded; no historical model was retrained.

The new complete-path test is
`runs/integration-v6-repair-f54dd39480/experiment`: 12/12 games through development
and two fresh test-only final groups, completed in 20.564312s including initial
reporting. It checked resets, chronological updates, complete report/hash output,
read-only timing stability and refusal to resume. Its reduced schedule is explicitly
test-only, not a successful replacement of the 720-game experiment.

Exact main commands run:

```powershell
. .\scripts\env.ps1
# Before source edits; audit passed for the original recorded partial data (exit 1):
.\.venv\Scripts\python.exe -m battlemind adaptation-report --experiment runs/v6-acceptance --audit > .local/v6-repair-original-audit.json
.\.venv\Scripts\python.exe -m pytest -q tests/test_adaptation.py tests/test_adaptation_accounting.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json > .local/v6-repair-doctor.json
.\.venv\Scripts\python.exe -m pytest -q -m integration -k 'not v4_real_record_training and not v5_real_selfplay' > .local/v6-repair-integration-console.log 2>&1
.\.venv\Scripts\python.exe .local/v6-repair-equivalence.py > .local/v6-repair-equivalence-console.json
# The single authorized replacement, now consumed (exit 1):
.\.venv\Scripts\python.exe -u -m battlemind adaptation-run --specification repair --output runs/v6-acceptance-repair > .local/v6-acceptance-repair-console.log 2>&1
.\.venv\Scripts\python.exe .local/verify-v6-acceptance-repair.py > .local/v6-repair-verification-console.json
.\.venv\Scripts\python.exe .local/v6-repair-tables.py > .local/v6-repair-tables.json
git -c core.safecrlf=false -c core.autocrlf=false diff --check
```

The verification script actually invoked the read-only command
`python -m battlemind adaptation-report --experiment runs/v6-acceptance-repair --audit`,
saving `.local/v6-repair-cli-audit.json`; exit 1 preserves incomplete status.
All verification/analysis scripts collect zero games and leave frozen outputs intact.

Artifacts:

- `runs/v6-acceptance-repair/`: frozen copies/spec/source/config, ledger, 99 cells,
  final gate, public exports, separate journals, labels, shadow reports and hashes.
- `runs/v6-repair-equivalence.json`: identical original decisions/memory after repair.
- `runs/v6-repair-verification.json`: timings, preservation, full hashes, partitions,
  test counts, cleanup and supplemental audit of the capped cell.
- `runs/v6-repair-analysis.json`: partial final group/target/arm tables and choice effects.
- `runs/v6-repair-cap-review.json`: the exact capped battle, legal actions/scores and
  unchanged memory digest. No cap is relabeled as a draw or win.

Replacement artifact-manifest SHA-256:
`4fa8881c98df904de5590633e14ad7c96e8ed912d05e5bca0a99bad19a0a1c63`.
Equivalence SHA-256:
`380f380b6d2bc9bb35ed3565ab82346debce4f7839ce59adf94212b62edc01c8`.
Verification SHA-256:
`858244db58c8a3f5e576cea62dca2af81a0d85a395360844a4b41c688a2c1f54`.

## Conclusions and remaining blocker

1. **Accounting defects fixed and tested:** yes. Phase durations stop once;
   planned/reserved/requested/started/completed counts remain distinct.
2. **Replacement completed its declared schedules:** no. Development passed, but
   final has one capped game and 324 unrequested slots; only one full final group.
3. **Individual memory improved final estimates:** lower aggregate losses in the
   partial final sample, but worse switch-active log loss and no completed four-group
   confirmation. General adaptation benefit is not established.
4. **Battle benefit:** inconclusive. Recorded individual wins are higher, but the
   schedule stopped unbalanced and group-level uncertainty is unavailable.

The exact remaining blocker is the frozen switch-active heuristic's refusal to take
a legal healthy switch in the observed frozen-active state, causing the unchanged
300-turn cap and an ineligible comparison cell. Changing that opponent, the cap or
completion rules would require a separately authorized scientific decision. Nothing
was tuned after collection, and no second replacement or V7 work was performed.
