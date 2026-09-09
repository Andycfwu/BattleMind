"""Single-use development/final reservations; no transfer, refund, retry or resume."""

import json
from pathlib import Path
import time

from .dataset import write_json


class AdaptationLedger:
    def __init__(self, root: Path, config: dict, clock=time.monotonic):
        if (config["total_games"] > 864 or config["total_seconds"] > 900
            or sum(config["games"].values()) != config["total_games"]
            or sum(config["seconds"].values()) > config["total_seconds"]):
            raise ValueError("Invalid adaptation budget")
        self.root, self.clock, self.started = root, clock, clock()
        self.active, self.phase_start = None, None
        self.state = {"schema_version": "v6-budget-1", "status": "running", "resume_supported": False,
            "final_reserved_before_development": True, "requested_games": 0, "total_games": config["total_games"],
            "total_seconds": config["total_seconds"], "consumed_seconds": 0.0, "failure": None,
            "phases": {p: {"allocated_games": config["games"][p], "allocated_seconds": config["seconds"][p],
                "requested_games": 0, "consumed_seconds": 0.0, "status": "reserved"} for p in ("development", "final")},
            "runs": [], "battle_partitions": {}, "resets": []}
        write_json(root / "ledger.json", self.state)

    def save(self):
        self.state["consumed_seconds"] = self.clock() - self.started
        temporary = self.root / "ledger.pending.json"
        temporary.write_text(json.dumps(self.state, indent=2, allow_nan=False))
        temporary.replace(self.root / "ledger.json")

    def begin(self, phase: str):
        if (phase not in self.state["phases"] or self.active is not None
            or self.state["phases"][phase]["status"] != "reserved"
            or (phase == "final" and self.state["phases"]["development"]["status"] != "finished")):
            raise ValueError("Invalid phase order/resume")
        self.active, self.phase_start = phase, self.clock()
        self.state["phases"][phase]["status"] = "running"
        self.save()

    def remaining(self):
        if self.active is None:
            raise ValueError("No active phase")
        return min(self.state["total_seconds"] - (self.clock() - self.started),
                   self.state["phases"][self.active]["allocated_seconds"] - (self.clock() - self.phase_start))

    def reserve(self, metadata: dict, games: int):
        phase = self.state["phases"][self.active]
        if (type(games) is not int or games < 1 or self.remaining() < 15
            or phase["requested_games"] + games > phase["allocated_games"]
            or self.state["requested_games"] + games > self.state["total_games"]):
            raise ValueError("Adaptation game/wall budget exhausted; no borrowing final allocation")
        phase["requested_games"] += games
        self.state["requested_games"] += games
        self.state["runs"].append({**metadata, "phase": self.active, "requested_games": games, "status": "reserved"})
        self.save()
        return len(self.state["runs"]) - 1

    def record(self, index: int, run_id: str, battles: list[dict], summary: dict):
        record = self.state["runs"][index]
        keys = [f"{run_id}:{b['match']}" for b in battles]
        if len(keys) != record["requested_games"] or len(set(keys)) != len(keys) or set(keys) & self.state["battle_partitions"].keys():
            raise ValueError("Missing or overlapping encounter accounting")
        self.state["battle_partitions"].update({k: {"phase": self.active, "group": record["group"]} for k in keys})
        record.update(status="recorded", run_id=run_id, summary=summary)
        self.save()

    def finish_phase(self):
        phase = self.state["phases"][self.active]
        phase["consumed_seconds"] = self.clock() - self.phase_start
        if (self.remaining() <= 0 or phase["requested_games"] != phase["allocated_games"]
            or any(r["status"] != "recorded" for r in self.state["runs"] if r["phase"] == self.active)):
            raise ValueError("Phase incomplete or wall budget exhausted")
        phase["status"] = "finished"
        self.active = None
        self.save()

    def finish(self, failure=None):
        if self.active is not None:
            self.state["phases"][self.active].update(status="failed", consumed_seconds=self.clock() - self.phase_start)
        if any(p["status"] != "finished" for p in self.state["phases"].values()):
            failure = failure or "Incomplete adaptation schedule"
        if self.clock() - self.started > self.state["total_seconds"]:
            failure = failure or "Aggregate wall budget exhausted"
        self.state.update(status="failed" if failure else "finished", failure=failure)
        self.save()
