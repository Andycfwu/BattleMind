# BattleMind V5 — actual learning, inconclusive battle improvement

V5 is implemented and the single declared acceptance experiment finished:
**840/840 completed games, two nonzero outcome-driven updates, separate selection,
and frozen final evaluation**, within its 1,200-game/20-minute user ceiling.
Selected c1 won 104/144 final games versus initialization's 98/144, but the
descriptive difference interval includes regression. A working self-play learning
loop is demonstrated; better battle strength is not established.

V4's full status is preserved verbatim in [MILESTONE4.md](MILESTONE4.md): its logistic
predictor improved probability estimates without establishing a battle benefit.
V3's negative evidence remains in [MILESTONE3.md](MILESTONE3.md). Original scorers,
predictors, teams and historical recorded artifacts remain unchanged. No rerun,
retuning, commit, push or deployment was performed. Git was clean at inspection;
the starting commit was `4b47dc412450c68d73c1268f6b80672251030c23`.

## Implemented behavior

- `learned_policy.py`: four immutable score parameters, exact V4-equivalent zero
  initialization, safe JSON checkpoints, compatibility/bounds/finite-score checks.
  Only frozen snapshots enter scoring; checkpoint provenance never enters features.
- `policy_search.py`: seeded antithetic proposals, complete-game reward validation,
  arithmetic bounded updates and deterministic selection ties. This is derivative-free
  random-direction policy optimization, not gradient-based reinforcement learning.
- `learning_ledger.py` / `learning.py`: reserved game/time allocations, two immutable
  opponent pools containing archived checkpoints, fresh selection and frozen final
  schedule. Updates happen only between fully completed audited batches. No resume.
- `learning_report.py`: actual accounting, block uncertainty, same-snapshot choice
  comparison, reconstruction of updates/selection and existing decision/label audits.
- CLI: `policy-train`, `policy-evaluate`, `policy-report`, and per-player
  `--checkpoint-a` / `--checkpoint-b` options for ordinary battles. README has examples.

Package 0.5.0 uses unchanged Python 3.14.3, Node 24.19.0, poke-env 0.16.1, NumPy
2.5.2 and official Showdown `2f5b273925862ac242b419086c1e7a8868b51da1`.
No dependency download/change was needed. Installed poke-env request/message
source was inspected before checkpoint wiring; the private hook bodies and label
recorder were not changed. Services stayed on 127.0.0.1 with concurrency 1.

## Frozen specification, budgets and partitions

[V5-EXPERIMENT.md](V5-EXPERIMENT.md) and `configs/v5-experiment.json` were written
before training. Specification SHA-256:
`6fa0f1ea3fbd1068dcd53039f6b776df977666061730a0a7b122fadeba4cd701`.
Every 24-game cell covers the unchanged four teams' six unordered pairs, both
assignments and both challenger sides. All phases have distinct run-manifest-hash
plus match identities; audit found **zero overlap**. Policy seeds do not control
Showdown randomness and do not create matched engine trajectories.

| Phase | Requested / completed | W/L/D for player a | Allocated wall | Consumed phase wall |
|---|---:|---:|---:|---:|
| Training | 336 / 336 | 188/145/3 | 420s | 157.71s |
| Selection | 216 / 216 | 115/96/5 | 300s | 96.23s |
| Final, reserved before training | 288 / 288 | 202/81/5 | 420s | 122.81s |
| **Total** | **840 / 840** | **505/322/13** | **1,200s including 60s overhead margin** | **436.64s including initial offline reporting/audit** |

Phase outcome totals pool different policies and are accounting, not learning curves.
Ledger wall is 7m16.64s; final artifact hashing and later read-only CLI/verification
are additional small overhead. No extra training or evaluation games were launched.
Each cell retained the 300-turn/60s-match limits; phase remaining time bounded the
run timeout. All requested games completed; unused user-ceiling capacity was not spent.

## Actual proposals and updates

Order is anticipation, recovery, status, switch-threshold. Each coordinate is
bounded [-1,1]. Zero equals unchanged V4; sigma .4 and alpha 2 were fixed before play.
For each direction e, update is clip(parent + 2 * (Jplus-Jminus)/.8 * e).
Rewards are completed win=1/draw=.5/loss=0 only, with no shaping.

| Round | Proposal seed / direction | Frozen opponents | Plus W/L/D; J | Minus W/L/D; J | Updated vector |
|---|---|---|---|---|---|
| 1 | 51501 / (+,-,-,-) | V2, active, c0 | 36/36/0; .500000 | 45/26/1; .631944 | c1=(-.329861, .329861, .329861, .329861) |
| 2 | 51502 / (-,-,+,+) | V2, active, c0, c1 | 59/37/0; .614583 | 48/46/2; .510417 | c2=(-.590278, .069444, .590278, .590278) |

The first update changes every coordinate by magnitude .329861; the second by
.260417 along its new direction. The two J columns are evaluated on each round's
pool, which changes once when c1 is admitted; they are not a comparable monotonic
learning curve. Round 1's c0 self-play results were plus 11/13/0 and minus 15/8/1.
Round 2 included both c0 and c1 throughout each sign's batch. Those real archived
self-play outcomes contributed to both arithmetic updates. All candidates, including
weak ones and c2's later poor selection result, are retained.

Safe checkpoint SHA-256 digests:

- c0: `1344e13ca7c5e675ca0c3c0f1c1da858fc77ebf90d06bb154d7f3bf77654d709`
- c1 / selected: `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e`
- c2: `3288455637d0d47d91ab992231617dc1e2fd7c557ac82768f84899a99f300cf7`

The V4 predictor remains exactly
`44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`.
No predictor coefficients, preprocessing, features or counts changed.

## Fresh selection and final results

Selection used exactly 72 fresh games per checkpoint against V2, moderate and c0:

| Checkpoint | W/L/D | Mean terminal reward |
|---|---:|---:|
| c0 | 39/32/1 | .548611 |
| **c1 — selected** | **40/29/3** | **.576389** |
| c2 | 36/35/1 | .506944 |

c1 had the highest reward; neither tie breaker was needed. Selection copied c1 to
`selected.json` and froze its hash before final play. c2 was not used because it
was newer; final results never changed selection. No additional V4 final arm was
needed because initialization equivalence passed on every one of 20,620 archived
V4 final snapshots (exact scores, choices and probabilities).

Each final cell below is 24 fresh, balanced games; W/L/D is from the tested arm:

| Fixed opponent | Initial c0 W/L/D | Selected c1 W/L/D |
|---|---:|---:|
| RandomLegal | 24/0/0 | 24/0/0 |
| MaxBasePower | 23/1/0 | 22/1/1 |
| V2 Gen1Heuristic | 14/9/1 | 13/10/1 |
| switch-active | 13/10/1 | 17/7/0 |
| archived c0 | 10/13/1 | 12/12/0 |
| archived c1 | 14/10/0 | 16/8/0 |
| **Overall, 144 each** | **98/43/3** | **104/38/2** |

Completed win rates: c0 **68.06%** (Wilson 95% 60.06–75.12%), c1 **72.22%**
(64.40–78.89%). Mean reward: .690972 versus .729167. The predeclared 1,000-resample
four-game-block bootstrap gives selected-minus-initial reward **+3.82 percentage
points [−4.86, +12.50]**, win-rate **+4.17 points [−4.17, +12.50]**. These are
descriptive fixed-panel intervals; they resample schedule blocks, not turns or
matched engine randomness. Wilson overlap is not the significance argument.

The observed total increased, but improvement remains **inconclusive**. V2 and
MaxBasePower each yielded one fewer selected win, while active and archived
checkpoints yielded more. These cells check earlier opponents but are too small
to establish absence of forgetting. Even c1 versus itself was 16/8/0 on this
schedule, illustrating finite-sample engine variability. No unseen-opponent,
held-out-team, human-level or competitive-strength claim is supported.

## What changed in decision behavior

Initial and selected choices differed on **1,458/10,045 (14.51%)** identical final
player-a snapshots: 853/4,538 on c0's visited states and 605/5,507 on c1's. The
comparison recomputes both policies on the same immutable data; it does not
estimate counterfactual wins. Most transitions favored status/setup or recovery:
760 damage→status/setup, 261 damage→recovery, 140 switch→status/setup,
127 switch→recovery, 92 switch→damage, 46 switch→engine, 29 damage→damage and
3 recovery→damage. Engine scores stay unchanged; a higher switch threshold can
change a mixed request's winner from switching to its existing engine action.

Concrete trace: `final/selected-vs-random/decisions.jsonl`, `m0:a:r2`, turn 1.
Both policies have p=.08128793. Initial scores prefer switch:4 at 115 over Thunder
Wave at 95. c1 raises Thunder Wave to 127.986 and lowers that switch to 101.806,
choosing Thunder Wave. Recover at full HP remains zero. This explains the choice
through visible utility and frozen parameters, without claiming it was optimal.

c1 reduces the anticipation adjustment to 67.01% of V4's, adds 32.986 utility to
supported positive healing/status rules, and raises switch threshold from 80 to
93.194. These coarse changes affect choices much more often than V4's probability
source changes did. c2's worse selection reward shows that taking another update
does not ensure progress. Two noisy directions move all coordinates together;
the experiment cannot identify which individual weight caused a result.

## Labels, warnings, failures and resources

Across the acceptance experiment: **zero invalid actions, caps, timeouts, crashes,
cancellations, not-started/unrecorded games, server crash reports or unexpected
warnings**. Cleanup never became a win. There were **10 recognized Wrap/Clamp
annotation warnings**, retained unchanged in events logs: 2 in initial-vs-random,
8 in selected-vs-random.

| Phase | Attempts / verified commitments | Unknown commitments | Eligible paired targets / voluntary switches |
|---|---:|---:|---:|
| Training | 26,911 / 26,911 | 0 | 19,128 / 1,629 |
| Selection | 16,405 / 16,405 | 0 | 11,323 / 963 |
| Final | 20,423 / 20,414 | 9 | 14,338 / 1,485 |

Overall commitment coverage is **63,730/63,739 = 99.9859%**. There are 15 unknown
eligibility records in final; eligibility is never supplied to live features.
The nine unknown commitment labels occur in selected-vs-random, match 6, from
turn 24 onward. Both requests have `maybe_locked`: submitted Rock Slide corresponds
to official `move fight`, and submitted Agility corresponds to official `move wrap`
after publicly observed Wrap. The recorder preserves both unmatched suffixes as
unknown and does not search ahead. This is the documented Gen 1 commitment
ambiguity, not an invalid-action retry. The game had matching natural terminal
win/loss messages, so its final outcome remains valid under the predeclared rule.
See `runs/v5-label-review.json` for the first mismatches and visible history.

Sampled Python peak RSS was **244.09 MiB**, managed server tree **435.69 MiB**.
Runner Python CPU totaled 111.78s; server last CPU samples summed to 118.47s.
These are sampled runner measurements, exclude offline CPU, and are not exact
lifetime peaks/totals. The ledger includes run/audit wall time. No port-8000
listener remained after completion. Logs and checkpoints remain local and ignored.

## Tests, verified commands and artifact paths

**106 unit tests passed** (0.52s); **10 integration tests passed** (69.54s).
Integration requested **37 separate games**: 35 completed, one deliberate cap and
one deliberate timeout, both excluded from wins. This includes 12 new V5 games:
perturbed self-play batches → actual update → checkpoint reload → frozen evaluation
→ audit. Official-engine protocol probes are tests, not performance evidence.
The existing integration suite and new tests cover immutable/hidden-information
boundaries, forced/engine legality, reproducible proposals, finite bounds, safe
checkpoint compatibility, outcome updates, frozen pools, disjoint phase identities,
incomplete rewards, reserved budgets, selection ties and evaluation immutability.

`pip check`, the pinned runtime/four-team doctor and `git diff --check` passed.
Read-only CLI audit reconstructed all **35 runs, 840 battles, 63,739 decisions,
two nonzero updates**, and checked **3,917 artifact files** with zero overlaps.
The embedded summary audit runs before the artifact hash manifest exists; the
later `.local/v5-cli-audit.json` records all 3,917 file checks without rewriting
the hashed experiment summary.
Historical V3 acceptance (667 files), V4 development (668) and V4 acceptance
(1,330) hashes all matched; original V2/V3/V4 scoring, schemas, labels, teams,
dependency lock and server config remained unchanged.

Commands actually run from the project root (PowerShell):

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json > .local/v5-doctor.json
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration > .local/v5-integration-console.log 2>&1
.\.venv\Scripts\python.exe .local/verify-v5-initial.py
.\.venv\Scripts\python.exe -m battlemind policy-train --output runs/v5-acceptance --predictor models/v4-supervised.json > .local/v5-acceptance-console.log 2>&1
.\.venv\Scripts\python.exe -m battlemind policy-report --experiment runs/v5-acceptance --audit > .local/v5-cli-audit.json
.\.venv\Scripts\python.exe .local/verify-v5.py > .local/v5-verification-console.json
.\.venv\Scripts\python.exe .local/review-v5-labels.py
git diff --check
```

Actual artifacts, relative to this project root:

- `runs/v5-acceptance/`: immutable specification/source freeze, ledger, 35 run
  directories, all proposals/checkpoints, round updates, selection/final freeze,
  copied predictor, same-snapshot choices, summary and artifact hash manifest.
- `runs/v5-acceptance/selected.json`: frozen c1; ordinary battle and `policy-evaluate`
  loading interfaces are documented in README. No extra CLI evaluation was launched
  outside the experiment/test allocations; integration exercises the same runner path.
- `runs/v5-initial-equivalence.json`: all 20,620 V4 snapshots checked offline.
- `runs/v5-verification.json`: preserved historical/source/model hashes,
  per-opponent training/selection counts, label summaries, transition counts and trace.
- `runs/v5-label-review.json`: exact unknown-commitment reproduction from retained logs.
- `runs/integration-v5-9991245205/`: real 12-game learning/reload/evaluation test.
- `.local/v5-*.log`, `.local/v5-cli-audit.json`, `.local/v5-doctor.json` and
  `.local/verify-v5*.py`: retained command output and read-only verification helpers.

## Explanation, limits and next milestone

A request becomes a frozen visible snapshot. The unchanged V4 logistic predictor
computes p; V4 scoring computes utilities; four frozen V5 parameters adjust them.
The policy chooses a legal ID and the adapter checks its current request command.
Separate journals and post-match engine evidence retain the original label boundary.
Only completed **training** batches can drive the offline arithmetic update.
Fresh selection chooses a checkpoint; final evaluation cannot learn.

[POLICY-LEARNING.md](POLICY-LEARNING.md) explains the code and separates standard
optimization methods from BattleMind's information boundaries, score design,
budget/phase orchestration and audits. Supervised prediction learns choice
probabilities; policy optimization learns action preferences from terminal outcomes;
self-play includes archived versions as opponents; individual adaptation is absent.

Current utilities still approximate damage, switch destinations and action value.
Gen 1 effective stats and live opposing choice eligibility remain unknown; HP retains
raw precision. Four teams, related rule opponents, two coupled update directions and
a small selection panel limit inference. Strict checkpoint compatibility deliberately
rejects changed scoring/schema/predictor files. Resume and source-only reproduction
without the retained original V4 model are unsupported. No external replay ingestion,
profiles, frontend, hosted models, public ladder, paid infrastructure or GPU was added.

The single recommended next milestone is **V6 — individual-opponent adaptation,
informed by V5's evidence**. It should isolate individual-history benefit with frozen
controls and an explicit rule for how that information affects these approximate
scores; V5 does not justify assuming that more accurate prediction or more updates
will improve battle outcomes.
