"""Offline audited observer joins. Privileged labels determine targets/eligibility only."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .environment import sha256, source_manifest
from .labels import audit_labels, read_jsonl, snapshot_hash
from .prediction import FEATURE_DEFINITIONS, FEATURE_VERSION, Context, CountTable, estimate_counts, table_from_dict
from .schema import snapshot_from_dict
from .prediction import context_from_snapshot


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        json.dump(data, file, indent=2, allow_nan=False)
        file.write("\n")


def exclusion_reason(label: dict) -> str | None:
    if label["match_status"] != "completed":
        return "incomplete_battle"
    if label["commit_status"] != "verified":
        return "unknown_commitment:" + str(label["unknown_reason"])
    if label["intended_kind"] == "forced_replacement":
        return "forced_replacement"
    if label["intended_kind"] == "engine_action":
        return "engine_mandated_action"
    if label["genuine_switch_move_choice"] is None:
        return "unknown_choice_eligibility"
    if label["genuine_switch_move_choice"] is not True:
        return "no_meaningful_move_switch_choice"
    if label["voluntary_switch_target"] not in {0, 1} or label["intended_kind"] not in {"voluntary_switch", "move_choice"}:
        return "unknown_binary_target"
    if label["observer_decision_id"] is None:
        return "no_verified_observer_join"
    return None


def joined_examples(run_id: str, decisions: list[dict], labels: list[dict], battles: list[dict],
                    policy_names: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Inputs must first pass audit_labels; explicit alignment checks guard the feature join."""
    by_id = {r["decision_id"]: r for r in decisions}
    terminal = {r["match"]: r for r in battles}
    examples, excluded = [], []
    for label in labels:
        identity = {"run_id": run_id, "battle_key": f"{run_id}:{label['match']}", "match": label["match"],
                    "target_decision_id": label["decision_id"]}
        if label["match"] not in terminal or terminal[label["match"]]["status"] != label["match_status"]:
            raise ValueError("Label/terminal alignment mismatch")
        reason = exclusion_reason(label)
        if reason:
            excluded.append({**identity, "reason": reason})
            continue
        target = by_id[label["decision_id"]]
        observer = by_id[label["observer_decision_id"]]
        obs = observer["observation"]
        if (observer["match"] != label["match"] or observer["player"] == label["player"]
            or obs["turn"] != label["turn"] or obs["request_kind"] != "move"
            or target["observation"]["request_id"] != label["request_id"]
            or snapshot_hash(obs) != label["observer_snapshot_sha256"]
            or snapshot_hash(target["observation"]) != label["snapshot_sha256"]
            or label["voluntary_switch_target"] != int(label["intended_kind"] == "voluntary_switch")):
            raise ValueError("Observer-to-label alignment mismatch")
        # The only feature function input is the OBSERVER's frozen pre-decision snapshot.
        context = context_from_snapshot(snapshot_from_dict(obs))
        examples.append({**identity, "observer_decision_id": observer["decision_id"],
            "observer_snapshot_sha256": label["observer_snapshot_sha256"], "observer_request_id": obs["request_id"],
            "target_request_id": label["request_id"], "target_policy": policy_names[label["player"]],
            "features": asdict(context), "target": label["voluntary_switch_target"]})
    return examples, excluded


def split_battles(run_battles: dict[str, list[int]], seed: int, role: str) -> dict[str, str]:
    if role not in {"development", "evaluation"}:
        raise ValueError("Dataset role must be development or evaluation")
    result = {}
    for run_id, matches in sorted(run_battles.items()):
        if len(set(matches)) != len(matches):
            raise ValueError("Duplicate match in run")
        keys = [f"{run_id}:{match}" for match in matches]
        ordered = sorted(keys, key=lambda key: hashlib.sha256(f"{seed}:{key}".encode()).hexdigest())
        fit_count = int(0.75 * len(ordered))
        for i, key in enumerate(ordered):
            result[key] = "evaluation" if role == "evaluation" else "development_fit" if i < fit_count else "development_check"
    return result


def balance(rows: list[dict]) -> dict:
    battles = {r["battle_key"] for r in rows}
    switches = sum(r["target"] for r in rows)
    return {"examples": len(rows), "battles_with_examples": len(battles), "switches": switches,
        "moves": len(rows) - switches, "switch_fraction": switches / len(rows) if rows else None,
        "battles_with_switches": len({r["battle_key"] for r in rows if r["target"] == 1})}


def build_dataset(runs: list[Path], output: Path, seed: int = 2026, role: str = "development") -> dict:
    if not runs or len(runs) > 12:
        raise ValueError("Supply 1..12 bounded source runs")
    if output.exists():
        raise ValueError("Dataset output must be a fresh directory")
    examples, excluded, sources, run_battles = [], [], [], {}
    for run in runs:
        run = run.resolve()
        run_id = sha256(run / "run.json")  # includes original timestamp; survives moving/copying the run
        if run_id in run_battles:
            raise ValueError("Duplicate run identity; copying a run cannot create independent battles")
        audit = audit_labels(run)
        decisions, labels, battles = [read_jsonl(run / p) for p in ("decisions.jsonl", "privileged/labels.jsonl", "battles.jsonl")]
        metadata = json.loads((run / "run.json").read_text())
        policy_names = {s: metadata["policies"][s]["name"] for s in ("a", "b")}
        if sum(b.get("decisions", 0) for b in battles) != len(decisions):
            raise ValueError("Terminal decision counts disagree")
        rows, missing = joined_examples(run_id, decisions, labels, battles, policy_names)
        examples.extend(rows)
        excluded.extend(missing)
        run_battles[run_id] = [b["match"] for b in battles]
        files = [run / p for p in ("run.json", "decisions.jsonl", "events.jsonl", "battles.jsonl", "privileged/labels.jsonl")]
        for battle in battles:
            if battle.get("engine_record"):
                files.append(run / battle["engine_record"]["path"])
            history = run / "privileged" / f"{battle['match']:03d}-histories.json"
            if history.exists():
                files.append(history)
        sources.append({"path": str(run), "run_id": run_id, "audit": audit,
            "hashes": {p.relative_to(run).as_posix(): sha256(p) for p in sorted(set(files))},
            "label_coverage": sum(l["commit_status"] == "verified" for l in labels) / len(labels) if labels else None,
            "label_attempts": len(labels), "policy_names": policy_names})
    partitions = split_battles(run_battles, seed, role)
    for row in examples + excluded:
        row["partition"] = partitions[row["battle_key"]]
    output.mkdir(parents=True)
    for name, rows in (("examples", examples), ("exclusions", excluded)):
        with (output / f"{name}.jsonl").open("x", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
    manifest = {"schema_version": "v3-dataset-1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": role, "seed": seed, "feature_version": FEATURE_VERSION, "feature_definitions": FEATURE_DEFINITIONS,
        "split_rule": "whole battles; SHA256(seed:run_id:match) order per run; first floor(75%) development_fit; remainder development_check; evaluation role uses all battles",
        "claim_scope": "reported M2 records are development evidence, including development_check; fresh evaluation is restricted-pool only",
        "sources": sources, "battle_partitions": partitions, "code_sha256": source_manifest(),
        "examples_sha256": sha256(output / "examples.jsonl"), "exclusions_sha256": sha256(output / "exclusions.jsonl"),
        "balance": {part: balance([r for r in examples if r["partition"] == part]) for part in sorted(set(partitions.values()))},
        "exclusions": dict(Counter(r["reason"] for r in excluded)), "excluded_count": len(excluded),
        "eligibility_scope": "privileged post-battle eligibility is used only for labels/evaluation, never an online feature"}
    write_json(output / "manifest.json", manifest)
    return manifest


def read_dataset(path: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest["feature_version"] != FEATURE_VERSION or manifest["feature_definitions"] != FEATURE_DEFINITIONS:
        raise ValueError("Dataset feature definitions changed")
    for name in ("examples", "exclusions"):
        if manifest[f"{name}_sha256"] != sha256(path / f"{name}.jsonl"):
            raise ValueError("Dataset content hash mismatch")
    rows = read_jsonl(path / "examples.jsonl")
    identities = set()
    for row in rows:
        if row["partition"] != manifest["battle_partitions"][row["battle_key"]]:
            raise ValueError("Battle split mismatch")
        identity = (row["run_id"], row["target_decision_id"])
        if identity in identities:
            raise ValueError("Duplicate dataset example")
        identities.add(identity)
        Context(**row["features"])
        if type(row["target"]) is not int or row["target"] not in {0, 1}:
            raise ValueError("Invalid binary target")
    return manifest, rows


def fit_predictor(dataset: Path, output: Path) -> dict:
    manifest, rows = read_dataset(dataset)
    if manifest["role"] != "development":
        raise ValueError("Counts may be estimated only from a designated development dataset")
    fit = [r for r in rows if r["partition"] == "development_fit"]
    table = estimate_counts((Context(**r["features"]), r["target"]) for r in fit)
    artifact = {"schema_version": "v3-counts-1", "table": asdict(table), "feature_definitions": FEATURE_DEFINITIONS,
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"), "dataset_path": str(dataset.resolve()),
        "fit_battle_keys": sorted(k for k, p in manifest["battle_partitions"].items() if p == "development_fit"),
        "development_battle_keys": sorted(manifest["battle_partitions"]), "fit_balance": balance(fit),
        "code_sha256": source_manifest(), "frozen": True,
        "estimation": "Beta(1,1) global frequency; conditional cells shrink toward global with strength 12; fewer than 5 examples fall back to global"}
    write_json(output, artifact)
    return artifact


def load_predictor(path: Path):
    artifact = json.loads(path.read_text())
    if artifact["schema_version"] == "v4-supervised-1":
        from .supervised_data import load_bundle
        return load_bundle(path)
    if artifact["schema_version"] != "v3-counts-1" or artifact["feature_definitions"] != FEATURE_DEFINITIONS or artifact["frozen"] is not True:
        raise ValueError("Unsupported or unfrozen predictor artifact")
    return artifact, table_from_dict(artifact["table"])
