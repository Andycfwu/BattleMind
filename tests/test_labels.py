import copy
from dataclasses import asdict

from battlemind.adapter import snapshot_request
from battlemind.labels import build_labels, genuine_switch_move_choice, label_summary, snapshot_hash
from battlemind.runner import scheduled_match


def decision(turn_request, tracker, side="a", choice="move:psychic", rqid=7):
    obs, mapping = snapshot_request(turn_request, 1, tracker)
    data = asdict(obs)
    # Match the serialization boundary used by the journals.
    import json
    data = json.loads(json.dumps(data))
    data["request_id"] = rqid
    return {"match": 0, "player": side, "decision_id": f"m0:{side}:r{rqid}",
            "snapshot_sha256": snapshot_hash(data), "observation": data,
            "chosen_action": choice, "command": mapping[choice].split("|")[0] + f"|{rqid}"}


def test_distinct_request_ids_pair_only_after_authoritative_commit(turn_request, tracker):
    a = decision(turn_request, tracker)
    b = decision(turn_request, tracker, "b", "switch:2", 8)
    labels = build_labels([a, b], {}, {"inputLog": [">p1 move psychic"]}, {"a": "p1", "b": "p2"}, "timeout")
    assert labels[0]["observer_decision_id"] is None
    assert labels[1]["intended_kind"] == "unknown"
    labels = build_labels([a, b], {}, {"inputLog": [">p1 move psychic", ">p2 switch 2"]}, {"a": "p1", "b": "p2"}, "completed")
    assert [r["intended_kind"] for r in labels] == ["move_choice", "voluntary_switch"]
    assert labels[1]["observer_decision_id"] == a["decision_id"]
    assert labels[1]["observer_snapshot_sha256"] == a["snapshot_sha256"]
    assert labels[1]["voluntary_switch_target"] == 1
    assert labels[0]["voluntary_switch_target"] == 0


def test_forced_replacement_not_voluntary_and_no_fake_pair(turn_request, tracker):
    turn_request["forceSwitch"] = [True]
    turn_request.pop("active")
    a = decision(turn_request, tracker, choice="switch:2")
    labels = build_labels([a], {}, {"inputLog": [">p1 switch 2"]}, {"a": "p1"}, "completed")
    assert labels[0]["intended_kind"] == "forced_replacement"
    assert labels[0]["genuine_switch_move_choice"] is False
    assert labels[0]["voluntary_switch_target"] is None
    assert labels[0]["observer_decision_id"] is None


def test_missing_rejected_misaligned_and_unlocked_are_unknown(turn_request, tracker):
    a = decision(turn_request, tracker)
    b = decision(turn_request, tracker, "b", rqid=8)
    absent = build_labels([a, b], {}, None, {"a": "p1", "b": "p2"}, "completed")
    assert all(r["commit_status"] == "unknown" for r in absent)
    mismatched = build_labels([a, b], {}, {"inputLog": [">p1 move recover", ">p2 move psychic"]}, {"a": "p1", "b": "p2"}, "completed")
    assert mismatched[0]["intended_kind"] == "unknown"
    assert all(r["observer_decision_id"] is None for r in mismatched)
    a2 = copy.deepcopy(a)
    a2["decision_id"] = "later"
    labels = build_labels([a, a2], {}, {"inputLog": [">p1 move psychic", ">forcewin p2"]}, {"a": "p1"}, "truncated")
    assert labels[0]["commit_status"] == "verified"
    assert labels[1]["unknown_reason"] == "no_committed_choice_for_attempt"
    assert label_summary(labels)["coverage"] == 0.5


def test_intention_and_execution_are_separate(turn_request, tracker):
    a = decision(turn_request, tracker)
    before = a["observation"]["public_history"]
    history = before + [{"turn": 1, "kind": "cant", "actor": "own:1", "values": ["par"]}]
    labels = build_labels([a], {"a": history}, {"inputLog": [">p1 move psychic"]}, {"a": "p1"}, "completed")
    assert labels[0]["intended_kind"] == "move_choice"
    assert labels[0]["execution"]["status"] == "prevented_or_engine_wait"
    history = before + [{"turn": 1, "kind": "move", "actor": "own:1", "values": ["psychic"]}]
    labels = build_labels([a], {"a": history}, {"inputLog": [">p1 move psychic"]}, {"a": "p1"}, "completed")
    assert labels[0]["execution"]["status"] == "move_announced"


def test_drag_does_not_establish_intended_switch_execution(turn_request, tracker):
    a = decision(turn_request, tracker, choice="switch:2")
    history = a["observation"]["public_history"] + [{"turn": 1, "kind": "drag", "actor": "own:2", "values": ["tauros", "100/100"]}]
    labels = build_labels([a], {"a": history}, {"inputLog": [">p1 switch 2"]}, {"a": "p1"}, "completed")
    assert labels[0]["execution"]["status"] == "unknown"
    assert labels[0]["intended_kind"] == "voluntary_switch"  # from the input log, never from drag


def test_engine_wait_and_uncertain_locks_are_not_binary_training_targets(turn_request, tracker):
    a = decision(turn_request, tracker)
    for flag in ("maybe_locked", "maybe_disabled"):
        obs = {**a["observation"], flag: True}
        assert genuine_switch_move_choice(obs) is None
    obs = copy.deepcopy(a["observation"])
    obs["legal_actions"][0]["kind"] = "engine"
    assert genuine_switch_move_choice(obs) is False


def test_balanced_schedule_covers_all_pairs_assignments_and_sides():
    from collections import Counter
    schedule = [scheduled_match(i, 4) for i in range(24)]
    assert len({(a["a"], a["b"], side) for a, side in schedule}) == 24
    assert Counter(side for _, side in schedule) == {"a": 12, "b": 12}
    for team in range(4):
        assert sum(a["a"] == team for a, _ in schedule) == 6
        assert sum(a["b"] == team for a, _ in schedule) == 6
