# V5 experiment specification — written before training

V5 tests whether a small outcome-driven policy update helps. Improvement is a
hypothesis. V4 predictor SHA-256 is fixed at
`44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`.
Its preprocessing, `visible-logistic-v1` features and coefficients never change.
The four Gen 1 OU teams and pinned engine/runtime remain unchanged.

## What learns

Four dimensionless parameters theta, initialized to zero and bounded [-1, 1]:

1. **anticipation**: add theta[0] * p * (switch utility - stay utility) to ordinary
   damaging-move V4 scores. -1 cancels the original anticipation adjustment; +1
   doubles its effect. The actual probability p is unchanged.
2. **recovery**: add 100 * theta[1] to Recover, Soft-Boiled or Rest only where V4's
   unweighted healing utility is positive. Known unusable healing is not rewarded.
3. **status**: add 100 * theta[2] to other ordinary zero-power moves with positive
   original utility (including setup). Unsupported zero-utility moves stay zero.
4. **switch_threshold**: voluntary switching requires visible position gain
   > 80 + 40 * theta[3] (40..120); retain V2's own-switch two-turn cooldown.
   Eligible switch utility is best original move utility + gain - threshold;
   ineligible switches retain -1000. This reuses V2 position utility, not a simulator.

Forced replacement and engine-action scores stay V4's, including mixed requests.
Unknown quantities remain unknown. Zero parameters directly preserve the original
V4 score values and ties; initialization equivalence will be tested on fixtures
and real archived observations. V4 remains unchanged and no extra V4 final arm is
needed if equivalence passes. The primary control is frozen initialization c0.

## Update equations and training outcomes

Two rounds of antithetic, derivative-free score optimization:

```
epsilon_r[i] independently in {-1,+1}, NumPy default_rng(51500 + r)
sigma = 0.4; alpha = 2.0
theta_plus  = clip(theta_parent + sigma * epsilon_r, -1, 1)
theta_minus = clip(theta_parent - sigma * epsilon_r, -1, 1)
J(theta) = mean(completed win=1, draw=0.5, loss=0)
theta_next = clip(theta_parent + alpha * (J_plus-J_minus)/(2*sigma) * epsilon_r, -1, 1)
```

No damage, survival, turn-length or other reward shaping. Parameters update only
after both complete candidate batches and their audits. The arithmetic step is
not guaranteed better than its parent and is not called a promotion. Equal
objectives mean a recorded zero update; no extra round is added to force learning.
This is a small random-direction evolutionary/finite-difference method, not
gradient-based reinforcement learning. One direction per round has high variance;
clipping makes the estimate biased near bounds. No gradient through Showdown is used.

All requested games in a candidate comparison must complete with audited legal
choices and no action failures/unexpected warnings. Caps, crashes, cancellation,
timeouts, missing games and cleanup forfeits have **no terminal reward**. Any
incomplete block makes the entire round ineligible for update and stops the
experiment, preserving remaining phase reservations. Known Wrap/Clamp annotation
warnings and explicitly unknown intended-label suffixes remain visible; a valid
completed-game outcome does not require guessing those labels.

## Opponents, admission and schedules

All opponents are frozen for a full round. IDs are orchestration metadata only.

- Round 1 parent c0: candidates +/- against V2, `switch-active`, frozen c0.
  2 * 3 * 24 = **144 training games**. Save arithmetic update as c1.
- Round 2 parent c1: candidates +/- against V2, `switch-active`, c0 and c1.
  2 * 4 * 24 = **192 training games**. Save arithmetic update as c2.
- Pool is capped at four; c0 stays to check forgetting, plus both fixed heuristics.
  c1 enters only after round 1 completes. No opponent changes inside a comparison.
- Candidate policy seed 51601 in round 1 and 51602 in round 2, identical across
  signs. All six unordered team pairs have both assignments and challenger sides:
  **24 games per cell**, concurrency 1. Simulator randomness is uncontrolled.

These outcome updates include play against frozen earlier versions of the same
parameterized policy. This is bounded self-play policy optimization mixed with
handwritten opponents, not exclusively handwritten-opponent optimization and not
individual-opponent adaptation. If c1's parameters happen not to change, report it.

## Selection and reserved final evaluation

Selection uses **fresh games** for exactly c0, c1, c2 against V2,
`switch-moderate`, c0: 3 * 3 * 24 = **216 games**, policy seed 51701.
Choose highest mean terminal reward, then smallest squared distance from c0,
then earliest checkpoint (c0 before c1 before c2). Incomplete selection stops;
no replacement games. Selection cannot update parameters. Save chosen artifact
and its hash before any final game. The selected checkpoint may be c0.

Final arms: **c0 and selected**, each against random, MaxBasePower, V2,
`switch-active`, c0 and c1: 2 * 6 * 24 = **288 games**, seed 51801.
All opponents are fixed before final play; no new checkpoint is admitted afterward.
Both arms use identical predictor, scoring implementation, teams/sides and limits.
c0/c1 and the old heuristics check forgetting; this is a fixed-panel experiment,
not an unseen-opponent/held-out-team claim. If selected equals c0, retain both
scheduled arms and say explicitly that no parameter contrast was selected.

Battle identity is SHA256(run.json):match. Record all battle keys, including failed
or empty-label games, in separate training/selection/final partitions. No overlap
is allowed. Earlier V4 outcomes are historical context, not V5 update or selection
data. Final outcomes cannot affect parameters, checkpoint choice or this protocol.

## Exact budgets and stopping

| Phase | Requested-game allocation | Wall allocation |
|---|---:|---:|
| Training | 336 | 420 seconds |
| Selection | 216 | 300 seconds |
| Final, reserved before training | 288 | 420 seconds |
| Setup/final reporting margin | 0 | 60 seconds |
| **Total** | **840** | **1,200 seconds** |

The user ceiling is 1,200 requested games/20 minutes; this design reserves only
840 games. Allocations cannot be transferred to additional training or retries.
Per-run limits remain unchanged; acceptance uses 24 games, 300 turns, 60s/match,
run timeout capped by phase time remaining with cleanup margin. Before each run,
reserve its requests durably and verify source/predictor/checkpoint hashes. Stop
on deadline, budget exhaustion, mutation or invalid/incomplete evidence. Preserve
unstarted allocations separately. Resume is unsupported: an existing experiment
directory/ledger is rejected, including interrupted work. Never overwrite it.

Separate verification budget: existing integration suite 25 requested games plus
at most 12 V5 integration games, total <=37 (not training/selection/final data).
No acceptance data is recollected to improve results. All services use 127.0.0.1.

## Metrics, uncertainty and audit

Report every proposal/seed/parent, actual outcome contrast, updated vector, checkpoint
hash, pool change, selection score/tie handling and final freeze. Record complete
W/L/D, requested/completed/incomplete games by phase/opponent, warnings, label
coverage/exclusions, invalid actions, resources, consumed wall time and hashes.
Terminal reward is primary; completed-game win rate includes draws in denominator.

Final uncertainty: descriptive 1,000-resample bootstrap, seed 51901, of complete
four-game team-pair blocks within each fixed opponent. Resample the same schedule
block indices across arms, retaining all four actual outcomes in each arm; this
matches schedule composition, **not engine trajectories/RNG**. Report selected
minus initial mean-reward and win-rate differences with percentile 95% intervals.
Wilson intervals are descriptive win-rate summaries, never the sole significance
argument. No turn-level outcome samples. Interpret this small fixed panel only.

Offline audit replays learned scoring and initial/selected alternate choices on
the same frozen snapshots, validates legal commands and post-match labels, and
reconstructs candidate proposals, complete-block objectives, both updates and
checkpoint selection from retained games. Parameters and all comparison identities
stay outside policy features. Preserve weak candidates and negative findings.
