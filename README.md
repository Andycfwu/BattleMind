# BattleMind

A local Pokémon Showdown player and experiment harness. **Milestones 1 and 2:** three transparent baselines, four legal teams, immutable observations, bounded battles, and intended-choice labels checked against the official engine's committed inputs. No predictor, training, frontend, hosted service, API key, or GPU is involved.

The research question for later milestones is whether a learned opponent predictor improves the **same** decision-making system. This repository currently proves that the local pipeline works. It does not establish competitive strength.

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

Only concurrency **1** and `gen1ou` are supported. Unsupported values fail explicitly. Hard limits are 100 battles, 1,000 turns, 300 seconds per match, and 3,600 seconds per run. Raising budgets or adding concurrency requires a deliberate future change. There are no training loops.

- **RandomLegalAgent:** samples uniformly from actual request-backed legal actions using its own seeded `random.Random`.
- **MaxBasePowerAgent:** selects the ordinary legal move with the highest Gen 1 listed base power. Ties use request order, even when all powers are zero. Fixed-damage moves use their listed value (e.g. Seismic Toss is 1), not calculated damage. When no ordinary move is offered, it uses the first engine action if available, otherwise the first legal original team slot. It ignores accuracy, STAB, matchups, survival, and strategy; it often chooses Explosion or Self-Destruct.
- **Gen1HeuristicAgent** (`gen1-heuristic`): scores power, nominal accuracy, STAB and type matchup, with explicit healing, status, setup, recharge, and self-KO rules. It switches only for a substantial improvement in visible matchup/health utility, with a two-turn cooldown; forced replacements use the best bench utility. Scores are arbitrary utility, not damage or win probability. All weights, ties and limitations are explained in [docs/HEURISTIC.md](docs/HEURISTIC.md), and each candidate score is logged.

The schedule traverses unordered team pairs in four-game blocks: both assignments on both challenger sides. Four teams require 24 games for a complete block; two teams require 4. Shorter runs can be unbalanced. Policy seeds are independently derived from the root seed, match index, and agent label. **The server RNG is not seeded by this interface.** A repeated policy seed does not guarantee the same battles or results.

## Tests and results

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration
```

Unit tests run offline. Explicit integration tests start and stop the pinned local server on available loopback ports; they preserve real smoke/limit logs under `runs/integration-*`. They also run bounded scenarios inside the official engine to verify Gen 1 requests. These test scenarios are never counted as evaluation games.

See [docs/STATUS.md](docs/STATUS.md) for actual acceptance results and known limitations, [docs/SCHEMA.md](docs/SCHEMA.md) for the information boundary, [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for verified source details, and [docs/PROJECT.md](docs/PROJECT.md) for the full staged vision.

## One decision

`LocalPlayer` receives a request through `poke-env`. `adapter.snapshot()` copies own request data and the public history into frozen dataclasses. It pairs semantic choices such as `move:psychic` and `switch:2` with commands for that request. The policy sees only the immutable snapshot and returns one ID. `resolve_action()` checks it against that snapshot's legal set and request number. A separate journal for that player records the snapshot hash, mapping, intended choice and scores before submission. Later messages reveal the outcome. Neither policy gets the other's submitted choice.

After both clients stop, the recorder reads both journals and the official end log. Engine `inputLog` entries prove which choices were committed after all required sides chose. Exact sequence matches get intended-choice labels; a mismatch makes the remaining sequence unknown. Public announcements provide separate execution evidence. A verified opponent label points to the **other player's pre-decision snapshot**, not the choosing opponent's private observation. No dataset or training pipeline exists yet. `report --audit` rebuilds labels and checks hashes, request/choice mappings, submissions and per-battle label counts.

The engine and networking library are reused infrastructure. BattleMind's main contributions here are its information boundary, understandable utility policy, request mapping, post-commit evidence alignment, bounded orchestration, audits, and tests. See [docs/ATTRIBUTION.md](docs/ATTRIBUTION.md).
