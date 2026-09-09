# BattleMind project vision

“Pokémon Showdown, but the bot studies how its opponent plays, predicts whether they will attack or switch, and uses those predictions to make better decisions.”

The owner is a college CS student with full-stack experience who wants to learn enough ML and engineering to explain their own work in an interview. Replacing the Property Evidence resume project is an ambition, not a promised result. Priorities are demonstrable contributions, readable code, honest experiments, and an explanation the owner can defend.

The initial system runs locally on CPU without paid services, rented GPUs, API keys, or cloud accounts. Small data and models come before scaling. The environment must be inspected rather than assumed. This repository builds a **player for the official Showdown engine**, not a battle engine.

## Questions to test later

1. Does adding a learned opponent predictor help the same decision-making system win more battles than it wins without that predictor?
2. Does remembering an opponent's previous visible actions help more than looking only at the current position?

These are hypotheses. Negative findings are useful. Neither competitive strength, automatic improvement, research novelty, human-level performance, nor a particular win rate is promised. A percentage prediction alone is not the eventual contribution: the prediction must change a defined action-scoring rule, and improved prediction does not automatically imply improved battle play.

## Six separate responsibilities

| Responsibility | Present boundary / later role |
|---|---|
| Local battle environment | Official local Showdown; owns rules, legal requests, resolution, results, and validation |
| Observation/action adapter | Frozen, typed, versioned player-visible snapshots; stable semantic IDs mapped to current legal commands |
| Our battle policy | Chooses our action from sanitized observations: RandomLegalAgent, MaxBasePowerAgent and the documented Gen1HeuristicAgent |
| Opponent predictor | Later: probabilities and uncertainty over the opponent's voluntary switch versus move decision; separate from our policy |
| Data/training | Present: separate post-commit intended-choice recorder and audits. Later: leakage-safe battle datasets, small models, versioned checkpoints and training configurations |
| Evaluation/reporting | Fixed match schedules, explicit failures, reproducible metadata, JSONL and JSON/CSV; independent of training |

Current flow: local Showdown → player's request and public history → immutable observation/legal choices → policy ID → checked command → Showdown. Completed games are logged. Later, a separate dataset/training pipeline will produce a frozen predictor or policy for a separate evaluation run. Public history can feed prediction; privileged recording data cannot feed features.

## Information boundaries

Running both agents on one computer never authorizes hidden-state access. Features must exclude unrevealed opposing team members/moves/stats, the opponent's submitted current choice, future turns/results, hindsight-filled state, simulator RNG, usernames, team-file identities, and assignment metadata. Snapshots are captured before decisions and never contain a mutable live battle object.

Unknown Pokémon or moves remain unknown, not absent or impossible. Preserve the actual HP precision shown to the player. Own legal requests govern forcing, trapping, disabled moves, depleted PP, and engine-mandated actions; never assume four moves or six switches. Distinguish displayed Gen 1 stages from exact derived stats. Test only what is depended upon, use narrow workarounds or explicit unknowns, and never silently change formats to avoid a library issue.

The Milestone 2 recorder combines both players' attempts only after the clients stop, then verifies commitment against the official engine's end log. It stores labels separately from pre-decision observations. Neither policy receives the other's current choice. An intended move may never execute. Voluntary switches, forced replacements, engine actions and ambiguous/missing labels remain distinct; game-effect switches are public events, not evidence of a selected switch. The hidden-state mutation, batching, commitment and alignment tests are durable requirements. See `SCHEMA.md` for observer-to-label joins and exclusions.

## Staged roadmap

| Milestone | Scope and evidence required |
|---|---|
| 1. Local foundation | Real matches by both simple baselines; legal mappings, honest unknowns, immutable snapshots, bounded runs, logs, tests, diagnostics, summaries. A 20-match smoke run validates plumbing only. |
| 2. Better baselines and trustworthy data | Stronger documented Gen 1 heuristic, more varied versioned teams/opponents, and validated intended-choice labels with voluntary/forced/ambiguous handling. No claim of prediction yet. |
| 3. Small opponent predictor | Counts first, then a small classifier such as logistic regression for voluntary switch versus choosing a move when the opponent genuinely has options. Train/validate/test by whole battle; compare probability quality with simple frequency baselines. |
| 4. Prediction changes decisions | Connect predicted probabilities to an explicit shared scoring system. Run matched prediction-off/state-only/history comparisons and report win-rate effects, including negative findings. |
| 5. Optional stronger learning | Investigate imitation learning, then carefully budgeted self-play against diverse frozen opponents. An actual update step and held-out evaluation are required to call it learning. |
| 6. Demonstration and explanation | A lightweight local replay/report viewer, architecture explanation, reproducible experiments, and clear original/reused-work attribution. Human challenges and individual-opponent adaptation are optional extensions. |

Milestones 1 and 2 are implemented; `STATUS.md` records their acceptance evidence and limitations. No predictor, training, checkpoint, frontend, or dashboard scaffolds have been added. Every milestone should be independently useful; completing all six is not a prerequisite for a useful project.

## Later prediction experiment

Use the same candidate-action scoring system across three variants:

- A: fixed/simple opponent-behavior estimate.
- B: learned prediction from the current visible state.
- C: prediction also using past visible opponent actions.

One possible transparent approximation scores consequences of the opponent staying versus voluntarily switching, weighted by predicted probabilities. Define exactly how this changes scores. For unknown switch destinations, use documented assumptions instead of the true hidden team. Start lightweight: do not introduce an alternate full simulator or expensive search just to complete the design. Return actual probabilities/uncertainty, not natural-language “thoughts.”

Switch/move labels must reflect genuine choices. Later targets might distinguish move categories, destinations, or hidden moves, but may not use the opponent's private legal-action list as prediction input. Opponent-specific adaptation is a stretch goal that needs measured benefit over a non-adaptive comparison before being advertised.

## Evaluation design

- Keep training separate from evaluation. Freeze checkpoints and compare against random, a stronger documented heuristic, and frozen previous versions; beating random is not the endpoint.
- Match team assignments, opponents, sides, compute, and limits between comparison variants. Use several matchups, with suitable held-out teams/opponents or time periods for generalization claims. Restricted-pool wins are restricted-pool results.
- Split by **whole battle**, keeping both perspectives and all turns together. Never split turns independently. Do not repeatedly tune against the final test set.
- Report actual wins/losses/draws and completed-game denominators with uncertainty intervals for later inferential experiments. Choose sample sizes from observed variance and resource constraints; no arbitrary count guarantees significance.
- Keep truncations, invalid actions, timeouts, crashes, and resource use separate. Never turn a cap or crash into a genuine win. Decide draw/cap handling before comparisons.
- For voluntary-switch prediction, report class balance, majority/frequency baselines, and probability quality such as Brier score or log loss, rather than accuracy alone. Better classification is not proof of stronger battle play.
- Store code/dependency/server versions, format, hashes of teams, policy/model version, config, and supported seeds. Distinguish policy/team schedule seeds from engine randomness. Claim exact replay determinism only after actual verification.
- Preserve weak and failed runs. Do not invent metrics, substitute engine fixtures for real matches, or select only convenient opponents/results.

## Later data and integrations

Start with local simulated games. External replay data can be added only after verifying what it reveals, hides, or infers. Public replays do not necessarily contain every private choice or original player observation. [Metamon](https://github.com/UT-Austin-RPL/metamon) and its [replay parser](https://github.com/UT-Austin-RPL/metamon/blob/main/metamon/backend/replay_parser/README.md) are optional candidates to investigate later, not dependencies now. Check licensing, downloads, format compatibility, and observation assumptions before use; explain the size and purpose of substantial downloads first.

No screenshots, OCR, mouse automation, public ladder, player scraping, public account creation, paid decision-maker APIs, cloud provisioning, or internet-exposed insecure server belong in this project. No database, distributed training, microservices, login system, or frontend is needed for the initial milestones. Keep generated logs/datasets/weights and the third-party checkout outside normal source commits; preserve upstream notices.

## Learning and engineering habits

Prefer a small Python package and `poke-env`, versioned legal team fixtures, type hints, clear errors, configuration, and behavioral tests. Engine rules remain authoritative. Every milestone should explain the important paths in plain English and distinguish original work from reused infrastructure/algorithms/data. Keep training dependencies optional until actually needed. Inspect before editing, preserve unrelated work, and do not commit, push, deploy, or start prolonged workloads without a separate request.
