# Player boundary and run records

Milestone 2 uses observation schema **1.1**, decision/battle/label schema **2.0**, and the backward-compatible accounting summary schema **1.0** with additional fields. Milestone 1 logs retain their original schemas and have no verified labels.

All policy-visible values are nested frozen dataclasses containing primitives and tuples. The policy interface is `choose(DecisionSnapshot) -> str`. The adapter alone sees the player's current request. `PublicTracker` sees only messages delivered to that client and applies a small allowlist; it is a protocol projection, not a battle engine. Its mutable records are copied before every decision.

## Observation

- `format`, `turn`, `request_id`, `request_kind`, and `trapped`: current request context. Wait requests produce no decision. Team preview and uncertain trapping are rejected explicitly in this Gen 1 implementation.
- `maybe_locked` and `maybe_disabled`: the player's request flags, retained as uncertainty. These exclude the decision from binary switch-versus-move eligibility; they are not assertions of the opponent's options.
- `own_team`: species, original team slot, active flag, exact request HP fraction, status, all own request move IDs, and displayed boost stages. Original slots are retained even if Showdown reorders the request; commands use the current request indices. Nicknames remain internal keys and never enter features.
- `opponent_revealed`: only Pokémon introduced by a public switch/drag message, indexed by reveal order, **not** their hidden team positions. Each view contains publicly shown HP numerator/denominator, status, displayed stages, and move IDs actually announced in earlier public messages. Publicly called moves would be evidence of an observed move, not proof of a permanent moveset.
- `opponent_team_size` comes only from `teamsize`; `opponent_unseen` is the corresponding unrevealed count. Both remain `null` when total size was not announced. There are no invented Pokémon placeholders containing species.
- `legal_actions`: semantic ID, kind (`move`, `switch`, `engine`), optional move ID / own team slot / listed base power. `Fight`, `Recharge`, and `Struggle` are explicit engine choices when requested. A request with no supported choices fails visibly; it never invents `/choose default`.
- `public_history`: immutable events up to the decision, with turn, event kind, canonical `own:N` / `opponent:N` actor, and whitelisted values. Includes switches, announced moves, HP/status changes, displayed boosts, fainting, inability to act, and public effects. It excludes chat, names, requests, choices, team-file IDs, winners, and runner metadata. It does not claim to be a complete replay or exact Gen 1 state.

`null` denotes unknown/unsupported information, not zero. Healthy is the explicit string `healthy`; fainted is `fnt`. Own `hidden_moves=[]` and `moves_complete=true` indicate a complete own request move list. Opponent `hidden_moves=null` and `moves_complete=false` retain uncertainty. An empty revealed list means **nothing revealed yet**, not no moves. `effective_stats` and `gen1_derived_counters` remain `null`.

HP uses `exact` for our request fraction, `public_scale` for an opposing fraction exactly as shown (e.g. `49/100`, without treating it as exact HP), and `fainted` for `0 fnt` without an invented maximum. Public boost stages are displayed stages only; they do not incorporate Gen 1 status reapplication, overflow, or other hidden derived effects.

The pinned message hook processes one line at a time. If one transport batch contains a request followed by a future move announcement, the snapshot is frozen before that later line is parsed. An offline behavioral test exercises exactly this boundary. Another test mutates an actual wrapper's opponent moves, HP, stats, unseen team, name, and final result while holding request/history fixed; the observation remains identical.

## Artifacts

Every run directory is created exclusively and contains:

| File | Contents |
|---|---|
| `run.json` | Configuration, version checks, team hashes, source/config/script file hashes, OS/CPU/RAM, policy seeds and simulator-seed limitation |
| `decisions.jsonl` | Per-player journals merged only after both clients stop; frozen observation, snapshot hash, unique decision ID, full legal mapping, chosen semantic ID, request-bound command and heuristic candidate scores |
| `events.jsonl` | Client send completions (not engine acknowledgments), terminal results for each perspective, and client/server/adapter warnings/errors |
| `battles.jsonl` | One terminal accounting row per scheduled match, including status, outcome, actual terminal messages, cap/failure reason, turns, time, decision counts, seeds, assignments, and challenger |
| `summary.json` / `summary.csv` | Recomputed accounting from `battles.jsonl` |
| `resources.json` | Wall time, Python CPU time and sampled RSS, managed-server sampled RSS and last CPU sample; external-server resources explicitly unmeasured |
| `server.log` | Official server stdout/stderr when the run owns the server |
| `privileged/attempts/NNN-a.jsonl`, `NNN-b.jsonl` | Separate live journals per player; no reading or joining the other journal during decisions |
| `privileged/engine/**` or `privileged/NNN-engine.json` | Official end logs, including private teams/RNG and committed `inputLog`; never feature input. The terminal battle row records the path and SHA-256 |
| `privileged/NNN-histories.json` | Each client's final public projection, retained only for post-decision execution evidence |
| `privileged/labels.jsonl` | One verified or explicitly unknown label record for every attempted policy choice |

The outer decision rows and run metadata are **recorder data**, not policy inputs. They must not be blindly concatenated into future feature vectors. Both perspectives are logged locally but are never read back by policies. The policy receives only its `DecisionSnapshot`; its own raw request, recorder, mapping and other player's objects are not policy arguments.

## Intended-choice evidence

An attempted choice is not necessarily committed, and a committed choice is not necessarily executed. A client submission event means `send_message` returned. It cannot prove commitment. In the pinned official engine, `commitChoices()` appends both required sides' choices to `inputLog` only after `allChoicesDone()`, before resolving actions. The recorder waits until clients stop and reads this official end log. It checks the battle tag and both unique local usernames when locating evidence; those names never enter snapshots.

Each decision ID is `m<match>:<a/b>:r<rqid>`, scoped to its run. `snapshot_sha256` hashes sorted, canonical JSON of the immutable observation. The recorder compares each side's attempted sequence to the engine's normalized sequence: `move <move-id>` or `switch <current-request-index>`. Complete games require matching sequence lengths. Incomplete games can establish only an exact committed prefix. A mismatch invalidates that side's remaining suffix; the recorder never searches ahead for a convenient repeated move. Missing end logs, uncommitted attempts and mismatches retain an explicit `unknown_reason`.

Verified labels distinguish `move_choice`, `voluntary_switch`, `forced_replacement`, and `engine_action`; all other cases are `unknown`. Forcedness comes from that player's frozen request, not from the public animation. `drag` remains a game-effect event, never proof of a player's intended switch.

Binary `voluntary_switch_target` is 1 or 0 only when the verified choosing player had both an ordinary move and a switch, with no engine action or uncertain lock/disable flag. Forced replacements and Fight/Recharge/Struggle cases are excluded; uncertain legality gives `null`. This conservative eligibility may discard real voluntary choices. It avoids pretending that every turn offered a genuine move/switch decision.

For future opponent prediction, the label points to `observer_decision_id` and `observer_snapshot_sha256`: the **other player's** pre-decision observation at the same committed decision point. Request IDs differ between players. Pairing requires exactly one verified ordinary request per side on that turn, with adjacent official committed input entries. Forced/wait cases have no synthetic observer decision. Target counts include only completed battles and valid pairs. A later dataset builder must use this observer join, exclude recorder-only fields, and split by whole battle. This milestone does not construct or train a dataset.

## Execution evidence and auditing

For each verified intended choice, the recorder examines that client's public history after the frozen snapshot and before its next decision (or the final history). The earlier history must be an exact prefix. `move_announced` means a matching move announcement, **not** that it hit or had an effect. `switch_observed` requires a matching public switch. `prevented_or_engine_wait` records a public `cant` event. `not_announced` means no matching announcement in a completed stream, without guessing why. Incomplete, conflicting or missing evidence stays `unknown`. Event indices preserve the evidence window.

`report --audit` checks one-to-one decision/label IDs, snapshot hashes, chosen-action membership and command mapping, official end-log hashes, matching battle identity, client submission records, and per-battle label counts. It rebuilds all labels from retained inputs and public histories and requires exact agreement. It does not claim cryptographic authentication of files against a malicious local editor, and it does not prove a move caused damage.

The expanded pool exposed a legitimate ambiguity: a request offered Hyper Beam with `maybeLocked`, but the engine committed `move fight` during Clamp. The submitted ID remains in the attempt log, while that side's unmatched suffix has unknown committed-choice labels. This is preserved in `runs/m2-comparison-random`, not relabeled by guessing from subsequent events.

## Accounting

Only compatible terminal outcomes from **both** players without any earlier failure count as `completed`. Completed outcomes are A win, B win, or draw. Win rate uses all completed games as denominator, with draws contributing no win. Truncations, timeouts, crashes, cancellations, and not-started scheduled games are separate. The run aborts after a crash/timeout/cancellation; remaining schedule rows stay `not_started`. Caps can continue to the next scheduled match.

At a turn cap, the runner declines decisions for the next turn and cleans up with a forfeit. The observed boundary turn can therefore be cap + 1; no policy decision beyond the cap is sent. Timeout and error cleanup may also produce an engine forfeit result. These terminal messages are retained for audit but never converted to wins. Invalid/unavailable choices are visible incidents and abort the match, with no library random fallback.

`report` can rebuild a partial run's summary; `unrecorded` shows missing rows if the process was forcibly killed before finalization. Graceful cancellation writes remaining rows. A hard process kill or OS crash cannot guarantee final log writes.

M2 reports also include label coverage and exclusions, completed team/side cells, client warnings, and server `CRASH:` records separately from terminal match failures. A narrow known-warning classification recognizes the pinned wrapper's Wrap/Clamp trailing annotation cleanup; the original warnings remain in `events.jsonl`. The Wilson interval is a descriptive completed-game interval for the restricted schedule, not a claim about human opponents or all Gen 1 teams.

Resource peaks are samples at 0.1-second intervals, not exact OS lifetime peaks. Wall time includes managed-server startup/shutdown but excludes preflight validation and dependency setup. Source hashes capture the code that ran; no Git commit was created.
