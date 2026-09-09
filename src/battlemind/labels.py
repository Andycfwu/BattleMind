"""Post-match privileged recording. Nothing in this module is a policy feature.

Local attempts are checked against Showdown's inputLog, which is populated by
commitChoices only after all required choices are locked. No turn-number-only join
can establish commitment. Pairing uses verified decisions, never true hidden teams.
"""

import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any


def snapshot_hash(observation: dict) -> str:
    return hashlib.sha256(json.dumps(observation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def engine_record(log_root: Path, tags: set[str], usernames: set[str],
                        timeout: float = 3) -> tuple[dict | None, Path | None, str | None]:
    """Read only after the local players have stopped. Reject stale/wrong game files."""
    if not tags:
        return None, None, "no_battle_started"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for tag in sorted(tags):
            for path in log_root.glob(f"*/gen1ou/*/{tag.removeprefix('battle-')}*.log.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue  # the official async end-of-battle write may still be in progress
                if data.get("roomid") == tag and {data.get("p1"), data.get("p2")} == usernames:
                    return data, path, None
        await asyncio.sleep(0.05)
    return None, None, "official_end_log_missing_or_identity_mismatch"


def expected_engine_choice(row: dict) -> str:
    action = next(a for a in row["observation"]["legal_actions"] if a["id"] == row["chosen_action"])
    if action["kind"] in {"move", "engine"}:
        return f"move {action['move_id']}"
    return row["command"].removeprefix("/choose ").split("|", 1)[0]


def genuine_switch_move_choice(obs: dict) -> bool | None:
    if obs["request_kind"] == "forced_switch":
        return False
    if obs.get("maybe_locked") or obs.get("maybe_disabled"):
        return None
    kinds = {a["kind"] for a in obs["legal_actions"]}
    return "move" in kinds and "switch" in kinds and "engine" not in kinds


def intended_kind(row: dict) -> str:
    obs = row["observation"]
    action = next(a for a in obs["legal_actions"] if a["id"] == row["chosen_action"])
    if obs["request_kind"] == "forced_switch":
        return "forced_replacement" if action["kind"] == "switch" else "unknown"
    return {"switch": "voluntary_switch", "move": "move_choice", "engine": "engine_action"}[action["kind"]]


def execution_evidence(row: dict, history: list[dict], end: int, complete_stream: bool) -> dict:
    obs = row["observation"]
    start = len(obs["public_history"])
    if history[:start] != obs["public_history"] or end < start:
        return {"status": "unknown", "reason": "history_prefix_mismatch", "events": []}
    action = next(a for a in obs["legal_actions"] if a["id"] == row["chosen_action"])
    active = next((m for m in obs["own_team"] if m["active"]), None)
    slot = action["team_slot"] if action["kind"] == "switch" else active["slot"] if active else None
    actor = f"own:{slot}"
    evidence = [{"index": i, **event} for i, event in enumerate(history[start:end], start) if event["actor"] == actor]
    if action["kind"] == "switch":
        matches = [e for e in evidence if e["kind"] == "switch"]
        # A drag is a game effect, never evidence of a player's selected switch.
        status = "switch_observed" if len(matches) == 1 else "unknown"
    else:
        matches = [e for e in evidence if e["kind"] == "move" and e["values"] == [action["move_id"]]]
        status = "move_announced" if len(matches) == 1 else "unknown"
        if not matches:
            matches = [e for e in evidence if e["kind"] == "cant"]
            if len(matches) == 1:
                status = "prevented_or_engine_wait"
            elif complete_stream:
                status = "not_announced"  # no assertion of hit, damage, or exact cause
    return {"status": status, "events": matches,
            "reason": "announcement is not proof of a hit/effect; missing or multiple events stay unknown"}


def build_labels(rows: list[dict], histories: dict[str, list[dict]], record: dict | None,
                 roles: dict[str, str], match_status: str, missing_reason: str | None = None) -> list[dict]:
    committed: dict[str, list[tuple[int, str]]] = {"p1": [], "p2": []}
    if record:
        for index, line in enumerate(record.get("inputLog", [])):
            match = re.fullmatch(r">(p[12]) (move .+|switch \d+)", line)
            if match:
                committed[match[1]].append((index, match[2]))
    result = []
    for side in ("a", "b"):
        attempts = [r for r in rows if r["player"] == side]
        actions = committed.get(roles.get(side, ""), [])
        # Only a complete sequence or an exact prefix on an incomplete match is safe.
        alignment_ok = record is not None and len(actions) <= len(attempts)
        if match_status == "completed" and len(actions) != len(attempts):
            alignment_ok = False
        for index, row in enumerate(attempts):
            obs = row["observation"]
            expected = expected_engine_choice(row)
            found = actions[index] if index < len(actions) else None
            verified = bool(alignment_ok and found and found[1] == expected)
            if found and found[1] != expected:
                # Do not search ahead for a convenient matching move; repeated moves
                # would create false labels. All later decisions on this side stay unknown.
                alignment_ok = False
            if verified:
                reason = None
            elif record is None:
                reason = missing_reason or "official_end_log_missing"
            elif not found:
                reason = "no_committed_choice_for_attempt"
            else:
                reason = "engine_choice_or_sequence_mismatch"
            history = histories.get(side, [])
            end = len(attempts[index + 1]["observation"]["public_history"]) if index + 1 < len(attempts) else len(history)
            eligibility = genuine_switch_move_choice(obs) if verified else None
            label = intended_kind(row) if verified else "unknown"
            result.append({"schema_version": "2.0", "match": row["match"], "player": side,
                "match_status": match_status,
                "decision_id": row["decision_id"], "snapshot_sha256": row["snapshot_sha256"],
                "request_id": obs["request_id"], "turn": obs["turn"], "request_kind": obs["request_kind"],
                "commit_status": "verified" if verified else "unknown", "unknown_reason": reason,
                "engine_input_index": found[0] if verified else None,
                "committed_engine_choice": found[1] if verified else None,
                "intended_kind": label, "genuine_switch_move_choice": eligibility,
                "voluntary_switch_target": int(label == "voluntary_switch") if eligibility is True else None,
                "execution": execution_evidence(row, history, end, match_status == "completed") if verified else
                             {"status": "unknown", "reason": "unverified commitment", "events": []},
                "observer_decision_id": None, "observer_snapshot_sha256": None,
                "pairing_reason": "no_verified_simultaneous_move_request"})
    # Rqid is per request (different for each player), not a shared turn ID.
    for label in result:
        if label["commit_status"] != "verified" or label["request_kind"] != "move":
            continue
        candidates = [other for other in result if other["player"] != label["player"]
                      and other["turn"] == label["turn"] and other["request_kind"] == "move"
                      and other["commit_status"] == "verified"]
        same_side = [other for other in result if other["player"] == label["player"]
                     and other["turn"] == label["turn"] and other["request_kind"] == "move"]
        if len(candidates) == 1 and len(same_side) == 1:
            other = candidates[0]
            # Both entries must be adjacent in the official commit input sequence.
            if abs(other["engine_input_index"] - label["engine_input_index"]) == 1:
                label["observer_decision_id"] = other["decision_id"]
                label["observer_snapshot_sha256"] = other["snapshot_sha256"]
                label["pairing_reason"] = None
    return sorted(result, key=lambda r: (r["match"], r["request_id"], r["player"]))


def label_summary(labels: list[dict]) -> dict[str, Any]:
    verified = sum(r["commit_status"] == "verified" for r in labels)
    eligible = [r for r in labels if r["genuine_switch_move_choice"] is True and r["observer_decision_id"]
                and r["match_status"] == "completed"]
    return {"attempts": len(labels), "verified_intended_choices": verified,
            "unknown_intended_choices": len(labels) - verified,
            "coverage": verified / len(labels) if labels else None,
            "intended_kinds": dict(Counter(r["intended_kind"] for r in labels)),
            "unknown_reasons": dict(Counter(r["unknown_reason"] for r in labels if r["unknown_reason"])),
            "execution_statuses": dict(Counter(r["execution"]["status"] for r in labels)),
            "paired_opponent_targets": len(eligible),
            "paired_voluntary_switches": sum(r["voluntary_switch_target"] == 1 for r in eligible),
            "paired_move_choices": sum(r["voluntary_switch_target"] == 0 for r in eligible),
            "eligibility_unknown": sum(r["genuine_switch_move_choice"] is None for r in labels)}


def audit_labels(run: Path) -> dict:
    """Rebuild labels from immutable evidence and reject corruption/misalignment."""
    rows = read_jsonl(run / "decisions.jsonl")
    labels = read_jsonl(run / "privileged/labels.jsonl")
    battles = read_jsonl(run / "battles.jsonl")
    events = read_jsonl(run / "events.jsonl")
    by_id = {r["decision_id"]: r for r in rows}
    if len(by_id) != len(rows) or {r["decision_id"] for r in labels} != set(by_id) or len(labels) != len(rows):
        raise ValueError("Labels/decisions must have a one-to-one ID mapping")
    submissions = {(e["match"], e["player"], e["request_id"]) for e in events if e["kind"] == "submitted"}
    for row in rows:
        obs = row["observation"]
        if snapshot_hash(obs) != row["snapshot_sha256"]:
            raise ValueError("Snapshot hash mismatch")
        if row["chosen_action"] not in {a["id"] for a in obs["legal_actions"]}:
            raise ValueError("Choice is not legal in its snapshot")
        if row["legal_mapping"].get(row["chosen_action"]) != row["command"]:
            raise ValueError("Choice command differs from its legal mapping")
    for battle in battles:
        attempts = [r for r in rows if r["match"] == battle["match"]]
        if not attempts:
            continue
        evidence = battle.get("engine_record")
        record = None
        if evidence:
            path = (run / evidence["path"]).resolve()
            if not path.is_relative_to((run / "privileged").resolve()):
                raise ValueError("Engine evidence must stay in privileged run storage")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
                raise ValueError("Engine evidence hash mismatch")
            record = json.loads(raw)
            if record.get("roomid") not in battle["battle_tags"]:
                raise ValueError("Engine evidence is for a different battle")
        histories = json.loads((run / "privileged" / f"{battle['match']:03d}-histories.json").read_text())
        actual = [r for r in labels if r["match"] == battle["match"]]
        unknown_reason = next((r["unknown_reason"] for r in actual if r["unknown_reason"]), None)
        rebuilt = build_labels(attempts, histories, record, battle["player_roles"], battle["status"], unknown_reason)
        if rebuilt != actual:
            raise ValueError(f"Rebuilt labels differ for match {battle['match']}")
        if battle["labels"] != label_summary(actual):
            raise ValueError("Battle label counts disagree")
        for label in actual:
            if label["commit_status"] == "verified" and (label["match"], label["player"], label["request_id"]) not in submissions:
                raise ValueError("Verified choice has no matching client submission record")
    return {"ok": True, "decisions": len(rows), "labels": len(labels), "battles": len(battles)}
