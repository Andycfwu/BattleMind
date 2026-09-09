"""Durable single-use budgets. No resumable RNG/state reconstruction is promised."""

import json
from pathlib import Path
import time

from .dataset import write_json

PHASES = ("training", "selection", "final")


class ExperimentLedger:
    def __init__(self, root: Path, configuration: dict, clock=time.monotonic):
        self.root, self.clock, self.started = root, clock, clock()
        self.active = None
        self.phase_started = None
        if (configuration["total_games"] > 1200 or configuration["total_seconds"] > 1200
            or sum(configuration["phase_games"].values()) != configuration["total_games"]
            or sum(configuration["phase_seconds"].values()) > configuration["total_seconds"]):
            raise ValueError("Experiment allocations exceed aggregate budget")
        self.state = {"schema_version": "v5-ledger-1", "status": "running", "resume_supported": False,
            "created_unix": time.time(), "total_game_allocation": configuration["total_games"],
            "total_wall_allocation": configuration["total_seconds"], "requested_games": 0,
            "consumed_wall_seconds": 0.0, "final_reserved_before_training": True,
            "phases": {phase: {"status": "reserved", "game_allocation": configuration["phase_games"][phase],
                "wall_allocation": configuration["phase_seconds"][phase], "requested_games": 0,
                "consumed_wall_seconds": 0.0} for phase in PHASES},
            "runs": [], "battle_partitions": {}, "failure": None}
        write_json(root / "ledger.json", self.state)

    def save(self):
        self.state["consumed_wall_seconds"] = self.clock() - self.started
        temporary = self.root / "ledger.pending.json"
        temporary.write_text(json.dumps(self.state, indent=2, allow_nan=False) + "\n")
        temporary.replace(self.root / "ledger.json")

    def begin(self, phase: str):
        if (phase not in PHASES or self.active is not None or self.state["phases"][phase]["status"] != "reserved"
            or any(self.state["phases"][p]["status"] != "finished" for p in PHASES[:PHASES.index(phase)])):
            raise ValueError("Invalid phase order or attempted resume")
        if self.clock() - self.started >= self.state["total_wall_allocation"]:
            raise ValueError("Aggregate wall budget exhausted")
        self.active, self.phase_started = phase, self.clock()
        self.state["phases"][phase]["status"] = "running"
        self.save()

    def remaining(self) -> float:
        if self.active is None:
            raise ValueError("No active experiment phase")
        return min(self.state["total_wall_allocation"] - (self.clock() - self.started),
                   self.state["phases"][self.active]["wall_allocation"] - (self.clock() - self.phase_started))

    def reserve_run(self, games: int, metadata: dict) -> int:
        if self.active is None or type(games) is not int or games < 1:
            raise ValueError("A positive run reservation needs an active phase")
        phase = self.state["phases"][self.active]
        if (phase["requested_games"] + games > phase["game_allocation"]
            or self.state["requested_games"] + games > self.state["total_game_allocation"]
            or self.remaining() < 20):
            raise ValueError("Experiment game/wall budget exhausted; final reservation cannot be borrowed")
        phase["requested_games"] += games
        self.state["requested_games"] += games
        self.state["runs"].append({**metadata, "phase": self.active, "requested_games": games, "status": "reserved"})
        self.save()  # durable before any game can start
        return len(self.state["runs"]) - 1

    def finish_run(self, index: int, run_id: str, matches: list[int], summary: dict, audit: dict):
        record = self.state["runs"][index]
        keys = [f"{run_id}:{match}" for match in matches]
        if len(set(keys)) != len(keys) or any(k in self.state["battle_partitions"] for k in keys):
            raise ValueError("Battle overlap across runs/training/selection/final")
        if len(keys) != record["requested_games"]:
            raise ValueError("Missing terminal accounting rows")
        self.state["battle_partitions"].update({k: record["phase"] for k in keys})
        record.update(status="recorded", run_id=run_id, summary=summary, audit=audit)
        self.save()

    def finish_phase(self):
        if self.active is None:
            raise ValueError("No phase to finish")
        phase = self.state["phases"][self.active]
        phase["consumed_wall_seconds"] = self.clock() - self.phase_started
        if self.remaining() <= 0:
            raise ValueError("Experiment phase wall budget exhausted")
        if phase["requested_games"] != phase["game_allocation"]:
            raise ValueError("Experiment phase did not finish its declared schedule")
        if any(r["status"] != "recorded" for r in self.state["runs"] if r["phase"] == self.active):
            raise ValueError("Experiment phase contains missing run evidence")
        phase["status"] = "finished"
        self.active = None
        self.save()

    def finish(self, failure: str | None):
        if self.active is not None:
            phase = self.state["phases"][self.active]
            phase.update(status="failed", consumed_wall_seconds=self.clock() - self.phase_started)
        if self.clock() - self.started > self.state["total_wall_allocation"]:
            failure = failure or "Aggregate wall budget exhausted"
        if any(p["status"] != "finished" for p in self.state["phases"].values()):
            failure = failure or "Experiment stopped before all reserved phases finished"
        self.state.update(status="failed" if failure else "finished", failure=failure)
        self.save()
