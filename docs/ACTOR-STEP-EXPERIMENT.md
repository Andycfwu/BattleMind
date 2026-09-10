# Controlled actor-step experiment — frozen before collection

This is the one separately authorized experiment proposed in
[REINFORCE-AUDIT.md](REINFORCE-AUDIT.md), after the
[loader/report repairs](REINFORCE-REPAIRS.md). The audit measured small policy
movement, not a benefit from larger updates. Hypothesis: the original effective
actor step suppressed useful outcome-driven policy movement. Greater movement,
stable arithmetic and higher training reward are separate from better final play.
Historical REINFORCE conclusions and **incomplete V6 acceptance** remain unchanged.

## Exact contrast and unchanged settings

Both arms copy the original zero-residual c0 byte-for-byte. No imitation or
historical-data fitting. The 37-state × 22-action model, fixed clipped V2 prior,
observer-only 37-coefficient tanh critic, frozen snapshot boundary, legal lists,
temperature-one sampling, terminal R=+1/0/-1 and whole-episode commitment admission
are unchanged. V4 is only a frozen dependency of the V5 opponent. Neither the
predictor nor V5 is retrained. The critic and actor have no shared coefficients.

For N eligible complete episodes and T decisions, the existing gradients remain:

```
gW = -sum_episode sum_t [(R - V_old(s_t)) s_t (x_chosen - E_Pold[x])ᵀ] / (100 N)
gv = sum_t [(V_old - R)(1 - V_old²) s_t] / T
clip(g) = g / max(1, ||g||₂)
W_new = project_norm_6(W_old - 30 m clip(gW))       m = 1 control, 10 treatment
v_new = project_norm_3(v_old - 0.1 clip(gv))
```

Operation order: accumulate the original gradients; preserve their /100-episode
and decision-mean normalization; independently clip at norm one; apply the
actor-only multiplier; then project coefficients to the original norm limits.
This implements the audit's tenfold effective gain while honoring this request's
explicit requirement not to change averaging or clipping thresholds. It equals
the proposed /100-versus-/10 scaling when safeguards are inactive. Scaling before
clipping would differ if clipping activated; this implementation does not do that.
Projection can prevent a tenfold *realized* delta. Raw gradient norms, clipping,
preprojection step norms, projections and actual deltas are reported. Value
updates are identical on identical data, but may diverge across arms because
different battle trajectories supply different targets and states.

One SGD update follows each frozen 72-game batch. No entropy term, shaping,
replay, extra epochs, optimizer change, model change or new feature is added.
The original `reinforce.py`, `reinforce_training.py` and repaired historical
`reinforce_experiment.py` remain unchanged. `actor_step.py` implements only this
contrast. Ordinary inference still uses the strict repaired historical loader;
new checkpoints retain the original inference schema with actual current source
hashes. Experiment/update provenance is separately versioned and source-frozen.

## Schedule, seeds and selection

[configs/actor-step.json](../configs/actor-step.json) is the single allowed
configuration. Four unchanged teams, gen1ou, concurrency one, loopback only.
Every cell is 24 games: all six unordered team pairs × both team assignments ×
both challenger sides. Same policy seed scheme across arms; no simulator seed,
paired engine trajectory or matched randomness claim.

- Training: **864 requests**, six 72-game batches per arm (432 each), each 24 V2,
  24 selected V5, 24 own frozen archive. Archive sequence is **c0,c0,c0,c2,c0,c4**.
  The active pool has three policies, with c0 plus at most one recent learned
  archive retained for admission (at most four reference/archive identities).
  All saved checkpoints remain evidence. The admission procedure is equal;
  actual own c2/c4 opponents can differ between arms and are not identical bots.
  Odd batches run control then treatment; even batches reverse that order.
- Selection: **360 fresh requests**. Unique candidates in order: common c0,
  control c3, treatment c3, treatment c6, control c6. Each receives 24 V2, 24 V5,
  24 common historical c0. Within each arm choose c0/c3/c6 by most completions,
  then highest completed mean R, then earliest checkpoint. Initialization is
  eligible and its single 72-game selection result is shared. No updates here.
- Final: **864 fresh requests**, 288 each common initialization, selected control,
  selected treatment. Each receives two 24-game cells against each fixed panel
  member: random, MaxBasePower, V2, V5, historical c0, historical c6. Arm order
  rotates by (repeat + opponent index) modulo three. These references are frozen
  before training. V2/V5/c0 are familiar; random/MaxBasePower/historical c6 are
  reserved from new training/selection, not evidence of human generalization.

Base seed **194000**. Training cell seeds = base + 100×batch + opponent index;
selection = base + 5000 + opponent index; final = base + 10000 + 100×repeat +
opponent index. The existing per-match/player `policy_seed` derives RNG streams.
Same seeds do not match Showdown randomness. One learning seed per condition is
a major limitation; this is not a multi-seed optimization-reliability study.

Every battle identity is run-manifest SHA-256 plus match index. New phases are
disjoint from one another, retained main/smoke games and historical audit examples.
No replay buffer exists. Selection is frozen before final; final cannot change
weights, candidates, archives, exclusions, hyperparameters or reporting criteria.

## Allocations, feasibility and stopping

| Phase | Requests | Wall seconds |
|---|---:|---:|
| Training, both arms | 864 | 1200 |
| Selection, five candidates | 360 | 600 |
| Final, three arms | 864 | 1200 |
| Setup, reports, full audit, hashing | 0 | 600 |
| **Ceiling** | **2088** | **3600** |

All allocations are protected in a persistent single-use ledger before training;
selection/final capacity is reserved first. No borrowing, top-up, retry, resume,
second attempt or extra demonstration games. No battle-based engineering check
is needed: offline regression tests and retained real trajectories suffice.
Their new game count is zero; their measured preparation cost is reported
separately and also compared with the remaining overall wall allowance.
The automated driver protects **120 seconds within the 600-second overhead
allocation** for these offline readiness/test checks. It checks its own measured
elapsed time plus that reserve against the ceiling; the reserve is a conservative
budget charge, not a claim that preparation took exactly 120 seconds. Actual
measured preparation and process durations are reported separately. Interactive
implementation/review latency is not reported as experimental compute time.

Existing evidence: 864 historical training requests took 461.362s; 216 selection
102.708s; 576 final 264.025s. At those rates this schedule predicts roughly 461s
training, 171s selection and 396s final before extra diagnostics. Main reporting
took 24.375s and full replay 139–153s; proportional replay here is about 180–193s.
The 600s overhead reserve supports setup, source/model/team checks, two snapshot
diagnostic sets, replay and hashing. These are feasibility estimates, not promises.
The inspected machine has 42.83 GB physical memory, 23.69 GB available and 153.77 GB
free disk; the original 2.83 GB archive suggests about 3.6 GB for this experiment.
Server startup/shutdown and per-cell audits are already included in phase timings.
No shared server, cached safety check, relaxed audit or concurrency change is used.

Existing limits remain 300 turns, 60s per game, at most 300s per run, with
run timeout min(300, phase remaining−30). The conservative reservation guard
requires at least 90s before each 24-game cell. Setup/phase/report durations use
monotonic clocks; finish is idempotent and read-only reports do not charge ledgers.

Caps receive no reward and remain incomplete even after a cleanup forfeit. After
successful cleanup and audits, independent scheduled games/cells continue. Unknown
learner commitments exclude the whole episode exactly as before. No eligible
episodes means no update and stop. Protocol errors, invalid actions, timeouts,
crashes, cancellations, missing requested records, nonfinite state/losses, source
or identity mismatches, unexpected warnings, leakage, failed cleanup or exhausted
allocations stop. Preserve all partial results; do not repair frozen opponents to
avoid stalls. Unequal usable trajectories are reported, never topped up. Exclusion
is action-dependent and can bias learning; it does not yield an unbiased estimate
of the unfiltered win objective. Known Wrap/Clamp warnings and unknown suffixes
remain visible.

## Metrics, diagnostics and audit

Primary: final **selected treatment minus selected control completed mean R**.
Secondary: treatment minus fresh initialization, control minus fresh initialization;
W/L/D, completed denominators and incomplete counts/rates by phase/arm/opponent.
Report all requested outcomes separately from eligible training episodes. Training
loss/reward and value MSE/advantages are diagnostics, not performance evidence.

Use the unchanged 1,000-resample opponent-stratified four-game team/side-block
descriptive bootstrap, seeds **224000,224001,224002** for those three comparisons.
Resample the 12 four-game blocks per opponent with common schedule indices across
the compared arms. No turn-level intervals. Include the original unknown-outcome
[-1,+1] sensitivity bounds, without imputing rewards. Withhold intervals on an
unfinished requested final schedule. Fixed-team dependence, only one training run
per condition and unmatched engine randomness limit inference. Supported success
requires a positive supported difference versus both controls and no higher
incomplete rate; wide intervals or movement alone remain inconclusive.

Same-input diagnostics use **all learner-a snapshots in both first training
batches** (144 games, including excluded episodes), fixed independently of rewards,
for c0 and each arm's c3/c6. Historical audit snapshots are development only and
are never training examples. After final freeze, all final learner-a snapshots
also compare initial/selected control/selected treatment, descriptively. Record
TV=0.5 sum|P−Q|, KL(P||Q) and reverse KL in nats, entropy, maximum probability,
greedy changes (including exact initial ties) and sampled changes under the same
recorded uniform draw/right CDF boundary. Report generating-arm/opponent breakdowns.
Different sampled actions do not establish counterfactual wins. No diagnostic
value changes the frozen implementation or selects another rate.

Every cell replays both players' learned-policy probabilities, values, draws,
legal choices and commitment joins. The final audit repeats those checks,
reconstructs every update and target exclusion, verifies all frozen pools,
selection and phase identities, checks source/model/config/artifact hashes and
terminal reporting. Final policies are immutable checkpoint snapshots. Privileged
labels/terminal outcomes enter offline updates only; they do not enter features.

## Required inputs and execution

| Input | SHA-256 |
|---|---|
| `runs/reinforce-main/checkpoints/c0.json` | `f7734489bce5d74ce2dedffd8ab274a8483810a03e09b48a26ea0ebf28d44287` |
| `runs/reinforce-main/checkpoints/c6.json` | `597d456a01f009e4638f537d56b950983b4b2de7893f585418de1a567c51bff4` |
| `models/v4-supervised.json` | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| `runs/v5-acceptance/selected.json` | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |

Readiness also verifies retained repair/main manifests and 17 valid retained
checkpoint files through their intended loaders. Originals are required, copied
and hashed, never regenerated. A source-only clone cannot recreate them. Generated
models, runs and source snapshots stay ignored. No loader compatibility exemption
is added: repaired inference remains byte-identical and its explicit historical
compatibility profile remains strict. Future full-source replay needs this frozen
source snapshot and pinned dependencies; do not bypass checks.

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m pytest -q tests/test_actor_step.py tests/test_reinforce_repairs.py
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration'
# Exactly one authorized collection, fresh output required:
.\.venv\Scripts\python.exe -u -m battlemind actor-step-run --spec configs/actor-step.json --output runs/actor-step-acceptance
# Read-only stored report; --audit replays without updating/checkpoint writes:
.\.venv\Scripts\python.exe -m battlemind actor-step-report --experiment runs/actor-step-acceptance
```

No further learning, rate tuning or next action is automatically authorized.
