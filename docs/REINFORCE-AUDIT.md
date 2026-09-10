# REINFORCE retained-evidence audit — 2026-09-09

**The audited gradient/update path is mathematically consistent, but the learned
policy barely departed from its stochastic heuristic initialization.** Two narrow
loader/reporting defects were reproduced; neither affected the retained run.
The value baseline explained essentially none of the observed return variance.
These findings explain limited behavioral movement; they do **not** prove that
larger steps, a better critic, or different features would improve battle results.

This audit collected **zero games**, fitted **no model on historical data**, and
changed no production behavior or historical artifacts. Synthetic algorithm tests
are separate from Pokémon evidence. REINFORCE's original conclusion remains
“actual updates, no demonstrated improvement.” **V6 acceptance remains incomplete.**

## Evidence and what actually ran

The starting workspace was clean at Git `d1f86c2` (`reinforce`). The main frozen
source closure matches the current source byte-for-byte. Future strict audits
require that version or `runs/reinforce-main/source-snapshot`, compatible pinned
runtimes and retained inputs; a source-only clone cannot recreate historical
checkpoints or engine trajectories. The verified environment is Python 3.14.3,
NumPy 2.5.2, poke-env 0.16.1, Node 24.19.0 and official Showdown commit
`2f5b273925862ac242b419086c1e7a8868b51da1`.

The [configuration](../configs/reinforce-main.json),
[specification](REINFORCE-EXPERIMENT.md), [implementation](../src/battlemind/reinforce.py)
and [historical results](REINFORCE-RESULTS.md) agree:

- **No imitation and no random initial weights.** Actor W and value v start at
  zero. Initial logits are `clip(V2_score / 50, -3, 3)`. This intentionally differs
  from deterministic V2 and V5; c0 is the correct primary control.
- Each frozen observer snapshot supplies 37 normalized state features and 22
  features per **currently legal** action. Logits are `prior + sᵀWx`; value is
  `tanh(vᵀs)`. The 814 actor and 37 critic coefficients are separate. The V4
  predictor is used by the V5 opponent, not this learner or critic.
- Both rollout and evaluation sample temperature-one softmax using a seeded
  policy RNG. Opponent/checkpoint identities schedule games and never enter
  features. No simulator seed or private critic is used.
- Twelve frozen 72-game batches each contain 24 V2, 24 V5 and 24 archived learner
  games. Archives by batch: c0,c0,c0,c2,c0,c4,c0,c6,c0,c8,c0,c10. One SGD update
  follows each batch; no replay, shaping, entropy bonus or extra optimization epochs.
- Selection used fresh 72-game schedules for c0/c6/c12. Completed mean returns
  were −0.47222/−0.37500/−0.44444, all with 72 completions. The declared rule
  (completion count, then mean return, then earliest checkpoint) selected c6.

The read-only audit verified 7,713 main manifest entries, **83,170 recorded learned
decisions**, all 12 updates, 3,310 terminal-perspective checks, 1,656 disjoint phase
identities and zero smoke overlap. Original V4/V5 strict loaders passed.

| Required artifact | SHA-256 |
|---|---|
| Main freeze | `220f1f2be4fad0060420362515b9577696894bdc427dea780af430f192f67bc1` |
| Main configuration | `90bb8b5506b3617a43a2cd14b7c136589a55376abe433726f363f8885a205fa8` |
| Main specification | `89f14d3ad521d73ff7b6187dc36088f3325a90790aa04e9bd158e820b5b861ae` |
| Initial c0 | `f7734489bce5d74ce2dedffd8ab274a8483810a03e09b48a26ea0ebf28d44287` |
| Selected c6 | `597d456a01f009e4638f537d56b950983b4b2de7893f585418de1a567c51bff4` |
| Original V4 | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| Original selected V5 | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |

All thirteen checkpoint hashes and compatibility checks are in
[integrity.json](../runs/reinforce-audit-20260909/integrity.json).

## Correctness: supported checks and confirmed defects

For admitted episodes, terminal return R is +1/0/−1 for learner win/draw/loss.
The actor loss is `−sum[(R−V_old) log P_old(chosen)] / (100 × episodes)`.
The critic loss is the **decision mean** of `0.5 × (V−R)²`. Discount is one:
each decision receives the same eventual return; episode sums are not divided
by episode length. The /100 factor is a fixed step scale, not reward shaping.

Independent finite differences at nonzero weights, mixed outcomes, variable
episode lengths and masks gave maximum derivative error **4.91e−11**. Independent
arithmetic on retained data reproduced probabilities within **5.56e−16**, logits
and values exactly, and saved updates within **7.64e−17**. Log-softmax signs,
detached advantages, entropy and tanh derivatives agree. Actor/value gradients
are separately clipped to norm one; SGD rates are 30/.1, followed by coefficient
norm limits 6/3. Neither clipping nor projection activated in main training.

Legal sets are constructed from request-backed actions before softmax, with no
illegal output slots. Singleton engine requests give P=1 and zero actor gradient;
forced replacements use legal switches. Stored parent hashes, probabilities,
draws, request mappings and separate terminal targets replay correctly. Only
training player-a episodes enter updates; player-b rewards were independently
checked against swapped roles. Frozen evaluation only advances its local RNG.
No shared trainable trunk lets critic gradients overwrite actor coefficients.

Two **unrepaired** defects:

1. [reinforce.py:99](../src/battlemind/reinforce.py#L99), reached through
   `load_checkpoint`: validation converts coefficients to float for checking but
   retains the originals. A JSON numeric string passes loading and later causes
   inference `UFuncTypeError`. All **11,063** historical coefficients checked are
   genuine finite numbers; this did not affect collection or checkpoint replay.
2. [reinforce_experiment.py:294](../src/battlemind/reinforce_experiment.py#L294):
   common-draw reporting uses NumPy's default left CDF boundary; the sampler uses
   right. With P=(.5,.5), draw=.5, reported and actual indices differ. There were
   **zero exact boundary ties** in all 83,170 recorded learned decisions and in
   the five-checkpoint final comparison. The historical 0.74% result is unchanged.

These are defensive-validation/reporting bugs, not evidence of a reversed reward,
broken gradient, stale-policy update or historical information leak. Passing this
audit is not a proof of correctness for every possible future input.

## Movement and initialization

These are **same-input descriptive diagnostics** on all 20,389 final learner-a
snapshots from both generating arms. They are no longer untouched future test
data. KL below means the state-wise `sum P(c0) log[P(c0)/P(cK)]`, averaged over
snapshots; reverse-direction KL is also retained in `movement.json`.

| Checkpoint | Actor norm | Mean TV from c0 | Mean KL(c0‖cK) | Entropy, nats | Mean maximum P | Greedy changes | Common-draw changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| c0 | 0 | 0 | 0 | 1.05641 | .53474 | 0% | 0% |
| c3 | .11395 | .002573 | .00004295 | 1.05738 | .53513 | 6.41% | .525% |
| c6 | .16534 | .003974 | .00006963 | 1.05626 | .53530 | 8.06% | .741% |
| c9 | .26234 | .007714 | .00024291 | 1.05015 | .53767 | 6.23% | 1.604% |
| c12 | .30263 | .009686 | .00037164 | 1.04785 | .53993 | 6.83% | 1.766% |

The 0.740595% is **151/20,389**: apply each policy to the same legal list with
the *same recorded uniform draw*, then compare chosen IDs. It does not compare
independent RNG draws or imply matched simulator trajectories. Integrating the
ordered CDF disagreement intervals gives expected disagreement **0.7058%** for
these distributions. That coupling need not attain TV's minimum disagreement.

Of 1,644 greedy changes, **1,618 break exact initial ties**; only 26 overturn
strict order. The largest overturned initial logit gap is .02210. Direct TV/KL
measurements, not unchanged samples alone, establish small probability movement.
c6's mean action-relative residual logit range is **.03279**, versus the fixed
prior's **4.57837**; maximum residual range is .10265. Mean alternative-action
mass remains **46.47%**, so this is not a nearly deterministic, exploration-free
policy.

Movement is concentrated in ordinary requests: mean TV .004708, versus .000403
for forced replacements, .002721 for engine requests with alternatives and zero
for 682 singleton engine requests. Removing all singleton requests leaves mean
TV .004201. Conditional category mass changes are small: damaging moves
.75965→.75694, recovery .13911→.13867, status/other .15830→.16226, voluntary
switches .07703→.07734 and setup .14151→.14082. These have different
availability denominators; they must not be added together. Full state, opponent,
generating-arm, category and quantile breakdowns are in the diagnostic JSON/CSV.

c0 exactly reproduces its **specified clipped softmax**, not V2's choices.
Its greedy choice matches V2 96.49%, but its sampled choice matches only 52.97%
(48.75% on ordinary requests). Clipping creates extra ties, and sampling spreads
mass over lower-scored actions. Ordinary requests give V2-zero-scored moves
5.92% average mass. Across actual final choices from **both arms**, 113/1,112
Recover/Soft-Boiled selections occurred at full visible HP; 463/1,688 direct
status-move selections faced an already-statused visible target. Those are
potentially inefficient choices, not proven failures: damage or switching can
occur before resolution. No imitation objective or held-out imitation result exists.

The representation has real blind spots. In **2,046 snapshots**, Ice Beam and
Thunderbolt have identical action vectors and prior: **every possible W must
assign equal probabilities there**. Their secondary statuses differ in pinned
official move data, but those effects and PP are not features. Switch candidates
also collide after position-score compression. The critic omits move/coverage
composition and public history beyond its coarse state fields. Displayed boosts
remain observations, HP precision remains in snapshots, and effective stats stay
unknown. Adding parameters cannot recover information absent from these inputs;
the audit does not establish which omitted feature costs the most wins.
Also, the 37 actor coefficients multiplying the constant action-bias feature
shift every legal logit equally and cannot affect softmax choices. The nominal
851 coefficients are not 851 independent degrees of policy freedom.

## Credit assignment and exclusions

Training completed 863/864 games; **793 episodes** were admitted (250W/526L/17D),
including 252 archived-self-play episodes. They contain 30,879 decisions but only
793 distinct terminal targets, with schedule and shared-training-history dependence.

Decision-weighted return mean/SD is −.32715/.93132; advantage mean/SD is
−.31148/.93143. The old value prediction averages **−.01567**, ranging from
−.03861 to zero. Its MSE is **.96459**, versus .97438 for zero; explained variance
is **−.000243**. Episode-weighted explained variance, comparing each episode's
mean value to its return, is .000140. Per-batch values are similarly near zero.
The critic makes a small mean correction and offers almost no discrimination.

Actor gradient norms are .00161–.00298; update norms are .04825–.08951.
The norm of each batch's summed episode gradients is only 9.56–19.30% of the
sum of their separate norms. A descriptive four-game-block noise scale is
comparable to the net gradient (ratio .72–1.45), not a significance test.
Critic adjustment changes actor gradients by at most .0000696 in norm. Its
larger raw gradient norm cannot “overwhelm” the actor because weights are disjoint.

Early/middle/late thirds have mean per-decision gradient contribution norms
.255/.222/.185. All thirds contribute; there is no evidence that only final
actions receive credit. Longer episodes contribute more score-function terms:
mean episode gradient norm is 1.276 for ≤25 requests and 2.654 for >100, with
length/norm correlation .435. This follows the declared undiscounted episode-sum
objective, but can increase variance. Neither these data nor the passing delayed
synthetic task proves reward shaping or a larger model is necessary.

| Training opponent | Requested | Admitted | Unknown-commitment exclusions | Cap |
|---|---:|---:|---:|---:|
| V2 | 288 | 270 | 17 | 1 |
| V5 | 288 | 271 | 17 | 0 |
| Archived learners | 288 | 252 | 36 | 0 |

All **70** unknown episodes have equal attempt/engine-stream lengths, one recorded
successful send per attempt, and a first literal mismatch at `maybe_locked=True`.
The engine records **35 Wrap, 12 Clamp, 23 fight** substitutions. Pinned
`sim/side.ts:675–699` explicitly canonicalizes locked/partially-trapped choices.
The label recorder correctly preserves unknown suffixes instead of guessing.

This is strongly structured exclusion: unordered pair 0–1 loses 0/144 episodes;
0–2:5, 0–3:18, 1–2:4, 1–3:19, 2–3:24 unknown episodes. Own team 3 accounts
for 44/70. Median excluded/admitted lengths are 36.5/33 requests, so this is not
simply a long-game cutoff. Whole-episode filtering removes **983 unknown and
1,760 verified-prefix requests**. The excluded completed outcomes were 31W/38L/1D;
their higher win fraction and different self-play/team coverage show selection
bias, without proving the direction of the resulting policy bias. Every episode,
batch, ordered team assignment, first mismatch and public context is retained in
`exclusions.json`; none received a training reward during this audit.

The distinction matters: a legal **selected command**, attempted send, completed
send, canonical engine commitment, action announcement/effect and terminal result
are different events. REINFORCE can optimize sampled *commands* without requiring
the same move to execute: prevention/canonicalization may be part of the
environment. Therefore whole-episode exclusion is **not a mathematical
requirement** of REINFORCE and is broader than necessary for a validated command
trajectory contract. Establishing that contract is separate engineering work;
this audit does not promote unknown labels or relax historical admission. The
present action-dependent exclusion also prevents claiming an unbiased gradient
of the unfiltered win objective.

The sole cap is `training/b7-vs-v2`, match 16, pair 1–3. Its last public position
has frozen Chansey (343/703 exact) against frozen Zapdos (48/100 public scale),
with only `engine:fight` legal. **283/305 requests** are singleton engine requests.
The 300-turn cap is retained as incomplete; all 305 commitments were verified,
but no genuine terminal reward exists. It is not a loss or draw. Later audited
independent games continued. This stall provides no action-choice learning signal
at its singleton tail.

## Representative decisions and what followed

Ten first-occurrence cases were selected by the
[predeclared audit plan](../diagnostics/REINFORCE-AUDIT-PLAN.md), with no supplied
user turn. [details.md](../runs/reinforce-audit-20260909/diagnosis/details.md) and
`cases.json` contain full visible snapshots, **all** V2/c0/c6 scores/probabilities,
V5 evaluations, actual draws and subsequent observer-public events.

- First V2 loss: `selected-r0-vs-v2`, `m1:a:r2`, turn 1. Full-HP Starmie sees
  unrevealed-move Alakazam. V2/V5 and both sampled learners choose Surf
  (c0 .5101, c6 .5147). The opponent switches to Chansey; Surf leaves it at
  84/100. The eventual loss does not identify this shared opening as an error.
- First V5 loss: `selected-r0-vs-v5`, `m0:a:r2`. Full-HP Alakazam sees Starmie.
  V2 and both learners switch to Chansey (.3592→.3609); V5 instead prefers
  Thunder Wave. Surf then leaves own Chansey at 599/703. No hidden switch or
  move was known beforehand, and the alternative is not a demonstrated win.
- First recovery: `selected-r0-vs-random`, `m0:a:r24`. Chansey at 302/703
  selects Soft-Boiled (.5400→.5438), reaches 653/703, then takes Body Slam to
  393/703. At `r32`, just above V2's .55 threshold, both learners recover while
  V2/V5 prefer Ice Beam; Hyper Beam then leaves 188/703. A heuristic zero is
  not proof that healing was wrong.
- First common-draw disagreement: the same run, `m1:a:r78`. Chansey faces a
  paralyzed Chansey; draw .922973 changes c0 Soft-Boiled to c6 Thunder Wave
  (.06422→.06633 for Thunder Wave). The opponent switches to Alakazam, which
  is then paralyzed. That favorable resolution was not available to the policy.
- Switching, forced replacement, Sleep Powder, Amnesia and sleeping-engine
  cases are also retained. Amnesia was selected but paralysis prevented it;
  `engine:fight` produced a sleep `cant`. Announced/selected actions must not be
  mistaken for successful execution. This small case sample does not estimate
  strategic-error prevalence.

## Findings, ranked recommendations and one proposed experiment

**High confidence:** small distribution movement, a weak stochastic starting
policy relative to deterministic references, an ineffective retained value
baseline, representation collisions and structured exclusions. **Moderate
confidence:** terminal-credit cancellation and conservative effective actor
steps contributed to the small movement. **Untested:** whether more movement,
better baseline fitting or recovering command trajectories improves wins; which
representational omission matters most. One training seed cannot separate these
causes or measure optimizer reliability.

Recommendations, in order:

1. Test the **effective actor step scale** with a fresh control. It directly tests
   the measured .0328 residual-versus-4.578 prior gap without changing exploration,
   features, rewards or initialization. Larger steps may amplify noise and regress.
2. Separately harden numeric-type rejection and CDF reporting before future
   collection, with retained-snapshot invariance checks. They are not explanations
   of this run and no repair was made here.
3. Specify a trustworthy sampled-command trajectory contract before reconsidering
   whole-episode exclusions. Keep private intended-choice audits strict. Feature
   additions or critic redesign need separate evidence; do not bundle them into
   the step-scale experiment.

**Exactly one proposed experiment; NOT executed:** compare actor scale **/100
versus /10**, with the same SGD rate 30 (tenfold effective actor gain). This is
one principal change, retaining gradient/norm safeguards. Hypothesis: step scale
currently suppresses useful outcome-driven residual movement; the larger gain
will improve fresh completed-game outcomes without increasing incompletes.

- Two fresh learners start at the same frozen zero-residual c0. Freeze V2 prior,
  37×22 features, critic/lr .1, reward, masks, temperature-one sampling, admission,
  four teams and source compatibility. No imitation, shaping or historical-data
  fitting. Numerical preflight uses synthetic fixtures only.
- **Training: 864 games**, six 72-game batches per condition. Each batch is
  one-third V2, one-third V5, one-third frozen own archive, with archive sequence
  c0,c0,c0,c2,c0,c4 in both conditions. Freeze within batches; update between them.
  Use new fixed policy seeds and balanced 24-game cells; engine randomness remains
  unmatched. Historical audit snapshots are development diagnostics only.
- **Selection: 360 fresh games.** Five unique predeclared candidates: common c0,
  c3/c6 from each condition; each receives 72 against V2/V5/frozen common c0.
  Choose within each condition from c0/c3/c6 by completion count, mean return,
  earliest checkpoint. No selection updates or new hyperparameter search.
- **Final: 864 fresh games**, 288 each for common initialization, selected /100,
  selected /10. All face the same frozen panel: random, MaxBasePower, V2, V5,
  historical c0, historical c6; 48 games per opponent per arm. Those archived
  references are fixed before collection, not selected by new final performance.
  These are fixed-team results, not unseen-opponent/generalization claims.
- Proposed ceiling **2,088 requested games / 3,600 seconds**, concurrency one:
  training 1,200s, selection 600s, final 1,200s, setup/report/audit 600s. Reserve
  final first in a new single-use ledger; no borrowing, retries or extra games.
  Existing evidence supports feasibility but does not guarantee runtime. Caps
  get no reward; continue independent games only after valid cleanup. Protocol,
  numerical, identity/hash or cleanup failure stops the experiment.
- Primary comparison: final selected /10 minus selected /100 mean terminal return,
  with initial control also reported; opponent-stratified four-game-block
  descriptive intervals and explicit incomplete rates/bounds, never turn-level
  intervals. Success requires a positive supported difference versus both controls
  without higher incompletes. Supported regression or a numerical/integrity failure
  is failure. Changed probabilities alone, wide intervals or differential missing
  outcomes are inconclusive. A single fresh learning seed per condition remains
  a limitation even if final games favor one; no rerun for better results.

## Tests, commands and audit outputs

The fixed synthetic suite used eight active toy coefficients (zero-padded to call
production routines), seed 460901, and **1.855s wall / 1.828s CPU**, under the total
120s allowance. Constant-action, contextual, variable-mask and delayed-terminal
tasks passed their predeclared thresholds (.988, .987–.988, .942–.996, .995).
Opposite-return signs, nonzero-weight finite differences, clipping and both defect
reproductions passed. No repeated tuning occurred. Existing unit checks:
**179 passed, 14 integrations deselected, 5.01s; zero test games.**

Actual commands, from project root (none starts a server):

```powershell
.\.venv\Scripts\python.exe diagnostics/reinforce_integrity.py
.\.venv\Scripts\python.exe diagnostics/reinforce_synthetic.py
.\.venv\Scripts\python.exe -m py_compile diagnostics/reinforce_diagnose.py
.\.venv\Scripts\python.exe diagnostics/reinforce_diagnose.py
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration'
.\.venv\Scripts\python.exe diagnostics/reinforce_details.py
.\.venv\Scripts\python.exe diagnostics/reinforce_close.py
git diff --check
```

The standalone helpers intentionally live outside the historical source closure;
fresh-output guards prevent accidental overwrite. Console outputs were redirected
to `.local/reinforce-diagnostic-*.log` and `.local/reinforce-audit-unit-tests.log`.
All generated diagnostic data remain ignored under
**`runs/reinforce-audit-20260909/`**. Entry points:

- `integrity.json`, `inputs-before.json`, `closure.json`, `audit-hashes.json`:
  provenance, original-file preservation, exact hashes and final read-only closure.
- `synthetic/results.json`: fixed tests, timings and defect fixtures.
- `diagnosis/{movement,reference,action-categories,representation}.json` and
  `final-snapshots.csv`: distributions, state/category strata and feature collisions.
- `diagnosis/{updates,credit,exclusions}.json`, `training-{steps,episodes}.csv`:
  independent arithmetic, all 70 exclusions/cap and reward/gradient accounting.
- `diagnosis/{cases,additional}.json`, `details.md`: deterministic case reviews,
  tie audit and public cap evidence.

Full integrity replay took **142.454s wall / 141.453s CPU**; main diagnostics
**69.812s / 69.531s**, with maximum sampled RSS **621,944,832 bytes**; supplemental
tie/case analysis **12.771s / 12.672s**. These are audit costs, not new experimental
collection or synthetic-training time. Closure records its own timing and final
artifact sizes. Documentation/interactive latency is not a compute measurement.

The historical final result remains c0 **159W/125L/4D**, selected c6
**155W/128L/5D**, 288 completed games each. Mean-return difference −.02431,
descriptive block interval [−.15278,.09375], does not establish improvement or
reliable regression. V2 matchup: c0 7W/41L, c6 17W/31L; V5: c0 14W/33L/1D,
c6 9W/38L/1D. Different opponent point estimates do not establish forgetting.
The audit cannot supply missing counterfactual wins, additional training seeds,
human/general-generation evidence, or V6 acceptance.
