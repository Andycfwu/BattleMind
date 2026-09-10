# REINFORCE loader and comparison-report repairs — 2026-09-09

This narrow repair follows [REINFORCE-AUDIT.md](REINFORCE-AUDIT.md). The audit,
historical results, checkpoints and experiment artifacts remain unchanged. No
battles, new training, hyperparameter changes or actor-step experiment were run.

## The two fixes

**Checkpoint numeric types.** The old loader accepted JSON coefficients such as
`"0.1"`: NumPy converted them to floats for validation, but the stored immutable
tuple retained the string. Subsequent matrix multiplication raised
`UFuncTypeError`. The loader now requires numeric JSON arrays containing actual
integers/floats before constructing `Parameters`. Strings, booleans, nulls and
other nonnumeric values are rejected; existing shape, finite-value and norm checks
remain in force. Valid coefficients are not silently converted or repaired.

**Exact sampling boundaries in comparison reports.** The report used
`searchsorted(..., side="left")` implicitly, while `ReinforceAgent.act` uses
`side="right"`. For probabilities `[.5,.5]` and draw `.5`, reporting selected the
first action although the actual sampler selected the second. Both report-side
comparisons now use `side="right"`. The sampler itself is unchanged. Missing draws
raise a contextual error; invalid values (including null, strings, booleans,
nonfinite numbers and values outside `[0,1)`) raise rather than becoming choices.

Zero is still a valid draw. Unavailable comparisons retain `examples: 0` without
fabricated change counts. Missing battle records remain `unrecorded`, with no
completed-game win rate; unavailable uncertainty retains its reason. An invalid
checkpoint raises instead of being treated as an unavailable comparison. These
are focused checks of the changed boundary and existing accounting semantics,
not a redesign of historical metric definitions.

The production diff is limited to `reinforce.py` (loader/compatibility) and
`reinforce_experiment.py` (comparison draw handling). Features, distribution,
sampling, parameter mathematics, rewards, gradient/optimizer code, scheduling,
checkpoint selection and bootstrap definitions are unchanged. AST comparisons
check every original function/class except the two intentionally changed
definitions; `reinforce_training.py` is byte-for-byte unchanged.

## Strict compatibility across the repair

Changing loader code changes `reinforce.py`'s hash even though inference is
identical. The new [compatibility profile](../configs/reinforce-loader-compatibility.json)
permits precisely the audited original signature under the exact repaired
runtime signature. It contains the full original compatibility metadata; only
the runtime `reinforce.py` hash differs:

| Source revision | SHA-256 |
|---|---|
| Original | `bde8edd46a4348aded96b9e27cc833ba2aa174c52c24e86d226f97910aec928b` |
| Repaired | `8af399ea0172dfd5b40840d666a7e093c73405a09f011ac3e2afe7ad2ea76d0f` |

Old artifacts must match the entire original signature. Current code must match
the entire repaired signature, including unchanged heuristic/schema hashes,
feature order, shapes, bounds and runtime-version hash. Unknown source revisions
or altered metadata are rejected. New artifacts record their actual current
signature. No frozen hash, checkpoint or source snapshot was rewritten.

This loader compatibility rule does **not** waive experiment full-source checks.
Under current source, `reinforce-report --audit` correctly reports the historical
full-source mismatch while successfully replaying decisions and updates. Exact
historical full-source audits must use `runs/reinforce-main/source-snapshot/src`.
The verification helper launches a separate `python -B` process with that import
root, verifies the full original manifest first, and uses the original audit
without overrides. Bytecode generation is disabled in historical directories.

## Regression and retained-evidence checks

Before production edits, the focused tests produced **3 failures / 6 passes**:
numeric strings in actor and value arrays failed to raise, and the report chose
the wrong action at the exact CDF boundary. The preserved failure trace is
`runs/reinforce-repair-20260909/regressions-before.txt`.

After the repair and added guard coverage:

- **50 focused tests passed** in 1.24s: both defect regressions; zero, neighboring
  and upper-bound draws; malformed/nonfinite/out-of-bounds coefficients; original
  and current valid numeric checkpoints; changed source/feature/runtime rejection;
  missing/invalid/unavailable distinctions; repeated read-only reporting; and
  preservation of the full-source audit failure on mismatched source.
- **229 offline unit tests passed**, 14 integration tests deselected, in 5.51s.
  No battle-collecting or training integration suite ran.
- The repaired intended loader loaded all 13 main checkpoints, main selected,
  both smoke checkpoints and smoke selected (**17 retained files**). Original
  V4 and selected V5 also passed their unchanged intended loaders.
- Replayed **all 83,170 REINFORCE decisions** from every recorded main cell, both
  players and all three phases, preserving chronological per-match RNG streams.
  Recorded probabilities, logits, values, draws and choices reproduced exactly.
  All **12 recorded training updates** reconstructed unchanged, including their
  metrics. This recomputation did not fit or save a new model.
- Rebuilt the report in a fresh output directory while reading original cells.
  Its values equal the historical report; `decision-differences.jsonl` is
  byte-for-byte identical. The audit found no historical exact-boundary ties,
  so the **151/20,389 (0.740595%)** shared-draw difference remains unchanged.
- Two repeated ordinary read-only reports leave the input bytes untouched.
  Preservation checks include prior uncommitted diagnostics and the original
  audit document, as well as all retained main/smoke/audit files.

The separate exact frozen-source full audit **passed**, reproducing all 83,170
decisions and updates in 139.432s. The complete retained verification took
307.099s wall time, with 166.391s parent CPU plus 138.781s archived-audit CPU.
Before the README link was added, 8,187 pre-existing files were hash-verified
unchanged (excluding only the two authorized source edits), with no new files
left in historical directories. Results are recorded in
`historical-source-audit.json` and `verification.json` below. The
current-source replay artifact intentionally records a full-source mismatch;
it must not be presented as a passed full historical-source audit.

## Commands and artifacts

Commands actually run from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_reinforce_repairs.py
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration'
.\.venv\Scripts\python.exe -B diagnostics/reinforce_repair_verify.py
# The helper also invokes this separate original-source check:
.\.venv\Scripts\python.exe -B diagnostics/reinforce_repair_verify.py --historical-audit
git diff --check
```

The single-use verification helper writes only fresh outputs under
**`runs/reinforce-repair-20260909/`**, refusing to overwrite them. It is a retained
verification recipe, not a training or battle command. Entry points:

- [Verification](../runs/reinforce-repair-20260909/verification.json) and
  [frozen-source audit](../runs/reinforce-repair-20260909/historical-source-audit.json).
- `current-source-replay.json`, `corrected-report/report.json` and
  `corrected-report/decision-differences.jsonl` distinguish compatible replay,
  regenerated metrics and full source identity.
- `regressions-before.txt`, `regressions-after.txt`, `unit-tests.txt`,
  `inputs-before.json`, `closure.json` and `hashes.json` retain test failures,
  passes, source/artifact hashes and preservation evidence. Generated data stay
  ignored; the original uncommitted audit work stays intact.

Historical scientific conclusions are unchanged: REINFORCE updated parameters
but did not establish improved battle play; V6 acceptance remains incomplete.
The two identified loader/reporting blockers are repaired. The proposed actor-step
experiment can proceed past these blockers **only under a separate execution
request and frozen specification**. It was not started here, and passing these
checks gives no evidence that a larger step will improve performance. Future
source revisions require a new compatibility review; the original artifacts and
their retained inputs are still required for historical replay.
