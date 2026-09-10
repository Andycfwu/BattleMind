# BattleMind

A local Pokémon Showdown player and experiment harness, now with a **V7 local animated viewer and retained-evidence catalog**. Runs on CPU, with no account, API key or paid service. The official engine owns the rules. BattleMind owns the observation boundary, policies, conservative recording, experiments and local demonstration shell.

A separately authorized research extension adds **`reinforce`**, a compact
851-parameter action-conditioned stochastic policy with an observer-only value
baseline. It learns from completed local battle outcomes against fixed references
and archived learner checkpoints. The new architecture's frozen initialization is
its primary control; it is not presented as equivalent to V5. See the
[algorithm and commands](docs/REINFORCE.md),
[frozen experiment specification](docs/REINFORCE-EXPERIMENT.md), and
[actual research results](docs/REINFORCE-RESULTS.md). Historical V1–V7 evidence,
viewer defaults and the **incomplete V6 acceptance status** remain unchanged.

The [REINFORCE loader/reporting repair note](docs/REINFORCE-REPAIRS.md) documents
the two audit fixes, strict historical compatibility and offline replay checks.

The separately authorized [controlled actor-step experiment](docs/ACTOR-STEP-RESULTS.md)
completed **2,088/2,088 games**. A 10× actor-only step produced much greater
policy movement without numerical instability, but **did not establish better
final results** than the fresh control or initialization. The
[frozen specification](docs/ACTOR-STEP-EXPERIMENT.md) and ignored
`runs/actor-step-acceptance` retain both arms, all 12 updates, selection and audits.
Its allocation is consumed; no further training is authorized by these commands.

## Watch a battle

This retained workspace already has the verified demonstration bundle:

```powershell
.\scripts\start-demo.ps1 -Bundle runs/v7-release-bundle -Output runs/MY_FRESH_DEMO
# Open http://127.0.0.1:8765
# Stop from another terminal, or use Ctrl+C in the first:
.\scripts\stop-demo.ps1 -Run runs/MY_FRESH_DEMO
```

The launch script loads `scripts/env.ps1`. Select a recording, then use Play/Pause,
speed, previous/next turn, reset or go-to-turn. Available examples include a normal
battle, a V5 scored-choice change, the freeze-related cap and four ordered V6
memory encounters. Chosen available frozen agents can play two bounded live demo
games by default. Simulation runs faster than animation and is labeled **delayed
playback**. Controls never enter policy observations. All runtime assets and both
services stay on 127.0.0.1. No remote sprites, login, telemetry or replay upload.

V6 adaptation is demonstrated through audited chronological recordings, **not live
cross-encounter adaptation**. The cold start/reset and prior-encounter cutoffs are
visible. These selected examples are explanations, not a benchmark sample.

For a fresh checkout, install the pinned environment below, retain
`runs/v7-release-bundle.zip`, and import it without fitting or training:

```powershell
.\.venv\Scripts\python.exe -m battlemind bundle-import --source PATH_TO_RETAINED_ZIP --output runs/MY_IMPORTED_BUNDLE
.\.venv\Scripts\python.exe -m battlemind bundle-verify --bundle runs/MY_IMPORTED_BUNDLE
.\scripts\start-demo.ps1 -Bundle runs/MY_IMPORTED_BUNDLE -Output runs/MY_FRESH_DEMO -Games 0
```

Recorded playback needs no running engine; live games additionally require the
pinned Showdown setup below. A source-only clone lacks ignored historical models,
checkpoints, datasets, records and renderer assets. It can run the transparent
baselines after setup, but cannot reconstruct historical artifacts from code alone.
[ARTIFACTS.md](docs/ARTIFACTS.md) documents the ~1.96 MB portable zip, exact hashes,
safe export/import, compatibility checks and full-archive requirements.

## Evidence and conclusions

[Consolidated report](runs/v7-evidence-release/REPORT.md) ·
[Machine-readable catalog](runs/v7-evidence-release/catalog.json) ·
[Current status and verification](docs/STATUS.md) ·
[Viewer design](docs/V7.md) · [Interview guide](docs/INTERVIEW.md).

```powershell
.\.venv\Scripts\python.exe -m battlemind evidence --output runs/MY_FRESH_EVIDENCE
```

This read-only command recomputes terminal accounting and checks historical file
hashes. It collects no games and does not weaken historical source audits. It needs
the full retained archive, which is intentionally excluded from the minimal bundle.
There is no cross-version win-rate ranking across different populations.

V1/V2 established local play, legal choices, recording and transparent strategy.
V3 count predictions changed decisions but worsened probability estimates. V4
improved prediction on its declared mixture; V5 made real outcome-driven updates
with archived self-play. Neither established better battle results. V6 public
memory works technically, but **both acceptance attempts remain incomplete**.
V7 packages these claims; it adds no training or performance experiment and is
the final planned milestone. Historical commands below are documentation, not
authorization to repeat consumed experiments.

The central experiment is whether opponent prediction improves the **same** decision-making system. V4 compares a trained classifier with constant and conditional frequencies fitted on the same training rows. Probability quality and battle wins are separate outcomes. See [actual results](docs/STATUS.md) and the preserved [negative V3 findings](docs/MILESTONE3.md).

## V6 public opponent memory

**Accounting repaired and tested; acceptance remains incomplete.** The separately
authorized replacement completed **144 development games**, then stopped with
**251 completed final games, one turn cap and 324 never-requested final slots**.
The frozen switch-active heuristic repeatedly chose an engine action with a frozen
active Pokémon despite a legal healthy replacement. It hit the unchanged 300-turn
cap. No retry or opponent/cap tuning occurred. Partial probability losses improved
overall, but battle benefit remains inconclusive.

The original attempt remains unchanged: **96 completed development games;
development budget exhausted; zero final games**. Its status is preserved in
[MILESTONE6-FIRST-ATTEMPT.md](docs/MILESTONE6-FIRST-ATTEMPT.md). Neither attempt is
called complete. [STATUS.md](docs/STATUS.md) records both, the exact blocker, tests,
hashes, resource use and the limited interpretation of partial final results.

V6 preserves the original V4 predictor and selected V5 scoring checkpoint. It
compares no memory, pooled history and individual history using the **same scoring
code and parameters**. Each arm uses only its own earlier completed encounters;
memory is frozen within a battle. Public announcements are a conservative proxy,
with forced, ambiguous, engine and missing evidence retained as exclusions.

[V6-EXPERIMENT.md](docs/V6-EXPERIMENT.md) is the unchanged original specification.
The separate [acceptance repair](docs/V6-ACCEPTANCE-REPAIR.md) preserves its science
and 144/576-game schedule, with authorized 420/1,080-second phases plus 300 seconds
overhead. Phase clocks stop once; planned/reserved/requested/started/completed games
are distinct. Both specifications are single-use: no retry, resume, budget borrowing,
self-play training or final-result tuning. The replacement used 868.72 seconds
including separately measured read-only verification; its stop was a cap, not time.

```powershell
. .\scripts\env.ps1
# Actual replacement command already run once; allocation is now consumed:
.\.venv\Scripts\python.exe -u -m battlemind adaptation-run --specification repair --output runs/v6-acceptance-repair
# Read-only replay of memory, shadow predictions, choices and private label audits:
.\.venv\Scripts\python.exe -m battlemind adaptation-report --experiment runs/v6-acceptance-repair --audit
```

Do not rerun collection: both outputs are consumed and resume is unsupported.
The replacement CLI returns exit code 1 and flags its incomplete cell. Its 4,364
artifact hashes match; supplemental public/private audits verify even the capped
cell's retained evidence without making that cell acceptance-eligible. Original
files and their older accounting limitations were not rewritten. Historical full
source-freeze audits require the original code; their checks were not weakened.

Collection output must be new. Required retained inputs are `models/v4-supervised.json`
and `runs/v5-acceptance/selected.json`; missing or incompatible files stop before
collection. Their exact hashes, regeneration limitations and code explanation are
in [ADAPTATION.md](docs/ADAPTATION.md). A source-only clone does not contain these
ignored artifacts. V5 evidence is preserved in [MILESTONE5.md](docs/MILESTONE5.md).
The replacement has only one complete final group and one partial group. Group
uncertainty is unavailable; no turn-level interval substitutes for missing groups.
Adaptation is not assumed to improve either probability quality or wins.

## V5 bounded policy learning

V4 improved probabilities without establishing a battle benefit; its full status is
preserved in [MILESTONE4.md](docs/MILESTONE4.md). V5 freezes that predictor and learns
four bounded score parameters: anticipation strength, healing preference, status
preference and voluntary-switch threshold. Zero initialization exactly reproduces
V4. Only completed-game outcomes from training can update these parameters.
Selection uses fresh games; final evaluation uses frozen checkpoints.

[V5-EXPERIMENT.md](docs/V5-EXPERIMENT.md) was written before training: two rounds,
840 requested games, 20-minute maximum, concurrency 1, four unchanged teams.
The accepted run is retained under `runs/v5-acceptance`: 840/840 games completed,
two nonzero updates, 436.64s including the first offline audit. Selected c1 won
104/144 final games versus c0's 98/144; the reward-difference interval includes
regression, so improvement remains inconclusive. Do not repeat it to pursue a
better result. Resume is unsupported and existing output directories are rejected.

```powershell
. .\scripts\env.ps1
# Entire declared training -> selection -> frozen final evaluation, once only:
.\.venv\Scripts\python.exe -m battlemind policy-train --output runs/v5-acceptance --predictor models/v4-supervised.json
# Read-only report and reconstruction of updates, selection, decisions and labels:
.\.venv\Scripts\python.exe -m battlemind policy-report --experiment runs/v5-acceptance --audit
```

The following are interfaces for a separately budgeted future use, not extra
acceptance runs. Both load safe, frozen JSON and cannot perform learning:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/milestone2.json --agent-a learned-score --agent-b gen1-heuristic --predictor models/v4-supervised.json --checkpoint-a runs/v5-acceptance/selected.json --battles 24 --output runs/NEW_FROZEN_BATTLE
.\.venv\Scripts\python.exe -m battlemind policy-evaluate --checkpoint runs/v5-acceptance/selected.json --predictor models/v4-supervised.json --opponent gen1-heuristic --battles 24 --output runs/NEW_FROZEN_EVALUATION
```

For a learned opponent, use `--agent-b learned-score --checkpoint-b PATH` in
`battle`, or `--opponent learned-score --opponent-checkpoint PATH` in
`policy-evaluate`. The original V4 artifact is required by the fixed training
specification and remains ignored; a source-only clone cannot recreate its exact
content hash from unspecified data. See [POLICY-LEARNING.md](docs/POLICY-LEARNING.md)
for code paths, checkpoint compatibility, method limitations and interview notes.

## V4 supervised workflow

[The experiment specification](docs/V4-EXPERIMENT.md) freezes opponents, teams, splits,
features, metrics and a 432-game schedule before collection. These commands use
fresh output names; do not rerun a final comparison to obtain a better result.

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe scripts/experiment-v4.py collect --output runs/v4-development --predictor models/v3-counts.json --budget runs/v4-budget.json
.\.venv\Scripts\python.exe -m battlemind supervised-train --dataset runs/v4-development/development-data --output models/v4-supervised.json
.\.venv\Scripts\python.exe -m battlemind supervised-evaluate --dataset runs/v4-development/development-data --predictor models/v4-supervised.json --partition development_check --output runs/v4-validation-quality
.\.venv\Scripts\python.exe scripts/experiment-v4.py final --output runs/v4-acceptance --predictor models/v4-supervised.json --budget runs/v4-budget.json
.\.venv\Scripts\python.exe -m battlemind report --run runs/v4-acceptance/logistic-vs-switch-moderate --audit
```

The driver builds datasets automatically. For other **validated local runs** use
`python -m battlemind supervised-dataset --runs RUN1 RUN2 --output FRESH_DIRECTORY`
(add `--role evaluation` for fresh final data). It does not accept arbitrary
Showdown replay files. Complete battles stay together across both perspectives.
Only runner-b eligible opponent labels enter the primary training/evaluation
population. Numeric preprocessing and model coefficients use training rows only;
three declared regularization strengths are selected on validation log loss.

`models/v4-supervised.json` is safe JSON with frozen coefficients, preprocessing,
fair count baselines and provenance. NumPy 2.5.2 was already in `requirements.lock`;
the `train` extra now declares its direct use without adding a download. The
collection driver requires this workspace's retained original V3 artifact; models
and recorded runs are ignored, so a source-only clone must retain/recover those
artifacts to reproduce this exact specification. Independent new experiments can
use the generic battle/dataset/training commands with their own declared setup.

`switch-logistic`, `switch-constant` and `switch-context` share unchanged candidate
scoring. `switch-moderate` and `switch-active` are fixed data-collection opponents
with switch thresholds 40 and 0; V2's threshold 80 remains unchanged. See
[PREDICTION.md](docs/PREDICTION.md) for the model and interview explanation.

## Setup (verified on Windows / PowerShell)

Run from this project directory. The verified versions are Python **3.14.3**, Node **24.19.0**, pnpm **11.19.0**, and `poke-env` **0.16.1**. Showdown is pinned to `2f5b273925862ac242b419086c1e7a8868b51da1`. Git is needed for the engine checkout and provenance checks. The setup uses normal development dependencies only, with no models or datasets.

```powershell
# Makes the existing bundled Git/Node/pnpm available in this terminal, if present.
. .\scripts\env.ps1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\scripts\setup-showdown.ps1
```

On a machine without the bundled tools, install the pinned versions and put `node`, `git`, and `pnpm` on PATH first. If npm is already available, `npm install --global pnpm@11.19.0` provides the pinned package manager. That alternative bootstrap has not been tested here. Only Windows has been verified; the Python runner contains portable process handling, but no cross-platform claim has been tested.

Run `. .\scripts\env.ps1` in **each new PowerShell terminal** before server commands. The system now also has Node 24.20.0; the project correctly rejects it until the pinned 24.19.0 bundle is selected. V3 adds no dependencies; `requirements.lock` remains unchanged.

The setup script uses a shallow official-engine checkout under ignored `.local/`, installs production dependencies from the saved pnpm lock, and installs esbuild's small platform executable. Optional native database packages and dev tools are omitted. Its esbuild installer may print an npm fallback warning when npm is absent; the upstream direct-registry fallback successfully installed the binary here. It refuses to overwrite a differing existing server configuration or change a different checkout. Third-party license files remain in the checkout and installed distributions.

## Run

The managed-server option is the easiest path. It starts the reviewed server on `127.0.0.1`, runs the command, and shuts it down. It refuses to take over an occupied port.

```powershell
.\.venv\Scripts\python.exe -m battlemind doctor --start-server
.\.venv\Scripts\python.exe -m battlemind battle --start-server --agent-a random --agent-b max-base-power --battles 20 --seed 42 --output runs/my-smoke
.\.venv\Scripts\python.exe -m battlemind report --run runs/my-smoke
```

Milestone 2 comparison: each 24-game run covers every pair of the four teams with both assignments and both player sides. These are small restricted-pool checks, not held-out performance estimates.

```powershell
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/milestone2.json --agent-b random --output runs/my-m2-random
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/milestone2.json --agent-b max-base-power --output runs/my-m2-max
.\.venv\Scripts\python.exe -m battlemind report --run runs/my-m2-random --audit
```

An output directory must be new; runs never overwrite earlier logs. Omit `--output` to create a timestamped directory. With the venv activated, the shorter `python -m battlemind ...` commands work as well.

## V3 count prediction and comparison

These commands build an audited dataset from the two retained M2 runs, split whole battles into count-estimation and development-check partitions, and save immutable smoothed frequencies. Previously reported M2 games remain development evidence. Use fresh output names if the example files already exist.

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m battlemind dataset --runs runs/m2-comparison-random runs/m2-comparison-max-base-power --output datasets/my-v3-development --seed 2026
.\.venv\Scripts\python.exe -m battlemind predictor-fit --dataset datasets/my-v3-development --output models/my-v3-counts.json
.\.venv\Scripts\python.exe -m battlemind predictor-evaluate --dataset datasets/my-v3-development --predictor models/my-v3-counts.json --partition development_check --output runs/my-v3-development-quality
.\.venv\Scripts\python.exe scripts/benchmark-v3.py --predictor models/my-v3-counts.json --output runs/my-v3-acceptance
```

The fixed benchmark runs constant, conditional and unchanged V2 policies against random and MaxBasePower: **six 24-game cells, 144 games total**, one battle at a time and a 600-second overall budget. It writes a pre-run freeze manifest, copies the predictor into every run, audits decisions, builds a fresh evaluation dataset, compares Brier score/log loss/calibration, and saves content hashes. No counts or rules are updated during evaluation. A new clone without ignored M2 artifacts first needs bounded local development runs; do not fabricate fixture data as performance evidence.

For one smaller run:

```powershell
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/v3-battle.json --predictor models/my-v3-counts.json --agent-a switch-context --agent-b max-base-power --battles 4 --output runs/my-v3-probe
.\.venv\Scripts\python.exe -m battlemind report --run runs/my-v3-probe --audit
```

Four games cover one team pair, not the complete four-team pool. `switch-constant` uses the same policy with the overall frequency. [PREDICTION.md](docs/PREDICTION.md) explains features, smoothing, uncertainty, scoring, evaluation and the important code paths.

For an explicitly managed server in another terminal:

```powershell
.\.venv\Scripts\python.exe -m battlemind server --seconds 600
# In a second terminal, from this directory:
.\.venv\Scripts\python.exe -m battlemind doctor
.\.venv\Scripts\python.exe -m battlemind battle --battles 2
```

`server` stops after the requested duration or Ctrl+C. Its log is printed at startup. The server config binds only to loopback, disables the REPL and file watching, runs with no child workers, and points login-server traffic at loopback. There is no public-ladder command or configurable remote host.

`doctor` checks pinned Python/Node/library/engine versions, clean tracked engine source, the reviewed configuration, `gen1ou` existence, singles/Gen 1 identity, every configured team through Showdown's validator, and the public species/type/move tables used by the heuristic against the engine. Use `configs/milestone2.json` to validate all four teams. It then checks the local WebSocket handshake. Without `--start-server`, the handshake checks connectivity; it does not independently attest that an arbitrary existing listener uses the checked-out engine.

Milestone 2 enables official challenge end logs. Managed battles place these under the run's `privileged/engine/`; the separate `server` command uses the checkout's `logs/`, and the recorder copies matching end logs into the run. These contain private teams and simulator RNG and must never be policy features. A custom server log directory is not supported by the collector; missing evidence produces unknown labels. When upgrading a Milestone 1 checkout, inspect the configuration difference and copy the reviewed `configs/showdown.config.js` into `.local/pokemon-showdown/config/config.js`. The setup script deliberately refuses an unexplained config mismatch.

## Limits and policies

`configs/smoke.json` has small defaults: 2 battles, concurrency 1, a 300-turn cap, 60 seconds per match, and 600 seconds for the run (including server startup). CLI options override that file: `--agent-a`, `--agent-b`, `--battles`, `--seed`, `--output`, `--concurrency`, `--turn-cap`, `--timeout`, `--run-timeout`, `--port`, `--showdown`, and `--config`. Team paths are configurable in JSON. Paths in the config are relative to the project directory, or absolute.

Only concurrency **1** and `gen1ou` are supported. Unsupported values fail explicitly. Hard limits are 100 battles, 1,000 turns, 300 seconds per match, and 3,600 seconds per run. Raising budgets or adding concurrency requires a deliberate future change. V5's sole policy-learning command additionally enforces its smaller fixed phase and aggregate allocations.

- **RandomLegalAgent:** samples uniformly from actual request-backed legal actions using its own seeded `random.Random`.
- **MaxBasePowerAgent:** selects the ordinary legal move with the highest Gen 1 listed base power. Ties use request order, even when all powers are zero. Fixed-damage moves use their listed value (e.g. Seismic Toss is 1), not calculated damage. When no ordinary move is offered, it uses the first engine action if available, otherwise the first legal original team slot. It ignores accuracy, STAB, matchups, survival, and strategy; it often chooses Explosion or Self-Destruct.
- **Gen1HeuristicAgent** (`gen1-heuristic`): scores power, nominal accuracy, STAB and type matchup, with explicit healing, status, setup, recharge, and self-KO rules. It switches only for a substantial improvement in visible matchup/health utility, with a two-turn cooldown; forced replacements use the best bench utility. Scores are arbitrary utility, not damage or win probability. All weights, ties and limitations are explained in [docs/HEURISTIC.md](docs/HEURISTIC.md), and each candidate score is logged.
- **SwitchAwareAgent** (`switch-constant` / `switch-context`): weights each damaging move's V2 utility against the current foe and possible switch destinations by a frozen switch probability. Both names use exactly the same scoring code. Revealed living bench Pokémon and anonymous unseen alternatives get equal destination weight; anonymous alternatives have neutral type utility. Status, healing and our switching rules retain V2 scores. This is an approximation, not a second simulator.
- **LearnedScoreAgent** (`learned-score`): starts with unchanged V4 logistic scores and applies four frozen, bounded score parameters. It retains forced replacements, engine actions, raw HP precision, unknown fields and request-backed legality. Training may change parameters only between complete batches; ordinary battles and evaluation cannot update them.

The schedule traverses unordered team pairs in four-game blocks: both assignments on both challenger sides. Four teams require 24 games for a complete block; two teams require 4. Shorter runs can be unbalanced. Policy seeds are independently derived from the root seed, match index, and agent label. **The server RNG is not seeded by this interface.** A repeated policy seed does not guarantee the same battles or results.

## Tests and results

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration
```

The full integration selection above includes game collection and V4/V5 training
scenarios; do not run it under V7's consumed functional budget. V7 ran only the
single new `tests/test_v7_integration.py` game, plus two browser demos. See
[V7-VERIFICATION.md](docs/V7-VERIFICATION.md) for its predeclared allocation.

Unit tests run offline. Explicit integration tests start and stop the pinned local server on available loopback ports; they preserve real smoke/limit logs under `runs/integration-*`. They also run bounded scenarios inside the official engine to verify Gen 1 requests. These test scenarios are never counted as evaluation games.

See [docs/STATUS.md](docs/STATUS.md) for actual acceptance results and known limitations, [docs/SCHEMA.md](docs/SCHEMA.md) for the information boundary, [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for verified source details, and [docs/PROJECT.md](docs/PROJECT.md) for the full staged vision.

## One decision

`LocalPlayer` receives a request through `poke-env`. `adapter.snapshot()` copies own request data and the public history into frozen dataclasses. It pairs semantic choices such as `move:psychic` and `switch:2` with commands for that request. The policy sees only the immutable snapshot and returns one ID. `resolve_action()` checks it against that snapshot's legal set and request number. A separate journal for that player records the snapshot hash, mapping, intended choice and scores before submission. Later messages reveal the outcome. Neither policy gets the other's submitted choice.

After both clients stop, the recorder reads both journals and the official end log. Engine `inputLog` entries prove which choices were committed after all required sides chose. Exact sequence matches get intended-choice labels; a mismatch makes the remaining sequence unknown. Public announcements provide separate execution evidence. A verified opponent label points to the **other player's pre-decision snapshot**, not the choosing opponent's private observation. V3's offline dataset builder uses that join; only visible context categories enter count estimation. `report --audit` rebuilds labels and, for V3, recomputes predictions, candidate scores and chosen actions from the frozen run artifact.

The engine and networking library are reused infrastructure. BattleMind's main contributions here are its information boundary, understandable utility policy, request mapping, post-commit evidence alignment, bounded orchestration, audits, and tests. See [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md).
