# V4 experiment specification — frozen before collection

Written 2026-09-09, before any V4 collection. This is supervised learning from
audited local recorded battles, not arbitrary replay-file ingestion or self-play
learning. V3's negative results and original count artifact remain historical.

## Population and schedule

- Format/server/wrapper: existing pinned Gen 1 OU engine and poke-env 0.16.1.
- Teams: unchanged `ou-v1-a`, `ou-v1-b`, `ou-v2-c`, `ou-v2-d`.
- Target opponents, always runner player **b** (engine sides still swap): V2
  `gen1-heuristic`, `switch-moderate`, `switch-active`. The two new fixed policies
  reuse V2 move/position utilities and two-turn own-switch cooldown, but require
  position gain >40 and >0 respectively instead of >80. Forced choices use V2.
  These rules are chosen before collection and will not be tuned to results.
- Development: two observer policies (`gen1-heuristic`, original frozen V3
  `switch-constant`), each against all three opponents, 24 games per cell = **144**.
  Policy seeds 5101 and 5102 respectively. No M2/V3 recorded examples reused;
  original V3 counts are used only to define a fixed development observer.
- Final: `switch-constant`, `switch-context`, `switch-logistic`, and V2 reference
  against each fixed opponent, 24 games per cell = **288**, seed 6101.
- Each cell uses all six unordered team pairs, both assignments, both challenger
  sides: complete four-game blocks. Simulator RNG is uncontrolled.
- Planned reported collection + final benchmark: **432 games**. Hard aggregate
  ceiling **600 games / 900 seconds**, including run setup, audits and phase
  reports; persistent reservations prevent budget reuse. No retry of final cells.
  Integration checks are separate verification (at most 32 games planned), also
  reported; they are never training or final evaluation data. Concurrency 1,
  127.0.0.1 only, turn cap 300, match timeout 60s, run timeout at most 600s.

## Splits, features and fitting

Battle key = SHA256(run.json) + match index. Hash-order each development run with
split seed **20260909**: first floor(75%) train, remaining 25% validation. Both
perspectives, every turn, and exclusions inherit that battle's partition. Training
and probability evaluation select eligible labels for runner b only; identity and
eligibility are offline selection metadata, never features. All development keys
are forbidden in fresh final evaluation. No held-out team/opponent claim.

Features are extracted only from the observer's frozen snapshot: V3's three
context categories; own healthy/impaired/unknown status; own and displayed foe HP
fractions; capped best own legal attack utility and capped best revealed foe
attack utility (divided by 100); own/foe public switch-or-drag in the previous two
turns. Public switches are not inferred voluntary labels. Unknown HP/attack utility
stays missing; raw snapshots retain their original HP precision and unknown stats.

Train-only preprocessing: numeric observed-value means/population standard
deviations, mean imputation, explicit missing indicators; categorical training
vocabulary with an explicit unseen bucket. No feature selection or interactions.
Fit logistic regression with NumPy already in the lock: average negative log
likelihood + lambda/2 * squared coefficients, unpenalized intercept, deterministic
zero initialization, Newton steps with backtracking, maximum 100 iterations and
gradient tolerance 1e-8. This is a standard algorithm, not a new learning method.
Search **lambda in [0.01, 0.1, 1.0]**, select lowest validation log loss, then Brier,
then larger lambda. No class weighting, resampling, probability recalibration or
refit on validation. Both classes must occur in training; otherwise stop fitting.

Refit fair Beta(1,1) constant and conditional counts (strength 12, support >=5) on
the exact same selected training rows. Save all three predictors together as safe
JSON coefficients/counts/preprocessing, with hashes and provenance. Inference is
frozen. V2 utilities and SwitchAwareAgent candidate stay/switch scoring stay fixed.

## Primary metrics and interpretation

Primary population: all eligible runner-b intended choices in the final fixed
mixture, pooled across the four observer variants. Report log loss and Brier,
prevalence, examples, battles, battles with switches, five calibration bins with
support, each target-policy group and observer-policy group. Report exclusions,
label coverage, paired point differences and 1,000 whole-battle bootstrap
resamples (seed 20260909, descriptive percentile 95% intervals). Negative
classifier-minus-baseline differences favor the classifier. Turns remain correlated
within resampled battles. This mixture is restricted-pool evidence.

Separately report per-cell completed wins/losses/draws and Wilson win intervals,
caps/timeouts/crashes/invalid actions/not-started games, every wrapper warning,
resources, and same-snapshot alternate-action counts. No cleanup forfeit counts as
a win. Freeze model/baselines/features/scoring/opponents/schedule/source hashes
before final play. No final-result tuning or reruns. Probability improvements,
changed actions and battle benefits are three separate questions.
