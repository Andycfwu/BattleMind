"""Fixed, bounded V3 acceptance: three policies × two opponents × 24 games.

Run with the pinned environment loaded. No fitting or parameter selection occurs here.
Every invocation needs a fresh output root; original evidence is never overwritten.
"""

import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time

from battlemind.dataset import build_dataset, load_predictor, write_json
from battlemind.environment import ROOT, sha256, source_manifest
from battlemind.prediction_report import audit_predictions, evaluate_predictor
from battlemind.runner import RunConfig, run


async def benchmark(output: Path, predictor: Path) -> dict:
    if output.exists():
        raise ValueError("Benchmark output must be a fresh directory")
    load_predictor(predictor)
    data = json.loads((ROOT / "configs/v3-battle.json").read_text())
    data["teams"] = tuple(data["teams"])
    base = RunConfig(**data)
    base.validate()
    if len(base.teams) != 4 or base.battles != 24:
        raise ValueError("This acceptance schedule requires four teams and 24 games per cell")
    schedule = [(name, agent, opponent) for opponent in ("random", "max-base-power")
                for name, agent in (("v2", "gen1-heuristic"), ("constant", "switch-constant"), ("context", "switch-context"))]
    output.mkdir(parents=True)
    frozen = {"schema_version": "v3-freeze-1", "created_unix": time.time(), "code_sha256": source_manifest(),
        "predictor_sha256": sha256(predictor), "predictor_path": str(predictor.resolve()),
        "cells": [{"name": f"{name}-vs-{opponent}", "agent_a": agent, "agent_b": opponent, "games": 24} for name, agent, opponent in schedule],
        "planned_games": 144, "overall_wall_limit_seconds": 600,
        "probability_primary_targets": ["random", "max-base-power"],
        "ablation": "constant vs conditional uses identical switch-aware scoring; V2 is a separate reference",
        "rules": "no refitting/tuning; concurrency 1; loopback; same team/side cells, seed and budgets; simulator randomness unmatched"}
    write_json(output / "freeze.json", frozen)
    started = time.monotonic()
    summaries, audits, paths = {}, {}, []
    for name, agent, opponent in schedule:
        if sha256(predictor) != frozen["predictor_sha256"] or source_manifest() != frozen["code_sha256"]:
            raise ValueError("Frozen predictor/source changed during benchmark")
        remaining = 600 - (time.monotonic() - started)
        if remaining < 30:
            break
        path = output / f"{name}-vs-{opponent}"
        config = replace(base, agent_a=agent, agent_b=opponent, predictor=str(predictor.resolve()), run_timeout=min(base.run_timeout, remaining))
        print(f"Starting {path.name}: 24 games, concurrency 1", flush=True)
        summaries[path.name] = await run(config, path, start_server=True)
        audits[path.name] = audit_predictions(path)
        paths.append(path)
        if summaries[path.name]["completed"] != 24 or summaries[path.name]["invalid_action_incidents"]:
            break  # preserve incomplete evidence; no cleanup outcome becomes a win
    quality = None
    if paths:
        dataset = output / "evaluation-dataset"
        build_dataset(paths, dataset, role="evaluation")
        quality = evaluate_predictor(dataset, predictor, output / "probability-quality", "evaluation", ["random", "max-base-power"])
    result = {"schema_version": "v3-benchmark-1", "planned_games": 144,
        "completed_games": sum(s["completed"] for s in summaries.values()), "unstarted_cells": 6 - len(paths),
        "wall_seconds_including_audits": time.monotonic() - started, "cells": summaries, "audits": audits,
        "probability_quality": quality, "freeze_sha256": sha256(output / "freeze.json"),
        "final_source_matches_freeze": source_manifest() == frozen["code_sha256"],
        "final_predictor_matches_freeze": sha256(predictor) == frozen["predictor_sha256"]}
    write_json(output / "summary.json", result)
    write_json(output / "artifact-hashes.json", {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob("*")) if p.is_file()})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--predictor", type=Path, default=ROOT / "models/v3-counts.json")
    args = parser.parse_args()
    result = asyncio.run(benchmark(args.output.resolve(), args.predictor.resolve()))
    print(json.dumps({"output": str(args.output), "completed_games": result["completed_games"],
                      "wall_seconds": result["wall_seconds_including_audits"]}, indent=2))
    raise SystemExit(0 if result["completed_games"] == result["planned_games"] else 1)
