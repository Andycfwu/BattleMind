"""Single-use reservations, dispatch accounting and separately stopped monotonic clocks."""

import json
from pathlib import Path
import time

from .dataset import write_json


def request_accounting(planned: int, records: list[dict], battles: list[dict]) -> dict:
    """Requested means dispatched to the bounded runner, not necessarily challenged."""
    reserved = sum(r.get("reserved_games", r["requested_games"]) for r in records)
    requested = sum(r["requested_games"] for r in records)
    if not 0 <= len(battles) <= requested <= reserved <= planned:
        raise ValueError("Invalid planned/reserved/requested/recorded accounting")
    not_started = sum(b["status"] == "not_started" for b in battles)
    return {"planned_games": planned, "reserved_games": reserved, "requested_games": requested,
        "reserved_not_requested_games": reserved - requested,
        "never_requested_games": planned - requested,
        "recorded_games": len(battles), "completed_games": sum(b["status"] == "completed" for b in battles),
        "started_games": len(battles) - not_started,
        "never_started_games": planned - requested + not_started,
        "missing_requested_records": requested - len(battles),
        "start_status_unknown_games": requested - len(battles)}


class AdaptationLedger:
    def __init__(self, root: Path, config: dict, clock=time.monotonic, started=None):
        overhead = config.get("overhead_seconds", config["total_seconds"] - sum(config["seconds"].values()))
        if (config["total_games"] > 720 or config["total_seconds"] > 1800 or overhead < 0
            or sum(config["games"].values()) != config["total_games"]
            or sum(config["seconds"].values()) + overhead != config["total_seconds"]):
            raise ValueError("Invalid adaptation budget")
        self.root, self.clock = root, clock
        self.started = clock() if started is None else started
        self.active, self.phase_start = None, None
        self.state = {"schema_version": "v6-budget-2", "status": "running", "resume_supported": False,
            "final_reserved_before_development": True, "requested_games": 0, "reserved_games": 0,
            "total_games": config["total_games"], "total_seconds": config["total_seconds"],
            "overhead_allocated_seconds": overhead, "consumed_seconds": 0.0, "failure": None,
            "timing": {"collection_stop_elapsed_seconds": None, "setup_seconds": None,
                "reporting_audit_seconds": None, "overhead_seconds": None, "finalized": False},
            "phases": {p: {"allocated_games": config["games"][p], "allocated_seconds": config["seconds"][p],
                "allocation_reserved_games": config["games"][p], "reserved_games": 0, "requested_games": 0,
                "completed_games": 0, "consumed_seconds": 0.0, "start_elapsed_seconds": None,
                "stop_elapsed_seconds": None, "status": "reserved"} for p in ("development", "final")},
            "runs": [], "battle_partitions": {}, "resets": []}
        write_json(root / "ledger.json", self.state)

    def save(self):
        if self.state["timing"]["finalized"]:
            return
        self.state["consumed_seconds"] = self.clock() - self.started
        self._write()

    def _write(self):
        temporary = self.root / "ledger.pending.json"
        temporary.write_text(json.dumps(self.state, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(self.root / "ledger.json")

    def begin(self, phase: str):
        if (phase not in self.state["phases"] or self.active is not None
            or self.state["timing"]["collection_stop_elapsed_seconds"] is not None
            or self.state["phases"][phase]["status"] != "reserved"
            or (phase == "final" and self.state["phases"]["development"]["status"] != "finished")):
            raise ValueError("Invalid phase order/resume")
        if self.overhead_remaining() <= 0:
            raise ValueError("Setup/overhead budget exhausted")
        self.active, self.phase_start = phase, self.clock()
        self.state["phases"][phase].update(status="running", start_elapsed_seconds=self.phase_start - self.started)
        self.save()

    def remaining(self):
        if self.active is None:
            raise ValueError("No active phase")
        return min(self.state["total_seconds"] - (self.clock() - self.started),
            self.state["phases"][self.active]["allocated_seconds"] - (self.clock() - self.phase_start))

    def overhead_remaining(self):
        phase_seconds = sum(p["consumed_seconds"] for p in self.state["phases"].values())
        if self.active is not None:
            phase_seconds += self.clock() - self.phase_start
        return self.state["overhead_allocated_seconds"] - (self.clock() - self.started - phase_seconds)

    def reserve(self, metadata: dict, games: int):
        if self.active is None:
            raise ValueError("No active phase")
        phase = self.state["phases"][self.active]
        if (type(games) is not int or games < 1 or self.remaining() < 15
            or phase["reserved_games"] + games > phase["allocated_games"]
            or self.state["reserved_games"] + games > self.state["total_games"]):
            raise ValueError("Adaptation game/wall budget exhausted; no borrowing final allocation")
        phase["reserved_games"] += games
        self.state["reserved_games"] += games
        self.state["runs"].append({**metadata, "phase": self.active, "reserved_games": games,
            "requested_games": 0, "status": "reserved"})
        self.save()
        return len(self.state["runs"]) - 1

    def dispatch(self, index: int):
        record = self.state["runs"][index]
        if record["status"] != "reserved" or record["phase"] != self.active or self.remaining() < 15:
            raise ValueError("Invalid dispatch or exhausted reservation guard")
        record.update(status="requested", requested_games=record["reserved_games"],
            dispatch_elapsed_seconds=self.clock() - self.started)
        self.state["requested_games"] += record["requested_games"]
        self.state["phases"][self.active]["requested_games"] += record["requested_games"]
        self.save()

    def record(self, index: int, run_id: str, battles: list[dict], summary: dict):
        record = self.state["runs"][index]
        keys = [f"{run_id}:{b['match']}" for b in battles]
        if (record["status"] != "requested" or record["phase"] != self.active
            or len(keys) > record["requested_games"] or len(set(keys)) != len(keys)
            or set(keys) & self.state["battle_partitions"].keys()):
            raise ValueError("Invalid or overlapping encounter accounting")
        self.state["battle_partitions"].update({k: {"phase": self.active, "group": record["group"]} for k in keys})
        record.update(status="recorded", run_id=run_id, summary=summary,
            recorded_games=len(battles), completed_games=sum(b["status"] == "completed" for b in battles))
        self.state["phases"][self.active]["completed_games"] += record["completed_games"]
        self.save()

    def _stop_phase(self, status):
        if self.active is None:
            return
        now = self.clock()
        self.state["phases"][self.active].update(status=status, consumed_seconds=now - self.phase_start,
            stop_elapsed_seconds=now - self.started)
        self.active = self.phase_start = None
        self.save()

    def finish_phase(self):
        if self.active is None:  # A stopped phase never accrues reporting time.
            return
        phase = self.state["phases"][self.active]
        complete = (self.remaining() > 0 and phase["completed_games"] == phase["allocated_games"]
            and phase["requested_games"] == phase["allocated_games"]
            and all(r["status"] == "recorded" for r in self.state["runs"] if r["phase"] == self.active))
        self._stop_phase("finished" if complete else "failed")
        if not complete:
            raise ValueError("Phase incomplete or wall budget exhausted")

    def finish(self, failure=None):
        """Stop collection exactly once. Reporting gets a separate bounded clock."""
        timing = self.state["timing"]
        if timing["collection_stop_elapsed_seconds"] is not None:
            return
        self._stop_phase("failed")
        if any(p["status"] != "finished" for p in self.state["phases"].values()):
            failure = failure or "Incomplete adaptation schedule"
        elapsed = self.clock() - self.started
        timing.update(collection_stop_elapsed_seconds=elapsed,
            setup_seconds=elapsed - sum(p["consumed_seconds"] for p in self.state["phases"].values()))
        self.state.update(status="failed" if failure else "reporting", failure=failure)
        self.save()

    def finalize(self, failure=None):
        """Close total/report clocks once, after bulk auditing and artifact hashing."""
        timing = self.state["timing"]
        if timing["finalized"]:
            return
        self.finish(failure)
        elapsed = self.clock() - self.started
        reporting = elapsed - timing["collection_stop_elapsed_seconds"]
        overhead = timing["setup_seconds"] + reporting
        failure = self.state["failure"] or failure
        if overhead > self.state["overhead_allocated_seconds"] or elapsed > self.state["total_seconds"]:
            failure = failure or "Reporting/overhead or aggregate wall budget exhausted"
        timing.update(reporting_audit_seconds=reporting, overhead_seconds=overhead, finalized=True)
        self.state.update(status="failed" if failure else "finished", failure=failure, consumed_seconds=elapsed)
        self._write()
