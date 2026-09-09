# V6: cross-encounter adjustment from public behavior

V6 keeps the supervised predictor from V4 and the selected scoring parameters from
V5 frozen. It compares no memory, pooled history and individual history. Only the
historical public summary changes; all three call the same existing V5 scorer.
The [experiment specification](V6-EXPERIMENT.md) fixes rules and budgets before
reported games. [STATUS.md](STATUS.md) records the actual **budget-stopped** result:
96 completed development games, no final evaluation, and acceptance incomplete.

## Required retained artifacts

The V4 predictor is `models/v4-supervised.json`, SHA-256
`44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252`.
The selected V5 checkpoint is `runs/v5-acceptance/selected.json`, SHA-256
`35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e`.
Both passed existing loaders and compatibility checks before V6 implementation.
Their originals stay unchanged. V6 copies them into its fresh ignored experiment
root and each run, records their hashes, and fails on missing or altered inputs.

A source-only clone lacks these ignored artifacts and their retained inputs.
The existing regeneration commands, shown for explanation rather than execution:

```powershell
# Requires the retained audited V4 development dataset:
.\.venv\Scripts\python.exe -m battlemind supervised-train --dataset runs/v4-development/development-data --output models/NEW_V4.json
# Requires original V4 artifact; starts an entire separately authorized V5 experiment:
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m battlemind policy-train --predictor models/v4-supervised.json --output runs/NEW_V5
```

V4 numeric fitting is deterministic for identical inputs, but provenance may change
the JSON digest. V5 uses uncontrolled engine randomness; rerunning cannot promise
the historical selected vector/hash. Neither command can silently replace a missing
V6 dependency. No new self-play experiment or predictor fitting occurs in V6.

## From one finished encounter to the next

The existing adapter and `DecisionSnapshot` schema remain unchanged. `runner.py`
constructs the observer's policy with a frozen `MemoryContext` at battle start.
That context contains two versioned numeric `HistorySummary` values, pooled and
individual. It has no names, keys, paths, team identities or provenance. Policies
still accept only a frozen snapshot on each `evaluate`/`choose` call.

Once both clients stop, `EncounterController` reads **only observer a's own**
snapshot journal and its own public tracker. It exports these allowed inputs to
`observer/NNN.json` before the existing privileged recorder reads either player's
committed choice evidence. The memory evidence function receives frozen snapshots,
public events, the frozen predictor and a completion flag; it receives no winner,
private opponent request, current opposing choice, labels or engine end log.

`opponent_memory.encounter_evidence()` checks exact public-history prefixes and
chronological request/turn cutoffs. Each decision's evidence ends at the next own
snapshot or the final own public projection. A visibly living opponent's manual
switch is a switch proxy. One ordinary move announcement is a move proxy. Public
faint replacements and drag are distinguished; no switch announcement never implies
a selected move. Missing, conflicting, engine, forced and uncertain evidence is
explicitly skipped. Lock/copy/charge contexts are conservatively excluded, including
the prior two turns, because the legacy public projection omits trailing annotations.

The proxy is not the V4 target. It can lack genuine-choice eligibility, miss a move
that never announces, or discard turns associated with status/faint/locking effects.
V6 does not fill these gaps using privileged labels. Offline evaluation measures
coverage and selection bias against the original observer-to-label joins.

For each complete encounter with at least four admitted proxies, compute the mean
of `(proxy - frozen V4 probability)`. Give the entire encounter weight one. Add
these means across earlier encounters; divide by `8 + supported encounters`, clip
the correction to [-.15,.15], and add it to the current frozen probability. Clip
the resulting adjusted probability to [.01,.99]. With fewer than two supported
encounters, return the original probability exactly. The eight-encounter zero
residual prior shrinks toward V4. Counts indicate support, not calibrated confidence;
many correlated turns cannot inflate the encounter weight.

## Identity, isolation and frozen scoring

`ObserverMemory` owns a registry of opaque synthetic session keys. These represent
repeated encounters with fixed local bots, not humans or accounts. Only orchestration
routes a summary by key. Key-renaming tests require identical numeric summaries,
digests, predictions and choices given identical histories. Each arm/group gets a
fresh manager, so no evidence crosses arms, development/final, or reset groups.
Unknown sessions start empty even when that observer's pooled memory is nonempty.

`adaptation.AdjustedLogistic` retains the exact frozen `LogisticModel` fields and
overrides only the final probability-return step with the immutable historical
adjustment. `AdaptedAgent` passes these frozen probability sources to the unchanged
`LearnedScoreAgent`. No V4 coefficient, preprocessing field, feature schema, V5
parameter, utility formula, switch rule or tie rule is edited. V5 checkpoint
compatibility therefore remains valid. The probability layer is explicitly versioned
separately; its logged predictor hash always identifies the underlying V4 artifact.

Each observer computes three shadow probabilities/choices on the same snapshot.
Only its assigned arm controls the action. Every arm's shadows use that arm's own
past public evidence. This makes the within-snapshot probability comparison fair;
comparing predictions from different live arms' different visited states alone would
not isolate probability quality. Existing within-battle history is available equally
to all arms and never updates cross-battle summaries during play.

V6 extends the logged V5 decision with `base_probability`, `shadow_probabilities`,
`shadow_choices`, memory context/version/digest/mode and cold/sparse fallback flags.
Inherited V5 fields describe scoring under the played arm's probability; the explicit
`none` shadow is the unchanged selected-V5 control. The adjustment is not a refitted
logistic model. Outer recorder fields never become observation features.

## Replay and evaluation

`memory_audit.replay_cell()` opens only observer exports, its own journal, frozen
artifacts and routing records. It recreates each manager, verifies pre/post digests
and cutoffs, reruns evidence extraction, and reproduces every shadow score/choice.
It never opens labels or end logs. A separate `audit_labels()` call verifies private
commitment/execution evidence for evaluation. Integration tests mutate a copy of
private evidence: public replay must stay identical while private auditing fails.

`adaptation_report.py` joins eligible target-b labels to the observer's snapshot only
after play. It reports three probabilities on those same rows, calibration with bin
support, exclusions, proxy admission/disagreement, cold/later encounters, generating
arm, target and group. Outcome tables include draws and all incomplete categories.
The paired shadow comparison cannot establish counterfactual wins.

The independent unit for uncertainty is a whole reset group containing all related
encounters and arms. The fixed final design has only four such groups. Its cluster
bootstrap is descriptive and cannot establish robust population-level effects.
Targets remain two existing local policies and the team pool remains four fixtures.
Memory across encounters is real; individual-human profiling, unseen-opponent
generalization and new within-battle learning are not implemented or claimed.

## Standard methods and BattleMind work

Residual calibration, shrinkage, clipping and clustered resampling are standard
statistical ideas. This implementation does not claim a novel adaptation algorithm.
BattleMind's engineering work is the permitted public-evidence extraction, conservative
proxy handling, immutable summary boundary, identity isolation, frozen common scoring,
shadow comparison, chronological replay, dependency preservation and single-use
phase budgets. All battle mechanics remain the official engine's responsibility.

Frozen supervised prediction estimates switch probabilities from historical labels.
Prior self-play policy learning produced the already frozen V5 score vector. Pooled
adjustment uses one observer's prior encounters across sessions. Individual adaptation
uses that observer's earlier evidence for the current synthetic session only.

## Actual workflow and limitations found

`runs/v6-acceptance/` contains the one declared run. It stopped after four of six
team-pair blocks in its only development group; all 96 requested games completed.
The 180-second phase allocation could not cover 36 separate four-game server
lifecycles plus validation/auditing. The remaining-time guard stopped collection
at 165.731 seconds rather than borrowing final time. Total wall including report
and hashing was 181.465 seconds. All 576 reserved final games remain unused.

Public replay reproduced 3,643 observer decisions and 96 encounter updates;
89 encounters supplied enough evidence to update the residual summary. On the same
2,222 eligible development snapshots, Brier was .083013/.084411/.072807 for
none/pooled/individual. Individual log loss was better overall but worse than no
memory against switch-active (.302637 vs .288975). The additive correction can
improve one probability loss while worsening another; it is not a confidence model.
Only six identical-snapshot choices changed between individual and none, despite
3,196 probability changes. The existing coarse utility rules often keep the same
winner even when the probability changes.

The complete predefined final workflow is implemented but was **not exercised by
this acceptance run**. Unit tests cover partitions/resets, and the eight-game V6
integration test demonstrates public evidence -> next encounter -> changed frozen
prediction -> deterministic replay. That cannot substitute for the unused final
schedule. One partial development group supports no useful independent-group
uncertainty estimate or claim that individual adaptation improves battle play.

Read-only `adaptation-report --experiment runs/v6-acceptance --audit` validates
recorded evidence and returns failure status for the incomplete experiment. The
supplementary `runs/v6-development-review.json` groups those existing rows without
collecting games or changing memory/rules. `runs/v6-verification.json` records
compatibility, preservation and all artifact-hash checks. No source/specification
was changed after collection to obtain a different result. Failed-phase clock
finalization and the planned-denominator final grid have presentation limitations
documented in SCHEMA/STATUS; use actual phase requests and the reported stop time.
