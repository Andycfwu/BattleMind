"""Append-only run records and summary accounting from terminal battle rows."""

import csv
import json
import math
from pathlib import Path
from typing import Any


def known_gen1_warning(event: dict) -> bool:
    message = event.get("message", "")
    return (event.get("kind") == "client_log" and event.get("level") == "WARNING"
            and message.startswith("Unmanaged move message format received - cleaned up message")
            and any(f"'[from] {move}'" in message for move in ("Wrap", "Clamp")))


def wilson_interval(wins: int, games: int) -> list[float] | None:
    if not games:
        return None
    z = 1.959963984540054
    p, z2 = wins / games, z * z
    center = (p + z2 / (2 * games)) / (1 + z2 / games)
    half = z * math.sqrt(p * (1 - p) / games + z2 / (4 * games * games)) / (1 + z2 / games)
    return [max(0.0, center - half), min(1.0, center + half)]


class JsonlWriter:
    def __init__(self, path: Path):
        self.file = path.open("x", encoding="utf-8")

    def write(self, row: dict[str, Any]) -> None:
        self.file.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def summarize(rows: list[dict], requested: int) -> dict:
    if len({r["match"] for r in rows}) != len(rows):
        raise ValueError("Duplicate terminal match records")
    statuses = ("completed", "truncated", "timeout", "crash", "cancelled", "not_started")
    if any(r["status"] not in statuses for r in rows):
        raise ValueError("Unknown battle status")
    counts = {s: sum(r["status"] == s for r in rows) for s in statuses}
    completed = [r for r in rows if r["status"] == "completed"]
    if any(r["winner"] not in {"a", "b", "draw"} for r in completed):
        raise ValueError("Completed battle missing a genuine result")
    wins = {side: sum(r["winner"] == side for r in completed) for side in ("a", "b", "draw")}
    return {"schema_version": "1.0", "requested": requested, "recorded": len(rows),
            "unrecorded": requested - len(rows), **counts,
            "a_wins": wins["a"], "b_wins": wins["b"], "draws": wins["draw"],
            "completed_game_win_rate_a": wins["a"] / len(completed) if completed else None,
            "completed_game_win_rate_b": wins["b"] / len(completed) if completed else None,
            "win_rate_denominator": len(completed), "draw_handling": "included in denominator; not a win",
            "invalid_action_incidents": sum(r.get("invalid_actions", 0) for r in rows),
            "decisions": sum(r.get("decisions", 0) for r in rows),
            "claim_scope": "restricted team pool; pipeline smoke test, not competitive evidence"}


def report(run: Path) -> dict:
    metadata = json.loads((run / "run.json").read_text())
    rows = [json.loads(line) for line in (run / "battles.jsonl").read_text().splitlines()]
    summary = summarize(rows, metadata["config"]["battles"])
    labels_path = run / "privileged/labels.jsonl"
    if labels_path.exists():
        from .labels import label_summary, read_jsonl
        summary["labels"] = label_summary(read_jsonl(labels_path))
        events = read_jsonl(run / "events.jsonl")
        warnings = [e for e in events if e["kind"] == "client_log"]
        summary["client_warning_records"] = len(warnings)
        summary["known_gen1_annotation_warnings"] = sum(known_gen1_warning(e) for e in warnings)
        summary["unexpected_client_warning_records"] = sum(not known_gen1_warning(e) for e in warnings)
        server_log = run / "server.log"
        summary["server_crash_reports"] = server_log.read_text().count("CRASH:") if server_log.exists() else None
        summary["a_win_rate_wilson_95"] = wilson_interval(summary["a_wins"], summary["completed"])
        summary["interval_scope"] = "descriptive Bernoulli interval for this restricted schedule; not general performance"
        from collections import Counter
        schedule = Counter(f"a{r['team_indices']['a']}:b{r['team_indices']['b']}:challenger-{r['challenger']}"
                           for r in rows if r["status"] == "completed")
        summary["completed_schedule"] = dict(sorted(schedule.items()))
        if metadata.get("predictor"):
            predicted = [r["prediction_evaluation"] for r in read_jsonl(run / "decisions.jsonl") if "prediction_evaluation" in r]
            summary["prediction_decisions"] = len(predicted)
            summary["prediction_applied_decisions"] = sum(r["applied"] for r in predicted)
            summary["context_changes_vs_constant_on_same_snapshot"] = sum(r["constant_choice"] != r["conditional_choice"] for r in predicted)
            summary["chosen_action_changes_vs_v2_on_same_snapshot"] = sum(r["chosen_action"] != r["v2_choice"] for r in predicted)
            if any("logistic_choice" in r for r in predicted):
                summary["logistic_changes_on_same_snapshot"] = {
                    mode: sum(r["logistic_choice"] != r[mode + "_choice"] for r in predicted if "logistic_choice" in r)
                    for mode in ("constant", "conditional")}
    resource_file = run / "resources.json"
    if resource_file.exists():
        summary["resources"] = json.loads(resource_file.read_text())
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fields = [k for k, v in summary.items() if not isinstance(v, dict)]
    with (run / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerow({k: summary[k] for k in fields})
    return summary
