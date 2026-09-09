# Opponent prediction: V3 counts and V4 supervised training

V3 estimates **P(opponent voluntarily switches | opponent has a meaningful move-or-switch choice)**. It compares an overall frequency with conditional frequencies, then uses either estimate in the same action-scoring policy. It does not train a classifier, read external replays, adapt to an individual, or update during evaluation.

## Observation and target are different inputs

The existing post-match recorder establishes intended actions from official committed input logs. `dataset.joined_examples()` first requires audited commitments and a valid observer-to-label join. The target belongs to the opponent; features come from the **observer's frozen pre-decision snapshot**. Each row retains both decision/request IDs and the observer snapshot hash for audit. Target policy names, run identities and other recorder metadata support grouping and provenance only; the predictor never receives them.

Excluded target categories are incomplete battles, unknown commitments, forced replacements, engine-mandated actions, unknown eligibility, no meaningful move/switch choice, unknown binary labels, and missing verified observer joins. Each rejected label gets an exclusion row with its reason. Malformed alignment raises an error; it is not quietly converted into an example. Unmatched commitment suffixes remain unknown exactly as in V2.

Actual eligibility uses privileged post-battle evidence. During play it is often **unknown** to the observer. The policy does not receive that eligibility flag. It applies the conditional probability as an explicit approximation when our own request offers ordinary moves and there is a publicly possible destination. It skips mixture scoring for our forced replacement/engine-only requests or when public information leaves no possible opposing replacement. This is not an exact unconditional switch probability.

## Three visible categories

`context_from_snapshot()` accepts only a frozen `DecisionSnapshot`. Context version `visible-context-v1` contains:

| Feature | Categories |
|---|---|
| Opponent HP | `low` at displayed HP fraction ≤1/3, `other` above it, or `unknown` |
| Opponent status | `healthy`, `impaired` for a publicly known non-healthy status, or `unknown` |
| Our type pressure | Best Gen 1 type multiplier among our legal ordinary damaging moves: `resisted` <1, `neutral` =1, `super` >1, or `unknown` |

Seismic Toss, Night Shade and Super Fang are excluded from the type-pressure feature because listed type multipliers are not their fixed-damage behavior. No eligible damaging move or no visible foe yields unknown pressure. Own legal moves are information available to the observer; they are not claimed to have been revealed to the opponent.

These give at most 36 contexts. There is no account, team-file, matchup assignment, simulator RNG, future result, opponent hidden move, or private legal-action feature. Raw HP fractions remain unchanged; using their displayed ratio for a coarse category does not reconstruct exact HP. Displayed boosts and unsupported effective stats remain distinct. V3 does not use historical opponent counts or individual profiles.

## Estimation and freezing

Let `N` be eligible development-fit examples and `S` their switch count. The constant baseline is the Beta(1,1)-smoothed frequency:

`p_global = (S + 1) / (N + 2)`

For a context with `n` examples and `s` switches, conditional prediction is:

`p_context = (s + 12 × p_global) / (n + 12)`

This shrinks small cells toward the global frequency. Cells with fewer than five examples use `p_global` directly, labeled `sparse_context` or `unseen_context`. Every prediction records the probability, context, local/global counts, prior strength and fallback reason. Probabilities are numeric; supporting counts are not statistical confidence intervals.

`CountTable`, `Cell`, `Context`, `CountPredictor` and `Prediction` are frozen dataclasses; cells are a tuple. Estimation is a separate offline function. The policy has no update method. The runner copies the artifact once and constructs the predictor from the count table only; training provenance never enters the policy interface. Counts are **estimated from data**. Features, smoothing, thresholds and scoring rules are **handwritten**. There is no gradient training, reward optimization, classifier fitting, or evaluation-time learning.

## Auditable datasets and splits

A run identity is the SHA-256 of its original `run.json`. A battle key combines that identity with the match index, so match 0 from two runs cannot collide. Copying a run preserves its identity and is rejected as a duplicate source. Each source is re-audited and relevant decisions, labels, events, terminal records, engine evidence and histories are hashed.

Development splitting sorts whole battle keys by `SHA256(seed:key)` separately within each source run: the first floor(75%) are `development_fit`, the rest `development_check`. Splitting uses no labels. Both players and all turns stay together, including exclusions and battles with no eligible examples. The saved manifest contains the full battle-to-partition mapping, feature definitions, source/content hashes, coverage, exclusions and class balance.

`predictor-fit` reads only `development_fit` and records both fit and complete development battle membership. It refuses an evaluation dataset. `predictor-evaluate` refuses fitting-partition evaluation and refuses any fresh-evaluation overlap with any development battle. The already reported M2 games, including their development-check partition, are never described as an untouched test.

The actual fit used 36 M2 battles, 1,318 examples and 213 voluntary switches; 13 contexts appeared. The 12-battle development check had 457 examples and 69 switches. This supports a small frequency experiment, not broad coverage or hundreds of independent opponents. Repeated turns remain correlated; four teams and three baseline behaviors offer limited variety.

## How prediction changes the action

`SwitchAwareAgent` preserves `Gen1HeuristicAgent` as an unchanged reference. For each legal action, first obtain its V2 score. For an ordinary damaging move:

`score = (1 − p_switch) × stay_utility + p_switch × switch_utility`

`stay_utility` is the V2 score against the active foe. `switch_utility` averages the same attack utility over publicly revealed, non-active, non-fainted opposing Pokémon, with one equally weighted anonymous alternative per unseen slot. If unseen count itself is unknown, use one anonymous alternative. Anonymous alternatives use a neutral type multiplier, without inventing species, moves, HP or private team assignments in the observation. Equal destination weights are an assumption; the opponent may choose strategically.

Healing, setup, other status moves, engine actions and our own switches retain their V2 scores in both scenarios. Thus changing attack utility can also change the comparison with healing or switching, but the policy does not model status applied to an incoming Pokémon, simultaneous switches, future move sequences, or exact damage. V2's switch threshold/cooldown and move-specific penalties are unchanged. Ties use legal request order.

The two policy names differ only in the probability source: `switch-constant` versus `switch-context`. Each logs all stay/switch/mixture scores, the estimate and support, whether it applied, the public destination assumption and chosen action. It also computes constant/conditional/V2 choices on that **same snapshot**. These are alternate own-policy choices, not the other player's submitted action. They prove decision influence but cannot establish that an alternate choice would have won.

A real example is `context-vs-random`, decision `m10:a:r31`, turn 12. Constant probability 0.1621 favors Thunderbolt (utility about 177.17) over Soft-Boiled (170.02). Context probability 0.2601 reduces Thunderbolt's mixture utility to 169.41, so Soft-Boiled is selected. The snapshot and scoring rule are identical; only the probability changes. The conditional estimate is based on 16 switches among 57 development examples in that context. This is a traceable decision change, not evidence that healing was better.

## Evaluation and code paths

Probability quality uses Brier score, clipped log loss and five fixed calibration bins. A descriptive 1,000-resample paired bootstrap resamples whole battles, retaining selected turns/perspectives together. Metrics are example-weighted; longer games contribute more observations. Intervals describe this restricted schedule, not all Pokémon opponents.

The frozen benchmark compares three policies against the same random and MaxBasePower opponents. Every cell has all six unordered team pairs, both team assignments and both engine sides: 24 games. Constant versus conditional is the prediction ablation; comparisons to V2 also change scoring and must be described separately. No simulator randomness is matched. Probability evaluation's predeclared primary targets are the two reference opponents, while the dataset preserves both directions and reports excluded-by-selection counts. Policy identity is used only in offline report grouping.

`prediction.py` defines features and smoothed counts. `dataset.py` performs audited joins, splitting and estimation. `anticipation.py` weights action utility. `prediction_report.py` evaluates probabilities and replays the frozen decision calculations for audits. `runner.py` supplies only a frozen snapshot to each policy and keeps separate live journals. `scripts/benchmark-v3.py` freezes source/model hashes before the fixed schedule and never fits or tunes a model.

V3 works technically, but conditional probabilities were worse than the constant baseline, and a win-rate benefit was not established. Those findings remain in [MILESTONE3.md](MILESTONE3.md); V4 does not retune that benchmark.

## V4: what the model learns

The label is a **committed intended switch (1) or ordinary move (0)** when the
post-match audit establishes meaningful choice. It is not an executed-move label,
a reward, a win prediction, or a guess from an animation. `supervised_data.py`
first runs the existing V3 audit/join and preserves that intermediate dataset as
`audited-context/`. It then reads the paired **observer** snapshot to compute
`visible-logistic-v1` features. The chooser's private snapshot is never a model
input. Unknown/mismatched suffixes, forced replacements, engine actions, missing
joins, uncertain eligibility and incomplete battles remain explicit exclusions.

The compact feature vector has four categories (the three V3 categories plus own
healthy/impaired/unknown status) and six numbers: own/displayed foe HP fractions;
best own legal attack utility; best revealed foe attack utility; and a recent
public switch/drag indicator for each side. Attack utilities reuse V2, are capped
at 300 and divided by 100. They are approximations, never exact damage. A missing
foe, HP denominator or relevant attack yields a missing value. A known zero
utility is zero, not missing. Recent public switches include forced/game-effect
switches; the feature does not secretly know their intended-choice label.
No displayed boosts are converted into effective stats, and raw snapshots are
unchanged. There are no species IDs, names, team identities or policy IDs in the
feature vector. The own legal attacks are information the observer knows, even
when not yet revealed to the opponent.

`Preprocessor` fits means/scales from observed **training** values. Missing numbers
become the training mean (zero after scaling) plus an explicit missing indicator;
entirely missing/constant columns use scale 1. Each categorical vocabulary comes
only from training and has an explicit unseen bucket. Unseen-category weights
receive no positive examples during fitting and remain zero under L2. This is a
documented fallback, not learned knowledge about unseen categories.

`LogisticModel` learns a coefficient for each encoded feature and an intercept:
`p = sigmoid(intercept + sum(coefficient × encoded_feature))`. The handwritten
feature extractor, model form and action-scoring formula are fixed. The
coefficients, preprocessing parameters and fair baseline counts are learned or
estimated offline. A larger coefficient raises switch log-odds with other encoded
features held fixed; it does not prove a causal explanation of an opponent.

## Optimization, selection and freezing

`supervised_training.py` minimizes mean binary log loss plus
`lambda / 2 × sum(coefficients²)`; the intercept is unpenalized. It implements
standard Newton/IRLS optimization with analytic gradient/Hessian, a linear solve,
Armijo backtracking, zero initialization, at most 100 iterations, and gradient
infinity norm below 1e-8. Both training classes are required. Failed convergence
raises an error; it is never reported as a trained model. Tests check derivatives
by finite differences and verify actual learning on a small known relationship.
This follows standard [logistic-regression/Newton methods taught at CMU](https://stat.cmu.edu/~cshalizi/dm/20/lectures/07/lecture-07.html), with L2 regularization; no novel optimizer is claimed.

The predeclared search is lambda 0.01, 0.1, 1.0, selected by validation log loss,
then Brier, then larger lambda. Every candidate fits **training only**, including
its preprocessing. There is no train+validation refit, class weighting,
resampling, calibration fitting, reward update or feature-selection search.
Zero initialization/full-batch training needs no RNG. The split/bootstrap seed is
20260909; deterministic fitting is verified numerically in the pinned environment.
Resource/timestamp provenance means two JSON artifacts need not be byte-identical
even when fitted parameters and predictions are identical.

The fair constant/count table uses precisely the same selected training rows as
logistic regression. Original V3 counts remain unchanged. All three fitted sources
are stored in one `v4-supervised-1` JSON bundle. At runtime only frozen parameters
and a content digest cross into the policy; training battle identities and source
paths stay outside it. JSON loading validates feature definitions, column order,
finite values, counts, partitions and model compatibility. No pickle is loaded.

## Splits and the controlled V4 comparison

[V4-EXPERIMENT.md](V4-EXPERIMENT.md) was written before collection. Development uses
144 fresh recorded games against three fixed switching heuristics, with two fixed
observer policies. No previously inspected M2/V3 recorded examples enter training;
the old V3 constant artifact defines one observer's fixed behavior only.
Whole-battle hash splits produce 108 training and 36 validation battle assignments.
Both directions/all turns/exclusions stay together, even though the primary target
population selects runner b only. That selection is offline metadata; engine sides
and teams are balanced. Final evaluation rejects **every** development battle key,
including validation/model-selection battles, and uses 288 fresh scheduled games.

The 40/0 threshold opponents encourage more switching than V2's 80 threshold but
still require positive visible position gain and respect its two-turn cooldown.
They are deterministic frozen heuristics, not learned opponents or individual
profiles. They are not tuned to classifier results. Both classes, prevalence,
calibration support and results by target/observer group are reported rather than
assuming that their mixture is representative of humans.

In `anticipation.py`, `SwitchAwareAgent` uses its original `stay_score` and
`switch_score` calculations for all three sources. Only `p` in
`(1-p) × stay_score + p × switch_score` changes. Each V4 prediction decision records
all three probabilities, all three alternate legal choices, V2's alternate,
candidate utilities and bundle hash. Its `Prediction` count-support fields still
describe the fair count table; they are not logistic confidence intervals.
`report --audit` recomputes these values from the stored observer snapshot and
copied bundle and verifies exact agreement plus the original legal mapping audit.

`supervised_report.py` compares all probabilities on the same eligible examples,
with Brier/log loss, prevalence, five calibration bins, group results and paired
whole-battle bootstrap differences. Negative classifier-minus-baseline differences
favor the classifier. Turns are example-weighted and correlated within battles;
the bootstrap retains each sampled battle's selected turns. It is descriptive for
the fixed mixture, not proof of held-out team/opponent strength. Battle outcomes
are reported separately; simulator randomness is not matched across variants.

This is **supervised training from local recorded battles**: audited decisions
supply fixed targets and a likelihood objective fits a classifier once. Self-play
learning would require a defined policy/reward update loop and checkpoint
evaluation; merely generating these games is not such a loop. There is no external
replay ingestion, online adaptation, private-state oracle or second battle engine.
See [STATUS.md](STATUS.md) for the three separate empirical conclusions.
