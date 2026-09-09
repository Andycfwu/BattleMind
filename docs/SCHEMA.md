# Player boundary and run records

## V7 viewer and artifact records

V7 adds separate schemas; it does not revise historical observations, commitment
joins, memory summaries or scientific checkpoint compatibility.

- `v7-public-replay-1`: public protocol lines, normalized side identities, explicit
  origin/status/outcome, limitations and source hashes. Live data comes from an
  independent channel-0 guest spectator. Historical exports align the clients'
  public histories and use only the opposing observer's view for each actor's HP.
  Missing annotations are not reconstructed from private end logs. A winner/tie
  is permitted only for a genuine completed game; caps, cleanup and interruptions
  keep `outcome=null`. Unknown teams remain unrevealed in the display.
- Explanations are optional post-encounter own-player records: decision ID,
  snapshot digest, actual numeric scores/probabilities, chosen ID, shadow or
  initial alternatives and memory digest where recorded. They contain no live
  snapshot, current opponent choice or private engine data. They never feed play.
- `v7-demo-bundle-1`: a bounded safe ZIP/JSON closure, exact file hashes, pinned
  renderer identity, original V4/V5 hashes, source compatibility requirements and
  provenance. The offline V6 trace contains only the observing player's snapshots,
  public records, own journal and memory states. It is excluded from HTTP routes,
  as are models, checkpoints, private logs and source files. Existing model loaders
  and public memory replay validate import in an isolated temporary directory.
- `v7-demo-budget-1`: a fresh single-use functional ledger with actual requests,
  maximum games, aggregate monotonic run seconds, per-run summaries and audits.
  A full 75-second reservation is required to start; playback consumes zero games.
  It does not resume or mutate a historical experiment ledger. `service.json`
  holds a local control token and is never exported in a bundle.
- `v7-evidence-1`: read-only terminal counts recomputed from retained rows, scope,
  hashes, populations, phases, scientific reports, issues and audit limitations.
  Missing/zero-example metrics stay unavailable; planned slots are not requests.
  Original V6's zero final requests and old timing limitations are explained
  without rewriting its records. Mixed A/B totals are accounting, not a ranking.

See [V7.md](V7.md) for routing, pacing and projection limits. Integrity against
retained manifests, semantic replay coverage and current source compatibility are
reported independently. No historical full-source audit has been weakened.

V2 uses observation schema **1.1**, decision/battle/label schema **2.0**, and accounting summary schema **1.0** with additional fields. V3 keeps that observation and label boundary, adds decision schema **3.0** for prediction decisions, and adds separate dataset/count/probability-report schemas. Legacy policy decisions remain 2.0. Historical V1 logs retain their original schemas and have no verified labels.

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

For opponent prediction, the label points to `observer_decision_id` and `observer_snapshot_sha256`: the **other player's** pre-decision observation at the same committed decision point. Request IDs differ between players. Pairing requires exactly one verified ordinary request per side on that turn, with adjacent official committed input entries. Forced/wait cases have no synthetic observer decision. Target counts include only completed battles and valid pairs. V3's dataset builder uses this observer join, excludes recorder-only fields from features, and splits by whole battle; see `PREDICTION.md`.

## V3 artifacts

- `prediction_evaluation` in a 3.0 decision records the numeric probability, mode, visible context, supporting counts/fallback, application flag, public/anonymous destination weights, candidate stay/switch/mixture utility, chosen action, and alternate constant/conditional/V2 choices on the same frozen snapshot. It never records a live opponent choice as a feature.
- `predictor.json` in each V3 run is an unchanged copy of the input count artifact. `run.json` records its SHA-256 and `evaluation_updates=false`. Only its frozen count table enters a policy; fit battle identities and provenance do not.
- A dataset has `examples.jsonl`, `exclusions.jsonl`, and `manifest.json` (`v3-dataset-1`). Example rows contain three visible context features, the binary target and recorder-only join/provenance fields. Only `features` enters the predictor. Split membership uses run-manifest hash plus match identity and keeps whole battles intact.
- A count artifact (`v3-counts-1`) records frozen global/context counts, smoothing configuration, feature definitions, fit/development membership and source hashes. It is an empirical frequency model, not a trained classifier.
- A probability report has `predictions.jsonl` and `summary.json` (`v3-probability-report-1`) with class balance, coverage/exclusions, Brier score, log loss, calibration and battle-level uncertainty. Eligibility comes from post-battle labels only; it is not copied into live policy inputs.
- A benchmark root has `freeze.json`, six run directories, `evaluation-dataset/`, `probability-quality/`, `summary.json` and `artifact-hashes.json`. Existing runs and models are never overwritten. `report --audit` additionally recomputes V3 prediction evaluations from the saved snapshot and frozen count table.

## V4 supervised extensions

`v4-dataset-1` retains the complete audited V3 join in `audited-context/` and adds
`visible-logistic-v1` vectors to the paired observer examples. The original three
categories must still agree. `target_player`, `target_policy` and `observer_policy`
are offline grouping fields only. Feature extraction accepts a `DecisionSnapshot`,
never the joined row. All other identity/request/hash/target fields are preserved.
Exclusions retain their original reason and partition and add target grouping
metadata. The manifest records full and primary-population balances, exclusions,
source hashes and the audited intermediate manifest hash. Primary means runner-b
eligible decisions, not whichever engine side happens to be p2.

`v4-supervised-1` is a plain JSON bundle of a frozen `CountTable` and logistic
coefficients/intercept/preprocessing. It includes feature definitions, encoded
column order, regularization search/convergence, train/validation/development keys,
selected-population hashes/balance, software, source hashes and training resources.
No source or label identity is part of `PredictorBundle` passed to policies.
Datasets and models remain ignored generated files; unsupported schemas and
train/evaluation overlap fail explicitly.

V4 extends the 3.0 decision's `prediction_evaluation` with `logistic_choice`,
`predictor_version`, `predictor_sha256` and `alternate_probabilities`. Existing
fields and scoring semantics remain compatible. The raw snapshot is still 1.1.
The prediction's count-support fields refer to the fair baseline counts, including
when mode is logistic; they are not confidence or coefficient estimates.
`v4-probability-report-1` includes all three probabilities per eligible example,
group metrics, primary and full exclusions, calibration support and paired
whole-battle resampling. Run/decision/evidence hashes detect accidental changes;
they are not cryptographic authentication against a malicious local editor.

## V5 policy checkpoints and experiment records

The snapshot remains **1.1** with no new features or privileged fields. V5 adds to
`prediction_evaluation` the frozen four-parameter vector, checkpoint SHA-256,
`v5-residual-scores-1` scoring version, and initial-policy scores/choice on this
same snapshot. Existing alternate constant/count/logistic choices refer to the
unchanged V4 baseline scorer. `chosen_action` and `scores` record the played V5
policy. All of these outer evaluation fields are recorder output, never fed back
as observation features.

`checkpoint-a.json` / `checkpoint-b.json` are frozen `v5-policy-1` JSON copies.
`run.json.policy_checkpoints` records each input digest. The loader checks exact
field sets, finite parameter bounds, scoring-source hashes, predictor digest,
snapshot/feature/scoring versions and pinned version record. Only a
`FrozenCheckpoint(parameters, sha256)` enters the policy; provenance, parent IDs,
opponent identities and training outcomes remain in offline artifacts.

At the experiment root, `freeze.json` captures source/config/specification hashes
before training. `ledger.json` (`v5-ledger-1`) reserves requested games before each
cell starts, includes reserved final allocations, wall usage, all run results and
disjoint `SHA256(run.json):match` partitions. A missing result does not refund a
reservation. Phase order is training, selection, final. Resume is unsupported.
`rounds/round-N.json` freezes each proposal/seed/parent/pool before its games;
`rounds/update-N.json` points to completed training cells and records the outcome
contrast, arithmetic update and resulting checkpoint digest. No turn labels are
used as V5 rewards.

`selection.json` records the fresh selection games and declared tie rule;
`selected.json` copies the selected checkpoint verbatim. `final-freeze.json`
locks both evaluation arms and opponent panel before final games. Final outcomes
are reports only. `decision-comparisons.jsonl` re-evaluates initial and selected
choices on each final player-a snapshot, preserving run/decision/snapshot IDs.
`summary.json` reports phases, outcomes, warnings, labels, resource samples and
descriptive block intervals. `artifact-hashes.json` covers all earlier generated
files. Read-only `policy-report --audit` replays every decision/label audit and
reconstructs updates and selection from the appropriate completed-game partitions.

Hash checks detect accidental incompatibility; they are not authentication against
a malicious editor. A hard process kill can leave reserved-but-unrecorded games;
those are missing evidence, never ordinary rewards. Live player journals and exact
commitment matching below remain unchanged.

## V6 public memory and adaptation records

`DecisionSnapshot` remains **1.1**. No account, session, checkpoint, team-file or
target-policy identity is added to it. The underlying `visible-logistic-v1` features
and `v5-residual-scores-1` scoring implementation stay unchanged. The original V4
bundle and selected V5 checkpoint must pass their existing compatibility loaders.

A policy's immutable constructor `MemoryContext` contains only pooled and individual
`HistorySummary` values: version `public-encounter-residual-v1`, supported encounter
count, admitted example count and sum of per-encounter mean residuals. It contains no
registry, routing keys, source records or mutable manager. Both counts and residuals
are validated. Counts are support, not independent-turn confidence. A new summary is
constructed between encounters; the policy still receives only a frozen snapshot
on each decision. See [ADAPTATION.md](ADAPTATION.md) for the exact adjustment.

V6 files in each four-game cell:

- `run.json.adaptation` contains arm, opaque synthetic observer/session routing and
  version metadata **outside features**. Each arm/group owns a separate registry.
- `memory/NNN-before.json` records the frozen numeric context, its digest, global
  encounter ordinal, previous session encounter count and routing keys.
- `observer/NNN.json` contains only that observer's frozen snapshots, its own final
  public event projection, and completion flag. The runner exports this before
  post-match privileged recording. No winner, label or private engine field enters
  this file. Snapshot hashes and public-prefix indices identify chronological inputs.
- `memory/NNN-after.json` records every admitted/skipped evidence window and reason,
  public event references, earlier snapshot/request/turn, frozen base probability,
  admitted proxy, encounter residual and pre/post digests. Incomplete encounters
  contribute no memory update. Unknown, forced, engine and unannounced actions are
  retained as such; absence of a switch announcement never implies a move choice.
- The existing separate player journals and merged decision records gain outer
  `prediction_evaluation` fields: memory version/context/digest/mode, base V4
  probability, all three shadow probabilities and choices, support/fallback and
  played candidate scores. Only the designated arm controls play. Inherited V5
  fields describe that arm's probability/scoring; the explicit `none` shadow is the
  unchanged selected-V5 control. These output fields are never observation inputs.
- `adaptation-audit.json` records public replay and the separate private commitment
  audit. `memory_audit.replay_cell()` never opens labels or official end logs. It
  reconstructs memory only from the observer export, then checks predictions/scores
  and choices against that observer's saved journal. Private mutation may fail the
  commitment audit but cannot change public reconstruction.

At the experiment root, `freeze.json` records source/spec/config and required model
hashes; `predictor.json` and `checkpoint.json` are unchanged retained copies.
`ledger.json` (`v6-budget-1`) reserves final allocation before development, tracks
every requested cell and consumed time, and stores reset groups plus disjoint
`SHA256(run.json):match` identities. Memory-linked encounters stay in one partition.
No resume, refund, retry or borrowing is supported. `final-freeze.json` exists only
if completed development permits entry into final; it is **absent in the actual
budget-stopped V6 run**. No final memories or games were created there.

`shadow-predictions.jsonl` joins the three public-only predictions to eligible
privileged labels offline, preserving observer snapshot/decision and target joins.
`shadow-decisions.jsonl` also retains observer requests excluded from probability
evaluation. `public-updates.jsonl` summarizes memory admission/support per encounter.
`summary.json` reports phase outcomes, probability quality/calibration, exclusions,
coverage, choice differences, resources and audit status. `artifact-hashes.json`
protects the frozen output files. A later read-only audit verifies these hashes;
the original summary's `artifact_files: 0` reflects creation before the manifest,
not missing evidence. The completed CLI audit checked 1,064 files.

For the stopped run, `status: failed` means the experiment did not finish;
`audit.ok: true` verifies the **96 recorded encounters**, not acceptance completion.
Use `phases.final.requested_games: 0` for actual requests. The empty `final_battles`
grid retains the predeclared 192-game-per-arm allocation: its unrecorded values
describe planned final slots, not launched or failed games. No such slots become
outcomes. `runs/v6-development-review.json` supplies a separate, clearly exploratory
breakdown of the partial development rows by arm, target and cold/later encounters;
it does not modify the frozen experiment or its final reporting criteria.

One failed-phase timing limitation is preserved: repeated finalization charges
post-stop reporting/hashing to the still-active failed phase. The saved summary
captured development at 165.731s when collection stopped; the final ledger and
read-only report show 181.450s including that later overhead. Total experiment
wall is consistently 181.465s, and final usage is zero. See STATUS for the corrected
interpretation; no extra games ran during this difference and no ledger was edited.

## V6 acceptance repair accounting (new artifacts only)

The separately authorized replacement uses `v6-budget-2`, `v6-freeze-2` and
`v6-report-2`. No original ledger, summary or manifest is migrated. The original
96-game attempt remains development evidence and retains the limitations above.
The replacement's document/config are `V6-ACCEPTANCE-REPAIR.md` and
`configs/v6-acceptance-repair.json`; their paths and content hashes enter its freeze.
Snapshot, memory, proxy, predictor and scoring schemas are unchanged.

New reports expose an `accounting` object at experiment, phase and final-arm scopes:

- `planned_games`: the fixed schedule allocation.
- `reserved_games`: cells irrevocably admitted within that allocation, without
  refund. This differs from phase `allocation_reserved_games`, which protects all
  final capacity before development begins.
- `requested_games`: reserved games dispatched to the bounded runner. This counts
  requests to execute a schedule, not a claim that every game reached a challenge.
- `reserved_not_requested_games`: admitted capacity never dispatched.
- `never_requested_games`: planned slots not dispatched, including those above.
- `recorded_games`, `started_games`, `completed_games`: counts from actual terminal
  rows; explicit `not_started` rows are recorded but neither started nor completed.
- `never_started_games`: unrequested slots plus explicit not-started rows.
- `missing_requested_records` / `start_status_unknown_games`: dispatched slots
  without records. Their start/outcome cannot be guessed, and they never become wins.

For an untouched final arm, planned slots remain visible while requested, completed,
missing requested records and ordinary outcomes are all zero. Experiment status may
be failed even when every dispatched game completed. Incomplete cells remain
ineligible for further memory use or phase progression; no retry or borrowing occurs.

Each phase records monotonic `start_elapsed_seconds`, `stop_elapsed_seconds` and
`consumed_seconds`. A stop clears the active phase once; repeated finish calls are
idempotent. Untouched phases have null start/stop and zero duration. Collection stop
and total finalization are distinct boundaries:

- `timing.collection_stop_elapsed_seconds` freezes when collection ends.
- `setup_seconds` is collection-stop elapsed minus summed phase durations.
- `reporting_audit_seconds` measures later reporting, replay and bulk artifact hashing.
- `overhead_seconds` is setup plus reporting/audit and has its own allocation.
- `consumed_seconds` is total measured experiment duration. Finalization closes it
  once; tiny final ledger/summary/manifest writes follow the sample. Later read-only
  reports neither write the ledger nor extend any recorded duration.

Report audits validate these relationships and actual reservation/dispatch totals.
Probability intervals require complete independent final groups, as originally
specified; the existence of rows from a partial fourth group is insufficient.
Neither estimator nor scientific eligibility changed. Phase budgets cannot be
borrowed by setup/reporting, even when collection finishes early.

Historical source-freeze audits still require the historical code. Before source
changes, the original full audit passed for its recorded partial data. After the
accounting repair, independent replay in `runs/v6-repair-equivalence.json` reproduced
all 3,643 original decisions/scores/probabilities and 96 memory updates exactly,
without changing the original files or relaxing their audit checks.

Actual replacement: 396 reserved/dispatched/recorded games, 395 completed, one cap,
324 unrequested slots. Development is complete; final is not. The experiment's
report flags and excludes the last incomplete four-game cell from probability and
memory-summary aggregates while retaining its three completed outcomes and one
truncation in battle accounting. Consequently those final probability aggregates
cover 248 games, while final terminal accounting includes 251 completed games.
`audit.ok=false` and CLI exit 1 preserve incomplete acceptance.

A separate read-only supplemental replay in `runs/v6-repair-verification.json`
rebuilds all 396 encounters (including the flagged cell) and verifies that cell's
private labels. Its `ok=true` verifies evidence integrity only; `acceptance_status`
remains `failed`. The capped encounter has zero admitted evidence and unchanged
pre/post memory digests. No supplemental result is written back into the frozen
experiment, relabeled as a draw/win or used to resume collection.

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
