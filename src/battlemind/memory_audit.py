"""Deterministic public-memory replay; deliberately never reads labels or end logs."""

from dataclasses import asdict
import json
from pathlib import Path

from .adaptation import AdaptedAgent
from .labels import read_jsonl
from .opponent_memory import ObserverMemory, digest, encounter_evidence
from .schema import PublicEvent, snapshot_from_dict


def replay_cell(path: Path, manager: ObserverMemory, bundle, checkpoint) -> dict:
    metadata = json.loads((path / "run.json").read_text())
    routing = metadata["adaptation"]
    if (manager.next_ordinal != routing["ordinal_start"] or routing["session_encounters_before"] != manager.encounters.get(routing["session_key"], 0)
        or metadata["predictor"]["sha256"] != bundle.sha256 or metadata["policy_checkpoints"]["a"]["sha256"] != checkpoint.sha256):
        raise ValueError("Observer chronology/artifact mismatch")
    decisions, updates = [], []
    for match in range(metadata["config"]["battles"]):
        before = json.loads((path / f"memory/{match:03d}-before.json").read_text())
        after = json.loads((path / f"memory/{match:03d}-after.json").read_text())
        public = json.loads((path / f"observer/{match:03d}.json").read_text())
        if set(public) != {"version", "observations", "public_history", "completed"} or public["version"] != "v6-observer-evidence-1":
            raise ValueError("Unexpected observer evidence fields")
        ordinal = manager.next_ordinal
        prior_encounters = manager.encounters.get(routing["session_key"], 0)
        context = manager.begin(routing["session_key"], ordinal)
        if (before["ordinal"] != ordinal or before["session_key"] != routing["session_key"]
            or before["ordinal_start"] != ordinal or before["session_encounters_before"] != prior_encounters
            or before["observer_key"] != routing["observer_key"] or before["mode"] != routing["mode"]
            or before["pre_sha256"] != context.sha256 or before["pre_context"] != asdict(context)
            or any(after.get(k) != v for k, v in before.items()) or after["public_sha256"] != digest(public)):
            raise ValueError("Memory pre-cutoff/digest/routing mismatch")
        observations = tuple(snapshot_from_dict(o) for o in public["observations"])
        history = tuple(PublicEvent(**{**e, "values": tuple(e["values"])}) for e in public["public_history"])
        evidence = encounter_evidence(observations, history, bundle, public["completed"])
        if evidence != after["evidence"]:
            raise ValueError("Memory evidence differs from observer public history")
        # Only this player's journal verifies play. It is never a memory-update argument.
        journal = read_jsonl(path / f"privileged/attempts/{match:03d}-a.jsonl")
        if len(journal) != len(observations):
            raise ValueError("Observer journal/export alignment mismatch")
        agent = AdaptedAgent(bundle, checkpoint, context, routing["mode"])
        for row, obs, proxy in zip(journal, observations, evidence["records"]):
            predicted = agent.evaluate(obs)
            serialized = json.loads(json.dumps(asdict(predicted)))
            if (row["player"] != "a" or row["observation"] != asdict_json(obs)
                or row["snapshot_sha256"] != digest(asdict(obs)) or row["prediction_evaluation"] != serialized
                or row["chosen_action"] != predicted.chosen_action or row["action_scores"] != serialized["scores"]):
                raise ValueError("Frozen memory prediction/choice replay mismatch")
            decisions.append({"match": match, "decision_id": row["decision_id"], "snapshot_sha256": row["snapshot_sha256"],
                "probabilities": dict(predicted.shadow_probabilities), "choices": dict(predicted.shadow_choices),
                "played_choice": predicted.chosen_action, "session_encounter_index": prior_encounters,
                "cold_start": prior_encounters == 0, "individual_fallback": context.individual.encounters < 2,
                "support": {"pooled": context.pooled.encounters, "individual": context.individual.encounters},
                "proxy": proxy["proxy"], "proxy_reason": proxy["reason"], "memory_sha256": context.sha256})
        rebuilt = manager.finish(routing["session_key"], ordinal, evidence)
        if rebuilt.sha256 != after["post_sha256"] or asdict(rebuilt) != after["post_context"]:
            raise ValueError("Post-encounter memory update mismatch")
        updates.append({"match": match, "ordinal": ordinal, "completed": public["completed"],
            "admitted": evidence["admitted"], "switch_proxies": evidence["switch_proxies"],
            "skipped": evidence["skipped"], "update_eligible": evidence["update_eligible"],
            "residual": evidence["encounter_residual"], "pre_sha256": context.sha256, "post_sha256": rebuilt.sha256})
    return {"ok": True, "decisions": decisions, "updates": updates}


def asdict_json(value):
    return json.loads(json.dumps(asdict(value)))
