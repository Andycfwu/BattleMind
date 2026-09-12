# Replacement acceptance verification — incomplete

The single authorized replacement ran once on 2026-09-10 under
[ACCEPTANCE-LIVE-REPLACEMENT.md](ACCEPTANCE-LIVE-REPLACEMENT.md).
**24 original-engine games completed; the instrumented server failed before
requesting any games.** Its remaining 24 slots were never requested. No retry,
repair, dependency installation, training, policy/eligibility change or additional
collection followed. The failed first attempt remains unchanged.

| Phase | Planned/reserved | Requested | Completed | c0 wins / losses / draws | Never requested |
|---|---:|---:|---:|---:|---:|
| Original | 24 | 24 | 24 | 24 / 0 / 0 | 0 |
| Instrumented | 24 | 0 | 0 | 0 / 0 / 0 | 24 |

No battle caps, timeouts, crashes, cancellations or invalid actions occurred.
There was one **server-startup failure**, distinct from a battle outcome.
The original phase has a 24-game outcome denominator; the instrumented phase has
none. These restricted-pool outcomes do not establish strength or engine equivalence.

## Failure and integrity scope

The instrumented `server.log` reports `MODULE_NOT_FOUND: faye-websocket`, required
by `sockjs/lib/trans-websocket.js`. The original `node_modules/sockjs` is a Windows
junction into `.pnpm/sockjs@0.3.24/node_modules/sockjs`; the derived copy is an
ordinary directory. This changes Node's module-resolution ancestry. File-byte
validation passed but did not establish that the copied runtime dependency layout
was operational. No dependency or build was changed during or after this run.

Preflight completed its declared input hashing, source freeze, original runtime/
format/team checks, strict c0/V4/V5 loaders, derived build validation and equality
of official rule diagnostics. It took **11.302944s**, below 100s. This verifies the
bounded preflight path on this run, but exposes a readiness gap for copied package
layouts. The startup error correctly blocked further games.

All **1,641** original decisions passed frozen-policy probability/draw/action/command
replay and the legacy audit. Existing labels retain **1,637 verified intended
choices and four unknown choices** with `engine_choice_or_sequence_mismatch`.
No labels or exclusions were rewritten. Two recognized Wrap trailing-annotation
warnings were retained; there were zero unexpected warnings.

There are **zero new request-bound attempts or acceptance chains**. Ordinary
move/switch/replacement linkage, Wrap, Clamp, fight, Recharge and Struggle
normalization all remain unverified live. The original public Wrap announcements
are not proof of normalized-command acceptance. The instrumented isolation test,
full post-run runtime preservation pass and automated reporting worker did not run.
There is no live evidence supporting an eligibility change.

## Time, resources and cleanup

The ledger records **31.792949s** total: 11.302944s preflight, 11.282825s original
phase, 9.200914s instrumented phase preparation/failed startup, and small accounting
costs. Defined overhead was **11.309210s**; final accounting was **0.005232s**.
The external invocation measured **32.395492s**. No phase stopped for its budget.
The unused reporting allocation was not resumed. Supplemental read-only inspection
and report preparation are timed separately in the companion result/closure files;
the sealed ledger is not extended or rewritten. This is not a claim that all
acceptance checks completed, or that supplemental authoring fit the 60s allocation.

Original-phase Python CPU was 4.375s; sampled Python RSS peaked at 103,821,312 bytes.
Sampled server RSS peaked at 455,254,016 bytes, with 3.828125s server CPU at its last
sample. Sampling can miss brief peaks. The instrumented server failed before its
phase sampler acquired a running server PID: its zero server samples are missing
resource coverage, not evidence of zero resource use. Instrumentation overhead
cannot be estimated from unmatched completed games versus a failed startup.

Owned worker/server PIDs were gone and no listener remained on port 8000 at the
independent cleanup check. Recorded source/configuration and the selected first
attempt artifacts matched their pre-execution hashes. No historical archive scan
was performed; no full post-run engine-tree preservation claim is made.

## Commands and artifacts

The following collection command was invoked exactly once, in an outer
600-second watchdog that captured its output:

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -B diagnostics/acceptance_live_verify.py --output runs/acceptance-live-verification-replacement-1
```

- `runs/acceptance-live-verification-replacement-1/`: consumed stopped ledger,
  freeze, preflight I/O hashes, original matches/audits, instrumented startup log,
  resources, worker cleanup records and the harness closure report.
- `runs/acceptance-live-replacement-execution-20260910/`: before-execution hash
  review, exact invocation/PIDs, external timing, read-only inspection,
  `result.json` with selected artifact hashes, and supplemental closure.
- Prior proof: 362 offline tests and 45 final focused repair tests. Their recorded
  source hashes matched before this execution. No test-suite games were collected.

The exact blocker is the derived runtime's dependency-resolution failure. This
attempt remains consumed and incomplete. No fix, eligibility change or new run is
implemented or authorized by these results.
