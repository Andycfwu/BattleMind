# Acceptance live verification — stopped before collection

2026-09-10. The single authorized attempt **did not reach live verification**.
Runtime, engine-build and four-team diagnostic checks passed, but historical-input
hash verification exhausted the 180-second overhead allocation before the source
freeze manifest was complete. **Zero games were requested; no server launched.**
No retry, budget increase, training, policy change or eligibility change occurred.

The [proposal](ACCEPTANCE-LIVE-VERIFICATION.md),
[configuration](../configs/acceptance-live-verification.json) and earlier
[recording results](ACCEPTANCE-RECORDING.md) remain unchanged. Their existing
offline results are not substitutes for new live evidence. All historical
exclusions, including the 144 uncertain completed learner episodes, remain intact.

## Harness and failure

There was no live collector/ledger in the earlier deliverable. This request added
the narrow harness described in [ACCEPTANCE-LIVE-HARNESS.md](ACCEPTANCE-LIVE-HARNESS.md),
plus nine offline ledger/factory-scope tests. It reuses the unchanged existing
match and server lifecycle code. Both 24-game allocations were reserved before
preflight, and the original configuration and checkpoint were copied into fresh
outputs. The intended source snapshot was copied; **`freeze.json` was never
written**, because the subsequent historical-input hash scan did not finish.
The harness correctly did not start a phase before that freeze.

I introduced a preflight enforcement gap in this harness: the overhead deadline
was checked when entering a phase, **after** the synchronous historical hash loop,
but not during that loop. Offline tests covered phase/game reservation and
idempotent closing, but did not cover an overlong preflight scan. This is a harness
defect, not evidence of a simulator or acceptance-recording defect. No per-file
timing/progress was recorded, so the slow scan cannot be attributed more precisely.

The process tree was externally terminated when the overrun was detected at
**205.354985 charged seconds**. The stopped ledger was finalized at
**272.986537 seconds**, including post-stop bookkeeping and the **15.607276-second**
offline-test debit. That finalization interval was not additional collection.
The 180-second overhead allocation was exceeded; this attempt does **not** pass
its budget/acceptance requirements. No time was transferred to or from a battle
phase. `external-stop.json`, `ledger.json` and `report.json` preserve the actual
timing distinction. Later postmortem/reporting time is recorded separately in
`closure.json`, rather than continuously charging the sealed ledger.

## Actual counts and limits

| Phase | Planned / reserved | Requested | Completed | W / L / D | Caps / timeouts / battle crashes | Never requested |
|---|---:|---:|---:|---:|---:|---:|
| Original engine | 24 / 24 | 0 | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 24 |
| Instrumented engine | 24 / 24 | 0 | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 24 |

There is one experiment-level preflight budget failure and no battle-level failure
records. Untouched slots are not missing requested battles, losses or wins.
Both phases have zero collection time and no performance denominator.

No live request/attempt/acceptance/commitment chain was recorded. Ordinary moves,
switches, forced replacements, Wrap, Clamp, fight, Recharge and Struggle all remain
**unverified live**. Live policy isolation, full recording completeness, cancellation
timing and instrumentation overhead are also unavailable. Phase CPU/RSS samplers
never started; no CPU/RSS values are fabricated for the interrupted preflight.
There are no matched or unmatched battle outcomes to compare.

## Checks, commands and artifacts

Before the attempt, **335 offline tests passed**, with **14 integration tests
deselected**, in 11.25s. The **12 original/derived method comparisons**, plus disabled
and failed recording, passed again with zero games. The earlier nine harness tests
passed in 0.22s. Process wall time for the final offline suite/method check was
13.607276s; a conservative 2s allowance covered the earlier harness command.
This full 15.607276s was charged to the overhead/aggregate budget.

Actual collection invocation (no second invocation):

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B diagnostics/acceptance_live_verify.py --output runs/acceptance-live-verification-20260910 --preflight-seconds 15.6072756
```

Preflight used `python -B -m pytest -q -m 'not integration'` and the existing
`tests/acceptance_engine.cjs` method harness. No historical training integration
suite was run. `git diff --check` passed. The new files are the isolated live
harness, tests, harness review and this results note; earlier production and
recording modules were not edited.

Fresh retained paths:

- [`runs/acceptance-live-preflight-20260910/`](../runs/acceptance-live-preflight-20260910/):
  test outputs, zero-game method traces, measured check debit and parent console.
- [`runs/acceptance-live-verification-20260910/report.json`](../runs/acceptance-live-verification-20260910/report.json):
  zero-request counts, failed freeze, limitations and targeted preservation checks.
- `ledger.json`: single-use stopped allocation; neither reserved phase was consumed
  as requested games, and neither may be resumed under this authorization.
- `external-stop.json`: actual termination reason, PID and charged detection time.
- `specification.json`, `preflight.json`, `inputs/`, `source-snapshot/`: preserved
  preparation evidence. The specification SHA-256 is
  `1f16bbbbcb9adc9aae6eedb8a0a8ae9c0c8c8b080dcff1de57d066ca1bec84de`.
- `closure.json`: output/source hashes, cleanup and separate postmortem timing.

Cleanup confirmed both owned Python processes were gone and no listener remained
on port 8000. No server process or spectator service was started. A targeted
postmortem check verified original production sources, required retained models,
reviewed configuration, instructions and earlier uncommitted recording files
against the prior inventory. The full historical scan was interrupted and is
**not claimed complete**. No historical run/checkpoint/label files were written.

## Decision

**There is no new live evidence supporting an eligibility change.** The prior
offline contract remains useful, but cannot certify live normalization or recover
historical unknown suffixes. Preserve the exclusion rule.

The next necessary action is an offline repair/review of deadline enforcement
during preflight hashing and its reporting, including a slow-scan regression and
a realistic bounded preservation plan. A subsequent live attempt needs a separate
authorization. Neither that repair nor another collection is executed here.
