# Sampled action → command contract audit

2026-09-10. Retained evidence only. This follows the recommendation in
[ACTOR-STEP-RESULTS.md](ACTOR-STEP-RESULTS.md), its frozen
[specification](ACTOR-STEP-EXPERIMENT.md), and the
[original audit](REINFORCE-AUDIT.md) / [repairs](REINFORCE-REPAIRS.md).
No production code, dependency, checkpoint, eligibility rule, or historical result
was changed. No battles or training were run. V6 acceptance remains incomplete;
the actor-step experiment demonstrated greater movement, not better battle play.

## Contract and what the records prove

| Stage | Retained evidence and its limit |
|---|---|
| Observer state | Frozen `DecisionSnapshot`, serialized before sampling/submission, with snapshot SHA-256 and public-history prefix. Own raw HP/unknowns are preserved. No hindsight reconstruction is used. |
| Legal choices | Ordered semantic IDs and per-request command map. Move IDs represent the visible request's moves; switch IDs represent original own-team slots, translated to current request roster indices. Disabled/unavailable moves are filtered when the snapshot is built. |
| Sampling | Frozen checkpoint digest, ordered probabilities/logits, value, uniform draw, chosen ID. There is no separately stored scalar log probability: the update takes `log(p[chosen_index])` from the stored/reproduced vector. |
| Resolution | `resolve_action` checks membership and the `|rqid` suffix. Each retained chosen command matches its map. Raw request JSON, including its complete original index menu, is **not** retained; independently redoing request extraction is unavailable. |
| Attempt | Each player's separate journal receives the snapshot, sampled ID and resolved command before the send. This proves local intention, not receipt or acceptance. |
| Send completion | The `submitted` event follows awaited WebSocket send. It contains player/match/request ID, not a server acknowledgment. |
| Commitment | Official end-log `inputLog` is written after all choices are locked. It holds canonical move names/switch indices, without client `rqid` or per-choice timestamp. Original labels use strict same-ordinal matching per side, with no search ahead. |
| Public execution | The observer's subsequent public interval can show a move announcement, switch or `cant`; an announcement does not prove damage, success, or even that the submitted move was the one executed. Missing announcements do not establish another choice. |
| Outcome | Only the runner's consistent, completed terminal outcome may supply a reward. Cleanup callbacks are not sufficient. The retained cap has terminal cleanup loss/win callbacks, but `status=truncated`, `winner=null`, and no training reward. |

Decision IDs are `m{match}:{side}:r{rqid}`; identities across runs additionally need
the run-manifest SHA-256. `rqid` comes from the room's increasing request counter,
so it is not a shared turn number. Forced replacements can add requests without
an ordinary two-player move choice. Histories have turn numbers and event indices.
Run creation UTC and battle durations exist; per-decision/send/commit timestamps
do not. Neither wall-clock proximity nor a later convenient move establishes a join.

The pinned client serializes each battle's message handling through a battle lock.
BattleMind ignores repeated request IDs, rejects unexpected retry requests, and
intercepts choice errors instead of using poke-env's random/default fallback.
It sends the resolved string unchanged. The default battle timer is off; the
runner applies bounded caps/timeouts and closes the clients before combining
their journals with privileged end logs. Ordinary switches, forced replacements
and `fight`/`recharge`/`struggle` engine choices keep their different semantics.
There are no four-move/six-switch assumptions in the action mask.

`trajectories()` currently excludes **the whole learner episode** for a noncompleted
status, missing trajectory, or any `intended_kind=unknown`. One mismatch therefore
also excludes its verified prefix. Sampling validity and opponent-prediction
target eligibility are different contracts: an executed announcement is not
required for sampled-action credit, and a valid sampled action does not establish
a genuine voluntary-switch versus move target for the other observer.

## Pinned source and normalization

Inspected installed poke-env **0.16.1**, unchanged official Showdown commit
**`2f5b273925862ac242b419086c1e7a8868b51da1`**. File hashes are in the input inventory
and `source-references.json`. Relevant paths and lines:

- `runner.py:139–216,244–340`: isolated request handling, journal-before-send,
  send-completion events, terminal/cleanup boundary. `adapter.py:161–223`: mask,
  immutable extraction and request map. `labels.py:108–163,185–225`: ordered
  exact commitment matching and persistent unknown suffixes.
- Installed `poke_env/player/player.py:295–420`, `ps_client/ps_client.py:168–186,307–327`,
  and `player/battle_order.py:37–70`: request/error defaults, battle message lock,
  WebSocket send and unchanged string command. BattleMind overrides the relevant defaults.
- Engine `server/chat-commands/core.ts:1122–1127` and
  `server/room-battle.ts:617–638,778–812`: validate request ID, forward raw choice
  **without rqid** to the simulator, handle errors, assign new request IDs.
- `sim/side.ts:552–599,675–720`: numeric move menu lookup, locked/semi-locked move
  normalization, Gen 1 frozen/asleep/partially-trapped `fight`, unavailable-move
  `struggle`, and the special `testfight` branch. A legal index must pass initial
  lookup before normalization. `testfight` is not a command emitted by this adapter.
- `sim/pokemon.ts:955–969,1090–1134` and Gen 1 `conditions.ts:192–275`:
  request concealment through `maybeLocked`, trapping and fake trapping, and a
  semi-lock's stored move. Earlier random trapping duration influences the hidden
  state; `maybe_locked=True` alone does **not** prove that a lock still exists.
- `sim/battle.ts:2964–3035`, `sim/side.ts:323–350,1142–1181`:
  `inputLog` records `getChoice()` **before** `side.commitChoices()` performs Gen 1
  last-selected-move bookkeeping and changes the queued move ID. Gen 1
  `scripts.ts:145–220` then handles prevention, overrides and PP. Canonical input
  text is neither a complete simulator action structure nor an execution trace.

If a semi-lock exists, valid submitted move alternatives can all reach its stored
move. In the Gen 1 `fight` branch they can all reach the same waiting action.
These are source-supported deterministic branches conditional on actual engine
state, not proof that every `maybe_locked` request takes them. Switches are not
members of this move-only equivalence class. Missing raw menus and request-bound
acceptance evidence prevent certifying every counterfactual member from these
records. Equal canonical text in different states is not transition equivalence.

## Which probability the gradient needs

Let `O_t` be the frozen observer snapshot, `A_t` the sampled **semantic legal ID**,
`C_t=f(O_t,A_t,request_t)` its submitted command, and `X_t` the engine's accepted
action structure. The log probability is `log πθ(A_t|O_t)`, not the probability
of an announcement, canonical move name, or the move that eventually executes.
The actor logits are the frozen prior plus `x(O,a)^T W^T s(O)`; the value is a
separate observer-only baseline. For a genuinely completed game with reward `R`:

```
J(θ) = Eτ~πθ[R(τ)]
∇J = E[R Σt ∇ log πθ(A_t | O_t)]
g_actor = -1/(100 N) Σeligible episodes Σt
          (R - V_old(O_t)) s(O_t) [x(O_t,A_t) - Σa π_old(a|O_t)x(O_t,a)]^T
```

This last expression is the actual negative surrogate gradient at the frozen
rollout policy. The fixed 1/100 is a scale, not averaging by episode length.
Clipping and the actor-step multiplier occur later and do not change which action
the probability describes. No update function was called in this audit.

**Sampled-ID estimator:** a deterministic many-to-one map does not require summing
probabilities when the actual sampled ID remains known. Treat normalization,
prevention and subsequent randomness as the environment transition kernel. The
score-function identity remains valid provided the sampled command really drove
that kernel, the transition/opponent mechanism has no additional direct dependence
on θ, draws are sampled as recorded, and rewards/trajectory inclusion obey the
stated objective. The normalizer may depend on hidden pre-action state; that state
need not become a policy or critic feature. Its distribution and future independent
randomness are integrated out. Changing visited-state frequencies is already part
of the trajectory distribution, not permission to condition on favorable futures.

**Marginalized estimator:** if instead only an accepted action `X` were retained,
and a known fixed mapping `g_h` fully defined its action representation, then
`qθ(x|h)=Σ{a:g_h(a)=x} πθ(a|O(h))`. Use `∇log qθ`, the probability-weighted mean of
the contributing sampled-action scores. Using the probability of a convenient
canonical representative is wrong. A hidden/uncertain mapping needs its joint
conditional law; summing a few same-name menu entries is insufficient. A lossy
canonical string also cannot stand in for distinct bookkeeping/transition effects.
Grouping by future outcome or execution without the appropriate conditional law
is not a justified marginalization.

A rejected or replaced input could be part of a *specified* sampled-command
environment, but silently dropping the rejection or substituting another choice
does not prove that model. Here those cases trigger failure rather than retry.
With missing acceptance evidence we cannot distinguish such kernels reliably;
neither terminal completion nor successful sampling alone fills that gap.

## Retained replay and discrepancy census

The completed machine-readable audit is under
[`runs/trajectory-contract-audit-20260910`](../runs/trajectory-contract-audit-20260910/).
`episodes.csv` covers every training learner episode; `excluded-decisions.csv`
preserves every decision of an excluded episode and its original label/reason.
`exclusion-groups.json` provides batch, opponent, ordered team/side, outcome and
length counts. `selection-description.json` separates public context and sampled
action exposure from causal claims. `examples.json` links exact decisions,
snapshots and same-ordinal engine entries; it never searches ahead.

All **188,563** learned-policy decisions reproduced exactly: 83,170 original and
105,393 actor-step, both players and all phases. Every vector, logit, value, chosen
ID and recorded draw matched the intended strict loader and seeded sampler.
There were **zero internal-CDF-boundary draws** in those records; boundary ownership
was tested explicitly using the repaired strict-right sampler. Twenty-five distinct
checkpoint contents were loaded through 208 retained cell copies. No stale rollout
checkpoint was found: learner copies agree with the frozen batch parent and stored
trajectory targets. Public prefixes, immutable snapshots, journal/merged-record
equality and original snapshot hashes all passed. This rules out substitution in
the retained evidence under the reviewed capture code; it is not an independent
reconstruction of the missing raw requests or cryptographic proof of live execution.

All **280,476** attempts, including fixed opponents, had one send-completion record,
unique increasing per-side request IDs, matching map/command/rqid, and equal per-side
attempt/engine sequence lengths. All 156 cells' original private label audits rebuilt
unchanged. Among learned decisions, 182,704 retain exact-verified labels and 5,859
retain unknown labels across all phases. The exclusion census below concerns only
training learner `a`, not archived-opponent or selection/final decisions.

| Training population | Episodes | Admitted | Unknown episode exclusions | Caps | First normalized ordinal: Wrap / Clamp / fight |
|---|---:|---:|---:|---:|---|
| Original | 864 | 793 | 70 | 1 | 35 / 12 / 23 |
| Actor control | 432 | 397 | 35 | 0 | 22 / 4 / 9 |
| Actor treatment | 432 | 393 | 39 | 0 | 20 / 8 / 11 |
| Total | 1,728 | 1,583 | 144 | 1 | 77 / 24 / 43 |

The 144 completed unknown episodes contain **5,672** decisions: **3,757 verified
prefix** records and **1,915 unknown** records. Those unknowns are 144 first
source-supported normalization candidates, 1,673 later same-ordinal literal matches,
and 98 later mismatches. **All later records remain unknown**, even literal matches.
No search-ahead alignment was performed. The cap separately contains 305 verified
decisions, making 5,977 decisions in all excluded episodes. Of the unknown records,
163 are forced replacements and 185 are engine actions: these inherit prior
uncertainty; they do not prove a defect in forced-action resolution.

All first mismatches have `maybe_locked=True`, a sampled ordinary move, and multiple
legal move alternatives. Active status is healthy in 128 cases and paralyzed in
16; none is frozen/asleep. This supports the trapping interpretation of `fight`,
without treating a hidden volatile as an observed policy feature. For example,
original `training/b1-vs-v5`, match 11, `m11:a:r55`, samples Blizzard from Cloyster's
four moves while the same-ordinal engine entry is Clamp. The three normalization
categories cover every first mismatch; none is an unexplained different move name.
They are **conditional normalization candidates**, not newly verified commitments
or 144 independently observed counterfactual equivalence classes.

Recorded rejected choices: **0**; missing end logs: **0**; missing ordinal entries:
**0**; sequence-length or request-order violations: **0**; duplicate submissions:
**0**. Replaced commands are not evidenced, and raw receipts are unavailable, so
absence of recorded rejection/replacement is not a new request-bound acceptance
certificate. One `ConnectionClosedOK` adapter event follows cleanup terminal events
in original `training/b7-vs-v2`, match 16. The runner preserves the earlier turn-cap
reason and null winner. This is not a new crash reward or a sampled-action failure.
The original wrapper-warning records remain hashed and unchanged.

Exclusions are structured. Unknown rates for V2 / V5 / archived opponents are
17/288, 17/288, 36/288 in the original; 8/144, 8/144, 19/144 in control; and
10/144, 7/144, 22/144 in treatment. Across both experiments each unordered team
pair has 288 scheduled episodes; unknown counts for 0–1, 0–2, 0–3, 1–2, 1–3, 2–3
are **0, 10, 36, 8, 40, 50**. This descriptive aggregate is not a pooled performance
comparison between differently trained policies.

There are 223 episodes containing any `maybe_locked` snapshot; 144 are unknown
exclusions. Among the other 1,505, the only exclusion is the cap. The filter can
also depend on the sampled action: choosing the lock's canonical move can match
literally while a different legal move under the same lock would not. First
mismatches include 39 sampled Blizzards, 28 Razor Leafs and 23 Sleep Powders; the
full action exposure table is retained without treating turns as independent trials.
Length does not explain exclusions alone: mean unknown/admitted lengths are
39.19/38.94 original, 40.77/38.86 control, and 38.51/39.19 treatment requests.
Excluded completed W/L/D are 31/38/1, 12/23/0 and 9/26/4 respectively. Their
differences from admitted outcome mixtures do not establish the direction of
gradient bias. Selection occurs through states/actions correlated with outcomes,
not a literal outcome test in the admission code.

## Verification and reproducibility

**11 exact-estimator/sampler tests passed**, plus **28 existing offline adapter,
label, immutable-observer and legal-action tests**. Total subprocess wall time for
these checks was **2.44 seconds**, within the 120-second synthetic ceiling. The
one-to-one and many-to-one gradients agree with independent finite differences;
canonical-representative misuse, missing evidence, action-dependent filtering and
prefix omission have explicit counterexamples. A two-action filtered example has
full gradient `[.75,-.75]`, filtered gradient `[1,-1]`, and conditional-return
gradient `[0,0]`. These are arithmetic tests, not Pokémon performance evidence.

The complete retained replay took **382.43 seconds**, **380.98 CPU seconds**, with
maximum observed RSS **544,563,200 bytes**. It is separate from synthetic test time
and produced no model updates. Two earlier diagnostic executions stopped on audit
helper issues: a reversed `resolve_action` argument order, then an overbroad
assertion that incorrectly rejected the known cap-cleanup event. Both consoles
remain preserved. The helper was corrected, not the inputs or production code;
the complete third execution is `replay-console-3.txt`.

Original manifest verification covered 7,713 REINFORCE entries and all 9,792 files
in the actor-step external closure manifest. Both frozen source trees are present
and match their freeze files. Current runner/adapter/labels/schema/training source
equals both historical contract implementations; the explicit validation-only
REINFORCE compatibility profile permits the original checkpoints, without bypassing
source checks. The existing 12-update reconstruction artifacts for each experiment
were retained, not recomputed by invoking an update routine here.

Required unchanged hashes:

| Input | SHA-256 |
|---|---|
| V4 predictor | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| V5 checkpoint | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |
| Original main manifest | `2e7895f52d03c375a6fc4ee9cf2a1ecd4e12e26da3fcee1c532f9ac144c17600` |
| Actor-step complete file manifest | `e9ca7a47577015d90b546e4591abfe7616db6f24aa7600425dd54773344f15d8` |

The before/after inventory covers **21,726** pre-existing files, including inspected
dependency source, historical runs/models, documents and unrelated uncommitted
work. `inputs-after.json` records their unchanged contents and only the new audit
files. `closure.json` hashes the final audit outputs and source. Generated artifacts
remain ignored; historical documents are linked, not edited.

Actual commands used from the project root (fresh audit output, no server):

```powershell
.\.venv\Scripts\python.exe -B diagnostics/trajectory_contract_integrity.py before
.\.venv\Scripts\python.exe -B diagnostics/trajectory_contract_audit.py
.\.venv\Scripts\python.exe -B diagnostics/trajectory_contract_describe.py
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_trajectory_contract_math.py --junitxml=runs/trajectory-contract-audit-20260910/synthetic-junit.xml
.\.venv\Scripts\python.exe -B diagnostics/trajectory_contract_math.py
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_adapter.py tests/test_labels.py tests/test_reinforce.py::test_observer_only_and_deep_freeze tests/test_reinforce.py::test_variable_action_sets_have_only_legal_support tests/test_reinforce.py::test_policy_randomness_reproducible_and_evaluation_immutable tests/test_reinforce.py::test_softmax_model_errors_never_fallback
.\.venv\Scripts\python.exe -B diagnostics/trajectory_contract_integrity.py after
git diff --check
```

The test commands were launched by timeout-bounded subprocess wrappers; logs and
their actual durations are retained. The replay command's two failed diagnostic
attempts and complete run used separate console files. No full integration suite,
battle server, policy training command or checkpoint save was invoked.

## Exclusion consequences and contract decision

Let `E` indicate admission. The filtered population update is proportional to
`E[E (R-b) Σ score] / P(E)`. It is generally neither the gradient of the unfiltered
win objective nor the gradient of conditional mean return. Even when `E` is a
fixed functional of the trajectory,
`∇ E[R|E=1] = E[E (R-J_conditional) Σ score] / P(E)` under regularity assumptions.
An ordinary pre-action baseline cancels in the unfiltered estimator; conditioning
on later action-dependent admission can prevent cancellation. Finite accepted
batches introduce a random denominator as well. The audit does not estimate a
causal bias magnitude or direction from these observational exclusion counts.

Before a first mismatch, the original exact prefix remains verifiable and frozen
sampling can still reproduce throughout the unknown suffix. The completed terminal
outcome can be genuine even though its choice correspondence is unresolved.
Those facts do not make a prefix-only update unbiased: omitting later score terms
generally loses their contribution to the same final reward. Exceptions require
proof, such as omitted singleton decisions with identically zero score, zero
expected omitted terms, or a separately defined policy with frozen continuation.
None is established for these mixed-choice suffixes. The one capped episode has
no terminal target regardless of its verified prefix or forced tail.

**Recommendation A: preserve the current exclusion rule for these records.**
No confirmed sampled-probability/command recording corruption was established.
The exclusion of *all* normalized commands is mathematically broader than needed
for a proven sampled-command contract, but plausible normalization is not enough
to newly certify these unknown suffixes. Original labels and trained counts stay
unchanged. This is not a recommendation to equate intended and executed moves.

The single next action is a **separately scoped request-bound acceptance recording
design and its offline fixtures**, before proposing an eligibility change. It would
need an observer-request digest/menu, sampled ID/map/draw, unique attempt ID and
exact submitted bytes, plus a separate post-match engine acceptance record linking
that attempt/request to the accepted action and normalization branch. Preserve
ordering, rejection/replacement/cancellation records, source versions, and terminal
provenance. Such privileged evidence must never reach policies or an observer-only
critic. A new trajectory-evidence schema and eligibility version would be required;
the opponent-label schema and its unknown suffixes would remain intact.

Acceptance conditions for any later proposal: one unambiguous accepted submission
per recorded decision, exact request/attempt correspondence, source-reviewed
normalization preserving the sampled-command environment, reproducible probabilities,
and a genuine completed outcome. Missing/duplicate acknowledgments, stale menus,
rejections, replacement/undo/default commands, unexplained reorderings, nonfinite
probabilities, caps and cleanup failures must remain ineligible. Regression fixtures
must cover each, many-to-one locked/fight cases, legal switches during trapping,
forced replacements, strict CDF boundaries, unknown suffix preservation and
privileged-data isolation. These conditions were **not implemented** or retroactively
applied; no follow-up experiment is authorized by this audit.
