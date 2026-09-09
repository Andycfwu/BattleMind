# V5: what learns and how to explain it

V5 learns four numbers controlling action scores. It keeps V4's switch predictor,
preprocessing, visible features and original scoring implementation frozen. The
learned policy is a new class; V2/V3/V4 still run unchanged. Learning means an
actual arithmetic parameter update driven by completed training-game outcomes.
Winning more final games is a separate question answered in [STATUS.md](STATUS.md).

## One observation becomes one action

1. The existing adapter copies a player's request and public history into a frozen
   `DecisionSnapshot`. Opposing unseen species/moves and effective Gen 1 stats stay
   unknown; displayed HP numerator/denominator and boosts retain their meaning.
2. `LearnedScoreAgent.evaluate()` in `learned_policy.py` calls the unchanged V4
   `SwitchAwareAgent` with its frozen predictor. The predictor produces p from
   visible features. The baseline computes stay, possible-switch and mixed utilities.
3. Four immutable parameters adjust those scores. Anticipation changes the strength
   of p's effect, recovery/status add bounded utility preferences where the original
   rule has positive utility, and switch threshold changes the required visible
   position gain. Exact equations and scales are in [V5-EXPERIMENT.md](V5-EXPERIMENT.md).
4. The highest score wins; ties keep request order. Forced replacement and engine
   scores are preserved. Only a legal semantic ID leaves the policy. The existing
   adapter resolves it against that same request's mapping and number.
5. That player's journal records snapshot, mapping, chosen ID, scores, initial
   alternative and checkpoint digest before submission. The other player's
   journal is unavailable to this policy. The existing post-match recorder later
   combines evidence to establish intended-choice and execution labels.

The constructor receives frozen predictor parameters and a frozen policy vector
plus digest, not checkpoint provenance. Evaluating a snapshot cannot change either
artifact. The digest is logged metadata and is not read by the score function.
The outer decision row must never be treated as a feature vector.

Zero policy parameters return V4's score objects directly. Fixture tests cover
ordinary, forced, engine and unknown requests. An offline check also obtained exact
score/choice/probability equality on all 20,620 archived V4 final decisions. This
supports using c0 as the primary control without spending another final arm on V4.

## How an outcome changes the policy

`policy_search.py` creates one reproducible random direction with four +/-1 entries.
It perturbs all four parameters by +0.4 or -0.4 along that direction. Both frozen
candidates play the same opponent list, team assignments, player sides and budgets.
Policy seeds are repeated across signs; Showdown's RNG is uncontrolled.

After **every** scheduled game in both batches completes and passes its audit,
`complete_objective()` averages terminal rewards: win 1, draw 0.5, loss 0. If any
game is missing, invalid, capped, crashed or timed out, the comparison cannot update
anything. Cleanup forfeits are retained as failure evidence and have no reward.

`outcome_update()` computes a scaled difference of the two batch rewards, moves
the parent vector in that direction, and clips each coordinate to [-1,1]. It saves
the actual contrast and delta. It does not merely choose an existing bot, retrain
the predictor, or use damage/survival rewards. The arithmetic update can be worse
than either candidate; it is not called a guaranteed promotion.

This is standard derivative-free random-direction finite-difference optimization,
related to evolutionary strategies and simultaneous perturbation methods. It is
**not gradient-based reinforcement learning**. The project does not differentiate
through Showdown. One direction per round, discrete argmax choices, noisy outcomes,
coupled coordinates and clipping all limit what two rounds can establish.

## Why this includes self-play

`learning.py` freezes each opponent tuple before a round starts. Round 1 includes
the frozen initialization c0 alongside V2 and switch-active. After a complete first
round, the resulting c1 enters round 2 alongside c0 and both fixed rules. The pool
has at most four entries and cannot change inside a comparison. These are earlier
versions of the same trainable policy; their completed games contribute to the
update objective. The experiment is mixed archived self-play and heuristic-opponent
policy optimization. It neither trains exclusively against the latest checkpoint
nor models an individual player's behavior.

`learning_ledger.py` reserves final evaluation before training. Every run consumes
its requests before starting; reservations cannot be recovered by retrying or moved
between phases. Training, selection and final identities use run-manifest SHA-256
plus match index. All perspectives of a battle stay in its phase. A new process
cannot resume: the existing output directory is rejected. Interrupted evidence is
kept for inspection, not silently reused.

## Frozen selection, evaluation and audits

Fresh selection games score exactly c0, c1 and c2 against a fixed three-opponent
panel. Highest reward wins; ties prefer the smallest squared parameter norm, then
earliest checkpoint. `selected.json` is a byte-for-byte copy, frozen before final
games. Final compares c0 with selected on six predeclared opponents, including
earlier versions to inspect forgetting. Final results cannot select or update anything.

`policy-evaluate` calls the ordinary runner with a loaded checkpoint, then audits
the result. There is no optimizer call in this command or in the policy. The real
integration test plays two perturbed four-game batches against c0, performs an
outcome update, saves/reloads it, evaluates four frozen games and checks hashes.
Those 12 games are tests, separate from the 840-game experiment.

`learning_report.py` reconstructs proposals, updates and selection from actual
completed terminal records in their permitted phase. It also replays all existing
request/label audits and frozen policy scores. Same-snapshot initial/selected
choice differences show whether parameters changed behavior; they cannot establish
counterfactual wins. Outcome uncertainty resamples four-game schedule blocks,
never individual turns or supposedly matched simulator trajectories.

Safe JSON checkpoints include schema, exact parameter keys/bounds, predictor digest,
feature/snapshot/scoring versions, scoring-source and runtime-version hashes, and
offline provenance. Malformed/incompatible artifacts are rejected. This strict
compatibility means editing a scoring file requires a deliberate new artifact/version;
it cannot silently reinterpret old parameters. Source/model/run hashes detect
accidental mutation, not a malicious local editor rewriting evidence.

## What the student should be able to defend

Standard methods: logistic regression, random-direction black-box optimization,
bounded parameter projection, frozen checkpoint evaluation and block bootstrap.
BattleMind engineering: the immutable observation boundary, request legality,
exact post-commit label alignment, score parameterization with an equivalent control,
phase/budget ledger, frozen-opponent admission, safe compatibility checks, reproducible
update audit and honest experiment accounting. No external agent code was copied.

Supervised prediction learns probabilities from verified past choice labels. Policy
optimization learns action preferences from completed wins/draws/losses. Self-play
adds earlier policy versions as opponents. Individual-opponent adaptation would
change behavior using one opponent's previous visible actions across encounters;
that is V6 and is not implemented here.

These scores still approximate strategy: no exact damage, opponent private legal
list, known hidden switch destination, effective-stat reconstruction or battle tree.
Uniform public/anonymous switch destinations, conditional-choice probability applied
when live eligibility is unknown, coarse healing/setup rules and deterministic ties
remain limitations. Reproducible parameters and same-snapshot choices do not imply
reproducible engine trajectories, competitive strength or automatic improvement.
