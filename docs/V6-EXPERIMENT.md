# V6 specification — written before reported collection

Question: does an individual's earlier public behavior improve prediction or play
beyond frozen V4/V5 and pooled public history? Improvement is not required.
There is no supervised refit, policy optimization, additional self-play training,
human profiling or within-battle memory update. All services use 127.0.0.1.

## Required frozen artifacts

- `models/v4-supervised.json`: SHA-256
  `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`.
- `runs/v5-acceptance/selected.json`: SHA-256
  `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e`.
  Parameters (-.32986111111111105, .32986111111111105,
  .32986111111111105, .32986111111111105).

Both exist and passed the existing bundle/checkpoint loaders before implementation.
Freeze copies into each fresh ignored V6 experiment root; reject missing, altered
or incompatible artifacts. Original scoring/schema/predictor source stays intact
so V5 checkpoint compatibility remains valid. A source-only clone cannot reproduce
these hashes without retained inputs. Historical regeneration interfaces are
`supervised-train --dataset runs/v4-development/development-data --output FRESH`
and `policy-train --predictor models/v4-supervised.json --output FRESH`; the latter
uses stochastic engine outcomes and cannot promise the historical selected hash.
These are documentation, not authorization to retrain or substitute an artifact.

## Permitted evidence and proxy target

Memory sees only the observing player's immutable pre-decision snapshots and its
own chronological public event projection. It never reads the other journal,
private requests, chosen actions, end logs, labels, winner or simulator RNG.
The observer's completed-encounter flag only controls eligibility for updating.
No incomplete encounter contributes evidence, including an exact observed prefix.

For each observer decision, retain its snapshot/hash and the public event window
from that snapshot's history length to the next snapshot (or final own history).
Require exact history prefixes, nondecreasing turns, increasing request IDs, and
no public event after the snapshot's current turn in its prefix. The evidence
window is processed only after that encounter finishes. Never use a later
encounter or hindsight-filled Pokémon state as the earlier feature vector.

Admit at most one public proxy action per unique ordinary observer request/turn:
opponent was visibly living, not asleep/frozen, and a replacement was publicly
possible. Our own forced, engine-only or uncertain-lock/disable requests are
excluded. A switch from a visibly living active Pokémon before it acts, without
drag/faint/effect ambiguity, is a public voluntary-switch proxy (1). A single
ordinary opponent move announcement is an announced-move proxy (0), not proof of
selection eligibility, hit or successful effect. A later replacement after a
public faint is recorded as forced and is not a switch target.

Initial sendouts, drag, faint replacements, conflicting/multiple actions, cant,
missing announcements, unknown active state and unavailable visible alternatives
are retained with skip reasons. No observed switch is never automatically a move.
Exclude public locking/copy/charge move contexts (Wrap/Bind/Clamp/Fire Spin,
Hyper Beam, Bide, Rage, Thrash, Petal Dance, Metronome, Mirror Move, Transform,
Dig/Fly/Solar Beam/Razor Wind/Skull Bash/Sky Attack, Fight/Recharge/Struggle),
including the preceding two turns for either side. This deliberately conservative
filter handles the projection's missing trailing effect annotations by exclusion.

This is a biased **public-announcement proxy**, not the exact privileged
meaningful-choice label. Offline labels quantify admitted/skipped target coverage
and proxy disagreement; they cannot change memory. Unannounced selected moves,
hidden trapping/legality, status and faint timing create selection bias.

## Adjustment and support

All arms run the same unchanged V4 predictor and V5 score function/parameters.
Only the supplied immutable historical summary differs. Snapshot schema stays 1.1;
a versioned frozen constructor summary contains numeric permitted evidence only.
Opaque session keys, arm/target names, paths and provenance stay in orchestration.

For a completed encounter with at least four admitted proxy observations:

```
r_encounter = mean(proxy_y - frozen_V4_probability(earlier_snapshot))
R = sum(r_encounter) over supported earlier encounters
N = number of supported earlier encounters
delta = clip(R / (8 + N), -.15, .15)
p_adjusted = clip(p_frozen + delta, .01, .99)
```

If N<2, return p_frozen exactly (cold/sparse fallback). Each supported encounter
has weight one regardless of how many correlated turns it contained. Eight zero
residual prior encounters shrink toward V4. No estimated confidence or independent
turn-count claim is made. Additive residuals and clipping are a coarse calibration
heuristic; no hyperparameter search is planned. The same formula applies to pooled
and individual memory. Record support encounters/examples and all skips.

Arms: A `none` uses V4 probability unchanged; B `pooled` uses this observer's
earlier encounters across both sessions; C `individual` uses only its current
session's earlier encounters. Every arm maintains its own separate registry and
all three shadow summaries, including A. No evidence crosses arms or groups.
Summaries are frozen for each entire battle, then updated after completion.
Unknown/new keys start empty; explicit resets create fresh group registries.

## Fixed opponents, ordering and partitions

Two existing targets: MaxBasePower (no voluntary switching while ordinary moves
exist) and switch-active (V2 utility, zero gain threshold, two-turn cooldown).
Neither is tuned. Synthetic opaque keys route repeated encounters with these
fixed local targets; policy names are not visible to the observer's score/features.
There is no claim of unseen-opponent or human adaptation.

One independent group = three separate arm observers, two sessions each, 24 games
per target/arm = **144 games**. Every target receives six complete four-game
unordered team-pair blocks, both assignments and challenger sides. Targets are
interleaved at four-game boundaries; each observer's next block uses the other
target. A session's memories persist over its 24 encounters within that group only.
Group parity reverses target order, counterbalanced two-and-two across final's four
groups. Rotate arm ordering by (group+pair) modulo 3.
Seeds are 61000 + 100*phase_index + 10*group + pair, shared across arms/targets as
policy seeds only. Engine trajectories are not matched.

Development: one group, 144 games. Check usability/audits and describe proxy coverage;
no automatic tuning. Freeze the same rules before final, recording development
completion and final-empty reset. Final: four fresh independent groups, 576 games.
All connected encounters/arms of a group stay in one partition. Record every
run-manifest SHA-256:match identity and reject duplicates/phase overlap. Final
memories start empty and may use only the predeclared between-encounter updates.

## Budgets and stop rules

| Phase | Requested games | Wall allocation |
|---|---:|---:|
| Development | 144 | 180s |
| Final, reserved before development | 576 | 600s |
| Freeze/report/audit overhead | 0 | 120s |
| Total | **720** | **900s** |

This is below the 864-game user ceiling. Concurrency 1, four-game run cells,
300 turns, 60s per battle; run timeout also bounded by phase remaining time.
Persistent single-use ledger reserves each cell before launch. No refund, borrowing
from final, retries, extra data or resume. Stop on incomplete cell, exhausted time,
unexpected warning/error, invalid action, compatibility/hash change or failed audit.
Known Wrap/Clamp warnings and unknown commitment suffixes remain visible. Never
count caps, crashes, cancellation, missing games or cleanup forfeits as wins.
Retain evidence and unused reservations on failure; default excludes all memory
updates for incomplete encounters. A failure stops the experiment, not a rerun.

Verification games are separate: existing integration suite 37 plus at most 8 V6
games, total **45**. V5's existing regression test may calculate a test-only update;
no additional V5 training experiment is authorized or reported here.

## Metrics and uncertainty

Probability: all three shadow predictions on exactly the same eligible player-a
snapshots, using only that observer's own earlier evidence. Shadows cannot control
play. Offline observer-to-label joins evaluate committed target-b meaningful
move/switch labels. Report Brier, log loss, five calibration bins with support,
examples/switches, every exclusion, cold versus later session encounters, public
admitted/skipped evidence, support, proxy-versus-private-label agreement/coverage,
and individual-minus-pooled/none differences. Report by generating arm, target and
arm×target, plus the predeclared example-weighted all-arm fixed-mixture summary.
Different live state distributions are not a clean comparison between predictors;
within each observer snapshot the shadow comparison is paired.

Battles: W/L/D, completed denominators, mean reward (win 1/draw .5/loss 0), all
failure categories, labels, warnings/resources, and same-snapshot shadow choices.
Final comparisons include both pooled and individual against none, and individual
against pooled. No outcomes can update scores or select a checkpoint.

Descriptive uncertainty: 1,000 bootstrap resamples of the **four complete independent
final groups**, seed 61901. A sampled group includes all its shared-memory encounters
and arms, preserving dependence and schedule composition, not engine RNG. Report
point differences and percentile 95% intervals for probability losses and battle
reward/win rate, plus individual group results. Four groups are too few for robust
inference; do not infer significance or general adaptation strength. Never resample
turns or individual memory-linked battles as independent outcomes.

Replay audit rebuilds registries in chronological order from own observer-only
exports, checks pre/post summaries/digests/cutoffs/resets, and reproduces every
shadow prediction, score and live choice. This public audit has no label/end-log
dependency. A separate existing commitment audit checks privileged labels. Freeze
and hash config/source/artifacts; retain weak runs and report negative results.
