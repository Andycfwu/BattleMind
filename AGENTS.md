# BattleMind project rules

- Read `README.md`, `docs/STATUS.md`, and `docs/PROJECT.md` before extending work. Milestones 1 and 2 are implemented; do not add ML, a predictor, self-play, or a frontend without a new request.
- Inspect the directory and any Git changes before editing. Preserve unrelated work. Do not commit, push, deploy, or launch extended workloads without the user's request.
- All battles and services stay on `127.0.0.1`. Never use the public ladder, external authentication, cloud accounts, tunnels, hosted models, or paid APIs. Do not relax the reviewed server binding.
- Keep concurrency 1 and bounded battle/turn/time budgets. Never count cleanup forfeits, failures, or caps as wins.
- Policies accept only frozen `DecisionSnapshot` values. No live `Battle`/`Player`, account names, opponent private team/moves/stats, current other-player choices, future results, file identities, or simulator RNG may enter features.
- Read pinned installed source when touching `poke-env` hooks. `LocalPlayer` intentionally overrides private request/message hooks in 0.16.1; regression-test upgrades.
- Gen 1 displayed boosts are not exact effective stats. Preserve raw HP precision. Keep unsupported derived quantities unknown; do not write another simulator.
- Keep the live attempt journals separate per player. Only the post-match recorder may combine choices and read privileged official end logs. An attempted send is not a committed or executed action. Match exact engine input sequences; preserve unknown suffixes after mismatches. Pair opponent labels to the observer's snapshot, never the chooser's private observation. Read `docs/SCHEMA.md` before changing this boundary.
- Preserve wrapper warnings. Only the documented 0.16.1 Wrap/Clamp trailing-annotation warning is recognized by the audit; unexpected warnings/errors require investigation. No silent action retry.
- Freeze heuristic weights before comparisons. Use complete four-game blocks per unordered team pair (24 games for four teams) to balance assignments and player sides. Do not tune on a reported comparison or claim held-out strength.
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
```

Do not replace real-run metrics with fixtures. Report observed counts, failures, actual artifact paths, unsupported behavior, and the one next milestone. Explain code in plain English so the student can defend their own contributions.
