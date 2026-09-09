# BattleMind project rules

- The user's acceptance-repair request separately authorizes exactly one replacement,
  `runs/v6-acceptance-repair`, under `docs/V6-ACCEPTANCE-REPAIR.md` and
  `configs/v6-acceptance-repair.json`: 144 development / 576 final games,
  420s / 1,080s phases and 300s overhead, 1,800s total. Do not tune scientific rules,
  retrain or change opponents. Do not resume the original or retry this replacement.
  Read STATUS for its actual outcome before further work. Source/report repairs
  preserve original scientific modules and must reproduce retained snapshots.
  That authorization is now consumed: development completed 144/144; final stopped
  at 251 completed plus one cap, with 324 never requested. The fixed switch-active
  heuristic stalled with a frozen active despite a healthy legal switch. Do not
  change opponents/caps/rules or run another replacement without a new request.

- The original V6 attempt is **incomplete**, not passed: `runs/v6-acceptance` stopped on the
  180-second development allocation after 96 completed games; final requested zero.
  Do not resume, retry, borrow its final allocation or run a replacement without a
  new request. Public replay/hash audits passed for the recorded partial evidence.
  Read STATUS for the failed-phase timing and planned-final-denominator limitations.

- Read `README.md`, `docs/STATUS.md`, `docs/PROJECT.md`, `docs/PREDICTION.md`, `docs/SCHEMA.md`, `docs/POLICY-LEARNING.md`, `docs/V5-EXPERIMENT.md`, `docs/ADAPTATION.md`, `docs/V6-EXPERIMENT.md` and `docs/V6-ACCEPTANCE-REPAIR.md` before extending work. V1–V6 include frozen prediction, bounded policy learning and cross-encounter synthetic-opponent memory. Do not add external replay ingestion, human profiling, a frontend, additional training or another adaptation experiment without a new request. Preserve historical evidence in `docs/MILESTONE3.md`, `docs/MILESTONE4.md`, `docs/MILESTONE5.md` and `docs/MILESTONE6-FIRST-ATTEMPT.md`.
- Inspect the directory and any Git changes before editing. Preserve unrelated work. Do not commit, push, deploy, or launch extended workloads without the user's request.
- All battles and services stay on `127.0.0.1`. Never use the public ladder, external authentication, cloud accounts, tunnels, hosted models, or paid APIs. Do not relax the reviewed server binding.
- Keep concurrency 1 and bounded battle/turn/time budgets. Never count cleanup forfeits, failures, or caps as wins.
- Policies accept only frozen `DecisionSnapshot` values. No live `Battle`/`Player`, account names, opponent private team/moves/stats, current other-player choices, future results, file identities, or simulator RNG may enter features.
- Read pinned installed source when touching `poke-env` hooks. `LocalPlayer` intentionally overrides private request/message hooks in 0.16.1; regression-test upgrades.
- Gen 1 displayed boosts are not exact effective stats. Preserve raw HP precision. Keep unsupported derived quantities unknown; do not write another simulator.
- Keep the live attempt journals separate per player. Only the post-match recorder may combine choices and read privileged official end logs. An attempted send is not a committed or executed action. Match exact engine input sequences; preserve unknown suffixes after mismatches. Pair opponent labels to the observer's snapshot, never the chooser's private observation. Read `docs/SCHEMA.md` before changing this boundary.
- Preserve wrapper warnings. Only the documented 0.16.1 Wrap/Clamp trailing-annotation warning is recognized by the audit; unexpected warnings/errors require investigation. No silent action retry.
- Freeze heuristic weights before comparisons. Use complete four-game blocks per unordered team pair (24 games for four teams) to balance assignments and player sides. Do not tune on a reported comparison or claim held-out strength.
- V2 `Gen1HeuristicAgent` weights stay frozen. V3 constant and conditional variants share the same `SwitchAwareAgent` scoring. Prediction uses only observer snapshots; post-battle target eligibility is never an online input. Evaluation cannot update counts.
- V4 logistic uses the same scoring, with train-only preprocessing and a declared three-lambda validation search. Fair counts fit exactly the same training rows. Bundle policies receive frozen parameters/digest, never provenance or eligibility. No pickle or evaluation-time updates. Runner-b identity is offline population selection only; sides still swap.
- V5 freezes the original V4 predictor SHA-256 `44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252` and original V2/V3/V4 scorers. `learned-score` receives immutable bounded parameters and no checkpoint provenance or opponent IDs as features. Checkpoint compatibility checks cover scoring source, feature schema, predictor hash and bounds.
- V5's single-use specification allocates 336 training, 216 selection and 288 final games (840 total), at most 1,200 seconds. Reserve final before training; do not borrow phase allocations or retry. Only complete audited comparison outcomes permit updates. Freeze each round's pool and update between batches only. Resume is unsupported. Selection and final evaluation must never update parameters or predictor state; audit run-hash-plus-match partitions.
- V6 preserves V4's predictor and selected V5 checkpoint `35c2071bf94364bd8812a196091ab06c0d7c1fa994a6e0a4003c23d2ac8bcd6e`; validate originals before use. Never regenerate/substitute missing artifacts automatically. Keep original scoring/schema files unchanged so historical checkpoint compatibility remains valid.
- V6 memory reads only the observer's own frozen snapshots/public history after a completed encounter. No labels, private commitments/end logs, winner or other journal enters memory. Keep proxy admission/skips explicit. Incomplete encounters contribute no update; freeze numeric summaries during battles. Session keys/observer IDs route only in orchestration and never enter features.
- Follow the single-use V6 specification: 144 development + 576 final games, 900 seconds, concurrency 1. Final is reserved before development, with fresh empty registries for every arm/group. Only predeclared public-history updates are allowed during final; V4 coefficients, V5 parameters and adjustment rules stay frozen. No retry, resume or budget borrowing.
- V6 shadow comparisons use all probability variants on the same observer snapshots with that observer's own history only. Resample whole independent reset groups, not memory-linked turns/battles. Four final groups support descriptive uncertainty only. Public-memory replay and private label auditing are separate; corrupting private evidence must not affect reconstructed memory.
- Follow `docs/V4-EXPERIMENT.md`: fixed opponents, 24-game cells, aggregate collection/final ceiling 600 games/900 seconds and persistent single-use reservations. No tuning or retries on final results. Generated data/models remain ignored. Changes to fixed opponents or scoring require a new experiment specification.
- Dataset identities are run-manifest SHA-256 plus match index. Keep both perspectives/all turns together. Estimate counts only from `development_fit`; previously reported M2 `development_check` is not an untouched test. Fresh evaluation must not overlap any development battles. Preserve exclusions and source hashes.
- Benchmark every version as developed. Current roadmap: V1 legal matches, V2 basic strategy, V3 opponent prediction, V4 supervised training from local records, V5 self-play learning, V6 individual adaptation, V7 consolidated benchmarks. Do not implement the next version without a request.
- Source fixture teams/versions/configs are tracked candidates. `.local/`, `.venv/`, `runs/`, datasets, and weights remain ignored. Preserve third-party notices.
- Use `requirements.lock` and `configs/showdown-pnpm-lock.yaml`; update version records with intentional dependency changes. New runs use fresh output directories and record content hashes because this workspace may have no Git repository.

Verified PowerShell commands, from project root:

```powershell
. .\scripts\env.ps1
.\scripts\setup-showdown.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m battlemind doctor --start-server
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration
.\.venv\Scripts\python.exe -m battlemind battle --start-server --battles 20 --seed 42
.\.venv\Scripts\python.exe -m battlemind report --run runs/ACTUAL_DIRECTORY
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/milestone2.json --agent-b random --output runs/NEW_DIRECTORY
.\.venv\Scripts\python.exe -m battlemind report --run runs/ACTUAL_M2_DIRECTORY --audit
.\.venv\Scripts\python.exe -m battlemind dataset --runs runs/m2-comparison-random runs/m2-comparison-max-base-power --output datasets/NEW_DEVELOPMENT --seed 2026
.\.venv\Scripts\python.exe -m battlemind predictor-fit --dataset datasets/NEW_DEVELOPMENT --output models/NEW_COUNTS.json
.\.venv\Scripts\python.exe -m battlemind predictor-evaluate --dataset datasets/NEW_DEVELOPMENT --predictor models/NEW_COUNTS.json --partition development_check --output runs/NEW_QUALITY
.\.venv\Scripts\python.exe scripts/benchmark-v3.py --predictor models/NEW_COUNTS.json --output runs/NEW_V3_BENCHMARK
.\.venv\Scripts\python.exe -m battlemind supervised-dataset --runs runs/integration-v4-73e081637f/recorded --output datasets/NEW_V4_DATA
.\.venv\Scripts\python.exe -m battlemind supervised-train --dataset runs/v4-development/development-data --output models/NEW_V4_MODEL.json
.\.venv\Scripts\python.exe -m battlemind supervised-evaluate --dataset runs/v4-acceptance/evaluation-data --predictor models/v4-supervised.json --partition evaluation --output runs/NEW_V4_QUALITY
.\.venv\Scripts\python.exe -m battlemind report --run runs/v4-acceptance/logistic-vs-switch-moderate --audit
.\.venv\Scripts\python.exe -m battlemind policy-report --experiment runs/v5-acceptance --audit
.\.venv\Scripts\python.exe -m battlemind adaptation-report --experiment runs/v6-acceptance --audit
```

Load `scripts/env.ps1` in each new PowerShell terminal before server commands: the system PATH may select Node 24.20.0, while the pinned bundle is 24.19.0. Keep the version check. Historical V3 uses 144 games/600 seconds. V4's 432-game evidence is in `docs/MILESTONE4.md`, V5's 840-game evidence in `docs/MILESTONE5.md`, and current V6 commands/results in `docs/STATUS.md`. Historical full-source freeze audits require the source manifest that ran; V5 scoring/checkpoint compatibility remains preserved after V6 orchestration extensions. `policy-train` and another `adaptation-run` need a separate request. Never repeat final games just to obtain better outcomes.

Do not replace real-run metrics with fixtures. Report observed counts, failures, actual artifact paths, unsupported behavior, and the one next milestone. Explain code in plain English so the student can defend their own contributions.
