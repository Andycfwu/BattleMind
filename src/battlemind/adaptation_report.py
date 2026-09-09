"""Paired shadow probabilities, live outcomes and group-level descriptive uncertainty."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import time

from .adaptation import ARMS
from .adaptation_ledger import request_accounting
from .dataset import write_json
from .environment import sha256, source_manifest
from .labels import audit_labels, read_jsonl
from .memory_audit import replay_cell
from .opponent_memory import ObserverMemory, digest
from .prediction_report import probability_metrics, log_loss
from .reporting import summarize

COMPARISONS = (("individual", "none"), ("individual", "pooled"), ("pooled", "none"))


def metrics(rows):
    return {arm: probability_metrics([r["target"] for r in rows], [r["probabilities"][arm] for r in rows]) for arm in ARMS}


def cluster_interval(groups: list[tuple[float, float]], seed=61901) -> dict:
    """Each pair is numerator/denominator for one independent entire session group."""
    if len(groups) < 4 or any(d <= 0 for _, d in groups):
        return {"available": False, "groups": len(groups), "reason": "fewer than four complete supported groups"}
    rng = random.Random(seed)
    samples = []
    for _ in range(1000):
        sample = rng.choices(groups, k=len(groups))
        samples.append(sum(n for n, _ in sample) / sum(d for _, d in sample))
    return {"available": True, "groups": len(groups), "resamples": 1000, "seed": seed,
        "point": sum(n for n, _ in groups) / sum(d for _, d in groups),
        "interval_95": [sorted(samples)[24], sorted(samples)[974]],
        "group_points": [n / d for n, d in groups],
        "limitation": "Only four independent repeated-encounter groups; descriptive, not robust inference; no matched engine RNG"}


def probability_differences(rows):
    result = {}
    groups = sorted({r["group"] for r in rows})
    for candidate, reference in COMPARISONS:
        losses = {}
        for metric in ("brier", "log_loss"):
            def loss(row, arm):
                p, y = row["probabilities"][arm], row["target"]
                return (p - y) ** 2 if metric == "brier" else log_loss(y, p)
            aggregates = [(sum(loss(r, candidate) - loss(r, reference) for r in rows if r["group"] == group),
                           sum(r["group"] == group for r in rows)) for group in groups]
            losses[metric] = cluster_interval(aggregates)
        result[f"{candidate}_minus_{reference}"] = losses
    return result


def outcome_metrics(rows: list[dict], requested: int):
    result = summarize([{**r, "match": i} for i, r in enumerate(rows)], requested)
    result["mean_terminal_reward"] = (result["a_wins"] + .5 * result["draws"]) / result["completed"] if result["completed"] else None
    return result


def label_exclusion(label: dict) -> str | None:
    if label["match_status"] != "completed":
        return "incomplete_battle"
    if label["commit_status"] != "verified":
        return "unknown_commitment"
    if label["genuine_switch_move_choice"] is not True:
        return ("unknown_eligibility" if label["genuine_switch_move_choice"] is None else
                label["intended_kind"] if label["intended_kind"] in {"forced_replacement", "engine_action"} else "no_meaningful_choice")
    if label["observer_decision_id"] is None:
        return "missing_observer_join"
    return None


def build_adaptation_report(root: Path, audit: bool = True, write: bool = False, deadline: float | None = None) -> dict:
    from .adaptation_experiment import artifacts, group_schedule, CONFIG, SPEC
    from .environment import ROOT
    root = root.resolve()
    freeze = json.loads((root / "freeze.json").read_text())
    config = freeze["config"]
    ledger = json.loads((root / "ledger.json").read_text())
    repaired = ledger["schema_version"] == "v6-budget-2"
    if freeze["version"] == "v6-freeze-2":
        CONFIG, SPEC = ROOT / freeze["config_path"], ROOT / freeze["spec_path"]
    bundle, checkpoint = artifacts(root / "predictor.json", root / "checkpoint.json")
    if audit and (freeze["source"] != source_manifest() or sha256(CONFIG) != freeze["config_sha256"] or sha256(SPEC) != freeze["spec_sha256"]
                  or config != json.loads(CONFIG.read_text())):
        raise ValueError("V6 frozen source/specification changed")
    expected = [(phase, cell) for phase in ("development", "final") for g in range(config["groups"][phase])
                for cell in group_schedule(config, phase, g)]
    if ledger["requested_games"] != sum(r["requested_games"] for r in ledger["runs"]) or ledger["requested_games"] > config["total_games"]:
        raise ValueError("Aggregate V6 request budget mismatch")
    if len(ledger["runs"]) > len(expected):
        raise ValueError("Undeclared extra experiment cells")
    managers, partitions = {}, {}
    all_decisions, all_updates, probabilities, outcomes, summaries = [], [], [], [], []
    exclusions = defaultdict(Counter)
    audit_count = 0
    unverified = []
    for record, (phase, planned) in zip(ledger["runs"], expected):
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Reserved reporting wall budget exhausted")
        if (any(record.get(k) != v for k, v in planned.items()) or record["phase"] != phase
            or record.get("reserved_games", record["requested_games"]) != 4
            or record["requested_games"] not in ((0, 4) if repaired else (4,))):
            raise ValueError("Encounter schedule changed")
        path = root / record["path"]
        if record["status"] != "recorded":
            unverified.append(record["path"])
            continue
        metadata = json.loads((path / "run.json").read_text())
        if (sha256(path / "run.json") != record["run_id"] or metadata["config"]["seed"] != planned["seed"]
            or metadata["config"]["schedule_offset"] != 4 * planned["pair"]
            or metadata["config"]["teams"] != config["teams"] or metadata["config"]["agent_b"] != planned["target"]
            or metadata["adaptation"]["observer_key"] != planned["observer_key"]
            or metadata["adaptation"]["session_key"] != planned["session_key"]
            or metadata["adaptation"]["mode"] != planned["arm"]):
            raise ValueError("Run routing/team/seed provenance mismatch")
        battles = read_jsonl(path / "battles.jsonl")
        summary = json.loads((path / "summary.json").read_text())
        if summary != {k: v for k, v in record["summary"].items() if k != "run_directory"}:
            raise ValueError("Ledger/run summary mismatch")
        summaries.append({"phase": phase, **summary})
        for battle in battles:
            if battle["status"] == "completed":
                from .runner import scheduled_match
                assignments, challenger = scheduled_match(4 * planned["pair"] + battle["match"], 4)
                if battle["team_indices"] != assignments or battle["challenger"] != challenger:
                    raise ValueError("Actual team/side schedule differs from planned balance")
            key = f"{record['run_id']}:{battle['match']}"
            if key in partitions:
                raise ValueError("Memory-linked encounter overlap")
            partitions[key] = {"phase": phase, "group": record["group"]}
            outcomes.append({**battle, "phase": phase, "group": record["group"], "arm": record["arm"], "target_policy": record["target"]})
        if summary["completed"] != 4:
            unverified.append(record["path"])
            continue
        manager = managers.setdefault(record["observer_key"], ObserverMemory())
        replay = replay_cell(path, manager, bundle, checkpoint)
        if any(r["completed"] != (b["status"] == "completed") for r, b in zip(replay["updates"], battles)):
            raise ValueError("Public-memory completion flag differs from actual encounter status")
        if audit:
            audit_labels(path)  # Separate privileged evaluation audit, never a memory argument.
            audit_count += 1
        grouping = {"phase": phase, "group": record["group"], "arm": record["arm"],
                    "target_policy": record["target"], "run_id": record["run_id"]}
        decisions = [{**r, **grouping} for r in replay["decisions"]]
        all_decisions.extend(decisions)
        all_updates.extend({**r, **grouping} for r in replay["updates"])
        by_id = {r["decision_id"]: r for r in decisions}
        for label in read_jsonl(path / "privileged/labels.jsonl"):
            if label["player"] != "b":
                continue
            reason = label_exclusion(label)
            if reason:
                exclusions[phase][reason] += 1
                continue
            row = by_id.get(label["observer_decision_id"])
            if row is None or row["snapshot_sha256"] != label["observer_snapshot_sha256"]:
                raise ValueError("Privileged target does not align to the observer's frozen snapshot")
            probabilities.append({**row, "target": label["voluntary_switch_target"], "target_decision_id": label["decision_id"]})
    if partitions != ledger["battle_partitions"]:
        raise ValueError("Recorded phase/group partition mismatch")
    collection_complete = all(p["status"] == "finished" for p in ledger["phases"].values())
    if ledger["status"] == "finished" and not collection_complete:
        raise ValueError("Finished experiment contains an incomplete phase")
    for phase, allocation in ledger["phases"].items():
        requested = sum(r["requested_games"] for r in ledger["runs"] if r["phase"] == phase)
        if requested != allocation["requested_games"] or requested > config["games"][phase]:
            raise ValueError("Reserved phase budget mismatch")
        if collection_complete and (requested != config["games"][phase] or allocation["consumed_seconds"] > config["seconds"][phase]):
            raise ValueError("Finished phase incomplete or over budget")
        if repaired:
            records = [r for r in ledger["runs"] if r["phase"] == phase]
            rows = [r for r in outcomes if r["phase"] == phase]
            accounting = request_accounting(config["games"][phase], records, rows)
            if any(allocation[k] != accounting[k] for k in ("reserved_games", "requested_games", "completed_games")):
                raise ValueError("Phase dispatch/completion accounting differs from recorded evidence")
            start, stop = allocation["start_elapsed_seconds"], allocation["stop_elapsed_seconds"]
            if ((start is None) != (stop is None) or (start is None and allocation["consumed_seconds"] != 0)
                or (start is not None and (stop < start or abs(stop - start - allocation["consumed_seconds"]) > 1e-6))):
                raise ValueError("Stopped phase clock is inconsistent")
    if repaired:
        if ledger["reserved_games"] != sum(r["reserved_games"] for r in ledger["runs"]):
            raise ValueError("Aggregate cell reservations differ")
        timing = ledger["timing"]
        phase_seconds = sum(p["consumed_seconds"] for p in ledger["phases"].values())
        if abs(timing["collection_stop_elapsed_seconds"] - phase_seconds - timing["setup_seconds"]) > 1e-6:
            raise ValueError("Collection/phase/setup clock mismatch")
        if timing["finalized"]:
            if (abs(ledger["consumed_seconds"] - timing["collection_stop_elapsed_seconds"] - timing["reporting_audit_seconds"]) > 1e-6
                or abs(timing["overhead_seconds"] - timing["setup_seconds"] - timing["reporting_audit_seconds"]) > 1e-6
                or (ledger["status"] == "finished" and timing["overhead_seconds"] > ledger["overhead_allocated_seconds"])):
                raise ValueError("Final reporting/overhead clock mismatch")
    if collection_complete:
        resets = [{"phase": phase, "group": group, "observers": [digest(["v6-observer", phase, group, arm])[:24] for arm in ARMS],
                   "all_empty": True} for phase in ("development", "final") for group in range(config["groups"][phase])]
        final = json.loads((root / "final-freeze.json").read_text())
        if (unverified or ledger["resets"] != resets or ledger["consumed_seconds"] > config["total_seconds"]
            or final != {"freeze_sha256": sha256(root / "freeze.json"),
                "development_run_ids": [r["run_id"] for r in ledger["runs"] if r["phase"] == "development"],
                "rules_changed_after_development": False, "final_memories_start_empty": True}):
            raise ValueError("Final reset/freeze/budget validation failed")
    final_probs = [r for r in probabilities if r["phase"] == "final"]
    final_games = [r for r in outcomes if r["phase"] == "final"]
    phase_reports = {}
    for phase in ("development", "final"):
        rows = [r for r in probabilities if r["phase"] == phase]
        decisions = [r for r in all_decisions if r["phase"] == phase]
        updates = [r for r in all_updates if r["phase"] == phase]
        admitted = [r for r in decisions if r["proxy"] is not None]
        eligible_admitted = [r for r in rows if r["proxy"] is not None]
        phase_reports[phase] = {**ledger["phases"][phase], "accounting": request_accounting(config["games"][phase],
            [r for r in ledger["runs"] if r["phase"] == phase], [r for r in outcomes if r["phase"] == phase]),
            "outcomes": outcome_metrics([r for r in outcomes if r["phase"] == phase],
                ledger["phases"][phase]["requested_games"]), "probability_metrics": metrics(rows),
            "eligible_examples": len(rows), "switches": sum(r["target"] for r in rows), "exclusions": dict(exclusions[phase]),
            "public_evidence": {"encounters": len(updates), "supported_encounters": sum(r["update_eligible"] for r in updates),
                "admitted": len(admitted), "switch_proxies": sum(r["proxy"] for r in admitted),
                "skipped": dict(Counter(r["proxy_reason"] for r in decisions if r["proxy"] is None)),
                "admitted_with_eligible_privileged_target": len(eligible_admitted),
                "proxy_target_disagreements": sum(r["proxy"] != r["target"] for r in eligible_admitted),
                "eligible_admitted_switches": sum(r["target"] for r in eligible_admitted),
                "eligible_skipped_switches": sum(r["target"] for r in rows if r["proxy"] is None),
                "support_encounters": {a: {"minimum": min((r["support"][a] for r in decisions), default=0),
                    "maximum": max((r["support"][a] for r in decisions), default=0)} for a in ARMS[1:]}},
            "same_snapshot_choice_differences": {f"{a}_minus_{b}": sum(r["choices"][a] != r["choices"][b] for r in decisions)
                for a, b in COMPARISONS}, "observer_decisions": len(decisions)}
    complete_groups = [g for g in range(config["groups"]["final"]) if
        sum(r["status"] == "completed" for r in final_games if r["group"] == g) ==
        sum(4 for p, cell in expected if p == "final" and cell["group"] == g)]
    def differences(rows):
        # The original specification requires complete independent groups.
        return probability_differences(rows if len(complete_groups) >= 4 else [])
    groups = {}
    for field in ("arm", "target_policy", "cold_start", "individual_fallback", "group"):
        groups[field] = {str(key): {"metrics": metrics([r for r in final_probs if r[field] == key]),
            "differences": differences([r for r in final_probs if r[field] == key])}
            for key in sorted({r[field] for r in final_probs})}
    groups["arm_by_target"] = {f"{arm}/{target}": metrics([r for r in final_probs if r["arm"] == arm and r["target_policy"] == target])
        for arm in ARMS for target in config["targets"]}
    def live_scope(arm, target=None, group=None):
        def matches(r):
            return r["arm"] == arm and (target is None or r.get("target_policy", r.get("target")) == target) and (group is None or r["group"] == group)
        rows = [r for r in final_games if matches(r)]
        records = [r for r in ledger["runs"] if r["phase"] == "final" and matches(r)]
        planned = sum(4 for p, cell in expected if p == "final" and matches(cell))
        accounting = request_accounting(planned, records, rows)
        return {**outcome_metrics(rows, accounting["requested_games"]), "accounting": accounting}
    live = {arm: {"overall": live_scope(arm),
        "by_target": {t: live_scope(arm, target=t) for t in config["targets"]},
        "by_group": {str(g): live_scope(arm, group=g) for g in range(config["groups"]["final"])}} for arm in ARMS}
    live_differences = {}
    for a, b in COMPARISONS:
        result = {}
        for metric in ("reward", "win_rate"):
            aggregate = []
            for g in range(config["groups"]["final"]):
                subsets = {arm: [r for r in final_games if r["arm"] == arm and r["group"] == g] for arm in (a, b)}
                if any(len(rs) != 48 or any(r["status"] != "completed" for r in rs) for rs in subsets.values()):
                    continue
                scores = {arm: sum(1 if r["winner"] == "a" else .5 if metric == "reward" and r["winner"] == "draw" else 0 for r in rs) for arm, rs in subsets.items()}
                aggregate.append((scores[a] - scores[b], 48))
            result[metric] = cluster_interval(aggregate)
        live_differences[f"{a}_minus_{b}"] = result
    warnings = {k: sum(s.get(k) or 0 for s in summaries) for k in ("client_warning_records", "known_gen1_annotation_warnings", "unexpected_client_warning_records", "server_crash_reports")}
    labels = {k: sum(s["labels"][k] for s in summaries) for k in ("attempts", "verified_intended_choices", "unknown_intended_choices", "paired_opponent_targets", "eligibility_unknown")}
    resources = {"python_cpu_seconds": sum(s["resources"]["python_cpu_seconds"] for s in summaries),
        "server_cpu_last_samples": sum(s["resources"]["managed_server_cpu_seconds_last_sample"] or 0 for s in summaries),
        "python_peak_sampled_rss_bytes": max((s["resources"]["python_peak_sampled_rss_bytes"] for s in summaries), default=0),
        "server_peak_sampled_rss_bytes": max((s["resources"]["managed_server_peak_sampled_rss_bytes"] or 0 for s in summaries), default=0)}
    hashes = json.loads((root / "artifact-hashes.json").read_text()) if (root / "artifact-hashes.json").exists() else {}
    if audit and any(sha256(root / p) != h for p, h in hashes.items()):
        raise ValueError("V6 artifact hash mismatch")
    report = {"version": "v6-report-2" if repaired else "v6-report-1", "status": ledger["status"], "failure": ledger["failure"],
        "requested_games": ledger["requested_games"], "consumed_seconds": ledger["consumed_seconds"],
        "accounting": request_accounting(config["total_games"], ledger["runs"], outcomes),
        **({"timing": ledger["timing"]} if repaired else {}),
        "phases": phase_reports, "final_probability": {"metrics": metrics(final_probs), "groups": groups,
            "differences": differences(final_probs)}, "final_battles": live, "battle_differences": live_differences,
        "labels": labels, "warnings": warnings, "resources": resources, "predictor_sha256": bundle.sha256,
        "checkpoint_sha256": checkpoint.sha256, "audit": {"ok": not unverified, "public_decisions": len(all_decisions),
            "encounters": len(all_updates), "private_audited_cells": audit_count, "overlapping_battles": 0,
            "reset_groups": len(ledger["resets"]), "artifact_files": len(hashes), "unverified_runs": unverified}}
    if write:
        for name, rows in (("shadow-predictions", probabilities), ("shadow-decisions", all_decisions), ("public-updates", all_updates)):
            with (root / f"{name}.jsonl").open("x", encoding="utf-8") as file:
                for row in rows:
                    file.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
    return report
