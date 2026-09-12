# Instrumented-only acceptance verification — frozen specification

2026-09-11. The user authorizes **one run, at most 24 new instrumented-engine
games and 420 seconds**, concurrency one, on `127.0.0.1`. This implements the
proposal in [ACCEPTANCE-PACKAGING-REPAIR.md](ACCEPTANCE-PACKAGING-REPAIR.md), after
the [successful zero-battle readiness check](ACCEPTANCE-READINESS-RESULTS.md).
This file and the machine specification are frozen before collection; actual
results go in a separate document and fresh run directory.

The consumed first attempt and replacement remain unchanged. The latter completed
24 original-engine games and requested zero instrumented games. Those 24 games
are retained reference evidence; **none are rerun**. Their unmatched outcomes do
not certify equivalence, instrumentation overhead or competitive strength. V6
acceptance and historical training exclusions remain as previously reported.

## Fixed schedule and accounting

| Phase | New games | Maximum seconds |
|---|---:|---:|
| Runtime/model/input checks, reference audit, source freeze, zero-battle readiness | 0 | 100 |
| Instrumented collection, startup/shutdown, per-match commitment/replay audit | 24 | 240 |
| Post-run isolation, labels, coverage, preservation, hashing and mandatory reports | 0 | 60 |
| Cleanup and constant-size final accounting reserve | 0 | 20 |
| Total | **24** | **420** |

All capacity is persistently reserved before preflight. Only dispatch increments
requested games; never-started slots stay distinct from missing requested records.
Fresh exclusive directory: `runs/acceptance-instrumented-only-1`. Single-use ledger
schema: `bm-acceptance-instrumented-ledger-1`. No resume, retry, borrowing, additional
games, optional archive scan or after-run experiment is permitted. A new game
requires its whole 60-second timeout plus six cleanup seconds before the collection
deadline. Import time after entering the harness is included in its aggregate
clock; an outer invocation watchdog also measures the full process.

Use original frozen REINFORCE c0 versus RandomLegalAgent, seed **260911**, the
existing four teams, Gen 1 OU, 300-turn cap, 60-second game timeout and concurrency
one. `scheduled_match(0..23,4)` gives six unordered team pairs, four games each
balancing team assignments and challenger sides. The simulator seed is not set;
policy seeds do not match engine trajectories. All policies, sampling, hooks,
warning handling, public observations and private label/eligibility rules stay fixed.

An ordinary cap remains a cap, not a reward or win; retain evidence and continue
only an independent scheduled game after the unchanged cleanup/audit checks pass.
Unexpected protocol warnings/errors, invalid actions, numerical corruption,
missing/unsealed/corrupted recording, uncertain commitment in a completed game,
policy isolation failure, failed cleanup or exhausted allocation stop collection.
No failed game is retried. Terminal battle accounting is separate from functional
acceptance: a correctly completed battle can still have a recording failure.

## Inputs and compatibility

Machine configuration:
[`configs/acceptance-instrumented-only.json`](../configs/acceptance-instrumented-only.json).
Explicit critical input manifest:
[`configs/acceptance-instrumented-only-inputs.json`](../configs/acceptance-instrumented-only-inputs.json),
SHA-256 `9740fb6c49a15c4d8337e8ab80ab1d130b0bdcd3f4e1b5a603f6965df53acee0`.
It contains 83 named current source/config/test/design files and 17 pinned artifact
identities, including the 4,049-file original-engine/poke-env inventory and selected
historical ledgers/documents. This is not a full historical archive scan.

The required original checkpoints must exist and pass their unchanged loaders:

| Artifact | SHA-256 |
|---|---|
| `runs/reinforce-main/checkpoints/c0.json` | `f7734489bce5d74ce2dedffd8ab274a8483810a03e09b48a26ea0ebf28d44287` |
| `models/v4-supervised.json` | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| `runs/v5-acceptance/selected.json` | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |
| New r5 build manifest | `41ec777dc02811d55c8b8c3762d24e6e5ee41c488bc3077ad3d2b1fc69d1a813` |

Derived engine: `.local/pokemon-showdown-acceptance-v2-r5`, build ID
`b2b0a1b1bdc30749a38e3c6ae3beea27ea03387d75dda0afe4e7ba7051d1b19a`.
Upstream commit: `2f5b273925862ac242b419086c1e7a8868b51da1`.
Patch SHA-256: `84c4c66dfdf4a165b8e17f54c5b32a455a5715a8b7daaae02bb7a3d1c40214d3`.
Runtime remains Python 3.14.3, poke-env 0.16.1, Node 24.19.0 and the existing
pnpm 11.19.0 installation. Do not rebuild, download, upgrade or replace inputs.

Preflight freshly verifies source/compiled/dependency files and pnpm link layout,
reviewed config, runtime pins, official team legality and wrapper rule parity.
Derived rule diagnostics must equal the original engine's. Required modules must
resolve from the actual entry/cwd, and a supervised zero-battle handshake/shutdown
must succeed before any game phase begins. Recording paths must be fresh/private
under this run; an occupied port is never taken over.

Reference compatibility checks inspect the original run configuration and exact
policy/team/source identities, replay all its frozen decisions and audit its
unchanged legacy labels. Only packaging-helper differences are permitted among
original package source files; policy/adapter/scientific hashes must match. The
full **one original 24-game directory**, not the archive, is hashed before collection
and rechecked afterward. Source/model/config/build and reference identities are
copied or hashed into the new freeze. Checks do not turn old unknown labels into
verified ones. The original 180s phase and new 240s phase differ in wall allocation;
resource comparisons are descriptive and unpaired.

## Harness review before freeze

`diagnostics/acceptance_instrumented_only.py` supplies only the new schedule,
ledger, reference preflight and reports. Its instrumented worker reuses the
unchanged `collect_phase` body from `acceptance_live_verify.py`, setting only the
worker process's budget class and derived-build path. Policy/player interfaces and
the match-level opt-in recorder/cleanup remain unchanged. No live object or new
private metadata enters a policy.

Review found one previously unexercised audit-path defect: `inspect_match` called
`read_chain` without importing it. An offline test reproduced `NameError` on
sealed own-client journals. The only change to that existing harness is importing
the already implemented strict reader. Its function body and validation rules do
not change. The original 24-game phase did not enter this instrumented-only branch.
The installed poke-env `send_message` source was reread; no dependency or hook is
modified. The regression and new ledger/report tests run offline before collection;
no test-suite game is authorized or collected.

## Predeclared acceptance and coverage

**Functional recording success for this run** requires 24 genuine completed games,
all scheduled assignments/sides, exact frozen-policy probability/draw/action/command
replay, one recorded own attempt per decision, sealed separate client/room/simulator
chains and request→attempt→parse→acceptance→commitment linkage for every completed
decision. The commit must match the exact index/text in its hashed official end
log. No searching ahead, silent retry or inferred commitment is allowed. Preserve
the original sampled semantic ID/probability and the engine's normalized choice
separately. Accepted/committed does not mean executed, successful or damaging.

The existing independent validator checks raw request hashes/rqid, client attempt
and connection counters, original own slots/current positions, legal menu order,
CDF sampling, room/engine dispatch epochs, parse status, branch-supported accepted
actions and current choice object commitment. Any invalid/incomplete trace blocks.
On caps, uncertainty remains explicit and never creates a reward.

**Coverage is a separate result.** Count only validated committed attempts:

- Ordinary move: a sampled `move:` ID without a normalization branch.
- Voluntary switch versus forced replacement: validated switch with the original
  snapshot's ordinary versus forced request kind (and engine switch/instaswitch).
- Wrap/Clamp continuation: emitted `locked_move` branch and accepted `move wrap`
  or `move clamp`, with a complete commitment chain.
- Gen 1 fight: emitted `gen1_fight` branch and committed `move fight`.
- Recharge/Struggle: record their supported locked/no-enabled-moves branches if
  encountered. Direct engine-menu actions without those branches are reported
  separately; they do not invent normalization coverage.

Report branch counts, original sampled IDs, accepted choices, command-change
counts and private example references. The target coverage is the original six
categories; Recharge and Struggle are additional descriptive categories. Missing
categories remain **unverified**, even if functional recording succeeds. No extra
game is permitted to fill coverage. Rejection, undo, duplicate, reconnect and other
rare branches retain their offline-only status unless actually encountered.

The existing isolation audit mutates **disposable copies** from the first completed
valid new trace: private acceptance/end data must invalidate private validation
while leaving frozen policy replay, predictor probabilities, permitted public
memory and spectator projection unchanged. It never modifies collected evidence,
updates learning, or launches a viewer. Legacy label audits preserve unknown suffixes.
Keep request-bound recording and historical training eligibility separate.

## Timed reporting and stop behavior

Every worker has an absolute monotonic deadline and process-tree watchdog. The
collection deadline reserves reporting/cleanup capacity. After either success or
failure, reporting gets 60s: at most 50s for existing replay/isolation/label audits,
input preservation and output hashing, then ten seconds for mandatory JSON/Markdown.
Blocking OS work is bounded by the parent watchdog; on timeout the owned worker
tree is terminated/reaped. The final 20s reserve covers cleanup and constant-size
ledger closure. Closed phase times are idempotent; read-only report commands cannot
mutate or extend them. No post-close supplemental scan or unbudgeted investigation
is part of the acceptance command. If detailed reporting fails, outcomes are
explicitly unavailable rather than invented.

Report planned/reserved/requested/recorded/completed/never-started counts; W/L/D
with completed denominator; caps, timeouts, crashes, cancellations, invalid actions;
experiment/audit failures separately; known/unexpected warnings; exact linkage and
coverage; resources, file sizes, observed validation time, phase/aggregate time;
source/artifact hashes and cleanup. Outcomes are restricted-pool accounting only.
Different trajectories/outcomes cannot establish engine equivalence or causal
overhead. Ordinary battle outcomes and acceptance evidence do not relax any
historical exclusion or authorize a later eligibility change.

Feasibility uses retained evidence only: the repaired zero-battle diagnostic took
13.69s in its ledger, the original 24-game phase took 11.28s, and a separate broad
targeted integrity check took 53.88s. The unchanged 100/240/60/20 allocations leave
room for added recording and reference work but provide no runtime guarantee.
If the reservation guard/deadline stops the run, preserve the partial result and
stop; no timing rehearsal battles or second attempt are permitted.

Execute once, after offline checks and source review:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B diagnostics/acceptance_instrumented_only.py --output runs/acceptance-instrumented-only-1
```

Read-only later report (no finalization or new audit):

```powershell
.\.venv\Scripts\python.exe -B diagnostics/acceptance_instrumented_only.py --output runs/acceptance-instrumented-only-1 --report
```

Do not commit, push, deploy, train, change policies/eligibility or automatically
execute a follow-up. All retained failed attempts and unknowns remain historical.
