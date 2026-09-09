"""Read-only evaluation of policy learning, separate from proposal/update code."""

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import random

from .environment import sha256, source_manifest
from .labels import read_jsonl
from .learned_policy import LearnedScoreAgent, PolicyParameters, load_checkpoint
from .policy_search import complete_objective, outcome_update, propose, select_checkpoint
from .prediction_report import audit_predictions
from .reporting import summarize, wilson_interval
from .schema import snapshot_from_dict
from .supervised_data import load_bundle


def terminal_metrics(rows: list[dict], requested: int) -> dict:
    # Match indices are local to runs; assign independent accounting indices here.
    result = summarize([{**b, "match": i} for i, b in enumerate(rows)], requested)
    result["mean_terminal_reward"] = ((result["a_wins"] + result["draws"] / 2) / result["completed"]
                                       if result["completed"] else None)
    result["win_wilson_95"] = wilson_interval(result["a_wins"], result["completed"])
    return result


def final_intervals(arms: dict, seed: int = 51901) -> dict:
    if set(arms) != {"initial", "selected"} or set(arms["initial"]) != set(arms["selected"]):
        return {"available": False, "reason": "incomplete final schedule"}
    for groups in arms.values():
        for rows in groups.values():
            if len(rows) != 24 or any(r["status"] != "completed" for r in rows):
                return {"available": False, "reason": "incomplete final block"}
    if not arms["initial"]:
        return {"available": False, "reason": "no final games"}
    def block_difference(opponent, index):
        blocks = {arm: arms[arm][opponent][4 * index:4 * index + 4] for arm in arms}
        reward = {a: sum(1 if r["winner"] == "a" else 0.5 if r["winner"] == "draw" else 0 for r in b) for a, b in blocks.items()}
        wins = {a: sum(r["winner"] == "a" for r in b) for a, b in blocks.items()}
        return reward["selected"] - reward["initial"], wins["selected"] - wins["initial"]
    blocks = {op: [block_difference(op, i) for i in range(6)] for op in sorted(arms["initial"])}
    denominator = len(blocks) * 24
    point = [sum(v[i] for group in blocks.values() for v in group) / denominator for i in (0, 1)]
    rng = random.Random(seed)
    samples = [[], []]
    for _ in range(1000):
        sampled = [group[i] for group in blocks.values() for i in rng.choices(range(6), k=6)]
        for i in (0, 1):
            samples[i].append(sum(v[i] for v in sampled) / denominator)
    return {"available": True, "resamples": 1000, "seed": seed, "games_per_arm": denominator,
        "difference": "selected minus initial; positive favors selected",
        "scope": "resampled four-game team-pair blocks within fixed opponents, same schedule block indices across arms; not matched engine RNG/trajectories",
        "point": dict(zip(("mean_reward", "win_rate"), point)),
        "interval_95": {name: [sorted(values)[24], sorted(values)[974]] for name, values in zip(("mean_reward", "win_rate"), samples)}}


def experiment_report(root: Path, write_choices: bool = False) -> dict:
    ledger = json.loads((root / "ledger.json").read_text())
    phases, arms, summaries = {}, {}, []
    for phase in ("training", "selection", "final"):
        records = [r for r in ledger["runs"] if r["phase"] == phase]
        rows = []
        for record in records:
            path = root / record["path"]
            battles = read_jsonl(path / "battles.jsonl") if (path / "battles.jsonl").exists() else []
            rows.extend(battles)
            if record.get("summary"):
                summaries.append(record["summary"])
            if phase == "final":
                arm = path.name.split("-vs-")[0]
                arms.setdefault(arm, {})[record["opponent"]["identity"]] = battles
        phases[phase] = {**ledger["phases"][phase], **terminal_metrics(rows, sum(r["requested_games"] for r in records))}
    counts = Counter()
    for summary in summaries:
        for key in ("known_gen1_annotation_warnings", "unexpected_client_warning_records", "client_warning_records", "server_crash_reports"):
            counts[key] += summary.get(key) or 0
        for key in ("attempts", "verified_intended_choices", "unknown_intended_choices", "paired_opponent_targets", "eligibility_unknown"):
            counts["labels_" + key] += summary.get("labels", {}).get(key, 0)
    resources = {"python_cpu_seconds": sum(s["resources"]["python_cpu_seconds"] for s in summaries),
        "server_cpu_seconds_last_samples": sum(s["resources"]["managed_server_cpu_seconds_last_sample"] or 0 for s in summaries),
        "python_peak_sampled_rss_bytes": max((s["resources"]["python_peak_sampled_rss_bytes"] for s in summaries), default=0),
        "server_peak_sampled_rss_bytes": max((s["resources"]["managed_server_peak_sampled_rss_bytes"] or 0 for s in summaries), default=0)}
    choice_comparison = {"decisions": 0, "different_choices": 0, "by_played_arm": {}}
    if (root / "selected.json").exists():
        _, predictor = load_bundle(root / "predictor.json")
        initial = load_checkpoint(root / "checkpoints/c0.json", predictor)[1]
        selected = load_checkpoint(root / "selected.json", predictor)[1]
        policies = {"initial": LearnedScoreAgent(predictor, initial), "selected": LearnedScoreAgent(predictor, selected)}
        comparisons = []
        for record in ledger["runs"]:
            if record["phase"] != "final" or not (root / record["path"] / "decisions.jsonl").exists():
                continue
            arm = Path(record["path"]).name.split("-vs-")[0]
            counts_for_arm = choice_comparison["by_played_arm"].setdefault(arm, {"decisions": 0, "different_choices": 0})
            for row in read_jsonl(root / record["path"] / "decisions.jsonl"):
                if row["player"] != "a":
                    continue
                obs = snapshot_from_dict(row["observation"])
                choices = {name: policy.choose(obs) for name, policy in policies.items()}
                different = choices["initial"] != choices["selected"]
                choice_comparison["decisions"] += 1
                choice_comparison["different_choices"] += different
                counts_for_arm["decisions"] += 1
                counts_for_arm["different_choices"] += different
                comparisons.append({"run_id": record["run_id"], "decision_id": row["decision_id"],
                    "snapshot_sha256": row["snapshot_sha256"], "played_arm": arm, "choices": choices})
        if write_choices:
            with (root / "decision-comparisons.jsonl").open("x", encoding="utf-8") as file:
                for row in comparisons:
                    file.write(json.dumps(row, separators=(",", ":")) + "\n")
        choice_comparison["initial_sha256"] = initial.sha256
        choice_comparison["selected_sha256"] = selected.sha256
        choice_comparison["identical_parameter_vectors"] = initial.parameters == selected.parameters
    updates = [json.loads(p.read_text()) for p in sorted((root / "rounds").glob("update-*.json"))]
    selection = json.loads((root / "selection.json").read_text()) if (root / "selection.json").exists() else None
    return {"schema_version": "v5-report-1", "ledger_status": ledger["status"], "failure": ledger["failure"],
        "planned_games": ledger["total_game_allocation"], "requested_games": ledger["requested_games"],
        "completed_games": sum(p["completed"] for p in phases.values()), "phases": phases, "updates": updates,
        "selection": selection, "final": {arm: {"overall": terminal_metrics([r for rows in groups.values() for r in rows], len(groups) * 24),
            "by_opponent": {op: terminal_metrics(rows, 24) for op, rows in groups.items()}} for arm, groups in arms.items()},
        "final_uncertainty": final_intervals(arms), "choice_comparison": choice_comparison,
        "warning_and_label_counts": dict(counts), "resources": resources,
        "total_wall_seconds": ledger["consumed_wall_seconds"], "predictor_sha256": sha256(root / "predictor.json")}


def audit_experiment(root: Path) -> dict:
    root = root.resolve()  # Stored opponent paths are absolute, including for CLI-relative runs.
    ledger = json.loads((root / "ledger.json").read_text())
    freeze = json.loads((root / "freeze.json").read_text())
    from .learning import CONFIG, SPEC
    if sha256(CONFIG) != freeze["configuration_sha256"] or sha256(SPEC) != freeze["spec_sha256"]:
        raise ValueError("Experiment configuration or specification changed")
    if source_manifest() != freeze["code_sha256"] or sha256(root / "predictor.json") != freeze["predictor_sha256"]:
        raise ValueError("Experiment source or predictor hash changed")
    _, predictor = load_bundle(root / "predictor.json")
    partitions, by_path, audits = {}, {}, []
    for record in ledger["runs"]:
        path = root / record["path"]
        if record["status"] != "recorded":
            if ledger["status"] == "finished":
                raise ValueError("Finished experiment has an unrecorded run")
            continue
        metadata = json.loads((path / "run.json").read_text())
        run_id = sha256(path / "run.json")
        if (run_id != record["run_id"] or metadata["config"]["seed"] != record["policy_seed"]
            or metadata["config"]["teams"] != freeze["configuration"]["teams"]
            or metadata["predictor"]["sha256"] != predictor.sha256
            or metadata["policies"]["a"]["name"] != "learned-score"
            or metadata["policies"]["b"]["name"] != record["opponent"]["policy"]
            or metadata["policy_checkpoints"]["a"]["sha256"] != record["candidate_sha256"]
            or sha256(root / record["candidate"]) != record["candidate_sha256"]):
            raise ValueError("Run schedule/checkpoint provenance mismatch")
        if record["opponent"]["checkpoint"] and metadata["policy_checkpoints"]["b"]["sha256"] != record["opponent"]["checkpoint_sha256"]:
            raise ValueError("Frozen training/evaluation opponent changed")
        audits.append(audit_predictions(path))
        rows = read_jsonl(path / "battles.jsonl")
        by_path[record["path"]] = (record, rows)
        for row in rows:
            key = f"{run_id}:{row['match']}"
            if key in partitions:
                raise ValueError("Battle split overlap")
            partitions[key] = record["phase"]
    if partitions != ledger["battle_partitions"]:
        raise ValueError("Recorded battle partitions disagree")

    def evidence(paths, phase):
        result = []
        if len(set(paths)) != len(paths):
            raise ValueError("Duplicate outcome sources")
        for path in paths:
            record, rows = by_path[path]
            if record["phase"] != phase:
                raise ValueError("Learning/selection evidence crossed a phase boundary")
            result.extend(rows)
        return result

    _, initial = load_checkpoint(root / "checkpoints/c0.json", predictor)
    if initial.parameters != PolicyParameters():
        raise ValueError("Initialization is not the declared V4-equivalent control")
    update_count, changed = 0, 0
    for path in sorted((root / "rounds").glob("update-*.json")):
        saved = json.loads(path.read_text())
        number = saved["round"]
        if number not in {1, 2}:
            raise ValueError("Undeclared training round")
        from .learning import frozen_opponents
        expected_pool = frozen_opponents({name: root / f"checkpoints/{name}.json" for name in ("c0", "c1")}, number)
        if [asdict(opponent) for opponent in expected_pool] != saved["opponents"]:
            raise ValueError("Training pool differs from declared admission schedule")
        _, parent = load_checkpoint(root / f"checkpoints/c{number - 1}.json", predictor)
        proposal = propose(parent.parameters, freeze["configuration"]["proposal_seed_base"] + number)
        if json.loads(json.dumps(asdict(proposal))) != saved["proposal"] or saved["parent_sha256"] != parent.sha256:
            raise ValueError("Candidate proposal/seed/parent differs")
        plus, minus = [evidence(saved["runs"][sign], "training") for sign in ("plus", "minus")]
        params, rebuilt = outcome_update(proposal, plus, minus, len(saved["opponents"]) * 24)
        if any(saved[k] != v for k, v in rebuilt.items()):
            raise ValueError("Update does not match actual completed outcomes")
        _, checkpoint = load_checkpoint(root / saved["checkpoint"], predictor)
        if checkpoint.parameters != params or checkpoint.sha256 != saved["checkpoint_sha256"]:
            raise ValueError("Updated checkpoint parameters/hash mismatch")
        for sign in ("plus", "minus"):
            _, candidate = load_checkpoint(root / f"checkpoints/round-{number}-{sign}.json", predictor)
            if candidate.parameters != getattr(proposal, sign):
                raise ValueError("Played proposal parameters differ")
            played = [by_path[p][0] for p in saved["runs"][sign]]
            if [r["opponent"] for r in played] != saved["opponents"] or any(r["candidate_sha256"] != candidate.sha256 for r in played):
                raise ValueError("Opponent pool/candidate changed inside a comparison")
        update_count += 1
        changed += rebuilt["changed"]
    if (root / "selection.json").exists():
        selection = json.loads((root / "selection.json").read_text())
        if [r["checkpoint"] for r in selection["candidates"]] != ["c0", "c1", "c2"]:
            raise ValueError("Undeclared selection candidate set/order")
        entries = []
        for entry in selection["candidates"]:
            _, cp = load_checkpoint(root / f"checkpoints/{entry['checkpoint']}.json", predictor)
            objective = complete_objective(evidence(entry["runs"], "selection"), 72)
            if cp.sha256 != entry["checkpoint_sha256"] or objective != entry["objective"]:
                raise ValueError("Selection checkpoint/outcome evidence mismatch")
            entries.append((entry["checkpoint"], cp.parameters, objective))
        if select_checkpoint(entries) != selection["chosen"] or sha256(root / "selected.json") != selection["chosen_sha256"]:
            raise ValueError("Selection violates the declared tie/score rule")
        final = json.loads((root / "final-freeze.json").read_text()) if (root / "final-freeze.json").exists() else None
        if final and (final["selected_sha256"] != selection["chosen_sha256"] or final["initial_sha256"] != initial.sha256
                      or final["selection_sha256"] != sha256(root / "selection.json")):
            raise ValueError("Final checkpoint freeze mismatch")
        if final:
            if [op["identity"] for op in final["opponents"]] != freeze["final_opponents"]:
                raise ValueError("Final opponent panel changed")
            for record in ledger["runs"]:
                if record["phase"] != "final":
                    continue
                arm = Path(record["path"]).name.split("-vs-")[0]
                if (arm not in {"initial", "selected"} or record["candidate_sha256"] != final[arm + "_sha256"]
                    or record["opponent"] not in final["opponents"]
                    or record["policy_seed"] != freeze["configuration"]["final_seed"]):
                    raise ValueError("Final run differs from frozen selection/panel")
    if ledger["requested_games"] > ledger["total_game_allocation"] or ledger["total_game_allocation"] > 1200:
        raise ValueError("Aggregate game budget exceeded")
    for phase, allocation in ledger["phases"].items():
        if allocation["requested_games"] > allocation["game_allocation"]:
            raise ValueError("Reserved phase game budget exceeded")
        if allocation["requested_games"] != sum(r["requested_games"] for r in ledger["runs"] if r["phase"] == phase):
            raise ValueError("Run and phase budget accounting mismatch")
        if ledger["status"] == "finished" and (allocation["status"] != "finished"
            or allocation["requested_games"] != allocation["game_allocation"]
            or allocation["consumed_wall_seconds"] > allocation["wall_allocation"]):
            raise ValueError("Finished experiment has incomplete/exceeded phase budget")
    if ledger["requested_games"] != sum(r["requested_games"] for r in ledger["runs"]):
        raise ValueError("Aggregate requested-game accounting mismatch")
    hashes = json.loads((root / "artifact-hashes.json").read_text()) if (root / "artifact-hashes.json").exists() else {}
    if any(sha256(root / name) != digest for name, digest in hashes.items()):
        raise ValueError("Experiment artifact hash mismatch")
    return {"ok": True, "runs": len(audits), "battles": len(partitions), "decisions": sum(a["decisions"] for a in audits),
        "rebuilt_updates": update_count, "nonzero_updates": changed, "overlapping_battles": 0,
        "checked_artifact_files": len(hashes), "predictor_unchanged": True}
