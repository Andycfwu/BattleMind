"""Frozen probability comparison on identical eligible observer examples."""

from dataclasses import asdict
import json
from pathlib import Path

from .dataset import balance, write_json
from .environment import sha256, source_manifest
from .labels import read_jsonl
from .prediction import CountPredictor
from .prediction_report import paired_battle_interval, probability_metrics
from .supervised import features_from_dict
from .supervised_data import load_bundle, read_supervised_dataset

MODES = ("constant", "conditional", "logistic")


def check_evaluation_partition(manifest: dict, artifact: dict, partition: str) -> None:
    if partition not in {"development_check", "evaluation"} or (partition == "evaluation") != (manifest["role"] == "evaluation"):
        raise ValueError("Invalid evaluation partition/role")
    forbidden = set(artifact["development_battle_keys"] if partition == "evaluation" else artifact["fit_battle_keys"])
    keys = {k for k, v in manifest["battle_partitions"].items() if v == partition}
    if keys & forbidden:
        raise ValueError("Evaluation overlaps training/validation/model-selection battles")


def evaluate_bundle(dataset: Path, predictor: Path, output: Path, partition: str) -> dict:
    if output.exists():
        raise ValueError("Supervised evaluation output must be fresh")
    manifest, rows = read_supervised_dataset(dataset)
    artifact, bundle = load_bundle(predictor)
    check_evaluation_partition(manifest, artifact, partition)
    selected = [r for r in rows if r["partition"] == partition and r["target_player"] == "b"]
    if not selected:
        raise ValueError("No eligible primary-population examples")
    predictions = []
    for row in selected:
        features = features_from_dict(row["features"])
        estimates = {mode: asdict(CountPredictor(bundle.table, mode).predict_context(features.context)) for mode in MODES[:2]}
        predictions.append({**row, **estimates, "logistic": {"probability": bundle.logistic.probability(features),
            "version": bundle.version, "predictor_sha256": bundle.sha256}})

    def metrics(group):
        return {mode: probability_metrics([r["target"] for r in group], [r[mode]["probability"] for r in group]) for mode in MODES}

    total = metrics(predictions)
    from collections import Counter
    primary_exclusions = dict(Counter(r["reason"] for r in read_jsonl(dataset / "exclusions.jsonl")
        if r.get("target_player") == "b" and r["partition"] == partition))
    differences = {}
    for candidate, reference in (("logistic", "constant"), ("logistic", "conditional"), ("conditional", "constant")):
        # Reuse V3's whole-battle bootstrap; rename fields only for its generic difference calculation.
        paired = [{"battle_key": r["battle_key"], "target": r["target"], "constant": r[reference], "conditional": r[candidate]} for r in predictions]
        interval = paired_battle_interval(paired, seed=20260909)
        interval["difference"] = f"{candidate} minus {reference}; negative favors {candidate}"
        differences[f"{candidate}_minus_{reference}"] = {"point": {m: total[candidate][m] - total[reference][m] for m in ("brier", "log_loss")}, **interval}

    result = {"schema_version": "v4-probability-report-1", "partition": partition, "target_player": "b",
        "balance": balance(selected), "metrics": total, "paired_battle_bootstrap": differences,
        "groups": {field: {name: {"balance": balance([r for r in selected if r[field] == name]),
            "metrics": metrics([r for r in predictions if r[field] == name])} for name in sorted({r[field] for r in selected})}
            for field in ("target_policy", "observer_policy")},
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"), "predictor_sha256": sha256(predictor),
        "source_label_coverage": [{"run_id": s["run_id"], "coverage": s["label_coverage"], "attempts": s["label_attempts"]} for s in manifest["sources"]],
        "dataset_exclusions": manifest["exclusions"], "dataset_balance": manifest["balance"],
        "primary_exclusions": primary_exclusions,
        "primary_eligibility_coverage": len(selected) / (len(selected) + sum(primary_exclusions.values())),
        "selection_excluded_examples": sum(r["partition"] == partition for r in rows) - len(selected),
        "code_sha256": source_manifest(), "claim_scope": "development model selection" if partition == "development_check"
            else "fresh fixed opponent/team mixture; no held-out opponent/team or general human-play claim"}
    output.mkdir(parents=True)
    with (output / "predictions.jsonl").open("x", encoding="utf-8") as file:
        for row in predictions:
            file.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
    result["predictions_sha256"] = sha256(output / "predictions.jsonl")
    write_json(output / "summary.json", result)
    return result
