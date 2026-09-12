# Acceptance preflight repair — offline only

This repairs the harness failure recorded in
[ACCEPTANCE-LIVE-RESULTS.md](ACCEPTANCE-LIVE-RESULTS.md), without changing that
historical report or the consumed ledger. The original attempt requested **zero
games**, exhausted its 180s overhead allowance and did not launch a server.
Its stopped ledger SHA-256 remains
`7dd4607e11c0928c6cd9ecf915c4271d742f88e1364acb0b40a8ccc787210571`.

## Defect and repair

The historical-input loop called whole-file `sha256` across the entire archive;
it checked the deadline only later, when entering a collection phase. The same
problem affected source copying, later preservation and output hashing. Upstream
Git/version calls in build validation had no timeout. Original doctor commands
already had 30-second timeouts individually, but lacked a shared deadline around
their sequence. Parsing, file enumeration and strict loaders could also block.

`diagnostics/acceptance_preflight.py` supplies task-specific bounded I/O: check
before opening, between files, before/after each 1 MiB read, after writes and before
accepting a digest. Subprocess waits use the lesser of remaining allocation and
their command limit. A separate parent watchdog bounds the entire preflight and
reporting worker, including existing doctor/loader calls and OS operations that
cannot be interrupted from inside Python. Timeout/cancellation terminates and
reaps the owned process tree; it never releases a game reservation or starts the
next phase. Partial hash progress remains evidence, never a successful validation.

The opt-in build verifier accepts this I/O implementation while preserving every
content, inventory, patch, provenance, runtime and loopback check. Its default
Git/version waits are now bounded too. No dependency source, patch, policy,
probability, legal mapping, sampling, reward, warning or eligibility code changed.

The repaired harness reserves 60s for full post-collection auditing/reporting and
20s for forced termination/final accounting before any game. It stops preflight
separately, requires successful preflight before any server phase, and rejects
re-entry after cancellation or closure. Stopped preflight/phase/report durations
remain immutable. The explicit read-only report command does not write files or
advance a clock. Planned/reserved slots remain distinct from actual requests and
missing requested records. A zero-request phase has a zero outcome denominator.

Durations use monotonic clocks and retain actual overruns rather than clipping
them to budgets. The ledger distinguishes preflight, collection stop, per-phase
time, reporting, post-collection time, final accounting and total time. This is
cooperative checking plus process supervision, not a real-time OS guarantee:
scheduling, process termination or an uninterruptible filesystem call can overrun
a deadline. Mandatory small closure writes may also take time; overruns remain
failures. No subsequent collection is permitted after them.

## Required work and optional history scanning

The [replacement specification](ACCEPTANCE-LIVE-REPLACEMENT.md) and its two input
manifests name the exact dependencies. Source/schema, engine identity/patch/full
compiled and dependency bytes, retained models, installed wrapper data, actual
team fixtures and strict loaders remain mandatory. A full historical-run scan is
not needed to operate these 48 verification games. Inputs are read afresh; the
retained inventories supply expected digests, not cached validation results.

Full archive preservation is an optional, separately budgeted offline operation:

```powershell
# Optional; NOT run by this repair or by live preflight.
.\.venv\Scripts\python.exe -B -m diagnostics.acceptance_preflight --inventory runs/acceptance-recording-offline-20260910/inputs-before.json --output runs/FRESH-OPTIONAL-ARCHIVE-SCAN --seconds 300
```

This uses a separate single-use ledger with 290s scanning and 10s cleanup/accounting,
zero games, a watchdog and per-file progress. It may stop without covering the full
archive. Mismatches remain mismatches, including legitimate later changes; it never
repairs expected hashes. It is not implicitly added to a live allocation.

## Verification and retained evidence

Artifacts are in `runs/acceptance-preflight-repair-20260910/`. `before/` preserves
the exact files edited here and targeted historical documents/closure inputs;
`before-hashes.json` records their digests. No archive-wide scan was run.

- `regressions-before.txt`: **3 failed, 9 passed**, reproducing expired-preflight
  startup, stopped-ledger startup, and advancing closed-ledger duration reads.
- `hash-loop-reproduction.json`: the exact retained loop performed three synthetic
  hashes past a one-second injected limit; the repaired loop stopped before file
  two. Actual diagnostic wall time was **0.041137s**, not a real slow archive scan.
- Focused fixtures exercise expiration before reads, interruption of a 4 MiB
  stream, between-file deadlines, subprocess timeout and termination, cancellation,
  zero/partial request accounting, reserved reporting/cleanup, idempotent stopping,
  strict tamper rejection, successful small preflight and optional scan behavior.
- `retained-input-checks.json`: original c0, V4 and selected V5 pass their intended
  strict loaders; exact model/build-manifest/inventory hashes and a **targeted**
  preservation check pass. This is not a new verification of every engine/archive
  file. The complete runtime inventories will be read by the future preflight.
- `runtime-membership.json`: bounded directory enumeration found exactly 1,088
  original compiled files, 1,832 Node dependency files and 78 wrapper files, with
  no missing/additional members. This checked membership, not content, in 0.159s.
- `validation-equivalence.json`: default/bounded patch generation returns identical
  text on the four actual pinned source files and helper. The existing factory,
  policy replay, match-validation and isolation-audit functions are AST-identical.

The offline suite passed **362 tests**, with **14 integrations deselected**, in
11.16s. After adding a final closure-failure visibility regression, the focused
suite passed **45 tests** in 1.14s. These overlapping counts are not added together.
Results, command output, final hashes and whitespace checks are in `verification.json`
and the test transcripts in that directory. Commands use the offline suite only:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_acceptance_live.py tests/test_acceptance_preflight.py tests/test_acceptance_build.py
.\.venv\Scripts\python.exe -B -m pytest -q -m 'not integration'
git diff --check
```

Changed files are the isolated live harness, new deadline/input-scope helper,
optional bounded I/O arguments in `acceptance_build.py`, focused tests, three new
configuration/manifests and these two new documents. The original instructions,
recording specification, live specification/results/harness history and failed
attempt's artifacts remain untouched. No model update, server, battle, training
integration, archive-wide scan, commit or push occurred.

Preflight is deadline-guarded and its dependency scope covers the verification
and later isolation audit. Actual full preflight duration, live acceptance linkage,
coverage, instrumented overhead and live cleanup remain unverified. The separately
specified 48-game/600s replacement has **not** been executed or authorized here.
