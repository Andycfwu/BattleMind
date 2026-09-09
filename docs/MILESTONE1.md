# Status — Milestone 1 verified

Verified on 2026-09-05. **Milestone 1 is implemented and passed its real local-server acceptance run.** Nothing from Milestone 2 or later has been implemented.

## What works

- Small editable Python package with exact dependency pins, separate baseline policies, typed immutable snapshots, a request/action adapter, bounded runner, diagnostics, and JSON/CSV reporting.
- Official pinned Showdown on loopback only; validated `gen1ou`, two versioned six-Pokémon team fixtures, and Gen 1 listed move powers checked against the wrapper.
- Real RandomLegalAgent versus MaxBasePowerAgent matches, stable original team-slot IDs mapped to current request positions, disabled/zero-PP moves, forced replacement, and explicit Fight/Recharge/Struggle handling.
- Opponent views derived only from player-visible protocol; no reads of the wrapper's opposing private team/state, no account/team-file identities in features, no future message leakage. Unsupported effective stats/counters remain unknown.
- Per-decision observation/legal mapping/intended command logs, submission/terminal/error events, terminal battle records, source/team/version/seed metadata, resource measurements, and regenerated summaries.
- Graceful managed-server cleanup, nonzero CLI status for incomplete runs, explicit failure/cap handling, and no silent random retry after action errors.

## Final acceptance evidence

Final run: `runs/milestone1-final-20/`.

| Measure | Observed result |
|---|---:|
| Requested / completed games | 20 / 20 |
| RandomLegalAgent wins | 2 / 20 (10%) |
| MaxBasePowerAgent wins | 18 / 20 (90%) |
| Draws | 0 |
| Truncations / timeouts / crashes | 0 / 0 / 0 |
| Invalid-action incidents | 0 |
| Policy decisions | 1,180 |
| Recorded / missing battle rows | 20 / 0 |
| Run wall time, including managed server | 5.845 seconds |
| Python CPU time | 1.094 seconds |
| Sampled peak Python RSS | 83,849,216 bytes (~80.0 MiB) |
| Sampled peak managed-server RSS | 453,484,544 bytes (~432.5 MiB) |

These are **restricted two-team-pool pipeline results**, not an estimate of competitive strength or human-level performance. No hypothesis about a predictor was tested. The server RNG is not controlled by `--seed`, so results can change. No inferential uncertainty interval or generalization claim is made from this smoke run.

The saved-log audit checked every one of the 1,180 choices: legal ID membership, matching command/request, corresponding client submission, earlier public evidence for each revealed opposing move, and no public event beyond the observation turn. Both perspectives' terminal results agree with the 20 battle records and regenerated summary. The final run's source/config/script hashes exactly matched the files after implementation. Port 8000 had no listener after managed shutdown.

Final tests: **32 offline unit tests passed** (4 integration cases deselected); **4 explicit integration tests passed** (32 unit cases deselected). Integration included two complete real battles, a real turn-capped match, a real timed-out attempt, server cleanup, and official-engine request probes. The latter are never counted as performance games. `pip check` reported no broken requirements. `doctor --start-server` passed.

## Earlier attempts retained

| Artifact | Observed result / purpose |
|---|---|
| Initial validator invocation | Rejected implicit zero EVs before any match; fixtures now specify legal EVs explicitly. |
| `runs/initial-probe` | 0 completed, 1 crash: adapter initially lacked Gen 1 `Fight`. Actual exception recorded; cleanup's terminal forfeit did not count as a win. |
| `runs/probe-fight-fixed` | 2 completed, 1 win each, no invalid actions; confirmed the narrow fix. |
| `runs/milestone1-smoke-20` | Earlier 20 completed, Random 0 / MaxBasePower 20, 1,102 decisions, no failures; retained before final schema/metadata clarification. |
| `runs/milestone1-final-20` | Final code acceptance: Random 2 / MaxBasePower 18, detailed above. |
| `runs/integration-*` | Both integration passes preserve their real smoke, cap, and timeout records; the cap/timeout cases are deliberate accounting tests. |

No run was overwritten, combined with fixtures, or discarded to improve the displayed final result. Generated runs remain ignored source-control artifacts; the final decision log is about 8.35 MB.

## Commands actually executed

From this project directory in PowerShell:

```powershell
python -m venv .venv
# Initial installation, followed by freezing the exact installed dependency versions:
.\.venv\Scripts\python.exe -m pip install poke-env==0.16.1 pytest==9.0.2 psutil==7.2.2
.\.venv\Scripts\python.exe -m pip freeze | Set-Content requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
# After saving the engine lock/config, the repeatable setup was rerun successfully:
.\scripts\setup-showdown.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m battlemind doctor --start-server
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration
.\.venv\Scripts\python.exe -m battlemind battle --start-server --agent-a random --agent-b max-base-power --battles 20 --seed 42 --output runs/milestone1-final-20
.\.venv\Scripts\python.exe -m battlemind report --run runs/milestone1-final-20
.\.venv\Scripts\python.exe -m pip check
```

The first engine setup used the bundled Git executable to run `clone --depth 1 https://github.com/smogon/pokemon-showdown.git .local/pokemon-showdown`, recorded its actual HEAD, installed via bundled pnpm with `install --prod --no-optional --ignore-scripts`, then ran `node node_modules/esbuild/install.js` and `node build`. The saved setup script subsequently succeeded with `--frozen-lockfile`. The upstream esbuild npm fallback failed because npm was not on PATH; its direct-registry fallback succeeded. No simulator installation blocker remains.

Final log/content-hash audit command, also executed:

```powershell
.\.venv\Scripts\python.exe -c "import json, sys; from pathlib import Path; sys.path.insert(0, 'tests'); from test_integration import audit_run; from battlemind.environment import source_manifest; p=Path('runs/milestone1-final-20'); audit_run(p, 20); m=json.loads((p/'run.json').read_text()); assert m['code_sha256'] == source_manifest(); print('FINAL AUDIT PASSED: 1180 decisions, 20 terminal records, legal mappings, submissions, public-reveal evidence, and matching source hashes')"
```

Use a **new** output path for another battle run; the existing acceptance directory deliberately cannot be reused. The `report` and audit commands are repeatable against its saved files.

## Known limitations

- Only Windows, the pinned runtime versions, `gen1ou`, concurrency 1, and the versioned restricted pool have been verified. Other generations and broad team/move coverage are outside scope.
- Gen 1 effective stats, overflow, Counter damage, residual counters, and trapping duration are unsupported unknowns. The public history is a documented projection, not a complete replay. See `COMPATIBILITY.md` and upstream issue #753.
- Policies are deliberately weak. MaxBasePower is not damage calculation and uses fixed listed power even for strategically poor or self-fainting choices. Performance against random is not the eventual success criterion.
- Submitted choices are intended actions; execution and trustworthy opponent switch labels are not implemented. Logs must not be treated as a ready-to-train dataset.
- Simulator randomness is unseeded by the challenge interface. Policy seeds control policy RNG only. Exact battle replay determinism is not claimed.
- `poke-env` request/message/cleanup hooks include private APIs and are pinned; upgrades need source review and regression tests. No changes were made to installed library or engine source.
- Manual-server diagnostics validate the specified checkout and a local handshake, not an independently launched listener's provenance. Managed-server mode launches the checked checkout.
- Resource peaks are sampled and may miss instantaneous peaks. Forced OS/process termination can leave a partial run; `report` exposes missing rows. External-server resource use is not measured.
- There was no existing Git repository. Run manifests use file hashes, and no Git commit, push, or deployment was made.

## Single next milestone

**Milestone 2: better baselines and trustworthy data.** Add a documented Gen 1 heuristic, widen the tested legal team/opponent pool, and validate opponent intended-choice labels while separating voluntary switches, forced replacements, and ambiguous events. Keep prediction/training for the subsequent milestones.
