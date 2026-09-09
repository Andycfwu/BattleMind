"""Predeclared V4 collection/final phases with one persistent aggregate budget.

Load scripts/env.ps1 first. Each phase requires a fresh output directory. Final
is single-use per budget ledger; failed/incomplete evidence is never overwritten.
"""

import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time

from battlemind.dataset import load_predictor, write_json
from battlemind.environment import ROOT, sha256, source_manifest
from battlemind.prediction_report import audit_predictions
from battlemind.runner import RunConfig, run
from battlemind.supervised_data import build_supervised_dataset, load_bundle
from battlemind.supervised_report import evaluate_bundle

OPPONENTS = ("gen1-heuristic", "switch-moderate", "switch-active")
SPEC = ROOT / "docs/V4-EXPERIMENT.md"


def begin_budget(path: Path, phase: str, games: int, output: Path) -> dict:
    if path.exists():
        ledger = json.loads(path.read_text())
    else:
        if phase != "collect":
            raise ValueError("Final phase needs the original collection budget ledger")
        ledger = {"schema_version": "v4-budget-1", "max_games": 600, "max_seconds": 900,
                  "spec_sha256": sha256(SPEC), "phases": {}}
    if (ledger["schema_version"] != "v4-budget-1" or ledger["max_games"] != 600 or ledger["max_seconds"] != 900
        or ledger["spec_sha256"] != sha256(SPEC)):
        raise ValueError("Experiment budget/specification mismatch")
    if phase in ledger["phases"] or any(p["status"] == "running" for p in ledger["phases"].values()):
        raise ValueError("Phase already reserved or previous phase interrupted; no automatic retry")
    if phase == "final" and ledger["phases"].get("collect", {}).get("status") != "finished":
        raise ValueError("Final requires finished collection")
    used_games = sum(p["reserved_games"] for p in ledger["phases"].values())
    used_seconds = sum(p["wall_seconds"] for p in ledger["phases"].values())
    if games + used_games > 600 or used_seconds >= 870:
        raise ValueError("Aggregate experiment budget exhausted")
    ledger["phases"][phase] = {"status": "running", "reserved_games": games, "wall_seconds": 0,
                               "output": str(output), "created_unix": time.time()}
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive phase marker prevents two local invocations sharing a reservation.
    marker = path.with_name(path.name + "." + phase + ".reserved")
    with marker.open("x") as file:
        file.write(str(output))
    path.write_text(json.dumps(ledger, indent=2) + "\n")
    return ledger


async def experiment(phase: str, output: Path, predictor: Path, budget: Path) -> dict:
    if output.exists():
        raise ValueError("Experiment output must be fresh")
    if phase == "collect":
        load_predictor(predictor)
        expected = "e46feb7dc665c046c03f4b7cb6e4072b0dafbd56c3b04625cae68537722222ef"
        if sha256(predictor) != expected:
            raise ValueError("Collection observer requires the original frozen V3 artifact")
        observers = (("v2", "gen1-heuristic", 5101), ("v3-constant", "switch-constant", 5102))
    else:
        load_bundle(predictor)
        observers = (("constant", "switch-constant", 6101), ("context", "switch-context", 6101),
                     ("logistic", "switch-logistic", 6101), ("v2", "gen1-heuristic", 6101))
    schedule = [(name, agent, seed, opponent) for opponent in OPPONENTS for name, agent, seed in observers]
    data = json.loads((ROOT / "configs/v4-battle.json").read_text())
    data["teams"] = tuple(data["teams"])
    base = RunConfig(**data)
    base.validate()
    if len(base.teams) != 4 or base.battles != 24:
        raise ValueError("V4 requires 24-game four-team schedule cells")
    ledger = begin_budget(budget, phase, len(schedule) * 24, output)
    used = sum(p["wall_seconds"] for p in ledger["phases"].values())
    limit = 900 - used
    output.mkdir(parents=True)
    frozen = {"schema_version": "v4-freeze-1", "phase": phase, "created_unix": time.time(),
        "spec_sha256": sha256(SPEC), "code_sha256": source_manifest(), "predictor_sha256": sha256(predictor),
        "predictor_path": str(predictor), "budget_path": str(budget), "available_wall_seconds": limit,
        "planned_games": len(schedule) * 24, "cells": [{"name": f"{name}-vs-{opponent}", "agent_a": agent,
            "agent_b": opponent, "seed": seed, "games": 24} for name, agent, seed, opponent in schedule],
        "primary_target_player": "b", "rule": "same frozen scoring; all team assignments/sides; simulator RNG uncontrolled"}
    write_json(output / "freeze.json", frozen)
    started = time.monotonic()
    summaries, audits, paths, failure, quality = {}, {}, [], None, None
    try:
        for name, agent, seed, opponent in schedule:
            if (sha256(predictor) != frozen["predictor_sha256"] or source_manifest() != frozen["code_sha256"]
                or sha256(SPEC) != frozen["spec_sha256"]):
                raise ValueError("Frozen source/model/spec changed during experiment")
            remaining = limit - (time.monotonic() - started)
            if remaining < 40:
                failure = "Aggregate wall budget exhausted; remaining cells not started"
                break
            path = output / f"{name}-vs-{opponent}"
            config = replace(base, agent_a=agent, agent_b=opponent, seed=seed, predictor=str(predictor),
                             run_timeout=min(base.run_timeout, remaining - 30))
            print(f"Starting {phase} {path.name}: 24 games, concurrency 1", flush=True)
            summary = await run(config, path, start_server=True)
            summaries[path.name] = summary
            audits[path.name] = audit_predictions(path)
            paths.append(path)
            if (summary["invalid_action_incidents"] or summary["unexpected_client_warning_records"]
                or summary["crash"] or summary["timeout"] or summary["not_started"]):
                failure = "Run incident: stop and preserve evidence; no retry"
                break
        if paths and time.monotonic() - started < limit - 15:
            dataset = output / ("development-data" if phase == "collect" else "evaluation-data")
            build_supervised_dataset(paths, dataset, role="development" if phase == "collect" else "evaluation")
            if phase == "final" and time.monotonic() - started < limit - 10:
                quality = evaluate_bundle(dataset, predictor, output / "probability-quality", "evaluation")
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        elapsed = time.monotonic() - started
        ledger["phases"][phase].update(status="failed" if failure else "finished", wall_seconds=elapsed,
            completed_games=sum(s["completed"] for s in summaries.values()), failure=failure)
        budget.write_text(json.dumps(ledger, indent=2) + "\n")
    result = {"schema_version": "v4-experiment-1", "phase": phase, "planned_games": len(schedule) * 24,
        "completed_games": sum(s["completed"] for s in summaries.values()), "unstarted_cells": len(schedule) - len(paths),
        "failure": failure, "wall_seconds_including_audits": elapsed, "cells": summaries, "audits": audits,
        "probability_quality": quality, "freeze_sha256": sha256(output / "freeze.json"),
        "final_source_matches_freeze": source_manifest() == frozen["code_sha256"],
        "final_predictor_matches_freeze": sha256(predictor) == frozen["predictor_sha256"],
        "aggregate_reserved_games": sum(p["reserved_games"] for p in ledger["phases"].values()),
        "aggregate_wall_seconds": sum(p["wall_seconds"] for p in ledger["phases"].values())}
    write_json(output / "summary.json", result)
    write_json(output / "artifact-hashes.json", {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob("*")) if p.is_file()})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("collect", "final"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--predictor", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(experiment(args.phase, args.output.resolve(), args.predictor.resolve(), args.budget.resolve()))
    print(json.dumps({k: result[k] for k in ("phase", "completed_games", "planned_games", "failure", "aggregate_wall_seconds")}, indent=2))
    raise SystemExit(1 if result["failure"] else 0)
