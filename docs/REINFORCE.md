# Richer outcome-driven policy research

This separately authorized extension follows V1–V7. It does not replace their
policies, checkpoints or conclusions, and does not complete either V6 acceptance
attempt. The historical V7 status is preserved verbatim in
[MILESTONE7.md](MILESTONE7.md), SHA-256
`d9340692350e5b8ccc7a236d37622dae56d1ec284fe20f06fe8ce5523de3c31f`.

## What learns

`reinforce` is one small stochastic policy, with 814 actor coefficients and 37
value coefficients. It uses the existing NumPy dependency on CPU. There is no
imitation phase, predictor retraining, replay buffer, neural-network framework,
privileged critic or online opponent memory. The V4 model is needed only by the
unchanged V5 reference opponent.

For each immutable player-visible snapshot, `reinforce.features` makes a
37-number state vector and a 22-number vector for **each currently legal action**.
State features describe visible HP fractions and missingness, statuses, own and
revealed remaining Pokémon counts, request flags, turn, and displayed boosts.
Action features describe move category, nominal power/accuracy, public type
matchup, own switch target condition, an approximate position difference and the
existing V2 score. The exact ordered names are in `reinforce.py`; checkpoint
compatibility includes their order, shapes and source hashes.

No opponent identity, own team-file identity, hidden opposing moves/team/stats,
current opposing choice or result enters either model. Stable action IDs identify
legal commands in the journal, but are not learned input categories. Own switch
slots only retrieve the observer's own permitted Pokémon information. Raw HP
values and denominators remain intact in snapshots; fractions are derived at the
precision shown. Displayed boosts are labeled observations, not exact effective
Gen 1 stats. Type and position features are approximations, not a damage simulator.

The fixed starting logit is V2's score divided by 50 and clipped to [-3, 3]. The
learned part is a bilinear interaction:

```
logit(s, a) = fixed_prior(s, a) + state(s)ᵀ W action(s, a)
probability(a | s) = softmax over the actual legal action list
value(s) = tanh(vᵀ state(s))
```

Both W and v start at zero. This initialization is a stochastic version of a
clipped heuristic prior; it is **not equivalent** to V2's deterministic maximum
or V5. The frozen zero initialization is the primary control. A single legal
engine action has probability one and zero actor gradient. Forced replacements
are scored over legal switches. There is no assumption of four moves or six
switches, and a malformed or nonfinite model raises an error instead of silently
choosing randomly. Training and evaluation both sample at temperature one using
the policy's own seeded RNG; simulator randomness remains uncontrolled.

## How experience changes it

`reinforce_training.trajectories` reads a completed run after the existing private
commitment audit. It joins that learner's recorded pre-decision snapshots and
probabilities to a **separate** terminal target: win +1, draw 0, loss -1. Capped or
failed battles get no target. An episode with any unknown learner commitment is
also excluded from updates, with its evidence and reason retained. This can bias
the training population, so exclusion rates are part of the result.

One batch uses a frozen learner and frozen opponents. For each eligible decision,
the actor increases the chosen action's relative preference when the completed
return exceeds its pre-batch value estimate, and decreases it when the return is
lower. The derivative of log-softmax is the chosen action vector minus the
probability-weighted mean legal action vector. Multiplying this by the state and
return-minus-value gives the actor gradient. The critic fits observed returns
with squared error through its tanh output. Both gradients use the old checkpoint;
updates happen only after the whole rollout batch finishes.

This is Monte Carlo **REINFORCE with a state-value baseline**, an established
policy-gradient method described in Sutton and Barto, Chapter 13
([authors' textbook, university copy](https://www.andrew.cmu.edu/course/10-703/textbook/BartoSutton.pdf)).
BattleMind implements the short analytic derivatives for this specific model,
checked against finite differences. It does not implement a general optimizer or
neural-network framework. Gradient clipping, parameter norm projection and plain
SGD are standard methods. BattleMind's contributions are the observer/action
representation, immutable inference boundary, conservative trajectory/commitment
joins, bounded archived-opponent schedule, reproducible checkpoints and audits.

An update can make play worse: outcomes have high variance, long games credit
many actions with the same terminal return, the value approximation is limited,
and the four-team opponent mixture is narrow. The initialization carries V2's
limitations. A decreasing training loss or a changed coefficient is not evidence
of stronger play. No damage, survival or switching reward is added to manufacture
a better-looking curve.

## What the experiment separates

[REINFORCE-SMOKE.md](REINFORCE-SMOKE.md) specifies the 48-game engineering check.
Its outcomes are not improvement evidence. The main experiment is frozen in
[REINFORCE-EXPERIMENT.md](REINFORCE-EXPERIMENT.md) and
`configs/reinforce-main.json`: 864 training, 216 selection and 576 final games,
with separate phase allocations totaling at most 3,600 seconds.

Training alternates archived learner checkpoints while retaining V2, V5 and
periodic c0 exposure. These completed archived self-play outcomes participate in
the actual updates; this is not merely choosing among fixed bots. Fresh selection
games choose among predeclared c0/c6/c12, prioritizing completion count, then mean
completed return, then the earliest checkpoint. Final evaluation compares the
frozen initialization with the frozen selected checkpoint, against the same six
opponents and balanced teams/sides. Selection/final games never enter updates.

Ordinary caps stay visible and reward-free; audited cleanup permits later
independent games. Unexpected protocol failures, numerical corruption, invalid
actions, failed cleanup or hash/audit mismatches stop collection. There are no
retries, resumed ledgers, borrowed final games or additional training after the
declared allocation. All games remain local and concurrency one.

## Files and commands

The inference code is `reinforce.py`, the offline update and reconstruction are
`reinforce_training.py`, and the single-use orchestration/accounting is
`reinforce_experiment.py`. `LocalPlayer` still captures the snapshot before
calling the policy, then maps the returned ID through that request's legal
commands. It additionally records probabilities, logits, value and RNG draw in
`policy_evaluation`. The existing separate per-player live journals and
post-match combination/commitment verification remain intact.

Checkpoints are versioned JSON containing finite bounded tuples, compatibility
metadata and separate provenance. Loads validate feature/source/runtime identity,
shapes and norm bounds; saves refuse to overwrite. No pickle is used. Inference
receives immutable parameters and a digest for logging, not provenance as features.
Main source copies are retained under `source-snapshot` for later strict audits.
Historical artifacts cannot be regenerated exactly from a source-only clone.

The consumed collection commands are documented for audit, not authorization to
repeat them:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -u -m battlemind reinforce-run --spec configs/reinforce-smoke.json --output runs/reinforce-smoke
.\.venv\Scripts\python.exe -u -m battlemind reinforce-run --spec configs/reinforce-main.json --output runs/reinforce-main
.\.venv\Scripts\python.exe -m battlemind reinforce-report --experiment runs/reinforce-main --audit
```

Ordinary frozen battle/evaluation and optional viewer commands accept the model
without updating it. The example fresh directories and game counts below are
usage instructions, not additional games collected for this experiment:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/milestone2.json --agent-a reinforce --checkpoint-a runs/reinforce-main/selected.json --agent-b gen1-heuristic --battles 24 --output runs/NEW_FROZEN_EVALUATION
.\.venv\Scripts\python.exe -m battlemind demo-serve --bundle runs/v7-release-bundle --reinforce-checkpoint runs/reinforce-main/selected.json --output runs/NEW_RECORDED_DEMO --games 0 --seconds 300
```

The optional viewer policy is separately named `reinforce`; historical defaults
and bundles stay unchanged. Frozen stochastic evaluation changes only its local
RNG position, never coefficients. Replay/audit reproduces recorded draws and
choices; that does not promise identical newly simulated battles.

Actual results and verification are recorded in [REINFORCE-RESULTS.md](REINFORCE-RESULTS.md).
Fixed-team Gen 1 outcomes do not establish human-level or all-generation strength.
