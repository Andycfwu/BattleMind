# V7 functional verification specification — before fresh games

V7 consolidates existing evidence. It does not authorize another V6 attempt,
training, adaptation tuning, opponent changes or a new performance benchmark.
Both incomplete V6 attempts remain historical evidence. Their current status is
preserved byte-for-byte as MILESTONE6-REPAIR.md, SHA-256
`cd6e9590e617701aca4089c68a029a465446790ca4bf43757c0527a85dbc5b29`.

## Allocation and stop conditions

At most **three fresh games total**, within **300 seconds aggregate run time**:
one explicit integration game (75-second run ceiling, 60-second game timeout),
and two browser-launched functional demo games (75 seconds each). Combined
reservation 225 seconds leaves 75 seconds for preflight/audit overhead. This is
below the user ceiling of eight games. All use 300 turns, concurrency one, the
pinned engine and loopback. No other game-producing regression tests are run.
Unit tests, retained evidence replay, UI playback and bundle import collect zero games.

The integration game uses frozen learned-score versus MaxBasePower, seed 71901.
Browser demos are learned-score versus MaxBasePower and Gen1Heuristic versus Random,
seeds 71001/71002. These are independent functional schedules, not a balanced
comparison or evidence of strength. No simulator randomness is matched. A natural
cap remains a cap; it may be followed by the next independently scheduled demo
only after valid audits and cleanup. Stop on corrupt evidence, private-channel
leakage, unexpected protocol/errors, failed cleanup or exhausted limits. No retry
for a prettier outcome. Existing acceptance ledgers remain untouched.

Each service gets a fresh ignored output and single-use ledger. The two-game
demo reserves before launch, records actual elapsed monotonic time and refuses
new work without a full 75-second remaining run allocation. Playback controls
do not communicate with policies. No decision delay is added. V6 live adaptation
is intentionally unsupported; four chronological retained encounters demonstrate
actual public memory and deterministic replay starting from empty memory.

## Verification coverage

- All fast existing unit checks and focused V7 projection/path/budget/accounting tests.
- One real spectator → completed/capped record → private commitment/scoring audit.
- Browser startup, official animation, pause/play, speed, turn navigation, completed
  result, preserved freeze-cap state and post-encounter explanation.
- Browser content security policy and recorded HTTP routes: no external runtime
  assets, scripts, fonts, audio, public services, account module or telemetry.
- Exact HTTP endpoint map excludes models, snapshots, private logs and memory audit
  inputs. State-changing requests require a local Host, same-origin JSON and token.
- Export/import in an isolated temporary directory, exact hashes, original V4/V5
  compatibility loaders and public-only chronological replay. No fitting or updates.
- Retained artifact manifests and terminal accounting read-only; semantic audit
  coverage and current source compatibility described separately.
- Stop command cleans the viewer and all managed engine/client processes/listeners.

Functional games/test artifacts are reported separately from V1–V6 experiments.
No outcome in V7 changes any historical conclusion or policy.
