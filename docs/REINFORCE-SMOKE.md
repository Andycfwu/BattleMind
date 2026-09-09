# Policy-gradient research extension — implementation smoke freeze

This is a separate research extension after V1–V7, not V8 or a revision of V6.
The user authorizes one smoke allocation of at most 48 games/300 seconds. No
historical training/integration suite will be run. No independent test games or
extra live UI games are allocated. Unit fixtures and recorded playback collect zero.

Before any training game: the algorithm is a bilinear action-conditioned softmax,
trained using REINFORCE with an observer-only value baseline. It uses the existing
NumPy 2.5.2, analytic derivatives and plain projected SGD. No neural network or
optimizer framework is written, and no new dependency is necessary. This follows
the standard Monte Carlo method in Sutton & Barto, chapter 13:
[author textbook, university copy](https://www.andrew.cmu.edu/course/10-703/textbook/BartoSutton.pdf).

## Model and initialization

State features are listed in `reinforce.STATE_NAMES`: bias, own/public foe HP and
missing flags, alive/unseen counts, request legality/uncertainty flags, capped turn
number, displayed atk/spa/spe stages and own/foe status one-hots. State is divided
by sqrt(37). Displayed stages are not effective stats. Foe-absent stages use zero
with the separate foe-unknown flags; no hidden quantities are reconstructed.

Each legal candidate uses `ACTION_NAMES`: kind, bounded power/nominal accuracy,
damage/healing/sleep/paralysis/setup/self-KO/recharge flags, STAB, public type
multiplier plus missing flag, switch target HP/status, approximate visible position
gain and bounded V2 prior. No species, action-slot or policy identity is a model
feature. Its own original slot maps a switch to the target's permitted information.
Fixed type data and V2 utilities are reused openly, not exact damage estimates.

For normalized state s and candidate vector x:

`z(s,a) = clip(V2_score(s,a)/50, -3, 3) + s^T W x(s,a)`

`pi(a|s) = exp(z(a)-max(z)) / sum_legal exp(z-max(z))`

`V(s) = tanh(v^T s)`

W is 37×22 (814 coefficients), v has 37: **851 learned numbers**. Only actual
request-backed candidates exist in the softmax, so illegal actions have zero
probability by construction. Forced replacements and engine actions remain legal
candidates; singleton requests have probability one and zero actor gradient.
Raw immutable snapshots are untouched. No predictor, runner identity, provenance,
current opponent choice, private state or result enters either actor or baseline.

Initialize W/v to zero. The stochastic clipped V2 prior is a practical handwritten
initialization, **not equivalent to V2's argmax or V5**. No imitation or historical
training examples are used. Both initial and learned policies sample softmax at
temperature one during training, selection, evaluation and demonstrations.

## Outcome update

Only completed own outcomes give R=+1 win, 0 draw, -1 loss. Gamma=1; no intermediate
rewards, shaping or entropy bonus. The entire learner checkpoint is frozen for a
rollout batch, including v. No replay buffer or multiple optimization passes.

For N admitted episodes, use a fixed learning-rate scale of 1/100:

`g_W = -sum_episodes sum_decisions (R - V_old(s)) s (x_chosen - sum_a pi_old(a)x_a)^T / (100 N)`

`g_v = mean_decisions (V_old(s)-R) (1-V_old(s)^2) s`

`W_new = project_norm6(W - 0.3 * g_W/max(1,||g_W||))`

`v_new = project_norm3(v - 0.1 * g_v/max(1,||g_v||))`

This is a gradient-based score-function update; it never differentiates the engine.
The actor sums within episodes, not an episode-length-normalized surrogate.
The critic is observer-only and uses the old batch baseline for actor advantages.
Clip each gradient norm at one; project parameter norms at six/three. Reject
nonfinite data/parameters/probabilities and stale or mixed-policy trajectories.
No silent random fallback. Poor credit assignment, noisy rewards, fixed features,
clipping and small batches can make updates worse. Loss values across different
on-policy batches are descriptive, not a strength or convergence test.

## Exact smoke allocation and stopping

`configs/reinforce-smoke.json`: training 24 games/130s against frozen c0; one
update c1; no selection games (10s bookkeeping); frozen c1 evaluation against V2
24 games/130s; setup/reporting reserve 30s. **48 games/300s** total. Seeds 82000
plus the code's documented batch/phase offsets. Each 24-game cell covers all six
unordered pairs of the unchanged four teams, both assignments and challenger sides.
Concurrency one, 127.0.0.1, 300 turns, 60s per match, <=300s per run bounded by
phase remaining minus 30s. A full 90-second phase reservation is required to start
a cell. Final allocation is reserved before training; no borrowing, retry or resume.

Caps are retained and supply no reward. After cleanup and complete commitment/
policy audits, independent scheduled games continue. Unknown learner commitment
suffixes exclude that whole completed trajectory from updates; no guessed action.
Report exclusions by opponent and possible completion/commitment selection bias.
Crashes, timeouts, numerical corruption, unknown protocol warnings, leakage,
failed cleanup, missing rows or budget exhaustion stop further cells. At least
one eligible completed training episode is required to update. Record zero updates
honestly; do not add games merely to force a parameter change.

Smoke outcome: check actual trajectory alignment, finite derivatives/losses,
parameter delta, safe checkpoint reload, frozen evaluation, audits, resources and
cleanup. Win rates will not tune architecture/hyperparameters. Repairs are recorded
before a separately frozen main specification. Main games must not start until
smoke passes and observed runtime supports its declared allocation. The main
experiment reserves at least 576 final games and may use no more than 2,400 total
requested games/3,600s. No new main specification is consumed by this smoke.
