# Status — V4 verified; better probabilities, battle benefit inconclusive

Verified 2026-09-09. **Supervised training and frozen inference work. Logistic
regression improved probability estimates over both fair baselines on the declared
fixed mixture. It did not establish a battle-result improvement.** Original V3
findings are preserved verbatim in [MILESTONE3.md](MILESTONE3.md), with earlier
evidence in [MILESTONE1.md](MILESTONE1.md) and [MILESTONE2.md](MILESTONE2.md).

## Implemented changes

- `supervised.py`: compact observer-only features, train-fitted immutable
  preprocessing, safe JSON logistic coefficients and frozen inference.
- `supervised_data.py`: V4 features layered over the existing audited observer
  join, with whole-battle partitions, hashes, exclusions and offline grouping.
- `supervised_training.py`: deterministic L2 logistic regression with tested
  gradient/Hessian, bounded Newton optimization and three-strength validation
  selection. Fair constant/count baselines use exactly the same training rows.
- `supervised_report.py`: Brier/log loss, supported calibration bins, target and
  observer groups, exclusions/coverage, paired whole-battle bootstrap differences.
- `anticipation.py`: separate `switch-logistic` source using the same existing
  candidate stay/switch scoring; all three probabilities and alternate choices are
  logged and audited against the frozen bundle.
- `opponents.py`: fixed V2 utility variants requiring switch gain >40 or >0,
  retaining the two-turn cooldown. Original V2 threshold 80 and all four teams are
  unchanged by content hash. No strong-agent implementation was imported.
- CLI commands, [pre-collection specification](V4-EXPERIMENT.md), bounded
  `scripts/experiment-v4.py`, tests, schema and interview explanations.

Package is 0.4.0. Python 3.14.3 / Node 24.19.0 / poke-env 0.16.1 / official
Showdown `2f5b273925862ac242b419086c1e7a8868b51da1` are unchanged. NumPy 2.5.2,
already locked, is now declared in the optional training extra. No new package
download was needed for ML. No external replay ingestion, self-play learning,
individual profiles, frontend, hosted models, public ladder or GPU.

## Development and frozen model

Actual collection: **144/144 completed**, 78 observer wins, 64 losses, 2 draws;
zero invalid actions, failures, caps, timeouts or warnings. Two fixed observers
(V2 and original V3 constant) faced three fixed target opponents, with all team
assignments and sides balanced. Target switch rates were 8.05% (V2), 14.26%
(moderate) and 21.89% (active). No M2/V3 recorded examples were reused for fitting;
V3's artifact defined one fixed observer only.

| Partition | Battles | Eligible primary examples | Switches | Battles with switches |
|---|---:|---:|---:|---:|
| Train | 108 | 2,615 | 388 | 107 |
| Validation | 36 | 938 | 140 | 35 |

Every turn, both perspectives and exclusions inherit the run-hash-plus-match
partition. Primary selection uses runner-b targets only, entirely offline. The
audit confirmed zero overlap between all 144 development and 288 final battles.
Fitting on the final evaluation dataset was explicitly rejected.

Selected lambda: **0.01** from the declared 0.01/0.1/1.0 search. Validation log
losses were respectively 0.253196 / 0.303456 / 0.388524. It converged in 6 Newton
steps, gradient infinity norm 9.06e-9. There was no validation refit, class
reweighting, resampling, recalibration or final-result tuning. Frozen global
frequency is 389/2617 = 0.1486435. The logistic model has 26 encoded coefficients
and an intercept; the complete provenance JSON is 39,656 bytes.

Validation Brier/log loss: constant 0.126977/0.421414, conditional
0.120732/0.397954, logistic 0.081312/0.253196. This is model-selection evidence,
separate from fresh final results.

## Fresh final probability results

Primary population: **7,377 eligible opponent decisions, 1,087 switches (14.735%),
288 battles, 279 battles with a switch**, pooled over the declared fixed mixture.
Both baselines and logistic were evaluated on exactly these same examples.

| Frozen probability source | Brier ↓ | Log loss ↓ |
|---|---:|---:|
| V4 constant frequency | 0.125640 | 0.418091 |
| V4 conditional counts | 0.118878 | 0.392674 |
| V4 logistic regression | **0.078675** | **0.246724** |

Paired descriptive 95% intervals from 1,000 **whole-battle** bootstrap resamples:

| Logistic minus reference | Brier difference [interval] | Log-loss difference [interval] |
|---|---|---|
| Constant | -0.046964 [-0.051960, -0.042271] | -0.171367 [-0.185147, -0.158430] |
| Conditional | -0.040203 [-0.044777, -0.035766] | -0.145950 [-0.160018, -0.132324] |

Negative differences favor logistic. Intervals retain correlated turns and
describe this fixed schedule, not held-out teams, unseen opponent rules or humans.

| Target group | Examples / switches | Constant Brier | Counts Brier | Logistic Brier |
|---|---:|---:|---:|---:|
| V2 | 2,191 / 211 | 0.089768 | 0.082622 | 0.073590 |
| Moderate | 2,453 / 346 | 0.121214 | 0.115375 | 0.075965 |
| Active | 2,733 / 530 | 0.158369 | 0.151088 | 0.085184 |

All three target groups and four observer groups had lower logistic Brier and log
loss. Full group metrics and calibration for every predictor are retained in the
JSON report. Logistic calibration is still imperfect:

| Predicted bin | Support | Mean prediction | Observed switch fraction |
|---|---:|---:|---:|
| [0, .2) | 5,270 | .0489 | .0309 |
| [.2, .4) | 1,236 | .2989 | .3010 |
| [.4, .6) | 587 | .4845 | .5400 |
| [.6, .8) | 198 | .6751 | .7828 |
| [.8, 1] | 86 | .8378 | .9302 |

The largest-magnitude standardized coefficient is recent public foe switch
(-1.7422), consistent with these fixed opponents' cooldown. This helps explain
why prediction is easier in this mixture; it does not show general opponent
understanding or establish a history-only benefit without an ablation.

## Battle results and decision influence

All **288/288 final games completed**. Each table cell is wins/losses/draws from
24 games, with complete team/side balance. No cleanup outcomes became wins.

| Observer policy | vs V2 | vs moderate | vs active | Total W/L/D | Completed win rate [Wilson 95%] |
|---|---|---|---|---|---|
| Constant | 11/13/0 | 13/11/0 | 16/8/0 | 40/32/0 | 40/72 = 55.56% [44.09, 66.46] |
| Conditional | 12/12/0 | 13/10/1 | 18/5/1 | 43/27/2 | 43/72 = 59.72% [48.18, 70.28] |
| Logistic | 10/14/0 | 11/12/1 | 19/5/0 | 40/31/1 | 40/72 = 55.56% [44.09, 66.46] |
| V2 reference | 12/10/2 | 12/11/1 | 18/5/1 | 42/26/4 | 42/72 = 58.33% [46.81, 69.01] |

Simulator RNG was not controlled. These restricted-pool results establish **no
battle benefit**: logistic tied constant wins, had fewer than counts and V2, and
varied by opponent. Better probability estimates did not reliably improve this
approximate scoring rule. There was no rerun or retuning.

Across 7,772 prediction-policy decisions, logistic's same-snapshot alternative
differed from constant 128 times and conditional 138 times. On logistic's own
2,684 decisions, it differed 46 times from constant, 57 from counts and 61 from V2.
These are choices, not counterfactual wins. A traceable example is
`runs/v4-acceptance/logistic-vs-gen1-heuristic/decisions.jsonl`, `m0:a:r6`, turn 3:
constant p=.14864 gives Thunderbolt utility 175.879; logistic p=.49046 lowers it
to 143.406, below Soft-Boiled's unchanged 148.257, so healing is selected. Both
choices are legal on the same snapshot. This does not prove healing was best.

## Label coverage, exclusions and resources

All 9,599 development and 20,620 final attempts matched committed engine inputs
(**100% commitment coverage** in these runs). Not every attempt is a training
example. Final records exclude 2,430 forced replacements, 1,379 engine actions and
1,987 requests without meaningful move/switch choice, leaving 14,824 eligible
joined examples across both directions. Primary runner-b eligibility is
7,377/10,357 attempts (71.23%); exclusions are 1,262 forced, 619 engine and 1,099
no-choice. Unknown commitments/eligibility, mismatches and missing joins were zero
here; conservative exclusion paths remain tested and unchanged.

Across **432 reported games**: zero invalid actions, caps, timeouts, crashes,
cancellations, not-started games, server crash reports or wrapper warnings.
Original warning handling remains active. Development took 62.98s, final 139.40s,
**202.37s combined** including run setup/audits/data reports, below the
600-game/900-second ceiling. Final checksum/verification and separate CLI commands
are additional small overhead, not represented as battle time. Training took
0.303s wall / 0.328s CPU and 80.75 MiB RSS at completion.

Sampled Python peak RSS was 173.23 MiB; managed server tree peak was 433.68 MiB.
Runner CPU totals were 48.44s Python and 58.03s server (last samples); these exclude
offline phases and are not exact lifetime CPU/peak measurements. No listener was
left on port 8000. Services used 127.0.0.1 and concurrency 1.

## Tests, exact commands and artifacts

**84 unit tests passed** (0.46s); **9 integration tests passed** (49.94s). Integration
requested 25 games: 23 completed, one deliberate cap and one deliberate timeout,
neither counted as a win. Official-engine probe scenarios are tests, not
evaluation games. Integration data is excluded from reported development/final
datasets. `pip check` and `git diff --check` passed.

Commands actually run from the project root in PowerShell (experiment console
logs are retained under `.local/`):

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration
.\.venv\Scripts\python.exe scripts/experiment-v4.py collect --output runs/v4-development --predictor models/v3-counts.json --budget runs/v4-budget.json
.\.venv\Scripts\python.exe -m battlemind supervised-train --dataset runs/v4-development/development-data --output models/v4-supervised.json
.\.venv\Scripts\python.exe -m battlemind supervised-evaluate --dataset runs/v4-development/development-data --predictor models/v4-supervised.json --partition development_check --output runs/v4-validation-quality
.\.venv\Scripts\python.exe scripts/experiment-v4.py final --output runs/v4-acceptance --predictor models/v4-supervised.json --budget runs/v4-budget.json
.\.venv\Scripts\python.exe -m battlemind report --run runs/v4-acceptance/logistic-vs-switch-moderate --audit
.\.venv\Scripts\python.exe -m battlemind supervised-dataset --runs runs/integration-v4-73e081637f/recorded --output datasets/v4-cli-smoke
.\.venv\Scripts\python.exe .local/verify-v4.py
git -c core.safecrlf=false diff --check
```

Load `env.ps1` in each new shell before server commands; it selects Node 24.19.0
over the default 24.20.0. Existing output directories are intentionally rejected.
Do not repeat the final benchmark to pursue a better outcome.

Actual retained artifacts, relative to this workspace:

- `runs/v4-development/`: six runs, freeze, audited dataset and summary;
  `artifact-hashes.json` verifies **668 files**.
- `models/v4-supervised.json`: SHA-256
  `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`.
- `runs/v4-validation-quality/`: selection-partition probability report.
- `runs/v4-acceptance/`: final freeze, twelve runs, evaluation dataset,
  `probability-quality/summary.json`, predictions, summary and **1,330** verified
  artifact hashes. Source/model hashes still match both freezes.
- `runs/v4-budget.json`: 432 reserved games, both phases finished; no retry.
- `runs/v4-verification.json`: hash checks, zero split overlap, final-training
  rejection, preserved V2/team/V3 hashes and listener check.
- `runs/integration-v4-73e081637f/`: real record → training → inference → audit test;
  `datasets/v4-cli-smoke/` verifies the dataset CLI on those test records.
- `.local/v4-collection-console.log`, `.local/v4-final-console.log`,
  `.local/v4-validation-console.json`, `.local/v4-final-cli-audit.json` retain CLI
  output. Generated datasets/models/runs and `.local/` remain ignored.

Original V3 model SHA-256 remains
`e46feb7dc665c046c03f4b7cb6e4072b0dafbd56c3b04625cae68537722222ef`.
V3's runs/model and unrelated uncommitted implementation were preserved. No commit,
push or deployment was made.

## Explanation and limits

One request becomes a frozen player-visible snapshot. The feature function reads
only that snapshot; the frozen logistic dot product produces a switch probability.
The shared policy weights existing stay/switch utilities, selects a legal ID,
and the adapter maps it to the current request command. Only after the match does
the separate recorder establish committed labels for future offline training.
The snapshot and mapping predate the label; no current opponent choice or private
team enters inference. [PREDICTION.md](PREDICTION.md) explains the important code
and separates original engineering work from standard statistical algorithms.

This is supervised learning from validated **local recorded battles**, not arbitrary
Showdown replay support. Data contains four teams and three related fixed rules.
History and classifier capacity were added together, so their effects are not
isolated. Live meaningful-choice eligibility remains unknown; its conditional
probability is applied under the existing approximation. Damage, switch
destinations and Gen 1 effective stats remain approximate or unknown as documented.
Calibration is imperfect; battle utility may not reward better predictions
appropriately. No competitive-strength or individual-adaptation claim.

The single recommended next milestone is **V5 — bounded self-play learning,
informed by V4's findings**. It needs a defined policy update and separate frozen
checkpoint evaluation; V4's probability gain alone does not justify scaling up.
