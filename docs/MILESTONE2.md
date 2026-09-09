# Status — Milestone 2 verified

Verified on 2026-09-05. **Milestone 2 is implemented:** a transparent Gen 1 heuristic, four legal versioned teams, and separate post-commit intended-choice labels with explicit unknowns. No ML, predictor, training, self-play or frontend was added. Historical Milestone 1 evidence is preserved in [MILESTONE1.md](MILESTONE1.md).

## Implemented behavior

- `Gen1HeuristicAgent` consumes only frozen snapshots. It scores public power/accuracy/STAB/type information, explicit healing/status/setup rules and conservative switching utility. Scores and reasons are logged. It never calculates exact damage or effective stats; [HEURISTIC.md](HEURISTIC.md) specifies every rule and limitation.
- RandomLegalAgent and MaxBasePowerAgent remain available, with their original policy behavior.
- The four-team schedule covers six unordered pairs, both assignments and both challenger sides: 24 games per comparison. Each policy uses each team six times and occupies actual engine side p1/p2 twelve times each.
- Separate per-player live journals are combined only after both clients stop. The recorder verifies exact intended-choice sequences against the official engine's committed `inputLog`. Verified opponent targets point to the observer's simultaneous frozen snapshot, never the opponent's private observation. Missing or mismatched evidence stays unknown.
- Forced replacements, voluntary switches, ordinary moves, engine actions and uncertainty remain distinct. Execution evidence is recorded separately: announcement, observed switch, inability to act, no announcement, or unknown. A move announcement does not prove a hit or effect.
- `report --audit` rebuilds labels from saved evidence and checks snapshot/end-log hashes, legal mappings, submissions and label counts. Full boundary details are in [SCHEMA.md](SCHEMA.md).

## Team pool

All four six-Pokémon files passed the pinned official `gen1ou` validator. Existing v1 files were preserved. These are project-assembled fixtures using familiar sets, not optimized or comprehensive metagame coverage.

| File | Species | Decisions exercised |
|---|---|---|
| `configs/teams/ou-v1-a.txt` | Alakazam, Tauros, Snorlax, Chansey, Exeggutor, Rhydon | Recovery, fixed damage, sleep, self-KO, Ground immunity |
| `configs/teams/ou-v1-b.txt` | Starmie, Tauros, Snorlax, Chansey, Exeggutor, Gengar | Water coverage, Ghost immunity, sleep, fixed damage |
| `configs/teams/ou-v2-c.txt` | Jynx, Dragonite, Jolteon, Snorlax, Chansey, Tauros | Lovely Kiss, Wrap, Agility, Amnesia, Rest, Double Kick |
| `configs/teams/ou-v2-d.txt` | Zapdos, Cloyster, Victreebel, Starmie, Golem, Tauros | Clamp/Wrap, sleep, Swords Dance, recovery, type matchups |

SHA-256 values, in that order:

```text
84196a5540d751c54b7d5a9475a2b56f471a34f7f453330a8e65ea689c5f1e9e
e438a6a32cf4393a40c25d9ee61e8c83a140f59abd26292a499770aa73d164a5
08740397a02db1aab46df3615c8780801445b50d609f57d641a223926c91cda9
ba1d05fc73c3e377772147c11659886340d3cc4b72df7683bfd3156d0a963b25
```

The saved diagnostic [runs/m2-doctor.json](../runs/m2-doctor.json) records all four validations, public-table checks, pinned Python 3.14.3 / poke-env 0.16.1 / Node 24.19.0 / Showdown commit `2f5b273925862ac242b419086c1e7a8868b51da1`, and the successful loopback handshake. BattleMind is now version 0.2.0; no runtime dependencies were added. `pip check` passed.

## Actual bounded comparisons

Policy A was the same frozen `gen1-heuristic-v1` in both runs. Configuration: `configs/milestone2.json`, seed 2026, concurrency 1, turn cap 300, match timeout 60 seconds, run limit 600 seconds. The simulator RNG is not controlled by this seed. No heuristic weights were tuned after seeing these results.

| Measure | Versus random | Versus MaxBasePower |
|---|---:|---:|
| Requested / completed | 24 / 24 | 24 / 24 |
| Heuristic wins / losses / draws | 24 / 0 / 0 | 22 / 2 / 0 |
| Completed-game heuristic win rate | 100% (24/24) | 91.67% (22/24) |
| Descriptive 95% Wilson interval | 86.20–100% | 74.15–97.68% |
| Invalid actions | 0 | 0 |
| Caps / timeouts / crashes / cancellations | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Missing / not-started matches | 0 / 0 | 0 / 0 |
| Server crash reports | 0 | 0 |
| Known wrapper warning records | 8 | 0 |
| Unexpected client warning records | 0 | 0 |
| Decisions | 1,377 | 1,050 |
| Verified intended choices / unknown | 1,370 / 7 | 1,050 / 0 |
| Intended-choice coverage | 99.49% | 100% |
| Verified voluntary / forced switches | 292 / 153 | 36 / 184 |
| Verified ordinary moves / engine actions | 839 / 86 | 763 / 67 |
| Eligible paired opponent targets | 1,026 | 749 |
| Paired voluntary switch / move targets | 249 / 777 | 33 / 716 |
| Run wall seconds | 7.047 | 6.507 |
| Python CPU seconds | 2.109 | 1.469 |
| Last sampled server CPU seconds | 3.172 | 3.266 |
| Sampled peak Python RSS, bytes | 90,480,640 | 90,660,864 |
| Sampled peak server RSS, bytes | 439,517,184 | 437,395,456 |

These are **restricted four-team-pool, weak-baseline results**, not held-out generalization or competitive-strength evidence. Wilson intervals are descriptive Bernoulli intervals for this small schedule; heterogeneous matchups are not an IID sample of human opponents. Resource peaks are sampled at 0.1 seconds, and wall time includes server lifecycle but excludes preflight/setup. Neither cleanup forfeits nor incomplete games contribute wins.

Artifacts:

- [Random comparison summary](../runs/m2-comparison-random/summary.json), [battle rows](../runs/m2-comparison-random/battles.jsonl), [decisions](../runs/m2-comparison-random/decisions.jsonl), [privileged labels](../runs/m2-comparison-random/privileged/labels.jsonl).
- [MaxBasePower comparison summary](../runs/m2-comparison-max-base-power/summary.json), [battle rows](../runs/m2-comparison-max-base-power/battles.jsonl), [decisions](../runs/m2-comparison-max-base-power/decisions.jsonl), [privileged labels](../runs/m2-comparison-max-base-power/privileged/labels.jsonl).
- [Final audit and SHA-256 inventory](../runs/m2-acceptance.json) covers every comparison artifact, observed engine-side balance and current source hashes. The run directories occupy about 22.96 MB and 15.79 MB, including separate journals and engine evidence.

Both complete saved-log audits passed: 1,377 and 1,050 snapshot/choice/label records, plus 24 terminal rows each. Original run manifests remain unchanged. After the comparisons, only reporting and launcher utilities changed: `reporting.py` added warning/interval/schedule reporting; `environment.py` and `cli.py` corrected the separate-server log location. The policy, adapter, schema, runner, label logic, team and config hashes still match both comparison manifests. Final integration tests cover the launcher correction. Documentation changes are outside the source manifest.

## Ambiguity, warnings and observed performance

In random-comparison match index 20, decision `m20:a:r78` at turn 34 offered Hyper Beam with `maybeLocked`; the engine committed `move fight` during Clamp. That mismatch invalidates seven decisions in that side's remaining sequence. They remain unknown with `engine_choice_or_sequence_mismatch`; the recorder does not guess how to resynchronize. Eleven decisions have unknown binary eligibility in total, including uncertain request flags. Coverage is reported over both players' attempts; paired targets are a smaller, explicitly filtered set.

Eight wrapper warning records describe four repeated Clamp announcements seen by both clients. Poke-env 0.16.1 strips the unsupported trailing `[from] Clamp` annotation. The independent public projection and current engine requests still provide the fields used here. Warnings remain in `events.jsonl`; none were suppressed or counted as invalid actions. Broad Gen 1 state-tracking correctness is not claimed.

The heuristic's advantage is plausible against these weak rules, but the run is not an ablation of its components. Against MaxBasePower, the heuristic selected self-KO moves 5 times versus 35 for MaxBasePower. Its type-aware attack utility and self-KO penalty avoid some obvious baseline behavior; this observation alone does not establish which term caused wins.

The two losses occurred at zero-based match indices 4 and 13. In match 4, the heuristic's team v1-a lost to v2-c in 24 turns; its Alakazam's Psychic left the opposing Tauros at publicly displayed 54/100 before Hyper Beam knocked Alakazam out. In match 13, v2-c lost to v1-b in 22 turns; repeated Fight requests and public freeze prevention constrained late actions, ending with a frozen Chansey. These logs show limits of the fixed utility rules; they do not justify attributing the whole losses to one event or tuning after the comparison.

## Tests and retained earlier attempts

Final checks: **49 offline unit tests passed** and **7 explicitly selected integration tests passed**. Integration includes complete baseline games, expanded-team games, real cap/timeout accounting, engine request probes, the authoritative commitment/unexecuted-move scenario, and separate-server evidence copying. Unit tests exercise hidden-state isolation, frozen/raw-HP preservation, reproducible randomness, mapping/fallbacks, Gen 1 type/recovery/status/switch rules, label pairing, forced/voluntary choices, missing/mismatched commitments, execution evidence and balanced schedules.

Latest integration artifacts include `runs/integration-1037044b41`, `runs/integration-truncated-66375a9b6d`, `runs/integration-timeout-ca7dcd1f48`, `runs/integration-m2-11ff7283ca`, and `runs/integration-separate-dce0910d19`. Caps and timeouts in these tests are intentional and contribute zero wins.

Earlier diagnostic attempts remain visible:

| Artifact | Actual outcome / discovered defect |
|---|---|
| `runs/m2-label-probe` | Four games completed, heuristic 2–2, 220 attempts, zero verified labels. Three server logging-directory `CRASH:` reports and a filename lookup error made this fail data acceptance despite completed games. Both defects were fixed. |
| `runs/m2-label-probe-fixed` | Two games completed, heuristic 2–0, 86 verified commitments; all execution fields were still unknown because JSON lists did not equal in-memory tuples during prefix checks. Serialization normalization was fixed before comparisons. |
| Earlier `runs/integration-*` | Retained real smoke/limit tests, including a check that initially rejected the newly observed Clamp warning until its source and supported-field impact were investigated. |

These early probes predate the final label schema and are not pooled with comparison results or presented as final audit passes. The original M1 runs remain intact too.

## Commands actually executed

From the project root in PowerShell; use new output paths for another run:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m battlemind doctor --start-server --config configs/milestone2.json > runs/m2-doctor.json
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m integration
.\.venv\Scripts\python.exe -m pytest -q -m integration -k separate_server
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/milestone2.json --agent-b random --output runs/m2-comparison-random
.\.venv\Scripts\python.exe -m battlemind battle --start-server --config configs/milestone2.json --agent-b max-base-power --output runs/m2-comparison-max-base-power
.\.venv\Scripts\python.exe -m battlemind report --run runs/m2-comparison-random --audit
.\.venv\Scripts\python.exe -m battlemind report --run runs/m2-comparison-max-base-power --audit
```

A local Python audit also ran `tests.test_integration.audit_run` and `labels.audit_labels` on both comparisons, checked actual p1/p2 balance and matching critical source hashes, and wrote the content inventory at `runs/m2-acceptance.json`. The full integration suite was rerun after the separate-server correction: seven passed in 27.69 seconds. No Git repository exists at the project root; no commit, push or deployment was made.

## Remaining limitations and single next milestone

Only the pinned Windows runtime, `gen1ou`, concurrency 1 and this restricted pool are verified. Effective stats, counters, trapping duration, hidden moves and other unsupported quantities remain unknown. Heuristic scores are approximations and can make poor choices. Missing end logs or normalization mismatches reduce label coverage; eligibility exclusions introduce selection bias. Public move announcements establish observation, not permanent moveset membership or successful execution. Manual-server identity is not independently attested, custom external log paths are unsupported, and external-server resources are unmeasured. No exact replay determinism or ready-to-train dataset is claimed.

**Next: Milestone 3 — a small opponent predictor.** Build a leakage-safe dataset from verified observer-to-label joins, split by whole battle, and compare frequency counts with a small switch-versus-move classifier using class balance, Brier score/log loss and held-out evaluation. Keep connecting predictions to action scores for Milestone 4.
