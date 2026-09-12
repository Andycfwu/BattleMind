# Proposed replacement acceptance verification — not executed

This proposal follows the [preflight repair](ACCEPTANCE-PREFLIGHT-REPAIR.md).
It requires **separate authorization**. The consumed
`runs/acceptance-live-verification-20260910` remains failed: zero requested games,
no server startup, and an overhead overrun during historical hashing. It is never
resumed, rewritten, or relabeled.

The new configuration is
[`configs/acceptance-live-replacement.json`](../configs/acceptance-live-replacement.json).
It preserves every scientific field of the
[original specification](ACCEPTANCE-LIVE-VERIFICATION.md); the harness checks that
equality. Only the preflight scope, overhead suballocations and output identity
change. No policy, sampling, engine patch, outcome, warning, acceptance or training
eligibility rule changes.

| Allocation | Maximum games | Maximum seconds |
|---|---:|---:|
| Critical preflight, source freeze and preparation | 0 | 100 |
| Original engine | 24 | 180 |
| Instrumented engine | 24 | 240 |
| Post-run replay/isolation, input preservation and reporting | 0 | 60 |
| Worker termination and mandatory final accounting reserve | 0 | 20 |
| Total | 48 | 600 |

Both 24-game allocations and the 80-second reporting/cleanup reserve exist before
preflight. A new game still needs its full 60-second timeout plus six seconds of
client cleanup. The collection deadline also protects the reserved 80 seconds.
Phase time includes child startup, server lifecycle, per-match audits and cleanup.
There is no borrowing, retry, resume, second attempt or spending leftover time on
extra games. A late worker is stopped even if it eventually produces a success file.

Use `127.0.0.1`, concurrency 1, Gen 1 OU, the same four teams, frozen original
REINFORCE c0 versus random, seed 260911, and unchanged 300-turn/60-second game
limits. Each phase uses `scheduled_match(0..23,4)`: all six unordered pairs with
both assignments and player sides. Engine randomness is unmatched.

## Exact required inputs

[`configs/acceptance-required-inputs.json`](../configs/acceptance-required-inputs.json)
is the explicit input manifest. Its named files, not an archive-directory glob,
define preflight. The replacement configuration pins its SHA-256 to
`554d93e9fc67d4c7d1a42e70236c260efc5a6f8d03606b209f55cf873f60ad4f`:

- 74 project files: the small Python package, opt-in harness, relevant diagnostic
  script, instructions/specification of the recording contract, actual four team
  fixtures, schema/scoring/loaders, runtime config/locks, and verification tests.
  The package is conservatively included because policy factories, compatibility
  checks, public-memory replay and spectator projection import these modules.
- [`configs/acceptance-runtime-inputs.json`](../configs/acceptance-runtime-inputs.json):
  4,049 explicit original-engine and installed poke-env files, with retained
  expected SHA-256 values. This includes tracked upstream source, full compiled
  output and Node dependencies, reviewed config/lock, and wrapper source/data.
  Compiled/dependency/wrapper tree membership is also checked; Python bytecode
  caches remain excluded as in the original inventory.
- The exact derived `acceptance-build.json` digest. Its **full** verifier still
  checks the upstream Git identity/clean source, exact patch/helper, all 2,142
  listed build files, 1,832 dependency files, complete inventory membership,
  config/lock and runtime versions. No prior success verdict is cached.
- All three retained artifacts required by play **and** the later isolation audit:

| Artifact | SHA-256 |
|---|---|
| `runs/reinforce-main/checkpoints/c0.json` | `f7734489bce5d74ce2dedffd8ab274a8483810a03e09b48a26ea0ebf28d44287` |
| `models/v4-supervised.json` | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| `runs/v5-acceptance/selected.json` | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |
| Derived build manifest | `8f89958982d74b4a36b106d745a2fd63deeac0f56c27739625f81ff7cca06547` |
| Original/wrapper runtime inventory | `72fcc6a11d1e8997d484e0e93f52b98c3c20a5ad2d0dde5cd5b93ea5994a3c27` |

The intended strict c0/V4/V5 loaders run before collection. The original doctor
still verifies runtime pins, loopback config, official team legality and wrapper
Gen 1 rule parity. Derived official diagnostic results must equal the original's.
`recording_environment` performs one full derived validation during preflight;
the previous additional immediately redundant validation is removed. Full derived
checks before its collection phase and after collection remain.

Every named runtime input is read and hashed, never accepted from modification
times. Required inputs are rechecked after collection. Preflight freezes the new
specification, project source copies, model, input digests and build manifest.
`preflight-io.jsonl` and `reporting-io.jsonl` list actual completed/partial reads,
byte counts, digests and elapsed time. Derived checks are included in those logs.
No claim is made that unrelated historical runs were reverified.

## Feasibility and limits

Existing evidence supports a bounded attempt, not a completion guarantee. The
old preservation report hashed 37,270 files in **15.200648s** on one warm run;
the later attempt exceeded its 180s overhead allocation while scanning history.
This variability makes a warm-cache runtime estimate unsafe. Neither record gives
a separate reliable cold preflight duration. The retained derived build contains
**208,538,938 bytes**. The replacement removes the archive-wide scans entirely,
limits required bytes to the actual engine/wrapper/model dependencies, and stops
preflight at 100s instead of waiting indefinitely. It does not assume a disk cache.

For collection context only, original REINFORCE final collection took
264.024682s for 576 games, including its run orchestration: about 11s per 24-game
cell on average. That is a different schedule and lacks the new instrumentation;
it is **not** a measured live-recording cost. Keeping 180/240s phases leaves large
headroom relative to that evidence, while the 100/60/20 overhead split protects
hashing, full final audits and cleanup. Full critical preflight and instrumented
throughput were not benchmarked in this offline repair. Completion within 600s
therefore remains unverified. If actual critical validation cannot fit, stop with
zero requests; do not remove checks or increase the budget.

## Execution after authorization only

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B diagnostics/acceptance_live_verify.py --output runs/acceptance-live-verification-replacement-1
```

The exact output must be absent. The new `bm-acceptance-live-ledger-2` is
exclusive-create and single-use. No replacement output directory or ledger was
created by this repair. Offline repair tests are separate zero-game engineering
checks, not a debit carried from the consumed attempt. Future setup, validation,
collection, reporting and shutdown belong to this fresh 600s allocation.

Read saved accounting without starting work or changing clocks:

```powershell
.\.venv\Scripts\python.exe -B diagnostics/acceptance_live_verify.py --report --output runs/acceptance-live-verification-replacement-1
```

All original failure/coverage rules remain. Missing ordinary move, voluntary
switch, forced replacement, Wrap, Clamp or fight evidence means partial live
verification; unencountered cases cannot pass. Unexpected warnings, recording
integrity failures, leaks, numerical errors or failed cleanup block further games.
Caps retain null outcomes and continue independent work only after existing checks.
Only post-match audits combine private streams. Historical unknown suffixes and
episode exclusions remain unchanged. Even full live success permits only a future
eligibility proposal, never its automatic implementation.
