# BattleMind project vision

“Pokémon Showdown, but the bot studies how its opponent plays, predicts whether they will attack or switch, and uses those predictions to make better decisions.”

The owner is a college CS student with full-stack experience who wants to learn enough ML and engineering to explain their own work in an interview. Replacing the Property Evidence resume project is an ambition, not a promised result. Priorities are demonstrable contributions, readable code, honest experiments, and an explanation the owner can defend.

The initial system runs locally on CPU without paid services, rented GPUs, API keys, or cloud accounts. Small data and models come before scaling. The environment must be inspected rather than assumed. This repository builds a **player for the official Showdown engine**, not a battle engine.

## Experimental questions

1. Does adding a learned opponent predictor help the same decision-making system win more battles than it wins without that predictor?
2. Does remembering an opponent's previous visible actions help more than looking only at the current position?
3. With the predictor fixed, can learning four action-score parameters improve completed-game outcomes? V5 tests this separately from probability estimation.
4. With predictor and scoring frozen, does one opponent's earlier public behavior help beyond pooled history? V6 tests cross-encounter memory separately from learning coefficients or policy weights.

These are hypotheses. Negative findings are useful. Neither competitive strength, automatic improvement, research novelty, human-level performance, nor a particular win rate is promised. A percentage prediction alone is not the eventual contribution: the prediction must change a defined action-scoring rule, and improved prediction does not automatically imply improved battle play.

## Six separate responsibilities

| Responsibility | Present boundary / later role |
|---|---|
| Local battle environment | Official local Showdown; owns rules, legal requests, resolution, results, and validation |
| Observation/action adapter | Frozen, typed, versioned player-visible snapshots; stable semantic IDs mapped to current legal commands |
| Our battle policy | Frozen-snapshot random, MaxBasePower, Gen 1 heuristic, prediction-weighted rules and V5's frozen four-parameter score policy |
| Opponent predictor | V3/V4: frozen constant frequency, conditional counts and supervised logistic regression; numeric switch probabilities, separate from shared action scoring |
| Cross-encounter memory within prediction | V6: observer-only public proxies, immutable per-battle summaries, pooled or synthetic-session routing, conservative residual adjustment with the predictor/scorer frozen |
| Data/training | Audited local supervised datasets and frozen logistic bundles; separately, bounded completed-outcome policy updates with archived opponents, phase budgets and safe JSON checkpoints |
| Evaluation/reporting | Fixed match schedules, explicit failures, reproducible metadata, JSONL and JSON/CSV; independent of training |

Current flow: local Showdown → player's request and public history → immutable observation/legal choices → frozen switch predictor → shared utility scoring → policy ID → checked command → Showdown. Completed games feed a separate audited dataset and supervised training/count-estimation step; evaluation never updates fitted parameters. Privileged recording data establishes targets and evaluation eligibility only and cannot feed policy features.

V5 also sends completed training outcomes to an offline four-parameter update.
Two perturbed candidates play the same frozen opponent panel and balanced schedule;
their terminal-reward difference determines the next vector. Fresh selection
games choose among initialization and two arithmetic updates. Only then is the
chosen checkpoint evaluated against the frozen initialization on six fixed opponents.
The V4 predictor never changes. This is derivative-free policy optimization with
archived self-play, not gradient-based reinforcement learning or individual adaptation.

V6 adds a distinct between-encounter path: the observer's completed public record
feeds a conservative proxy summary for later encounters. No memory update reads
private commitment labels or terminal rewards. Each live arm owns its memories;
all three shadow predictions use that same observer's earlier permitted evidence.
Keys remain outside features and memories reset across independent groups/phases.
The frozen V4 predictor and selected V5 score vector are identical across arms.

## Information boundaries

Running both agents on one computer never authorizes hidden-state access. Features must exclude unrevealed opposing team members/moves/stats, the opponent's submitted current choice, future turns/results, hindsight-filled state, simulator RNG, usernames, team-file identities, and assignment metadata. Snapshots are captured before decisions and never contain a mutable live battle object.

Unknown Pokémon or moves remain unknown, not absent or impossible. Preserve the actual HP precision shown to the player. Own legal requests govern forcing, trapping, disabled moves, depleted PP, and engine-mandated actions; never assume four moves or six switches. Distinguish displayed Gen 1 stages from exact derived stats. Test only what is depended upon, use narrow workarounds or explicit unknowns, and never silently change formats to avoid a library issue.

The Milestone 2 recorder combines both players' attempts only after the clients stop, then verifies commitment against the official engine's end log. It stores labels separately from pre-decision observations. Neither policy receives the other's current choice. An intended move may never execute. Voluntary switches, forced replacements, engine actions and ambiguous/missing labels remain distinct; game-effect switches are public events, not evidence of a selected switch. The hidden-state mutation, batching, commitment and alignment tests are durable requirements. See `SCHEMA.md` for observer-to-label joins and exclusions.

## Staged roadmap

| Version | Scope and evidence required |
|---|---|
| V1. Legal matches — implemented | Legal mappings, honest unknowns, immutable snapshots, bounded local games, logs, tests and diagnostics. Historical Milestone 1. |
| V2. Basic strategy — implemented | Documented Gen 1 heuristic, varied legal teams, audited intended choices and voluntary/forced/ambiguous handling. Historical Milestone 2. |
| V3. Opponent prediction — implemented | Frozen constant and conditional-count switch prediction, audited battle-level dataset, probability evaluation, and prediction-weighted decisions. Compare the same scoring policy with constant versus conditional probabilities; retain V2 as a separate reference. No trained classifier or evaluation-time learning. |
| V4. Supervised training from local records — implemented | Logistic regression from audited local recorded battles, train-only preprocessing, whole-battle validation, fair count baselines, safe frozen inference, and separate probability/decision/battle evaluation. No arbitrary replay-file ingestion. |
| V5. Bounded self-play learning — implemented | Four bounded policy-score parameters, outcome-driven antithetic updates against frozen heuristics and archived checkpoints, separate checkpoint selection and frozen initial/selected evaluation. See V5-EXPERIMENT.md and MILESTONE5.md for the single declared run and actual results. |
| V6. Individual-opponent adaptation — accounting repaired; acceptance incomplete | Public memory, frozen V4/V5 scoring and accounting regressions pass tests. Original: 96 completed development games, budget exhausted, zero final. Authorized replacement: 144 development completed; final stopped at 251 completed plus one cap caused by the frozen opponent heuristic. No retry or scientific tuning. See V6-ACCEPTANCE-REPAIR.md and STATUS.md for the exact blocker. |
| V7. Evidence and local demonstration — implemented | Read-only retained-evidence catalog, safe local artifact closure, official animated renderer and three bounded functional games. No new performance benchmark. V6 remains incomplete. See V7.md, ARTIFACTS.md and STATUS.md. |

This version roadmap follows the owner's requests and replaces the earlier six-milestone ordering. Prediction affects decisions in V3; supervised fitting begins in V4, policy learning in V5, and public cross-encounter adjustment in V6. Each version was evaluated as developed. V7 consolidates retained evidence without a new performance comparison. `STATUS.md` records current verification; historical documents preserve earlier findings. V7 is the final planned milestone. External replay ingestion, human profiling, public hosting and live cross-encounter adaptation in the viewer remain unsupported.

The viewer is a separate consumer: a guest spectator socket receives public engine
events and a browser animates them with pinned official client components. Playback
controls have no path to the policy. Historical projections and optional own-player
explanations are labeled and shown after the encounter. The minimal local bundle
contains frozen V4/V5 artifacts, public examples and an offline observer-owned V6
audit prefix; private engine logs and other-player journals are excluded.

## Prediction experiment and later extensions

Use the same candidate-action scoring system across three variants:

- A: fixed frequency estimated on development games (implemented V3).
- B: conditional counts using the current visible state (implemented V3).
- C: logistic regression using compact visible state plus recent public switch/drag indicators (implemented V4). V4 does not isolate the benefit of history from model capacity; a history ablation or individual adaptation requires a separate experiment.

V3 weights damaging-move utility against the current foe and a uniform mixture of publicly revealed living bench Pokémon plus anonymous neutral-type alternatives for unseen slots. Other V2 scores remain unchanged. The conditional probability is defined given a meaningful opponent choice; actual eligibility is often unknown during play, so applying it online is an explicit approximation. See `PREDICTION.md`. There is no alternate simulator or search, and no fabricated natural-language thoughts.

Switch/move labels must reflect genuine choices. Later targets might distinguish move categories, destinations, or hidden moves, but may not use the opponent's private legal-action list as prediction input. V6 implements individual synthetic-opponent memory using a public proxy; advertising a performance benefit still requires a separate completed comparison. The current partial development result does not meet that standard.

## Evaluation design

- Keep training separate from evaluation. Freeze checkpoints and compare against random, a stronger documented heuristic, and frozen previous versions; beating random is not the endpoint.
- Match team assignments, opponents, sides, compute, and limits between comparison variants. Use several matchups, with suitable held-out teams/opponents or time periods for generalization claims. Restricted-pool wins are restricted-pool results.
- Split by **whole battle**, keeping both perspectives and all turns together. Never split turns independently. Do not repeatedly tune against the final test set.
- For V6 memory, also keep every connected encounter in its reset-group partition. Resample independent groups rather than individual memory-linked battles. A whole-battle split alone cannot prevent cross-encounter leakage.
- Report actual wins/losses/draws and completed-game denominators with uncertainty intervals for later inferential experiments. Choose sample sizes from observed variance and resource constraints; no arbitrary count guarantees significance.
- Keep truncations, invalid actions, timeouts, crashes, and resource use separate. Never turn a cap or crash into a genuine win. Decide draw/cap handling before comparisons.
- For voluntary-switch prediction, report class balance, majority/frequency baselines, and probability quality such as Brier score or log loss, rather than accuracy alone. Better classification is not proof of stronger battle play.
- Store code/dependency/server versions, format, hashes of teams, policy/model version, config, and supported seeds. Distinguish policy/team schedule seeds from engine randomness. Claim exact replay determinism only after actual verification.
- Preserve weak and failed runs. Do not invent metrics, substitute engine fixtures for real matches, or select only convenient opponents/results.

## Later data and integrations

Start with local simulated games. External replay data can be added only after verifying what it reveals, hides, or infers. Public replays do not necessarily contain every private choice or original player observation. [Metamon](https://github.com/UT-Austin-RPL/metamon) and its [replay parser](https://github.com/UT-Austin-RPL/metamon/blob/main/metamon/backend/replay_parser/README.md) are optional candidates to investigate later, not dependencies now. Check licensing, downloads, format compatibility, and observation assumptions before use; explain the size and purpose of substantial downloads first.

No screenshots, OCR, mouse automation, public ladder, player scraping, public account creation, paid decision-maker APIs, cloud provisioning, or internet-exposed insecure server belong in this project. No database, distributed training, microservices, login system, or frontend is needed for the initial milestones. Keep generated logs/datasets/weights and the third-party checkout outside normal source commits; preserve upstream notices.

## Learning and engineering habits

### Separately authorized research after V1–V7

The richer policy extension is one CPU bilinear softmax actor with an observer-only
value baseline, trained by terminal-outcome REINFORCE with archived self-play and
fixed reference opponents. It is distinct from V4 supervised switch prediction,
V5 four-parameter derivative-free optimization, and V6 cross-encounter behavioral
adjustment. It adds no new generation, team construction, external data or human
profiling. V1–V7 remain the historical roadmap; V6 acceptance remains incomplete.

The new model starts from a fixed clipped V2 prior and zero learned coefficients,
with no imitation data. Balanced frozen rollout batches feed offline outcome joins
and one update per batch. Selection and final evaluation are fresh, disjoint and
cannot update weights. Main allocations are 864/216/576 games and at most 3,600s;
the separate engineering smoke is at most 48 games/300s. Consumed specifications
cannot be resumed or repeated without another request. See
[REINFORCE.md](REINFORCE.md), [the frozen design](REINFORCE-EXPERIMENT.md) and
[observed evidence](REINFORCE-RESULTS.md). Any next research/evaluation/port is a
separate decision, not an automatically executed milestone.

### Ongoing engineering rules

Prefer a small Python package and `poke-env`, versioned legal team fixtures, type hints, clear errors, configuration, and behavioral tests. Engine rules remain authoritative. Every milestone should explain the important paths in plain English and distinguish original work from reused infrastructure/algorithms/data. Keep training dependencies optional until actually needed. Inspect before editing, preserve unrelated work, and do not commit, push, deploy, or start prolonged workloads without a separate request.
