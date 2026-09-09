"""Observer-owned boundary between finished encounters and the next frozen policy."""

from dataclasses import asdict
from pathlib import Path

from .dataset import write_json
from .opponent_memory import ObserverMemory, digest, encounter_evidence
from .schema import DecisionSnapshot, PublicEvent
from .supervised import PredictorBundle


class EncounterController:
    def __init__(self, manager: ObserverMemory, session_key: str, observer_key: str, mode: str, predictor: PredictorBundle):
        if mode not in {"none", "pooled", "individual"}:
            raise ValueError("Unknown memory mode")
        self.manager, self.session_key, self.observer_key = manager, session_key, observer_key
        self.mode, self.predictor = mode, predictor
        self.pending = None

    def metadata(self) -> dict:
        return {"version": "v6-routing-1", "mode": self.mode, "observer_key": self.observer_key,
            "session_key": self.session_key, "ordinal_start": self.manager.next_ordinal,
            "session_encounters_before": self.manager.encounters.get(self.session_key, 0)}

    def before(self, output: Path, match: int):
        if self.pending is not None:
            raise ValueError("Encounter already pending")
        ordinal = self.manager.next_ordinal
        context = self.manager.begin(self.session_key, ordinal)
        self.pending = {**self.metadata(), "match": match, "ordinal": ordinal,
            "pre_context": asdict(context), "pre_sha256": context.sha256}
        write_json(output / f"memory/{match:03d}-before.json", self.pending)
        return context

    def after(self, output: Path, match: int, observations: tuple[DecisionSnapshot, ...],
              history: tuple[PublicEvent, ...], completed: bool):
        if self.pending is None or self.pending["match"] != match:
            raise ValueError("Missing pre-encounter cutoff")
        # Deliberately exported before the privileged recorder runs. No labels/results/other journal.
        public = {"version": "v6-observer-evidence-1", "observations": [asdict(o) for o in observations],
                  "public_history": [asdict(e) for e in history], "completed": completed}
        write_json(output / f"observer/{match:03d}.json", public)
        evidence = encounter_evidence(observations, history, self.predictor, completed)
        after = self.manager.finish(self.session_key, self.pending["ordinal"], evidence)
        update = {**self.pending, "public_sha256": digest(public), "public_path": f"observer/{match:03d}.json",
            "evidence": evidence, "post_context": asdict(after), "post_sha256": after.sha256}
        write_json(output / f"memory/{match:03d}-after.json", update)
        self.pending = None
