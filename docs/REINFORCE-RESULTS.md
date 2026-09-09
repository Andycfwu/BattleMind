# Richer policy research — observed results, 2026-09-09

**The learning pipeline works; better final battle play was not established.**
The main experiment made 12 real policy-gradient updates, including 252 admitted
archived self-play episodes. Fresh selection chose c6. In independent final games,
c6 scored **155 wins / 128 losses / 5 draws**, versus initialization's
**159 / 125 / 4**, with 288 completed games per arm. The selected model's overall
point estimate regressed slightly and the descriptive uncertainty remains wide.
No second experiment, retries, additional training or new generation followed.

This is separate from V1–V7. Both V6 acceptance attempts remain incomplete. Original
models, scorers and evidence are preserved, including the pre-extension
[V7 status](MILESTONE7.md). The new cap rule does not retroactively change V6.

## Actual collection and accounting

The predeclared [main specification](REINFORCE-EXPERIMENT.md) allocated 864 training,
216 selection and 576 final games, below the 2,400-game user ceiling. Every planned
cell was reserved, dispatched and recorded exactly once; never-requested and
missing records are zero. No allocation was reused or expanded. Concurrency was
one, all services bound to 127.0.0.1, with the existing 300-turn/60s-match limits.

| Phase | Requested | Completed | Wins / losses / draws | Caps | Phase wall seconds |
|---|---:|---:|---:|---:|---:|
| Training | 864 | 863 | 281 / 564 / 18 | 1 | 461.362 |
| Selection | 216 | 216 | 59 / 152 / 5 | 0 | 102.708 |
| Final, both arms | 576 | 576 | 314 / 253 / 9 | 0 | 264.025 |
| **Main total** | **1,656** | **1,655** | **654 / 969 / 32** | **1** | **828.094 summed phases** |

Wins/losses above belong to the learning/evaluated side, regardless of engine
player side. All phases have **zero invalid actions, timeouts, crashes,
cancellations, not-started records, missing records and unexpected warnings**.
The experiment finished under its declared cap-continuation rule; completion of
the schedule does not turn its one incomplete battle into a terminal reward.

The cap is `training/b7-vs-v2`, match 16. At turns 299–300, the learner's frozen
Chansey had only `engine:fight`; V2's frozen Zapdos repeatedly chose that engine
action despite legal bench switches. The boundary was recorded at turn 301, with
no policy action beyond the 300-turn cap. Cleanup produced a forfeit in the raw
terminal stream, but the battle has `winner:null` and its training target has
`reward:null`. All 608 commitments were verified. Audited cleanup permitted later
independent games. The frozen V2 opponent was not repaired to avoid the stall.

Full phase/opponent accounting is in
[outcomes.csv](../runs/reinforce-verification/outcomes.csv) and
[report.json](../runs/reinforce-main/report.json). Training versus V2 was
71–211–5 plus one cap in 288 requests; versus V5, 75–208–5 in 288; versus all
archives, 135–145–8 in 288. These changing-learner training results are not a
frozen-policy benchmark.

## Actual updates and exclusions

793 of 864 training episodes were admitted. Exclusions were **70 episodes with
unknown learner commitments and one cap** (71/864, 8.22%). The original attempts,
unknown suffixes and targets remain present. Reference V2 admitted 270/288,
V5 271/288 and archived self-play 252/288. The larger archive exclusion fraction
(12.5%, versus 6.25% and 5.90%) makes selection bias a practical limitation.
No missing target was converted into an ordinary loss, win or fabricated reward.

Every batch also contains fixed V2 and V5; the archive column identifies the third
frozen opponent. The table shows admitted rewards, not all requested outcomes.
Policy loss is the sampled REINFORCE surrogate and is not comparable as a measure
of playing strength across different batches/pools.

| Update | Archive | Admitted / 72 | Mean R | Policy loss | Value loss | Actor change L2 |
|---|---|---:|---:|---:|---:|---:|
| 1 | c0 | 64 | -0.2500 | -0.09783 | 0.50000 | 0.07406 |
| 2 | c0 | 68 | -0.2941 | -0.06409 | 0.48696 | 0.05935 |
| 3 | c0 | 67 | -0.4627 | -0.16826 | 0.49797 | 0.04825 |
| 4 | c2 | 68 | -0.5000 | -0.21988 | 0.48381 | 0.07129 |
| 5 | c0 | 67 | -0.4328 | -0.16961 | 0.47962 | 0.04873 |
| 6 | c4 | 65 | -0.2615 | -0.03499 | 0.48637 | 0.07506 |
| 7 | c0 | 65 | -0.3385 | -0.11000 | 0.46294 | 0.07216 |
| 8 | c6 | 65 | -0.1846 | -0.08901 | 0.48564 | 0.05385 |
| 9 | c0 | 63 | -0.2381 | -0.08558 | 0.47654 | 0.07766 |
| 10 | c8 | 67 | -0.4030 | -0.09652 | 0.49336 | 0.06922 |
| 11 | c0 | 68 | -0.2500 | -0.06496 | 0.45371 | 0.05867 |
| 12 | c10 | 66 | -0.5455 | -0.18811 | 0.48592 | 0.08951 |

All actor and value changes were nonzero and finite. Selected c6's actor norm is
0.165339 and value norm 0.061025, from zero initialization; c12's are 0.302628 and
0.111562. Neither reaches its projection bound (6 and 3). Full gradients, learning
rates, parent/checkpoint hashes, target keys and parameter changes are in
[updates.csv](../runs/reinforce-verification/updates.csv) and each original batch
record. The audit reproduced all 12 vectors and metrics exactly from the recorded
completed outcomes. These are genuine gradient-based policy updates; V5's earlier
derivative-free method and V4's supervised fitting were not rerun.

## Selection and independent final comparison

Each predeclared candidate completed 72 fresh selection games against V2/V5/c0.
Mean R was c0 **-0.472222**, c6 **-0.375000**, c12 **-0.444444**. The fixed rule
(most completions, then mean R, then earliest checkpoint) therefore chose c6.
Final results did not change that choice, opponents, weights or any rule.

| Final opponent | Initial c0 W/L/D | Selected c6 W/L/D | Completed per arm |
|---|---:|---:|---:|
| Random, reserved simple reference | 48 / 0 / 0 | 48 / 0 / 0 | 48 |
| MaxBasePower, reserved simple reference | 39 / 9 / 0 | 39 / 8 / 1 | 48 |
| V2 heuristic, familiar | 7 / 41 / 0 | 17 / 31 / 0 | 48 |
| Selected V5, familiar | 14 / 33 / 1 | 9 / 38 / 1 | 48 |
| Initial archive c0, familiar | 27 / 19 / 2 | 20 / 26 / 2 | 48 |
| Archive c6, familiar | 24 / 23 / 1 | 22 / 25 / 1 | 48 |
| **Overall** | **159 / 125 / 4** | **155 / 128 / 5** | **288** |

All final games completed; no final cap/failure censoring is present. Win rates
are **55.21% initial and 53.82% selected**, with draws in the denominator but not
counted as wins. Mean terminal R is 0.118056 versus 0.093750: selected-minus-initial
**-0.024306**, with the predeclared 1,000-resample, opponent-stratified four-game
team/side-block descriptive 95% interval **[-0.152778, 0.093750]**. No turns are
treated as independent samples. Unknown-outcome bounds collapse to the observed
difference because every final game completed.

The c6 panel opponent was predeclared before selection happened to choose c6;
this mirror matchup is retained. Random/MaxBasePower were reserved simple policies,
not held-out human strategies. Aggregate wins are strongly helped by those weak
references. Selected c6 still loses most games against both V2 and V5. Its V2
point improvement and V5/archive regressions are descriptive, with only 48 games
per matchup and unmatched engine randomness. They do not establish either robust
improvement or a reliable forgetting effect. There is one learning seed, four
teams, one generation and no human/generalization claim.

On the **same 20,389 final learner snapshots**, c6 changes the argmax in 1,644
(8.06%) and the shared-uniform-draw action in 151 (0.74%). Mean total-variation
distance between action distributions is only **0.003974** (maximum 0.017221).
Argmax changes often reflect near ties; actual stochastic behavior moved little.
This is evidence of modest policy change, not counterfactual wins. The value
baseline remains a coarse approximation and sparse terminal credit has high
variance. Greater capacity alone did not overcome these limits in 12 updates.

## Engineering evidence, runtime and artifacts

Before main collection: **179 unit tests passed, 14 integration tests deselected
(4.63s)**. The retained real smoke workflow check passed (**1 passed, 19 deselected,
4.00s**) while collecting **zero new test-suite games**. Existing unit suites cover
V1–V7 boundaries as well as the new finite-difference gradients, variable legal
sets, forced/engine actions, frozen inference, phase/stale-data rejection,
round-trip compatibility, outcome updates and budget/cap accounting.

The separately specified engineering smoke requested/completed **48/48** in
**25.013s**: 24 c0-versus-c0 games, one update using 20 admitted episodes, then
24 frozen c1-versus-V2 games. Four episodes had unknown commitments. Its actor
delta was 0.00095664; 40 recognized warnings and 99 unknown labels remained visible.
No smoke cap/invalid action/crash/timeout occurred. Its 13–11 training and 6–18
evaluation results are **not improvement evidence**. Main used a documented step
scale change based on the small finite gradient, not smoke win rates, and restarted
from zero coefficients with new identities. The original smoke freeze/audit was
preserved; later compatible trajectory/update replay passed without weakening its
historical full-source check.

Main collection stopped at **828.633s**. Its initial reporting/hashing took
**24.375s**, and setup/inter-phase overhead accounts for the remainder of the
**853.008s** closed experiment duration. The full read-only audit plus supplemental
checks took **153.352s**, reproducing **83,170 learned-policy decisions**, all
private commitment audits, 12 updates, target files, selection ranking, balanced
schedules and all **1,656 disjoint phase identities**, with zero smoke overlap.
The two zero-game viewer checks used 3.714s and 2.992s; derived CSV/distribution
analysis took 0.260s. Timed collection/reporting/verification work thus totals
about **1,013.33s**, including **185.23s overhead**, within the reserved automated
allocations. Read-only reports never extended or rewrote the closed ledger.
Documentation/interactive review latency is separate from these measured process
durations; it is not a claimed compute measurement.

Final closure additionally took 0.935s and rechecked the original scientific source
files against the starting Git version, full main source freeze, original V4/V5
loaders, V7 bundle/zip and empty server listeners/processes. After the CSS fix,
the full unit suite again passed 179 tests in 4.63s with 14 integrations deselected;
these checks collected zero games. `runs/reinforce-verification/closure.json`
and `hashes.json` retain this closure and hashes of the derived audit outputs.

During battle runs, summed sampled Python CPU was **249.984s**, last-sample server
CPU **272.047s**, maximum sampled RSS **404,131,840 bytes Python** and
**454,795,264 bytes server**. Sampling at 0.1s misses exact peaks and server final
CPU tails; these figures exclude between-run update/audit work. The separate full
audit used **152.828s Python CPU**, with 343,928,832-byte RSS at completion.
The full main archive contains **7,785 files / 2,827,054,816 bytes**. Initial JSON
is 12,915 bytes and selected c6 JSON 22,293 bytes. No dependency/model download or
paid infrastructure was added; NumPy 2.5.2 and all runtime pins are unchanged.

Across main games, **120,164/123,950 intended choices were verified (96.95%)**;
3,786 remain unknown. All **1,134 client warnings** were recognized pinned
Wrap/Clamp annotation warnings; zero unexpected warnings/server crash reports.
Labels remain distinct from execution evidence. The main audit and original
artifact hashes passed. Hashes detect corruption/compatibility errors, not a
malicious local editor replacing both evidence and manifests.

Viewer verification loaded c6 as optional `reinforce`, retained defaults
`learned-score`/`max-base-power`, and rendered the **first** final c6-versus-V2 game
at turn 5. It was chosen by schedule position, not outcome. Model/private endpoints
returned 404; runtime requests were local; launches were disabled at 0/0 games.
The first visual inspection exposed an existing late-loaded renderer CSS conflict;
a narrow `.bottom .official-log` containment rule fixed the overlapping log without
redesigning the viewer. The second check asserted panel bounds and inspected the
[corrected screenshot](../runs/reinforce-viewer-final-check/viewer.png). No live demo
launch was exercised for this optional model; ordinary frozen engine play was
already exercised by 576 final games. Both checks shut down cleanly; ports 8000
and 8765 had no remaining listeners. Historical bundles were not edited.

| Artifact | SHA-256 |
|---|---|
| Main configuration | `90bb8b5506b3617a43a2cd14b7c136589a55376abe433726f363f8885a205fa8` |
| Main specification document | `89f14d3ad521d73ff7b6187dc36088f3325a90790aa04e9bd158e820b5b861ae` |
| Freeze manifest | `220f1f2be4fad0060420362515b9577696894bdc427dea780af430f192f67bc1` |
| Initial c0 | `f7734489bce5d74ce2dedffd8ab274a8483810a03e09b48a26ea0ebf28d44287` |
| Selected c6 | `597d456a01f009e4638f537d56b950983b4b2de7893f585418de1a567c51bff4` |
| Retained c12 | `5ec8e162f59ab7432d5d99736e4140b4f1f50c89506709ae5217f45c94722fbc` |
| Closed ledger, unchanged by audit | `bded277ae802c96773dda7ef50f3038ffa7ca7d48c367e0fd154aa124a58f612` |
| Artifact hash manifest | `2e7895f52d03c375a6fc4ee9cf2a1ecd4e12e26da3fcee1c532f9ac144c17600` |
| Original V4, unchanged | `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` |
| Original selected V5, unchanged | `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e` |

Main results: `runs/reinforce-main/{summary,report,ledger,selection,freeze}.json`.
Full reconstruction: `runs/reinforce-verification/main-audit.json`; supplemental
target/partition/accounting checks: `verification.json`; derived distributions:
`analysis.json`. Viewer checks and screenshot: `runs/reinforce-viewer-final-check`;
public recording: `runs/reinforce-public-final`. The original V7 release zip and
minimal bundle remain unchanged. Generated experiments/models/records stay ignored;
a source-only clone does not contain or recreate these historical checkpoints.

## Commands actually run

All commands were run from the project root with `.venv` and the pinned env for
server work. No Git commit, push or deployment was made. The initial Git state was
clean at `cd34456` (`V7`); source content hashes describe this uncommitted extension.

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m pytest -q -m "not integration"
.\.venv\Scripts\python.exe -m pytest -q tests/test_reinforce.py -m integration
.\.venv\Scripts\python.exe -u -m battlemind reinforce-run --spec configs/reinforce-smoke.json --output runs/reinforce-smoke *> .local/reinforce-smoke-console.log
.\.venv\Scripts\python.exe -m battlemind reinforce-report --experiment runs/reinforce-smoke --audit > .local/reinforce-smoke-audit.json
.\.venv\Scripts\python.exe -u -m battlemind reinforce-run --spec configs/reinforce-main.json --output runs/reinforce-main *> .local/reinforce-main-console.log
.\.venv\Scripts\python.exe -u .local/reinforce-verify.py *> .local/reinforce-verification-console.log
.\.venv\Scripts\python.exe -m battlemind reinforce-report --experiment runs/reinforce-main > .local/reinforce-main-report-cli.json
.\.venv\Scripts\python.exe -u .local/reinforce-viewer-verify.py *> .local/reinforce-viewer-verification-console.log
.\.venv\Scripts\python.exe -u .local/reinforce-viewer-verify-final.py *> .local/reinforce-viewer-final-verification-console.log
git diff --check
```

The supplemental main script calls the same `report_experiment(..., audit=True)`
used by the CLI, then independently verifies targets, selection and terminal
accounting. Its content hash is retained in `verification.json`. It generates no
games or checkpoint files. The public repeatable command is
`python -m battlemind reinforce-report --experiment runs/reinforce-main --audit`;
as with other strict historical audits, use retained source if implementation
hashes change later. Scripts under `.local` are retained audit helpers, not required
installation dependencies. Model/battle/viewer usage is in [REINFORCE.md](REINFORCE.md).

The justified next action is **more learning research**, separately scoped around
the weak terminal-credit/value approximation and small changes in actual action
probabilities, using this retained evidence first. Merely adding games, teams or
another generation is not supported as the immediate remedy. Nothing further was
trained or automatically scheduled.
