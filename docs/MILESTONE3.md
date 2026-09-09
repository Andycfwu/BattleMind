# Status — V3 verified, benefit not established

Verified on 2026-09-08. **V3 works technically:** frozen count-based opponent prediction influences a separate action-scoring policy, with audited observer-only features, legal choices, logs and reproducible evaluation. **Conditional counts did not improve probability estimates, and a win-rate benefit was not established.** No trained classifier, external replay ingestion, self-play learning, individual-opponent adaptation, frontend or hosted service was added.

Historical evidence is preserved in [MILESTONE1.md](MILESTONE1.md) and [MILESTONE2.md](MILESTONE2.md). The owner's version roadmap is now V1 legal matches, V2 basic strategy, V3 opponent prediction, V4 replay training, V5 self-play learning, V6 individual adaptation, V7 consolidated benchmarks. Each version is benchmarked as it is developed.

## What changed

- Added audited dataset construction with run identity plus match identity, whole-battle partitions, source/snapshot hashes, class balance and explicit exclusion records.
- Added a constant switch-frequency baseline and a conditional-count predictor with three visible context categories, smoothing and sparse/unseen-context fallbacks. Counts are estimated offline and frozen.
- Added `SwitchAwareAgent`, available as `switch-constant` and `switch-context`. Both variants use identical scoring; only the probability source differs. The V2 heuristic implementation, weights and four team files remain unchanged.
- Added prediction/candidate-score logs, same-snapshot alternate choices, deterministic prediction audits, probability evaluation and a bounded benchmark driver. Updated package version to 0.3.0; no dependencies were added.

[README.md](../README.md) has runnable instructions. [PREDICTION.md](PREDICTION.md) explains the design and code; [SCHEMA.md](SCHEMA.md) describes the information boundary.

## Data, labels and frozen counts

The two reported M2 comparisons supplied 48 development battles and 2,427 decision/label records. Of these, 2,420 commitments were verified and 7 were unknown. Eligibility and observer alignment yielded 1,775 binary examples: 282 switches and 1,493 moves. The 652 exclusions remain recorded: 337 forced replacements, 153 engine actions, 151 cases without a meaningful choice, 4 uncertain eligibility cases and 7 ambiguous commitments.

| Partition | Battles with examples | Examples | Switch / move | Battles with switches |
|---|---:|---:|---:|---:|
| Development fit | 36 | 1,318 | 213 / 1,105 | 32 |
| Development check | 12 | 457 | 69 / 388 | 11 |

Splitting uses a seeded hash of whole battle identity within each source run, with 75% for estimation. Both perspectives and all turns stay together. The already reported M2 development-check games are **not an untouched final test set**.

The frozen overall frequency is `(213 + 1)/(1318 + 2) = 0.1621212`. Thirteen of 36 possible visible contexts appeared. Conditional counts shrink toward this frequency with prior strength 12; fewer than five examples trigger the global fallback. These are empirical estimates with handwritten features/rules, not a trained classifier or reward-based learning. The available 36 fitting battles and 213 switches support a small count experiment; they do not establish broad context, team or opponent coverage.

Development artifacts:

- [Dataset manifest and full split](../datasets/v3-development/manifest.json), [examples](../datasets/v3-development/examples.jsonl), [exclusions](../datasets/v3-development/exclusions.jsonl): about 1.16 MB together.
- [Frozen count artifact](../models/v3-counts.json): 13,677 bytes; SHA-256 `e46feb7dc665c046c03f4b7cb6e4072b0dafbd56c3b04625cae68537722222ef`.
- [Development probability report](../runs/v3-development-quality/summary.json).

## Probability quality: conditional counts were worse

The primary fresh evaluation was declared before the benchmark: predict the actions of random and MaxBasePower opponents, using the other player's earlier snapshot. The full dataset retains both perspectives; choosing target policy names is an offline report filter, never a prediction feature.

| Evaluation | Examples / switches | Constant Brier | Conditional Brier | Constant log loss | Conditional log loss |
|---|---:|---:|---:|---:|---:|
| Reported-M2 development check | 457 / 69 | 0.128312 | 0.130282 | 0.424879 | 0.430990 |
| Fresh reference-opponent targets | 2,576 / 665 | 0.200732 | 0.204089 | 0.600904 | 0.619197 |

Lower is better. On the fresh set, conditional-minus-constant differences were +0.003358 Brier and +0.018292 log loss. Descriptive 95% paired whole-battle bootstrap intervals were [0.001055, 0.005532] and [0.009644, 0.027430], respectively. These describe this restricted schedule, not human opponents or all teams.

The fresh primary set spans 144 separate battles; all 665 positive examples occur in the 72 random-opponent games. Random switched in 665/1,513 eligible examples (43.95%); MaxBasePower switched in 0/1,063. Conditional Brier was worse within both groups too: 0.325038 versus 0.323295 for random, and 0.031939 versus 0.026283 for MaxBasePower. This sharp behavior difference and the fitting mixture's 16.16% switch rate limit a single global/context model; no identity-based shortcut was added to hide the limitation.

Calibration also exposes the problem. Constant prediction was 16.21% against an observed 25.82% overall switch rate. Conditional predictions in the [0, 0.2) bin averaged 15.38%, but observed switches were 26.56% (2,093 examples). The [0.2, 0.4) bin averaged 23.04% against 21.98% observed (464 examples); the [0.4, 0.6) bin had only 19 examples. Two fresh contexts used the unseen-context fallback; 2,574 used context counts. Full bins and policy-specific reports are saved.

The complete fresh dataset contains 5,709 eligible joined examples, including both sides, and preserves 2,048 exclusions: 1,003 forced replacements, 578 without meaningful choice, 442 engine actions, 7 uncertain eligibility cases and 18 ambiguous commitments. The primary filter leaves 3,133 otherwise eligible examples for other target-policy groups out of its metric denominator; they remain in the dataset.

## Fresh battle comparisons

All features, counts, scoring rules and weights were frozen before this schedule. Each cell used all six unordered pairs from the four validated teams, both assignments and both challenger sides: **24 distinct schedule cells, p1/p2 twelve times each**. Configuration: root seed 20260908, concurrency 1, turn cap 300, match timeout 60 seconds, run limit 600 seconds. The fixed benchmark had an overall 600-second budget. Simulator randomness was not matched or controlled.

| Policy A | Opponent | Completed | Wins / losses / draws | Win rate and descriptive 95% Wilson interval |
|---|---|---:|---:|---|
| V2 reference | Random | 24 | 24 / 0 / 0 | 100%; 86.20–100% |
| V3 constant | Random | 24 | 24 / 0 / 0 | 100%; 86.20–100% |
| V3 conditional | Random | 24 | 24 / 0 / 0 | 100%; 86.20–100% |
| V2 reference | MaxBasePower | 24 | 23 / 1 / 0 | 95.83%; 79.76–99.26% |
| V3 constant | MaxBasePower | 24 | 22 / 2 / 0 | 91.67%; 74.15–97.68% |
| V3 conditional | MaxBasePower | 24 | 23 / 1 / 0 | 95.83%; 79.76–99.26% |

**144/144 completed. Zero invalid actions, caps, timeouts, crashes, cancellations, unstarted games or server crash reports.** Cleanup forfeits and incomplete games never count as wins. Constant versus conditional is the controlled scoring ablation; V2 is a separate scoring reference. The one-win difference against MaxBasePower is inconclusive, especially with unmatched simulator randomness and only 24 games per cell. Random is a weak opponent and all variants saturated this small comparison.

Recorded losses remain visible: V2/MaxBasePower match index 6; constant/MaxBasePower indices 4 and 13; conditional/MaxBasePower index 15. Both v1-a versus v2-c and v2-c versus v1-b assignments produced losses. No weights were adjusted or games repeated in response.

## Decision influence, warnings and resources

Across 2,448 V3 policy decisions, constant and conditional probabilities would choose different actions on **11 identical snapshots**. On the conditional policy's own 1,155 decisions, 9 choices differed from the constant alternative. Actual V3 choices differed from V2's choice on the same snapshot 28 times across all V3 cells. These comparisons prove that prediction affects selection; they do not establish which choice was better.

For example, `context-vs-random`, decision `m10:a:r31` at turn 12 chose Soft-Boiled using conditional probability 0.2601. The constant probability 0.1621 would choose Thunderbolt on exactly that snapshot. Logged stay/switch utilities explain the change; `PREDICTION.md` walks through the numbers. No opponent current choice enters that calculation.

The benchmark recorded 7,757 decisions: 7,739 verified commitments and **18 explicit unknowns**, all preserved engine-normalization mismatch suffixes. Coverage was 98.93% in `v2-vs-random`, 99.86% in `context-vs-random`, and 100% in the other four cells. Eighteen known Wrap/Clamp wrapper warning records remain in the three random comparisons (10, 2 and 6). There were zero unexpected client warnings. Unknown labels and wrapper warnings are separate counts; one does not automatically imply the other.

| Cell | Run wall seconds | Python CPU seconds | Sampled peak Python RSS, bytes | Sampled peak server RSS, bytes |
|---|---:|---:|---:|---:|
| V2 / random | 8.044 | 2.297 | 95,223,808 | 452,091,904 |
| Constant / random | 9.113 | 2.656 | 113,807,360 | 452,091,904 |
| Conditional / random | 7.250 | 2.359 | 117,825,536 | 427,192,320 |
| V2 / MaxBasePower | 6.576 | 1.641 | 123,047,936 | 457,789,440 |
| Constant / MaxBasePower | 6.755 | 1.828 | 127,942,656 | 444,047,360 |
| Conditional / MaxBasePower | 6.709 | 1.656 | 132,161,536 | 440,782,848 |

Total benchmark wall time including audits and evaluation: **59.237 seconds**. Memory is sampled at 0.1 seconds, not an exact lifetime peak; the same Python process ran the six cells, so later RSS can include retained allocations. Per-run measurements include server lifecycle but exclude preflight and post-run reporting/auditing. Server CPU samples are in each `resources.json`. No GPU or paid service was used.

## Artifacts and acceptance checks

The benchmark root [runs/v3-acceptance](../runs/v3-acceptance) contains:

- [Frozen specification/source/model hashes](../runs/v3-acceptance/freeze.json).
- [Combined actual results and audits](../runs/v3-acceptance/summary.json).
- Six complete run directories: `v2-vs-random`, `constant-vs-random`, `context-vs-random`, `v2-vs-max-base-power`, `constant-vs-max-base-power`, `context-vs-max-base-power`. Each contains decisions, terminal rows, warnings, privileged labels/evidence, a frozen predictor copy and JSON/CSV summaries.
- [Fresh evaluation dataset manifest](../runs/v3-acceptance/evaluation-dataset/manifest.json) and [probability-quality summary](../runs/v3-acceptance/probability-quality/summary.json), with per-example predictions in the same report directory.
- [SHA-256 artifact inventory](../runs/v3-acceptance/artifact-hashes.json): 667 files checked. The root is about 151 MB, including separate attempt journals and official engine evidence.

All six label/prediction audits passed. Saved decisions reproduce from their original snapshots and frozen counts. The source and model hashes match the pre-benchmark freeze; no experiment code, feature, scoring rule or count changed afterward. The V2 heuristic/team files match their existing Git versions. Documentation was updated after results.

**67 offline unit tests passed; 8 integration tests passed.** New tests cover frozen snapshot restoration, observer/target separation, real message-batch boundaries, whole-battle splits, fitting-partition isolation, overlap rejection, smoothing/fallbacks, finite probabilities, frozen repeated prediction, forced/engine legal choices, decision changes, calibration arithmetic, and an end-to-end real-game dataset/count/policy audit. The official server, label hooks and chronological observation boundary remain pinned.

An initial integration command without `scripts/env.ps1` failed seven preflight checks because system Node 24.20.0 differed from pinned 24.19.0; one official-engine probe passed. No evaluation games ran in that failed invocation. Loading the existing environment script fixed runtime selection; all eight integration cases then passed in 40.02 seconds. No version pin was relaxed. [Doctor output](../runs/v3-doctor.json) confirms Python 3.14.3, poke-env 0.16.1, Node 24.19.0, the unchanged engine commit, all four legal teams and loopback connectivity. `pip check` passed.

Latest integration evidence is under `runs/integration-v3-d75e7ea260`, `runs/integration-ce25fdc268`, `runs/integration-m2-75a48b4afc`, `runs/integration-separate-98aaa8c045`, `runs/integration-truncated-3da1ee89cf`, and `runs/integration-timeout-f4749c811d`. Deliberate limits contribute zero wins. All M1/M2 evidence remains intact.

## Commands actually executed

From this project root in PowerShell; benchmark/data/model outputs must be new for another run:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json > runs/v3-doctor.json
.\.venv\Scripts\python.exe -m battlemind dataset --runs runs/m2-comparison-random runs/m2-comparison-max-base-power --output datasets/v3-development --seed 2026
.\.venv\Scripts\python.exe -m battlemind predictor-fit --dataset datasets/v3-development --output models/v3-counts.json
.\.venv\Scripts\python.exe -m battlemind predictor-evaluate --dataset datasets/v3-development --predictor models/v3-counts.json --partition development_check --output runs/v3-development-quality
.\.venv\Scripts\python.exe scripts/benchmark-v3.py --output runs/v3-acceptance
```

A subsequent read-only Python check verified every benchmark artifact hash, unchanged source/model freeze, and actual p1/p2 schedule balance. The workspace began clean at Git commit `a5dbbe7`; this work did not commit, push or deploy.

## What remains uncertain and next version

Counts summarize a restricted mixture of weak local policies. Repeated turns are correlated, only four teams are used, some contexts have little support, and all fresh positive reference-opponent examples came from random. Private eligibility is unavailable online; applying the conditional probability to live scoring is an approximation. Equal switch-destination weights, neutral unseen types and unchanged status/switch utilities can be strategically wrong. Effective stats, trapping duration and other unsupported Gen 1 quantities remain unknown. A different action is not necessarily a better action, and unmatched simulator randomness prevents attributing a one-game difference to prediction.

**Conclusion:** prediction works technically; these conditional counts worsened probability estimates; action influence is demonstrated but better decisions or win rates are not established.

**Single next milestone: V4 — training from battle replays.** Begin with validated local battle/replay records and a small supervised model, preserving observer-only features, whole-battle splits, frozen evaluation and the V3 frequency baselines. Validate external replay assumptions before importing any later data.
