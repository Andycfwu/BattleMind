# Verified compatibility

V4 intentionally adds no runtime download: NumPy 2.5.2 was already locked and is
now declared directly in the optional `train` extra. Python 3.14.3, Node 24.19.0,
poke-env 0.16.1 and the official engine pin are unchanged. Logistic inference uses
Python math; training uses NumPy float64 linear algebra. Before V4 runner parameter
plumbing, the installed `player.py` message/request methods (approximately lines
295–420) were read again. Their chronological parsing, sending, error handling and
the existing BattleMind hook implementations were not changed. V4 regression tests
exercise a batched future message with the logistic policy and real local
record/training/inference/audit behavior.

V3 rechecked the pinned installation on 2026-09-08. The system PATH now also contains Node 24.20.0; source `scripts/env.ps1` to select the existing pinned 24.19.0 runtime. An initial integration invocation correctly failed its version guard (seven cases failed preflight, one engine probe passed); the pinned invocation subsequently passed all eight cases. No version pin was loosened and no dependency was added.

Before adding prediction logging, installed `poke_env/player/player.py` request/message dispatch and `choose_move` handling were inspected again. V3 extends BattleMind's own `choose_move` hook to call the snapshot-only policy evaluation once and journal it before submission. Chronological request processing, error handling, post-match label hooks, installed wrapper code and engine source remain unchanged. The batched-future-message regression now also runs with the conditional policy.

Checked on 2026-09-05 against current official documentation and the actual installed source. The environment is Windows 11 Home x64, Intel i7-11700KF (8 cores / 16 logical processors), about 39.9 GiB visible RAM. The system Python was available on PATH. Git, Node, and pnpm were discovered in the local bundled runtime; no GPU was used.

| Component | Selected version |
|---|---|
| Python | 3.14.3 |
| poke-env | 0.16.1, PyPI distribution; MIT |
| Node | v24.19.0 |
| pnpm | 11.19.0 |
| Pokémon Showdown | 0.11.11, commit `2f5b273925862ac242b419086c1e7a8868b51da1`; MIT |
| Python transitive packages | Exact versions in `requirements.lock` |
| Engine packages | Exact resolution/integrity in `configs/showdown-pnpm-lock.yaml` |

The Python package intentionally supports the tested 3.14 minor version; `doctor` requires the selected patch versions. Loosening these requirements should be accompanied by verification. This is a source checkout installed in editable mode, with configurations/scripts resolved from its root. Standalone wheel distribution is outside this milestone.

## Documentation versus source

The official [`poke-env` getting-started guide](https://poke-env.readthedocs.io/en/stable/getting_started.html) describes local server connections and shutdown. Its Node minimum is older than the current engine CLI recommendation. The checked-out Showdown `pokemon-showdown` executable uses modern Node APIs and recommends Node 22 or later; selected Node 24.19.0 successfully built and ran it. The engine package metadata's older minimum alone was not treated as sufficient evidence.

Verified installed interfaces: `poke_env.player.Player`, top-level `AccountConfiguration` and `ServerConfiguration`, `Battle.last_request`, `Battle.parse_request`, `SingleBattleOrder(str)`, `Player.battle_against`, and `PSClient.stop_listening`. `Player`'s constructor was given the actual asyncio loop, explicit local endpoints, no password, and concurrency 1. Its imports and lifecycle were checked against installed 0.16.1, rather than copied from an old tutorial.

The private hooks `_handle_battle_message` and `_handle_battle_request` are version-sensitive. BattleMind overrides them to maintain chronological public snapshots, bound every decision, and suppress the library's random default-choice retry after errors. Tests cover message batching, requests parsed by real `Battle` objects, and real server games. No library source was modified.

The checked-out `server/config-loader.ts` maps `--no-security` to `nothrottle`, `noguestsecurity`, and `noipchecks`. Those settings are explicit in the reviewed config instead of relying on a remembered flag. `server/sockets.ts` uses `bindaddress`; the fixture sets `127.0.0.1`. The config also disables REPL/file watching, uses no worker subprocesses, and directs the login server to `127.0.0.1:1`. No login server is needed for password-free local guest accounts.

## Gen 1 support boundary

The open upstream [issue #753](https://github.com/hsahovic/poke-env/issues/753) identifies wrapper limitations involving status/stat interactions, overflow, Counter damage, shared residual-damage counters, and partial trapping duration. These are not defects in Showdown's authoritative rule resolution. They are reasons not to use wrapper-derived quantities as exact policy features.

BattleMind's workaround is narrow: own actions come from the current engine request; opponent HP/status/moves/displayed stages come from this client's public protocol. Derived effective stats and counters remain unknown. We do not calculate damage, Counter values, residual increments, partial-trap duration, or stat overflow. No alternate format or replacement simulator was introduced.

Source and behavioral checks:

- `sim/pokemon.ts` emits `Fight` for Gen 1 sleep/freeze/partial-trapping states, `Recharge` when required, and `Struggle` after usable PP is exhausted. These pseudo-actions cannot be treated as ordinary move metadata. The first real probe uncovered the omitted `Fight` case; the failure is retained under `runs/initial-probe`.
- Gen 1 partial trapping can still allow switching. The official-engine regression scenario verifies that a `Fight` request also retains legal switches. The adapter follows `trapped` and `forceSwitch` rather than inferring restrictions from public effects.
- `scripts/probe-gen1.cjs` resolves actual moves inside the official engine, using bounded fixed-seed scenarios for sleep, Wrap, non-KO Hyper Beam, Explosion replacement, and real PP exhaustion. Its resulting requests pass through the installed wrapper and adapter in integration tests. These controlled engine probes are unit-like mechanics evidence, not game-performance results.
- Every move in the configured fixture teams is checked by `doctor` for agreement between Showdown's Gen 1 listed base power and `GenData.from_gen(1)`. M2 also verifies species types, move type/nominal accuracy/status/self-destruction/multihit metadata consumed by the heuristic, fixed-damage immunity exceptions, and the complete 15-type Gen 1 chart. This includes generation-specific powers such as Explosion 170 and Blizzard 120. No exact damage claim follows from that agreement.
- Initial fixtures without explicit EVs were rejected by the current validator. Explicit 252 EVs in all six exported stat fields were added; both six-Pokémon teams now validate in `gen1ou` through the official `TeamValidator`.
- M2 adds two six-Pokémon teams with sleep, Wrap/Clamp, setup, fixed multihit, recovery and varied type matchups. All four pass the pinned official validator with `doctor --start-server --config configs/milestone2.json`.
- `data/mods/gen1/moves.ts` lines 644–650, 679–685 and 783–789 contain the Recover/Rest/Soft-Boiled 255/511 HP failure and modulo exception. The heuristic uses only this narrow exact-own-HP guard; unit tests cover the exception. It does not simulate recovery.
- The wrapper's move table can retain modern physical/special categories (for example Hyper Beam is listed Special). The heuristic never consumes this category or computes effective stats from it. Its matchup utility uses power/type/accuracy only.
- The pinned wrapper warns when Gen 1 repeats a partial-trapping move with an extra `[from] Wrap` or `[from] Clamp` annotation. It strips that suffix and continues. The public tracker consumes the move ID independently; current actions still come from the engine request. Eight such client warning records remain in the random comparison, with zero action failures. Tests recognize only this narrow warning; unknown warnings are not silently accepted.

Public protocol references: [Showdown simulator protocol](https://github.com/smogon/pokemon-showdown/blob/2f5b273925862ac242b419086c1e7a8868b51da1/sim/SIM-PROTOCOL.md), [client/server protocol](https://github.com/smogon/pokemon-showdown/blob/2f5b273925862ac242b419086c1e7a8868b51da1/PROTOCOL.md), and the installed engine source. Snapshot projection is intentionally scoped to the versioned pool and tested Gen 1 behavior. Transform, Mimic, Metronome, and other moves outside the pool are not claimed as fully modeled; future team expansion requires observation tests before broader claims.

## M2 commitment hooks and evidence

Before changing hooks, the installed `.venv/Lib/site-packages/poke_env/player/player.py` and `ps_client.py` were inspected again: request dispatch, room message locking, send completion, cleanup and task tracking. Hook overrides remain pinned to **0.16.1**. Neither installed wrapper nor tracked engine source was edited.

The recorder uses existing official engine end logs instead of treating a network send as a locked decision:

- [`sim/battle.ts`, `commitChoices()`](https://github.com/smogon/pokemon-showdown/blob/2f5b273925862ac242b419086c1e7a8868b51da1/sim/battle.ts#L2998) requires `allChoicesDone()`, appends each `side.getChoice()` to `inputLog`, then clears requests and resolves the turn.
- [`sim/side.ts`, `getChoice()`](https://github.com/smogon/pokemon-showdown/blob/2f5b273925862ac242b419086c1e7a8868b51da1/sim/side.ts#L323) serializes normalized move IDs and current request switch indices. Some uncertain Gen 1 requests normalize an attempted move into Fight; exact disagreement stays unknown.
- [`server/room-battle.ts`](https://github.com/smogon/pokemon-showdown/blob/2f5b273925862ac242b419086c1e7a8868b51da1/server/room-battle.ts#L797) increments request IDs separately for each player. Equal turn number alone is insufficient pairing evidence. `sentchoice` is reconnect state, not a normal commitment acknowledgment.
- The same file's `logBattle()` writes a full end record when `Config.logchallenges` is enabled. Files use `gen1ou-N.log.json`, while their `roomid` uses `battle-gen1ou-N`. The collector checks both room identity and the two unique local usernames. Raw records include privileged state and stay under `privileged/`.

`scripts/probe-labels.cjs` proves in the official engine that the first submission alone does not append an input action, the second commits both, and a committed Growl never announces when its user faints first. It also verifies two simultaneous forced replacements wait for both required choices. Offline tests cover distinct request IDs, voluntary/forced distinctions, mismatches, missing logs, uncommitted attempts, game-effect drag, and public execution evidence. Real integration tests audit completed matches, caps/timeouts, managed logs and separate-server copies.

The reviewed config now enables challenge logs and takes an absolute `BATTLEMIND_LOG_DIR` supplied by the local launcher. The directory is created before server startup, and startup `CRASH:` reports fail health validation. A first probe exposed a missing-directory logging error and wrong filename lookup; those artifacts are retained in `STATUS.md`.

## Reproducibility limits

The Showdown checkout's commit and clean tracked source are checked. The client validates fixture files with that checkout before running. Managed mode launches that checkout; manual mode checks a local handshake without proving the identity of an independently started process. Python and server locks make dependencies repeatable, and run manifests include file hashes rather than inventing a Git version for an uncommitted directory.

The challenge interface used here does not set the simulator seed. Only policy RNGs and the deterministic match schedule are controlled. A fresh 20-match run can differ from recorded results even with `--seed 42`. Exact battle replay determinism is explicitly false in metadata.

Metamon has not been installed, downloaded, or integrated. Its licensing, model/data sizes, format support, and replay observation assumptions remain a later investigation; no compatibility claim is made here.
