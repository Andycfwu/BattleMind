# Controlled actor-step results — 2026-09-09

**Tenfold actor steps produced substantially greater policy movement without
numerical instability, but did not establish better final performance.** The
single authorized experiment completed all **2,088 games**, with six actual
outcome-driven updates per condition. Fresh selection chose control c3 and
treatment c6. In the primary final comparison, treatment-minus-control mean
terminal return was **−0.003472**, with a descriptive 95% interval
**[−0.107726, 0.100694]**. Neither improvement nor reliable regression is established.

The [specification](ACTOR-STEP-EXPERIMENT.md) and
[configuration](../configs/actor-step.json) were frozen before collection. This
executes the proposal in [REINFORCE-AUDIT.md](REINFORCE-AUDIT.md), after the
[two loader/report repairs](REINFORCE-REPAIRS.md). It does not change those
historical documents, the original REINFORCE result, or **V6's incomplete acceptance**.
No second attempt, rate tuning, extra games, model/predictor regeneration, viewer
change, commit, push or deployment occurred.

## What changed and what remained controlled

`actor_step.py` calls the unchanged historical gradient function. It keeps actor
episode averaging `/100`, decision-mean critic averaging, norm-one gradient
clipping and norm-six/norm-three parameter projections. After clipping, it applies
`30 × multiplier` to the actor only; the critic retains rate `.1`. Multipliers
are exactly 1 and 10. Actor and critic coefficients are disjoint. This is SGD
REINFORCE with the original observer-only baseline, not a new optimizer or model.

The audit phrased the contrast as /100 versus /10. The latest request explicitly
required unchanged averaging and clipping. The frozen specification therefore
placed the multiplier **after clipping and before projection**. This is the same
effective gain while safeguards are inactive; multiplying before clipping could
differ when they activate. **Neither gradient clipping nor parameter projection
activated in any of the 12 updates.** Each treatment update had 10 times its
same-input control delta, to floating-point precision. Actual updates across
conditions are not exact multiples because their trajectories differ.

The control reproduces the original update exactly on identical data, including
the retained first 72-game historical batch and every historical metric key.
Identical-input tests show identical critic changes under multipliers 1 and 10.
Critic parameters differ in actual runs because the arms observe different states
and outcomes. No critic rate, gradient normalization, features, sampling, rewards,
episode exclusions, checkpoint selection or evaluation convention changed.

Both arms copied the same original c0 file. Each batch used 24 V2, 24 frozen V5
and 24 own archived-policy games. Archive admission was c0,c0,c0,c2,c0,c4. The
procedure was identical; learned c2/c4 opponents **differ between arms** and are
not claimed to be identical opponents. Learner/opponents remained frozen within
each batch; one update followed its completed audited rollout. No replay buffer
or final/selection trajectory entered an update.

## Actual games and outcome accounting

All games used gen1ou, the same four teams, concurrency one and services bound
to 127.0.0.1. Every 24-game cell covered six unordered team pairs × both team
assignments × both player sides. Existing 300-turn/60s-game/300s-run limits and
the 90-second reservation guard remained intact.

| Phase / arm | Planned = reserved = requested = recorded = completed | W / L / D | Phase wall seconds |
|---|---:|---:|---:|
| Training control | 432 | 148 / 272 / 12 | shared training phase below |
| Training treatment | 432 | 128 / 291 / 13 | shared training phase below |
| **Training total** | **864** | **276 / 563 / 25** | **470.710** |
| Selection, five candidates | 360 | 116 / 238 / 6 | **182.023** |
| Final initialization | 288 | 158 / 122 / 8 | shared final phase below |
| Final selected control | 288 | 167 / 119 / 2 | shared final phase below |
| Final selected treatment | 288 | 165 / 118 / 5 | shared final phase below |
| **Final total** | **864** | **490 / 359 / 15** | **395.182** |
| **Entire experiment** | **2088** | **882 / 1160 / 46** | **1047.915 summed phases** |

Caps, timeouts, crashes, cancellations, not-started records, missing records,
invalid-action incidents and never-requested slots are **zero** in every arm and
phase. No cleanup forfeit became a win. The cap-continuation implementation/rule
is preserved and unit-tested; this experiment happened to exercise no real cap.
Training outcomes below are not frozen-policy improvement estimates.

There were **1,318 recognized Wrap/Clamp annotation warnings**, retained in the
logs, and zero unexpected warnings or server crash reports. Intended-choice
coverage was **152,608/156,526 (97.50%)**; **3,918** labels remain unknown. These
labels are distinct from selected-command and executed-action evidence. Unknown
commitments exclude training episodes, not otherwise genuine final battle results.

Full terminal counts by phase, arm and opponent are in
[`report.json`](../runs/actor-step-acceptance/report.json) and
[`outcomes.csv`](../runs/actor-step-verification/outcomes.csv).

## Learning updates and exclusions

Control admitted **397/432** episodes (35 unknown-commitment exclusions, 8.10%);
treatment admitted **393/432** (39 exclusions, 9.03%). No cap or fabricated reward
entered learning, and no excluded game was retried. Archive self-play contributed
125 admitted control episodes and 122 treatment episodes. The other admitted
counts were V2 136/134 and V5 136/137, respectively.

| Arm | V2 admitted / excluded | V5 admitted / excluded | Archives admitted / excluded |
|---|---:|---:|---:|
| Control | 136 / 8 | 136 / 8 | 125 / 19 |
| Treatment | 134 / 10 | 137 / 7 | 122 / 22 |

These are unchanged whole-episode exclusions. Their concentration in archived
self-play and different usable data by condition remain selection-bias concerns.
All 864 training targets, reasons, episode lengths, arm/batch/opponent joins and
battle keys are retained in
[`training-admission.csv`](../runs/actor-step-verification/training-admission.csv)
and `batches/*-targets-*.json`. No exclusion was converted into an ordinary loss.

| Batch | Own archive | Control N | Control mean R | Control actor delta L2 | Treatment N | Treatment mean R | Treatment actor delta L2 |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | c0 | 65 | −0.24615 | .06544 | 63 | −0.44444 | .52380 |
| 2 | c0 | 66 | −0.43939 | .06631 | 64 | −0.62500 | .92075 |
| 3 | c0 | 70 | −0.22857 | .11066 | 67 | −0.38806 | .80841 |
| 4 | own c2 | 67 | −0.17910 | .06946 | 64 | −0.31250 | .74647 |
| 5 | c0 | 62 | −0.20968 | .05392 | 68 | −0.16176 | .58310 |
| 6 | own c4 | 67 | −0.40299 | .06122 | 67 | −0.31343 | .45163 |

Raw actor gradient norms were .001797–.003689 control and .001505–.003069 treatment.
All coefficients, losses and probabilities remained finite. Control c6's actor
norm is **.171804**, treatment c6's **1.569502**; selected control c3 is **.136234**.
The actual treatment-to-same-input-control delta ratios are 10 within about
4e−15. Gradients were clipped in **0/12 actor and 0/12 critic updates**; projections
also occurred in **0/12** for each parameter group.

Eligible training mean R was **−.28463 control, −.37150 treatment**. Thus this run
does not even show a higher pooled training reward for treatment. Those values
combine changing policies/pools and differ in admitted data; they are not a
controlled frozen-policy comparison. Per-update actor loss, value loss, entropy,
raw gradients, applied steps, parent/child hashes and frozen pools are in
[`updates.json`](../runs/actor-step-acceptance/updates.json).

The critic remains weak: per-batch value losses (half mean squared error) range
.47702–.49308 control and .44202–.49770 treatment. Explained variance ranges
−.000257–.000033 control and −.000978–.000484 treatment. Advantage SD ranges
.86497–.97962 control and .85237–.94070 treatment. Full advantage/value/error means,
SDs and five-number quantiles are saved for every update. The larger actor step
did not address the critic, sparse terminal credit or missing representation
details identified in the audit.

## Fresh selection and final performance

Every candidate completed its 72-game V2/V5/common-c0 selection schedule:

| Candidate | Completed mean R | Selected? |
|---|---:|---|
| Common c0 | −.527778 | No |
| Control c3 | −.291667 | **Control** |
| Control c6 | −.361111 | No |
| Treatment c3 | −.333333 | No |
| Treatment c6 | −.180556 | **Treatment** |

Completion counts tied, so mean R selected control c3 and treatment c6. The
earliest-checkpoint tie rule was available but not needed. Initialization was
eligible for both conditions using one shared selection schedule. The selected
files and final panel were hashed before any final game. Final results did not
change selection or any scientific setting.

| Fixed final opponent | Initial W/L/D | Control c3 W/L/D | Treatment c6 W/L/D | Games per arm |
|---|---:|---:|---:|---:|
| Random | 45 / 3 / 0 | 48 / 0 / 0 | 47 / 0 / 1 | 48 |
| MaxBasePower | 36 / 10 / 2 | 41 / 6 / 1 | 35 / 12 / 1 | 48 |
| V2 | 13 / 32 / 3 | 12 / 35 / 1 | 16 / 31 / 1 | 48 |
| Selected V5 | 10 / 37 / 1 | 14 / 34 / 0 | 14 / 33 / 1 | 48 |
| Historical c0 | 28 / 19 / 1 | 29 / 19 / 0 | 22 / 26 / 0 | 48 |
| Historical c6 | 26 / 21 / 1 | 23 / 25 / 0 | 31 / 16 / 1 | 48 |
| **Total** | **158 / 122 / 8** | **167 / 119 / 2** | **165 / 118 / 5** | **288** |

Win rates, with draws in the denominator but not counted as wins, are 54.86%,
57.99% and 57.29%. Completed mean R is .125000, .166667 and .163194.

| Frozen comparison | Mean R difference | Descriptive 95% interval |
|---|---:|---:|
| **Treatment − control (primary)** | **−.003472** | **[−.107726, .100694]** |
| Treatment − initialization | +.038194 | [−.083420, .166667] |
| Control − initialization | +.041667 | [−.083333, .166667] |

These are the predeclared 1,000-resample opponent-stratified four-game team/side
block intervals (72 blocks per arm; seeds 224000/224001/224002). Turns were not
resampled as independent games. Unknown-outcome sensitivity bounds collapse to
the point differences because all final games completed. Shared block indices
and policy seeds do not match engine randomness. Neither positive initialization
point estimate establishes improvement; the primary estimate is nearly zero.

Treatment's point results vary by opponent: better versus historical c6, worse
versus historical c0 and MaxBasePower, with only 48 games per matchup. Neither
target-specific benefit nor forgetting is established. All three policies still
lose most games against V2 and V5, and the simple opponents lift aggregate wins.
Random/MaxBasePower/historical c6 were reserved from new learning/selection;
these fixed policies and four teams do not establish unseen-human or
other-generation generalization. One learning seed per condition, stochastic
trajectories, different admitted data and arm-specific learned archives remain
confounders/limitations. The evidence does not establish actor step size as the
sole reason the original system failed to improve.

## Same-snapshot movement

The fixed training diagnostic set contains **5,444 learner-a snapshots** from
both first training batches. It includes excluded episodes without using their
terminal targets. Both arms' c3/c6 were evaluated on this identical set:

| Checkpoint | Mean TV from c0 | Mean KL(c0 || checkpoint), nats | Shared-draw changes |
|---|---:|---:|---:|
| Control c3 | .003308 | .00006330 | 34/5444 = .6245% |
| Control c6 | .003605 | .00006886 | 43/5444 = .7899% |
| Treatment c3 | .021983 | .00237330 | 218/5444 = 4.0044% |
| Treatment c6 | .037801 | .00654340 | 389/5444 = 7.1455% |

At the same six-update depth, treatment's mean TV movement is about **10.5×**
control's on this set. This compares distributions, not unmatched battle actions.

On the **same 30,876 final learner-a snapshots**, evaluated only descriptively
after selection/final freeze:

| Model | Mean TV from c0 | Mean KL(c0 || model) | Entropy, nats | Mean max P | Greedy changes | Shared-draw changes |
|---|---:|---:|---:|---:|---:|---:|
| Initial | 0 | 0 | 1.04661 | .53874 | 0 | 0 |
| Selected control c3 | .003450 | .00006836 | 1.04477 | .53890 | 2241 (7.26%) | 240 (.78%) |
| Selected treatment c6 | .040035 | .00709015 | .99587 | .56591 | 3493 (11.31%) | 2282 (7.39%) |

TV is half the summed absolute probability difference. KL direction above is
initial to compared model; reverse KL is also retained. Greedy changes include
2,127 exact-initial-tie changes for control and 1,224 for treatment. Treatment
therefore changes more strict preferences too. Direct treatment-versus-control
mean TV is .039571, KL(control||treatment) .00700884, and shared-draw differences
are 2,227/30,876 (7.21%). All sampled comparisons use the same stored uniform draw
and the repaired right CDF boundary. They are **not counterfactual wins**.

[`movement.json`](../runs/actor-step-acceptance/movement.json) contains quantiles,
maximum values and generating-arm/opponent breakdowns. The two distribution
JSONL files retain snapshot hashes, identities, draws, all compared probabilities
and action IDs. No final diagnostic changed a rule or started further training.

## Verification, resources and preservation

- **77 focused tests passed**, including the repaired loaders/CDF boundaries,
  original-update equivalence, actor-only scaling, clipping/projection order,
  finite-error stops, frozen pools, equal schedules, selection ties, budget
  exhaustion, cap accounting and zero-request final arms.
- Final pre-freeze offline suite: **256 passed, 14 integration tests deselected,
  7.66s**. No battle-collecting historical integration suite ran. All test-game
  counts are **zero**; retained real data supplied the extra replay checks.
- Readiness loaded 17 retained original checkpoints, original V4 and selected
  V5 through strict intended loaders and verified the retained main/repair
  manifests. Repaired inference/loader, historical optimizer and old reporting
  code stayed byte-identical to the starting workspace.
- An additional retained 24-game cell audit reproduced 845 learned decisions and
  all 1,665 commitment labels, without collecting games. Original first-batch
  control reconstruction is also an offline regression test.
- The complete experiment audit **passed in 173.495s**, replaying **105,393 learned
  decisions**, all **12 updates**, target exclusions, frozen pools, selection,
  full balanced schedules and **2,088 disjoint battle identities**. Historical
  main/smoke overlap is zero. Evaluation did not update models.
- The separate closure preserved **17,721 pre-existing files** (excluding only
  authorized README/STATUS/CLI edits), verified all 9,792 experiment files unchanged
  around repeated read-only reports, and independently checked the first learner-a
  snapshot in every final game against all three models: **864 snapshots, zero
  probability error and exact sampled choices**. Ports 8000/8765 had no listeners.

Collection stopped at **1054.204s**. In-process reporting, replay and hashing took
**209.499s**; total measured process duration was **1263.957s**, including **216.042s
overhead**. The ledger also charged a conservative 120s offline-preparation reserve
(process plus reserve: **1383.957s**). Measured preparation test/readiness/hash
durations sum to about **82.91s**, below that reserve. Separate closure took
**72.780s**, and complete supplemental content hashing took **5.377s**. Process
plus the full preparation reserve plus these verification steps is **1462.115s**,
including **414.200s charged overhead**: within 3600s overall and the protected
600s overhead allocation. Later documentation/final-file checks are recorded
separately in `final-check.json`; no phase allocation was borrowed. Interactive
implementation/reading/writing latency is not experimental compute time.

The process used **725.609s Python CPU** including updates/audits. Battle-run samples
sum to **319.562s Python CPU** and **341.188s last-sampled server CPU**, with sampled
peak RSS **363,470,848 bytes Python** and **462,565,376 bytes server**. These samples
miss exact peaks/server shutdown tails; do not add their Python CPU to the whole
process CPU. Separate closure used 29.031s CPU. Full retained experiment size is
**9,792 files / 3,627,657,760 bytes**. No dependencies, paid services or downloads
were added. All original models, reports, configurations, ledgers, V6 evidence and
V7 bundles remain unchanged and ignored generated artifacts remain ignored.

## Commands, files and hashes

Actual commands, from the project root (focused/unit runs were repeated only
after implementation changes; all collected zero games):

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_actor_step.py tests/test_reinforce_repairs.py
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration'
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -u -m battlemind actor-step-run --spec configs/actor-step.json --output runs/actor-step-acceptance *> runs/actor-step-verification/experiment-console.txt
.\.venv\Scripts\python.exe -B diagnostics/actor_step_close.py *> runs/actor-step-verification/closure-console.txt
git diff --check
```

The single collection command exited **0**. It ran the full replay audit inside
its wall allocation. Do not repeat it: the output/ledger are consumed. Stored
reporting is read-only. For future full audits use an **absolute experiment path**
because frozen orchestration records contain absolute checkpoint paths:

```powershell
.\.venv\Scripts\python.exe -m battlemind actor-step-report --experiment (Resolve-Path runs/actor-step-acceptance).Path
# Optional future read-only replay; not a new training/collection command:
.\.venv\Scripts\python.exe -m battlemind actor-step-report --experiment (Resolve-Path runs/actor-step-acceptance).Path --audit
```

Relative-path full audits currently compare relative constructed opponent paths
with recorded absolute ones and can report a mismatch. Use the absolute command
above; do not rewrite frozen paths/hashes. The internal audit and closure used
absolute paths. Relocation/full-source portability is not claimed. Future source
changes need this retained source snapshot or a separately reviewed compatibility
mechanism; no compatibility guard was bypassed here. Historical source-only clones
still lack the ignored required models/records.

| Artifact | SHA-256 |
|---|---|
| Configuration copy | `fc458b47bd2169ebd11c3d79267a2c141fd62f640733d5cd3bb905a326014783` |
| Specification copy | `127c3d786f06ac4ba3534e05d80936fb1f716192e4c3b9f4b695af5a73ed6618` |
| Freeze | `a4e810ae9077a222d0312740bf84853aced2a0ddcebbebceb1d5795d9f593067` |
| Common original initialization | `f7734489bce5d74ce2dedffd8ab274a8483810a03e09b48a26ea0ebf28d44287` |
| Selected control c3 | `5ffac495a5288adb6f1e87f50e11705ba0a5d9fab50325bde46fc5c9f64e7710` |
| Selected treatment c6 | `bba36ebac7151fa47af62da5d682b5e9d66d473cd4a19a8ecf7e70951dd4e8c8` |
| Closed ledger | `4418497b26cba9871770e382a6155945efe8bd47d9be666b1050658becebc6e7` |
| Summary | `5fa4f449ff76250c38158d92e2ac13bd2e5255ff408d29df0190df5e40a86a1b` |
| Audit | `80357fd56eaacac0f76170b4cc1a10cb1d1ce3d20700b7f98053cd008f68f44c` |
| Experiment artifact manifest | `8324fdef025ac082a7719c202ee0a286716ac9423fabf07e36de4666397644b9` |
| Supplemental complete-content manifest | `e9ca7a47577015d90b546e4591abfe7616db6f24aa7600425dd54773344f15d8` |

`runs/actor-step-acceptance/` retains copied inputs, specification, source snapshot,
single-use ledger, every cell, all checkpoints/updates/targets, selection,
final freeze, reports and diagnostic rows. `runs/actor-step-verification/` retains
pre-change hashes, readiness, test logs, full console, closure, outcome/admission
CSVs and supplemental hashes. Its `experiment-content-hashes.json` covers **all**
run files, including per-cell summary files excluded by the inherited basename
filter in the experiment manifest. The final verification manifest is produced
after redirected console outputs finish. These are integrity hashes, not protection
against an adversary replacing both files and manifests.

In plain English: the policy sees the same frozen legal-choice snapshot as before.
It samples from its unchanged softmax model. After an eligible completed battle,
the old REINFORCE gradient credits the trajectory with its outcome; treatment moves
the actor farther in that direction while leaving the critic update rule alone.
Selection and final evaluation are separate fresh schedules. The standard
optimization mathematics is reused; BattleMind's engineering contribution here
is the controlled update boundary, equal bounded schedules, strict provenance,
outcome/commitment accounting and reproducible comparative audits. Larger moves
can amplify noise or preferences that do not improve wins, as this inconclusive
experiment illustrates.

**One next action:** separately scope an **offline sampled-command trajectory
contract validation** before considering a change to whole-episode exclusions.
The retained structured exclusions remain a concrete data-quality limitation;
this recommendation does not authorize relaxing private commitment labels,
collecting more games or running another learning rate. It was not executed.
