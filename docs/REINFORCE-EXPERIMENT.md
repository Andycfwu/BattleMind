# Richer policy research — main experiment freeze, before collection

This is the separately authorized extension after V1–V7. Historical policies,
models, datasets, bundles and conclusions are untouched. Both V6 attempts remain
incomplete. This specification is consumed once, without resume, retries,
restarting for favorable outcomes, new teams/generations or further training.

## Algorithm and scope fixed before main games

Use the single 851-parameter bilinear softmax/observer-only value model defined in
[REINFORCE-SMOKE.md](REINFORCE-SMOKE.md) and `reinforce.py`. The exact ordered 37
state and 22 action features, normalization, V2 clipped-prior initialization,
legal-action masking and safe JSON compatibility are unchanged from the smoke.
No imitation, original V4 retraining, neural-network library or additional model
is added. Both initial/selected use temperature-one stochastic softmax sampling.
The V4 predictor is used only by the unchanged V5 reference, not by the new model.

Actor gradient is the same REINFORCE sum of terminal-return advantages divided by
100N; the value baseline gradient is mean squared-return error with tanh derivative.
**Main actor learning rate 30; value learning rate .1**, one SGD step per rollout
batch, each gradient norm capped at one, actor/value norms projected to six/three.
This is equivalent to actor step size .3 on the unscaled episodic gradient while
that scaled gradient remains unclipped. No bootstrap targets, replay buffer,
multi-epoch stale-data reuse, advantage whitening, shaping or entropy reward.

The smoke's cautious actor rate .3 yielded gradient norm .003188799 and parameter
delta .000956640. Main uses a documented change in step scale based on that finite
gradient magnitude, not on win rates. No smoke policy is selected or promoted:
main c0 starts from the same zero coefficients with fresh RNG/battle identities.
Actor outputs are state-dependent action preferences; value is an observer-only
expected terminal-return approximation, not a hidden-state critic.

R=+1 win, 0 draw, -1 loss, only after genuine completion. The actor sums decision
gradients within episodes; the 1/100 constant rescales the step, not individual
episode lengths. Entire episodes with unknown learner commitments are excluded
from both actor/value updates. All caps and failures have no training reward.
Exclusions can bias the completed/verified training population; report them by
opponent and batch. Selected/announced/executed moves remain separate concepts.

## Feasibility and separate engineering evidence

The single smoke used **48/48 games in 25.013453s**: 24 frozen c0-versus-c0
training games, one update, then 24 frozen c1-versus-V2 games. The initial update
used 20 completed audited trajectories; four episodes were excluded for unknown
commitment suffixes. Both actor/value parameters changed; all probabilities/losses
were finite. Forty recognized Wrap/Clamp warnings and 99 unknown commitments
were retained; no invalid action, cap, crash, timeout or unexpected warning.
Frozen checkpoint reload and real trajectory/update/evaluation audits passed.

Sampled maximum RSS: 226,746,368 bytes Python, 450,859,008 server; summed Python
CPU 7.4375s, last server CPU samples 7.90625s. The 0.1s sampler misses exact peaks.
Extra retained-evidence integration auditing collects zero games and takes about
4s per pass. Full smoke evidence is `runs/reinforce-smoke`, with the original
full audit retained in `.local/reinforce-smoke-audit.json` before main code changes.
Its full-source freeze remains historical; compatible model/gradient replay still
works after orchestration validation changes. No historical audit is relaxed.

At the observed .521s/game including run setup/audits/update/reporting, 1,656 games
project to about **863 seconds**. Allowing three times that rate gives about 2,589s,
below the 3,600s ceiling. Each phase has a separate conservative allocation below.
All runs still repeat pinned server checks/startup/shutdown and label/policy audits.
There is no shared-server shortcut, lowered cap, concurrency or cached safety check.
No additional exploratory games were used for feasibility.

## Opponents, archived self-play and updates

Twelve rollout batches, **72 games each**: 24 versus V2 (`gen1-heuristic`), 24
versus the unchanged selected V5, 24 versus one archived new-policy checkpoint.
Thus V2/V5/archived learner proportions are exactly one third before exclusions.
The learner and opponents stay frozen through all three cells and update once
afterward. Record parent vector/hash, pool, run hashes, probabilities, rewards,
exclusions, losses, gradients, deltas and resulting checkpoint c1…c12.

The archive opponent is c0 for odd batches and batch 2. Even batches 4,6,8,10,12
use c2,c4,c6,c8,c10 respectively. The active registry is limited to V2, V5, c0 and
one recent even checkpoint (four identities); all historical files are retained
as evidence. Admission is scheduled regardless of reward, not a tournament.
c0 remains periodically revisited to limit exclusive latest-policy exploitation.
This is mixed reference-opponent learning and archived self-play; it is not
individual adaptation or pure latest-versus-latest play.

Base seed 83000. Batch b cell j uses `83000+100*b+j`, j=0,1,2 in V2/V5/archive
order. Runner derives independent side seeds via its existing SHA256 function.
The engine RNG is uncontrolled: shared seeds/schedules do not pair trajectories.

## Fresh checkpoint selection

Only **c0, c6 and c12** are selection candidates. Each plays V2, V5 and c0 for
24 games each: **216 selection games**. Per-opponent seeds `88000+j`. No updates
or memory changes occur; no fitting inputs come from this phase.

Choose lexicographically: largest number of completed scheduled games, then
highest completed mean terminal reward, then earliest checkpoint. Completion
count is prioritized to avoid rewarding censoring. Caps are not imputed losses or
training rewards. The reward criterion is still conditional and can be biased;
report all completion rates. The selected checkpoint may be c0; retain that result
without extra candidates or games. Copy selected bytes to `selected.json` and
freeze its digest before final evaluation.

## Independent final panel and primary comparison

Two arms: **frozen new c0 versus frozen selected**, each with 288 requested games.
Both use exactly the same model, features, stochastic selection convention, teams,
opponents and budgets. No parameter or rule can change after selection.

Each arm plays 48 games against random, MaxBasePower, V2, selected V5, c0 and c6:
two complete 24-game cells per opponent, **576 final games**. Random/MaxBasePower
are reserved from training and selection; label them reserved simple references,
not unseen strategic opponents. V2/V5/c0 are familiar; c6 is an archived training
opponent (batch 8). Head-to-head against V2/V5 is an additional reference comparison,
distinct from the primary same-architecture before/after contrast. No extra V2/V5
arms are needed or budgeted. No held-out teams, humans or generation claims.

Order: repeat r=0,1; opponents as listed; initial then selected for each opponent.
Seed `93000+100*r+j` is shared by schedule, not simulator randomness. Every 24-game
cell contains all six unordered pairs from the unchanged four-team pool; each
pair has both team assignments and both challenger sides. All selections and
both perspectives retain `SHA256(run.json):match` identity. Audit zero overlap
among smoke, training, selection and final. No buffer accepts evaluation data.

## Exact allocation and stop rules

| Phase | Requested-game allocation | Wall allocation |
|---|---:|---:|
| Training, 12×72 | 864 | 1,600s |
| Selection, 3×3×24 | 216 | 500s |
| Final, 2×6×48, reserved before training | 576 | 1,100s |
| Setup, report, integrity and verification reserve | 0 | 400s |
| **Total** | **1,656** | **3,600s** |

This is below the 2,400-game user ceiling. No borrowing between allocations;
unused capacity cannot fund extra games. One persistent ledger in a fresh
`runs/reinforce-main` tracks planned/reserved/requested/recorded/completed/never
requested and phase start/stop durations. Resume and duplicate directories fail.
Cell reservations are written before dispatch; no refund or retry. Phase finish
is idempotent and read-only reports never modify its clocks. One full 90-second
phase remainder is required before each 24-game cell; run timeout is min(300s,
remaining−30s). Existing 60s match/300-turn limits and concurrency one stay fixed.

An ordinary cap is retained without a reward; subsequent independent games/cells
continue only with successful cleanup, source/model validation and commitment/
policy audits. Caps do not automatically invalidate unrelated complete training
episodes. No eligible completed training episodes means stop without an update.
Crashes, timeout/cancellation, invalid actions, missing records, numerical issues,
leakage, unexpected protocol warnings or failed audits/cleanup stop the experiment.
Recognized Wrap/Clamp warnings and unknown suffixes stay visible; no silent retries.
An interrupted experiment preserves partial results and untouched final requests
remain zero. No frozen opponent is repaired during evaluation to avoid a stall.

## Reporting and uncertainty

Report requested/completed/W/L/D/caps/failures by phase/opponent/arm, all actual
updates and parameter deltas, frozen pools, selection ranking, completion/commitment
exclusions, warning/label coverage, source/model/artifact hashes and resources.
Training reward/loss trajectories identify pool changes. They are not proof of
improvement. Shared-snapshot analysis records initial/selected distributions,
argmax changes and shared-uniform-draw choices; these are not counterfactual wins.

Primary descriptive difference: selected minus initial completed-game mean R.
Use 1,000 bootstrap resamples (seed 103000) of four-game team/side blocks, stratified
by fixed opponent, retaining each block's four games and matching block indices
across arms. There are 72 blocks per arm (six pairs × two repeats × six opponents).
This respects schedule blocks rather than resampling turns. It is descriptive
for the fixed pool, not proof of independent human samples or matched engine RNG.

Report completion rates alongside conditional estimates. Also show sensitivity
bounds assigning every unknown final outcome the mathematical range [-1,+1],
and bootstrap envelopes for those bounds. These are bounds, never logged game
rewards, wins or ordinary losses. If the requested final schedule is incomplete,
withhold intervals. Interpret four-team dependence and fixed targets conservatively.
Do not infer improvement from training loss or an interval crossing alone.

Checkpoint JSON validates architecture, feature order, shapes, finite values,
parameter norm bounds and relevant source/runtime hashes. Preserve originals:
V4 `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`;
V5 `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e`.
No pickle or online optimizer crosses into policies. Main source copies are
retained in `source-snapshot` for compatibility context. All artifacts stay ignored.
