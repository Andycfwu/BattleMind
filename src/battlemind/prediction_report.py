"""Offline probability evaluation and deterministic audits, independent of battle wins."""

from collections import Counter, defaultdict
from dataclasses import asdict
import json
import math
from pathlib import Path
import random

from .anticipation import SwitchAwareAgent
from .dataset import balance, load_predictor, read_dataset, write_json
from .environment import sha256, source_manifest
from .labels import audit_labels, read_jsonl
from .prediction import Context, CountPredictor
from .schema import snapshot_from_dict


def probability_metrics(targets: list[int], probabilities: list[float]) -> dict:
    if len(targets) != len(probabilities) or any(y not in {0, 1} for y in targets):
        raise ValueError("Invalid probability/target alignment")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError("Probabilities must be finite and within [0,1]")
    n = len(targets)
    calibration = []
    for i in range(5):
        selected = [(y, p) for y, p in zip(targets, probabilities) if min(int(p * 5), 4) == i]
        calibration.append({"lower": i / 5, "upper": (i + 1) / 5, "count": len(selected),
            "mean_prediction": sum(p for _, p in selected) / len(selected) if selected else None,
            "switch_fraction": sum(y for y, _ in selected) / len(selected) if selected else None})
    return {"examples": n, "switches": sum(targets), "moves": n - sum(targets),
        "brier": sum((p - y) ** 2 for y, p in zip(targets, probabilities)) / n if n else None,
        "log_loss": sum(log_loss(y, p) for y, p in zip(targets, probabilities)) / n if n else None,
        "calibration": calibration, "log_loss_clip": 1e-15}


def log_loss(y: int, p: float) -> float:
    p = min(1 - 1e-15, max(1e-15, p))
    return -y * math.log(p) - (1 - y) * math.log1p(-p)


def paired_battle_interval(rows: list[dict], seed: int = 2026) -> dict:
    groups = defaultdict(list)
    for r in rows:
        groups[r["battle_key"]].append(r)
    aggregates = []
    for group in groups.values():
        aggregates.append((len(group),
            sum((r["conditional"]["probability"] - r["target"]) ** 2 - (r["constant"]["probability"] - r["target"]) ** 2 for r in group),
            sum(log_loss(r["target"], r["conditional"]["probability"]) - log_loss(r["target"], r["constant"]["probability"]) for r in group)))
    if len(aggregates) < 2:
        return {"battles": len(aggregates), "intervals": None}
    rng = random.Random(seed)
    draws = [[], []]
    for _ in range(1000):
        sample = rng.choices(aggregates, k=len(aggregates))
        denominator = sum(a[0] for a in sample)
        for i in (0, 1):
            draws[i].append(sum(a[i + 1] for a in sample) / denominator)
    return {"battles": len(aggregates), "resamples": 1000, "seed": seed,
        "difference": "conditional minus constant; negative favors conditional",
        "scope": "descriptive paired bootstrap over whole battles, retaining all selected turns/perspectives; restricted schedule",
        "intervals": {name: [sorted(values)[24], sorted(values)[974]] for name, values in zip(("brier", "log_loss"), draws)}}


def evaluate_predictor(dataset: Path, predictor: Path, output: Path, partition: str,
                       target_policies: list[str] | None = None) -> dict:
    if output.exists():
        raise ValueError("Probability report output must be fresh")
    manifest, all_rows = read_dataset(dataset)
    artifact, table = load_predictor(predictor)
    if partition not in {"development_check", "evaluation"}:
        raise ValueError("Evaluation cannot use the count-estimation partition")
    if (partition == "evaluation") != (manifest["role"] == "evaluation"):
        raise ValueError("Partition does not match dataset role")
    forbidden = set(artifact["development_battle_keys"] if partition == "evaluation" else artifact["fit_battle_keys"])
    selected_keys = {k for k, part in manifest["battle_partitions"].items() if part == partition}
    if selected_keys & forbidden:
        raise ValueError("Evaluation overlaps development/count-estimation battles")
    rows = [r for r in all_rows if r["partition"] == partition and (not target_policies or r["target_policy"] in target_policies)]
    if not rows:
        raise ValueError("No eligible examples in the selected evaluation partition")
    predictions = []
    for row in rows:
        context = Context(**row["features"])
        predictions.append({**row, **{mode: asdict(CountPredictor(table, mode).predict_context(context)) for mode in ("constant", "conditional")}})

    def metrics(group: list[dict]) -> dict:
        return {mode: probability_metrics([r["target"] for r in group], [r[mode]["probability"] for r in group]) for mode in ("constant", "conditional")}

    result = {"schema_version": "v3-probability-report-1", "partition": partition,
        "target_policies": target_policies, "balance": balance(rows), "metrics": metrics(predictions),
        "by_target_policy": {name: {"balance": balance([r for r in rows if r["target_policy"] == name]),
            **metrics([r for r in predictions if r["target_policy"] == name])} for name in sorted({r["target_policy"] for r in rows})},
        "conditional_fallbacks": dict(Counter(r["conditional"]["fallback"] or "context_used" for r in predictions)),
        "paired_battle_bootstrap": paired_battle_interval(predictions),
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"), "predictor_sha256": sha256(predictor),
        "source_label_coverage": [{"run_id": s["run_id"], "coverage": s["label_coverage"], "attempts": s["label_attempts"]} for s in manifest["sources"]],
        "dataset_exclusions": manifest["exclusions"], "dataset_balance": manifest["balance"],
        "selection_excluded_examples": sum(r["partition"] == partition for r in all_rows) - len(rows),
        "code_sha256": source_manifest(),
        "claim_scope": "previously reported M2 development check, not untouched test" if partition == "development_check" else "fresh restricted-pool evaluation after freezing; no human/generalization claim"}
    output.mkdir(parents=True)
    with (output / "predictions.jsonl").open("x", encoding="utf-8") as file:
        for row in predictions:
            file.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
    result["predictions_sha256"] = sha256(output / "predictions.jsonl")
    write_json(output / "summary.json", result)
    return result


def audit_predictions(run: Path) -> dict:
    audit = audit_labels(run)
    metadata = json.loads((run / "run.json").read_text())
    if not metadata.get("predictor"):
        return {**audit, "prediction_decisions": 0}
    path = run / "predictor.json"
    if sha256(path) != metadata["predictor"]["sha256"]:
        raise ValueError("Frozen run predictor hash mismatch")
    _, table = load_predictor(path)
    from .learned_policy import LearnedScoreAgent, load_checkpoint
    checkpoints = {}
    for side, saved in metadata.get("policy_checkpoints", {}).items():
        checkpoint_path = run / saved["path"]
        if sha256(checkpoint_path) != saved["sha256"]:
            raise ValueError("Frozen policy checkpoint hash mismatch")
        _, checkpoints[side] = load_checkpoint(checkpoint_path, table)
    count, contextual_changes, v2_changes = 0, 0, 0
    logistic_changes = {"constant": 0, "conditional": 0}
    for row in read_jsonl(run / "decisions.jsonl"):
        name = metadata["policies"][row["player"]]["name"]
        if name not in {"switch-constant", "switch-context", "switch-logistic", "learned-score"}:
            continue
        policy = (LearnedScoreAgent(table, checkpoints[row["player"]]) if name == "learned-score" else
                  SwitchAwareAgent(table, {"switch-constant": "constant", "switch-context": "conditional", "switch-logistic": "logistic"}[name]))
        if "memory_mode" in row.get("prediction_evaluation", {}):
            from .adaptation import AdaptedAgent
            from .opponent_memory import context_from_dict
            if row["player"] != "a" or metadata.get("adaptation", {}).get("mode") != row["prediction_evaluation"]["memory_mode"]:
                raise ValueError("Unexpected observer memory routing")
            before = json.loads((run / f"memory/{row['match']:03d}-before.json").read_text())
            context = context_from_dict(before["pre_context"])
            if context.sha256 != row["prediction_evaluation"]["memory_sha256"]:
                raise ValueError("Memory changed inside battle")
            policy = AdaptedAgent(table, checkpoints["a"], context, metadata["adaptation"]["mode"])
        rebuilt = policy.evaluate(snapshot_from_dict(row["observation"]))
        if json.loads(json.dumps(asdict(rebuilt))) != row["prediction_evaluation"]:
            raise ValueError("Prediction/scores differ from frozen snapshot and count table")
        if row["chosen_action"] != rebuilt.chosen_action or row["action_scores"] != json.loads(json.dumps([asdict(s) for s in rebuilt.scores])):
            raise ValueError("Logged action differs from prediction evaluation")
        count += 1
        contextual_changes += rebuilt.constant_choice != rebuilt.conditional_choice
        v2_changes += rebuilt.chosen_action != rebuilt.v2_choice
        if hasattr(rebuilt, "logistic_choice"):
            logistic_changes["constant"] += rebuilt.logistic_choice != rebuilt.constant_choice
            logistic_changes["conditional"] += rebuilt.logistic_choice != rebuilt.conditional_choice
    return {**audit, "prediction_decisions": count, "context_changes_vs_constant_on_same_snapshot": contextual_changes,
            "chosen_action_changes_vs_v2_on_same_snapshot": v2_changes,
            "logistic_changes_on_same_snapshot": logistic_changes}
