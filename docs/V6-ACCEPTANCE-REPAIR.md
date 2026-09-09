# V6 acceptance repair — specification before replacement collection

The user separately authorized accounting repairs and exactly one replacement of
the failed V6 acceptance experiment. This does not authorize V7, another replacement,
more games, coefficient fitting, V5 self-play, scientific tuning or a changed pool.

## Historical evidence and required inputs

Original: `runs/v6-acceptance`, **96 completed development games; development budget
exhausted; zero final games**. Its ledger, summaries, specification and 1,064 hashed
artifacts remain unchanged. `runs/v6-development-review.json` and
`runs/v6-verification.json` are development/historical evidence, never final data.
Original artifact-manifest SHA-256:
`52c22392d9cf6be514afb4c5ebaf71977dbdc17227658fb8172dfc178a02151c`.
Original specification SHA-256:
`07a73b4311ad630a317c90ae52de2ad6cd4229a8235a5287126d1f36f1a1ce3d`.
The starting workspace was clean at commit `e64f26e` (V6). Original incomplete
STATUS is copied byte-for-byte to `docs/MILESTONE6-FIRST-ATTEMPT.md`, SHA-256
`3f3a1a3057578a7d3ad3aa7aa93fe9a7cfca9950842404a106e6d65f52212163`.

Required retained inputs, checked through the existing compatibility loaders:

- V4 `models/v4-supervised.json`:
  `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`.
- V5 `runs/v5-acceptance/selected.json`:
  `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e`.

Missing or incompatible artifacts block collection. Originals are copied into the
fresh ignored replacement directory and hashed, not retrained or substituted.
A source-only clone without retained inputs cannot recreate historical checkpoints;
ADAPTATION documents historical regeneration interfaces and their limitations.

## Scientifically unchanged

The original [V6 specification](V6-EXPERIMENT.md) remains the scientific design.
All V4 coefficients, preprocessing and features; selected V5 score parameters;
public-proxy filters; residual equations; priors, clipping and fallback; targets;
four teams; encounter ordering, seeds, sides; reset boundaries; primary metrics and
offline eligibility remain unchanged. No choices or probabilities are tuned using
the inspected development result. Accounting/report orchestration is the only repair.

For clarity, memory still admits only conservative observer-public move/switch
announcements. Forced, engine, ambiguous, missing and lock/copy/charge contexts are
excluded. An encounter with at least four admitted proxies contributes one mean
residual from frozen V4 probabilities. For N supported earlier encounters and residual
sum R: correction = clip(R/(8+N), -.15, .15), adjusted probability clipped [.01,.99].
N<2 returns V4 exactly. Each arm owns its evidence and pooled/session summaries;
numeric summaries are immutable during a battle. Routing identities never enter
features. Only completed encounters update; private labels/end logs are offline only.

No additional scientific/information-boundary change is planned. Verify the original
scientific source hashes and replay all 3,643 retained observer snapshots/96 encounter
updates before replacement collection, requiring identical probabilities, candidate
scores, choices and memory digests. The original public replay and private label
audit are separate. The group-interval report must require complete groups as the
original specification already required; partial groups cannot become uncertainty
replicates merely because their records exist.

## Accounting repair

`v6-budget-2` distinguishes planned allocation, irrevocable cell reservations,
runner-dispatched requests, recorded/started/completed games and never-started slots.
The final allocation is protected before development; that capacity reservation is
distinct from dispatching its cells. `reserved_games` counts admitted cells;
`requested_games` increases only just before asking the runner to execute that cell.
It does not assert that every requested game reached an engine challenge. The runner
retains explicit `not_started` rows when a dispatched schedule aborts.

Unrequested slots plus explicit not-started rows are known never-started games.
Missing records for dispatched requests have unknown start status and remain visible,
not inferred losses. A reserved-but-undispatched cell consumes its reservation but
has zero requests. An untouched final arm has planned slots, zero actual requests,
zero missing requested records and no outcomes. Experiment failure is separate from
completed battle results. No reservation refund, retry, borrowing or resume is allowed.

Monotonic phase clocks record start, stop and duration. Stopping clears the active
phase and is idempotent. Collection stop freezes phase durations; reporting/auditing
and bulk hashing use a separate overhead clock. Finalization closes total time once.
Setup = collection-stop elapsed minus summed phase durations. Overhead = setup plus
post-collection reporting/audit time. Total = phase durations plus overhead. Tiny
final ledger/summary/manifest writes follow the timing sample and are explicitly
excluded from that sample. Later read-only reports do not write or advance clocks.

Old schema files are not migrated or rewritten. Their failed-phase timing and
planned-final denominator limitations remain documented. Full historical source-freeze
audits require the original code; compatibility checks are not weakened to conceal
new source differences. Retained public snapshots can independently be replayed
through unchanged scientific modules under the accounting repair.

## Replacement schedule and budgets

| Phase | Requested-game ceiling | Monotonic wall allocation |
|---|---:|---:|
| Development: one independent group | 144 | 420s |
| Final: four independent groups, reserved before development | 576 | 1,080s |
| Setup, reporting, verification and overhead | 0 | 300s |
| **Total** | **720** | **1,800s** |

Each group uses all three arms and the same two targets (MaxBasePower and
switch-active), six unordered team pairs with four games per pair/target/arm.
Group parity reverses target order; arm order rotates by group+pair. Interleave
targets at four-game boundaries. Identical policy seeds do not match engine RNG.
The pure schedule function is unchanged. Each final group/arm starts a fresh manager;
no evidence flows from development, the original attempt, another arm or observer.
Run-manifest-hash:match identities keep entire memory-linked groups in one partition.

Keep one managed loopback server per four-game cell, concurrency 1, 300-turn cap,
60s per game, run timeout <=600s and <=phase remaining minus 10s. Keep the conservative
15-second reservation/dispatch guard. Preserve every preflight, source/hash check,
warning, private label audit and public replay; no shared-server reuse, caching or
relaxed checks. Budgets cannot be transferred, even if total time remains unused.

Technical gate to final: every development cell completes its four games with no
invalid actions, unexpected warnings/server crashes, failed replay/label audit,
source/artifact mutation, overlap or phase deadline violation. Known Wrap/Clamp
warnings and explicitly unknown commitment suffixes remain visible. No probability
metric, reward, win rate or direction of effect controls eligibility to proceed.
Record `final-freeze.json` only after this gate; freeze the same rules and reset.

Stop on the first incomplete/invalid cell, exhausted budget or blocking audit error.
Preserve all partial evidence and unused allocations. Exactly one fresh output:
`runs/v6-acceptance-repair`. Reject an existing output. No retries or additional games.

## Feasibility from retained timings only

Original collection stopped at 165.731s for 24 cells/96 games. Summed run wall was
132.535s, including 37.949s battle time and 94.586s lifecycle/recording/memory work.
Another 33.196s covered preflight and between-cell auditing/hash work. Original
post-stop reporting/hashing added approximately 15.733s to total wall, although the
old ledger also incorrectly charged it to the failed phase.

Linear projections preserving all these costs: development 248.597s for 36 cells;
final 994.389s for 144 cells. New margins are approximately 171s and 86s. Projected
final margin is limited (~8.6% above estimated need); workload/OS variance or longer
unseen-in-the-partial-run team pairs may still cause a stop. Full 720-game reporting
scaled from retained time is about 118s versus 300s overhead. These are feasibility
estimates, not promises. No exploratory games are used to estimate runtime, and
no infrastructure safety changes are needed before this one authorized attempt.

## Verification allocation before acceptance

Run all fast unit tests plus relevant existing local integration tests, excluding
the V4 new-training and V5 self-play training integration scenarios. No historical
predictor is refit and no V5 learning experiment is repeated. Existing integration
allocation: 25 games (including eight V6 public-memory games and intentional cap/
timeout cases). Add exactly 12 test-only games exercising the shared production
phase driver: development four, two fresh final groups of four each, one individual
observer/target subset, with all four team/side assignments in its test pair.
Total planned test allocation: **37 games**, separate from acceptance metrics.

This reduced test is explicitly labeled test-only; it validates final gating, empty
memory, later encounter updates, replay, full report/hash path, read-only idempotence
and distinct partitions. It is not a replacement performance experiment. Unit tests
cover repeated finish/finalize calls, stopped phase timing, untouched final arms,
partial reservations/records, budget exhaustion and illegal state transitions.

## Metrics, audit and interpretation

Use unchanged same-snapshot shadow Brier, log loss, five calibration bins with
support; target, generating-arm, arm-by-target, cold/later and fallback breakdowns;
eligible switches/moves/exclusions; admitted/skipped public evidence and proxy bias.
Report individual-minus-none and individual-minus-pooled differences without mixing
the original attempt into replacement final results. All shadows use only that
generating observer's own earlier permitted evidence and never control other arms.

Live outcomes: W/L/D and actual completed denominators, all incomplete categories,
warnings/unknown labels/resources and same-snapshot choices. Cleanup forfeits,
unstarted allocations and missing records never become wins or terminal rewards.
Final updates are exclusively the predeclared public-history updates between games.

Uncertainty remains the original 1,000-resample bootstrap, seed 61901, over four
complete independent final groups containing all related encounters/arms. Four groups
give limited resolution; no turn-level or independent-battle substitute. Report
inconclusive/negative effects honestly. No matched engine trajectories, counterfactual
wins, held-out-team strength, human profiling or general opponent adaptation claim.

Freeze source/config/spec/model/checkpoint hashes before collection; preserve original
scientific source and schedule. Reconstruct all public memory, predictions and scores
chronologically, then audit private labels separately. Verify complete schedules,
resets, disjoint original/development/final identities, artifact hashes and no remaining
server listener. Read-only post-run verification collects zero additional games.

Actual collection command (execute once only after tests pass):

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m battlemind adaptation-run --specification repair --output runs/v6-acceptance-repair
.\.venv\Scripts\python.exe -m battlemind adaptation-report --experiment runs/v6-acceptance-repair --audit
```

STATUS will report the observed replacement separately. If complete, the only next
milestone is V7: consolidated reproducible benchmarks and a local watchable battle
demonstration. If incomplete, state the exact blocker; do not label V6 complete.
