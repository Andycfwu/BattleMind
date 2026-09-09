"""V4 features on top of the existing audited observer-to-intended-label join."""

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

from .dataset import balance, build_dataset, read_dataset, write_json
from .environment import sha256, source_manifest
from .labels import read_jsonl
from .prediction import FEATURE_DEFINITIONS as COUNT_FEATURES, table_from_dict
from .schema import snapshot_from_dict
from .supervised import (FEATURE_VERSION, FEATURE_DEFINITIONS, PredictorBundle,
                         features_from_dict, features_from_snapshot, model_from_dict)


def build_supervised_dataset(runs: list[Path], output: Path, seed: int = 20260909,
                             role: str = "development") -> dict:
    if output.exists():
        raise ValueError("Supervised dataset output must be fresh")
    # This path performs the established full engine/attempt/observer-label audit.
    context_path = output / "audited-context"
    base = build_dataset(runs, context_path, seed, role)
    _, joined = read_dataset(context_path)
    by_run = {}
    for source in base["sources"]:
        root = Path(source["path"])
        for name, digest in source["hashes"].items():
            if sha256(root / name) != digest:
                raise ValueError("Source changed after label audit")
        by_run[source["run_id"]] = ({r["decision_id"]: r for r in read_jsonl(root / "decisions.jsonl")}, source["policy_names"])
    rows = []
    for row in joined:
        decisions, policies = by_run[row["run_id"]]
        observer = decisions[row["observer_decision_id"]]
        target = decisions[row["target_decision_id"]]
        # Crucially, no target snapshot or offline eligibility enters this function.
        features = features_from_snapshot(snapshot_from_dict(observer["observation"]))
        rows.append({**row, "features": asdict(features), "target_player": target["player"],
                     "observer_policy": policies[observer["player"]]})
    with (output / "examples.jsonl").open("x", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
    exclusions = []
    for row in read_jsonl(context_path / "exclusions.jsonl"):
        decisions, policies = by_run[row["run_id"]]
        target = decisions[row["target_decision_id"]]
        exclusions.append({**row, "target_player": target["player"], "target_policy": policies[target["player"]]})
    with (output / "exclusions.jsonl").open("x", encoding="utf-8") as file:
        for row in exclusions:
            file.write(json.dumps(row, separators=(",", ":")) + "\n")
    selected = [r for r in rows if r["target_player"] == "b"]
    manifest = {**base, "schema_version": "v4-dataset-1", "feature_version": FEATURE_VERSION,
        "feature_definitions": FEATURE_DEFINITIONS, "examples_sha256": sha256(output / "examples.jsonl"),
        "exclusions_sha256": sha256(output / "exclusions.jsonl"), "code_sha256": source_manifest(),
        "audited_context_manifest_sha256": sha256(context_path / "manifest.json"),
        "primary_population": "eligible intended choices of runner player b; identities used only offline",
        "primary_balance": {p: balance([r for r in selected if r["partition"] == p]) for p in sorted(set(base["battle_partitions"].values()))},
        "primary_by_policy": {p: balance([r for r in selected if r["target_policy"] == p]) for p in sorted({r["target_policy"] for r in selected})},
        "non_primary_eligible_examples": len(rows) - len(selected),
        "primary_exclusions_by_partition": {p: dict(Counter(r["reason"] for r in exclusions
            if r["target_player"] == "b" and r["partition"] == p)) for p in sorted(set(base["battle_partitions"].values()))},
        "claim_scope": "local recorded battles; whole-battle development split or fresh fixed-mixture evaluation; no arbitrary replay support"}
    write_json(output / "manifest.json", manifest)
    return manifest


def read_supervised_dataset(path: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((path / "manifest.json").read_text())
    if (manifest["schema_version"] != "v4-dataset-1" or manifest["feature_version"] != FEATURE_VERSION
        or manifest["feature_definitions"] != FEATURE_DEFINITIONS):
        raise ValueError("Incompatible supervised dataset features/schema")
    parts = manifest["battle_partitions"]
    allowed = {"development_fit", "development_check"} if manifest["role"] == "development" else {"evaluation"}
    if manifest["role"] not in {"development", "evaluation"} or not set(parts.values()) <= allowed:
        raise ValueError("Invalid supervised dataset partitions")
    if sha256(path / "audited-context/manifest.json") != manifest["audited_context_manifest_sha256"]:
        raise ValueError("Audited join manifest hash mismatch")
    base, joined = read_dataset(path / "audited-context")
    if base["battle_partitions"] != parts or base["sources"] != manifest["sources"]:
        raise ValueError("Supervised split/source differs from audited join")
    for name in ("examples", "exclusions"):
        if manifest[f"{name}_sha256"] != sha256(path / f"{name}.jsonl"):
            raise ValueError("Supervised dataset content hash mismatch")
    rows = read_jsonl(path / "examples.jsonl")
    if len(rows) != len(joined):
        raise ValueError("Supervised dataset lost joined rows")
    for row, original in zip(rows, joined):
        if any(row[k] != v for k, v in original.items() if k != "features"):
            raise ValueError("Supervised example alignment changed")
        if (row["battle_key"] != f"{row['run_id']}:{row['match']}" or row["partition"] != parts[row["battle_key"]]
            or row["target_player"] not in {"a", "b"}):
            raise ValueError("Battle identity/partition mismatch")
        if ("target_request_id" in row and row["target_decision_id"] !=
            f"m{row['match']}:{row['target_player']}:r{row['target_request_id']}"):
            raise ValueError("Target player identity differs from audited decision")
        source = next((s for s in manifest["sources"] if s["run_id"] == row["run_id"]), None)
        if source and row["observer_policy"] != source["policy_names"]["a" if row["target_player"] == "b" else "b"]:
            raise ValueError("Observer grouping metadata mismatch")
        features = features_from_dict(row["features"])
        if asdict(features.context) != original["features"]:
            raise ValueError("V3/V4 visible contexts disagree")
    excluded = read_jsonl(path / "exclusions.jsonl")
    original_excluded = read_jsonl(path / "audited-context/exclusions.jsonl")
    if len(excluded) != len(original_excluded) or any(any(row[k] != v for k, v in original.items())
        for row, original in zip(excluded, original_excluded)):
        raise ValueError("Exclusion records differ from audited join")
    if dict(Counter(r["reason"] for r in excluded)) != manifest["exclusions"]:
        raise ValueError("Exclusion accounting mismatch")
    return manifest, rows


def load_bundle(path: Path) -> tuple[dict, PredictorBundle]:
    # Plain JSON only: no pickle, executable payloads or dynamic imports from models.
    artifact = json.loads(path.read_text())
    if (artifact["schema_version"] != "v4-supervised-1" or artifact["frozen"] is not True
        or artifact["feature_version"] != FEATURE_VERSION or artifact["feature_definitions"] != FEATURE_DEFINITIONS
        or artifact["count_feature_definitions"] != COUNT_FEATURES or artifact["target_player"] != "b"):
        raise ValueError("Incompatible/unfrozen supervised artifact")
    train, validation, development = [artifact[name] for name in ("fit_battle_keys", "validation_battle_keys", "development_battle_keys")]
    if (len(set(train)) != len(train) or len(set(validation)) != len(validation)
        or len(set(development)) != len(development) or set(train) & set(validation)
        or set(train) | set(validation) != set(development)):
        raise ValueError("Artifact development split overlap/inconsistency")
    model = model_from_dict(artifact["logistic"])
    if list(model.preprocessing.columns) != artifact["columns"]:
        raise ValueError("Artifact encoded column mismatch")
    table = table_from_dict(artifact["table"])
    if (table.examples != artifact["fit_balance"]["examples"] or table.switches != artifact["fit_balance"]["switches"]
        or model.regularization != artifact["selection"]["selected_regularization"]):
        raise ValueError("Artifact training provenance mismatch")
    return artifact, PredictorBundle(table, model, sha256(path))
