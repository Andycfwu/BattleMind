import copy
from dataclasses import FrozenInstanceError, asdict, replace
import json

import pytest

from battlemind.adapter import snapshot_request
from battlemind.anticipation import SwitchAwareAgent
from battlemind.dataset import exclusion_reason, joined_examples, split_battles
from battlemind.labels import build_labels, snapshot_hash
from battlemind.prediction import (Cell, Context, CountPredictor, CountTable,
                                  context_from_snapshot, estimate_counts, table_from_dict)
from battlemind.prediction_report import probability_metrics, paired_battle_interval
from battlemind.schema import Health, LegalAction, PokemonView, snapshot_from_dict


def make_observation(request, tracker):
    return snapshot_request(request, 1, tracker)[0]


def test_round_trip_is_frozen_and_rejects_recorder_fields(turn_request, tracker):
    obs = make_observation(turn_request, tracker)
    data = json.loads(json.dumps(asdict(obs)))
    restored = snapshot_from_dict(data)
    assert restored == obs
    data["own_team"][0]["moves"].append("explosion")
    assert restored == obs
    with pytest.raises(FrozenInstanceError):
        restored.turn = 8
    with pytest.raises(TypeError):
        snapshot_from_dict({**asdict(obs), "opponent_choice": "switch 2"})
    with pytest.raises(TypeError):
        context_from_snapshot(asdict(obs))


def test_visible_features_preserve_precision_and_unknowns(turn_request, tracker):
    obs = make_observation(turn_request, tracker)
    original = asdict(obs)
    assert context_from_snapshot(obs) == Context("other", "healthy", "resisted")
    foe = replace(obs.opponent_revealed[0], health=Health(33, 100, "public_scale"), status="par")
    assert context_from_snapshot(replace(obs, opponent_revealed=(foe,))).opponent_hp == "low"
    assert context_from_snapshot(replace(obs, opponent_revealed=())) == Context("unknown", "unknown", "unknown")
    assert context_from_snapshot(replace(obs, legal_actions=())).type_pressure == "unknown"
    assert asdict(obs) == original
    assert obs.opponent_revealed[0].effective_stats is None


def test_smoothing_sparse_unseen_and_frozen_evaluation():
    a, b = Context("low", "healthy", "super"), Context("other", "healthy", "neutral")
    table = estimate_counts([(a, 1)] * 10 + [(b, 0)] * 2)
    assert table.frequency == 11 / 14
    predictor = CountPredictor(table, "conditional")
    assert predictor.predict_context(a).probability == (10 + 12 * 11 / 14) / 22
    assert predictor.predict_context(b).fallback == "sparse_context"
    assert predictor.predict_context(Context("unknown", "unknown", "unknown")).fallback == "unseen_context"
    assert CountPredictor(table, "constant").predict_context(a).probability == 11 / 14
    frozen = asdict(table)
    for _ in range(20):
        assert 0 < predictor.predict_context(a).probability < 1
    assert asdict(table) == frozen
    assert table_from_dict(json.loads(json.dumps(frozen))) == table
    with pytest.raises(FrozenInstanceError):
        table.cells[0].switches = 100
    with pytest.raises(FrozenInstanceError):
        predictor.mode = "constant"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 0])
def test_invalid_smoothing_rejected(bad):
    with pytest.raises(ValueError):
        estimate_counts([(Context("low", "healthy", "super"), 1)], prior_strength=bad)


def test_bad_counts_targets_modes_rejected():
    c = Context("low", "healthy", "super")
    with pytest.raises(ValueError):
        estimate_counts([])
    with pytest.raises(ValueError):
        estimate_counts([(c, None)])
    with pytest.raises(ValueError):
        CountTable(10, 2, (Cell(c, 10, 3),))
    with pytest.raises(ValueError):
        CountPredictor(estimate_counts([(c, 1)]), "learning")


def switch_example(turn_request, tracker):
    obs = make_observation(turn_request, tracker)
    own = PokemonView(1, "starmie", True, Health(100, 100, "exact"), "healthy", ("surf", "thunderbolt"), True, ())
    foe = PokemonView(1, "gyarados", True, Health(100, 100, "public_scale"), "healthy", (), False, ())
    bench = replace(foe, slot=2, species="rhydon", active=False)
    return replace(obs, own_team=(own,), opponent_revealed=(foe, bench), opponent_unseen=0,
        legal_actions=(LegalAction("move:thunderbolt", "move", "thunderbolt", base_power=95),
                       LegalAction("move:surf", "move", "surf", base_power=95)))


def test_prediction_changes_decision_with_identical_snapshot_and_scoring(turn_request, tracker):
    obs = switch_example(turn_request, tracker)
    c = context_from_snapshot(obs)
    low = SwitchAwareAgent(estimate_counts([(c, 0)] * 100), "constant")
    high = SwitchAwareAgent(estimate_counts([(c, 1)] * 100), "constant")
    before = asdict(obs)
    assert low.choose(obs) == "move:thunderbolt"
    assert high.choose(obs) == "move:surf"
    assert [(s.stay_score, s.switch_score) for s in low.evaluate(obs).scores] == [(s.stay_score, s.switch_score) for s in high.evaluate(obs).scores]
    assert asdict(obs) == before


def test_context_and_constant_ablation_can_change_decision(turn_request, tracker):
    obs = switch_example(turn_request, tracker)
    c, other = context_from_snapshot(obs), Context("low", "impaired", "neutral")
    table = estimate_counts([(c, 1)] * 100 + [(other, 0)] * 900)
    constant, conditional = [SwitchAwareAgent(table, mode).evaluate(obs) for mode in ("constant", "conditional")]
    assert constant.chosen_action != conditional.chosen_action
    assert constant.constant_choice == conditional.constant_choice
    assert constant.conditional_choice == conditional.conditional_choice


def test_forced_engine_and_unknown_destinations_stay_legal(turn_request, tracker):
    obs = make_observation(turn_request, tracker)
    table = estimate_counts([(context_from_snapshot(obs), 1)] * 10)
    policy = SwitchAwareAgent(table, "conditional")
    for changed in (replace(obs, request_kind="forced_switch", legal_actions=(LegalAction("switch:2", "switch", team_slot=2),)),
                    replace(obs, legal_actions=(LegalAction("engine:fight", "engine", "fight"),))):
        result = policy.evaluate(changed)
        assert not result.applied and result.chosen_action == changed.legal_actions[0].id
    unknown = replace(obs, opponent_unseen=None)
    before = asdict(unknown)
    assert policy.evaluate(unknown).anonymous_destination_weight == 1
    assert asdict(unknown) == before


def test_whole_battle_split_is_stable_separate_across_runs_and_label_independent():
    runs = {"run-a": list(range(24)), "run-b": list(range(24))}
    split = split_battles(runs, 2026, "development")
    assert len(split) == 48
    assert sum(p == "development_fit" for p in split.values()) == 36
    assert split_battles({k: v[::-1] for k, v in runs.items()}, 2026, "development") == split
    assert set(split_battles(runs, 2026, "evaluation").values()) == {"evaluation"}
    with pytest.raises(ValueError):
        split_battles({"run": [1, 1]}, 0, "development")


def joined_fixture(turn_request, tracker):
    obs = json.loads(json.dumps(asdict(make_observation(turn_request, tracker))))
    rows = []
    for side, rqid, choice in (("a", 7, "move:psychic"), ("b", 8, "switch:2")):
        data = copy.deepcopy(obs)
        data["request_id"] = rqid
        if side == "b":
            data["opponent_revealed"][0]["health"]["current"] = 20
        rows.append({"match": 0, "player": side, "decision_id": f"m0:{side}:r{rqid}",
            "snapshot_sha256": snapshot_hash(data), "observation": data, "chosen_action": choice,
            "command": ("/choose move 1" if side == "a" else "/choose switch 2") + f"|{rqid}"})
    labels = build_labels(rows, {}, {"inputLog": [">p1 move psychic", ">p2 switch 2"]}, {"a": "p1", "b": "p2"}, "completed")
    return rows, labels


def test_join_uses_observer_not_target_private_snapshot_and_detects_misalignment(turn_request, tracker):
    rows, labels = joined_fixture(turn_request, tracker)
    args = ([{"match": 0, "status": "completed"}], {"a": "heuristic", "b": "random"})
    examples, excluded = joined_examples("run", rows, labels, *args)
    assert not excluded
    assert examples[0]["features"]["opponent_hp"] == "low"  # target a uses observer b
    before = examples[0]["features"]
    rows[0]["observation"]["own_team"][0]["species"] = "gengar"
    rows[0]["observation"]["opponent_unseen"] = 100  # privileged target change, not observer input
    digest = snapshot_hash(rows[0]["observation"])
    labels[0]["snapshot_sha256"] = labels[1]["observer_snapshot_sha256"] = digest
    after, _ = joined_examples("run", rows, labels, *args)
    assert after[0]["features"] == before
    labels[0]["observer_decision_id"] = rows[0]["decision_id"]
    with pytest.raises(ValueError, match="alignment"):
        joined_examples("run", rows, labels, *args)


def test_posthoc_eligibility_only_filters_labels_and_all_reasons_remain_visible(turn_request, tracker):
    rows, labels = joined_fixture(turn_request, tracker)
    obs = snapshot_from_dict(rows[0]["observation"])
    policy = SwitchAwareAgent(estimate_counts([(context_from_snapshot(obs), 1)] * 8), "conditional")
    before = policy.evaluate(obs)
    cases = [({"match_status": "timeout"}, "incomplete_battle"),
             ({"commit_status": "unknown", "unknown_reason": "mismatch"}, "unknown_commitment:mismatch"),
             ({"intended_kind": "forced_replacement"}, "forced_replacement"),
             ({"intended_kind": "engine_action"}, "engine_mandated_action"),
             ({"genuine_switch_move_choice": None}, "unknown_choice_eligibility"),
             ({"genuine_switch_move_choice": False}, "no_meaningful_move_switch_choice"),
             ({"voluntary_switch_target": None}, "unknown_binary_target"),
             ({"observer_decision_id": None}, "no_verified_observer_join")]
    for fields, reason in cases:
        assert exclusion_reason({**labels[0], **fields}) == reason
        assert policy.evaluate(obs) == before


def test_probability_metrics_and_calibration_are_hand_checkable():
    result = probability_metrics([0, 1], [0.25, 0.75])
    assert result["brier"] == 0.0625
    import math
    assert result["log_loss"] == pytest.approx(-math.log(0.75))
    assert sum(b["count"] for b in result["calibration"]) == 2
    assert probability_metrics([], [])["brier"] is None
    for bad in ([float("nan")], [-0.1], [1.1]):
        with pytest.raises(ValueError):
            probability_metrics([1], bad)
    assert paired_battle_interval([])["intervals"] is None


def dataset_fixture(path, *, role="development"):
    from battlemind.dataset import write_json
    from battlemind.environment import sha256
    from battlemind.prediction import FEATURE_VERSION, FEATURE_DEFINITIONS
    path.mkdir()
    rows = [{"run_id": "run", "battle_key": f"run:{i}", "target_decision_id": f"m{i}:a:r7",
             "features": asdict(Context("low", "healthy", "super")), "target": y,
             "partition": "development_fit" if i < 2 else "development_check", "target_policy": "random"}
            for i, y in enumerate((0, 1, 1))]
    (path / "examples.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (path / "exclusions.jsonl").write_text("")
    manifest = {"role": role, "feature_version": FEATURE_VERSION, "feature_definitions": FEATURE_DEFINITIONS,
                "examples_sha256": sha256(path / "examples.jsonl"), "exclusions_sha256": sha256(path / "exclusions.jsonl"),
                "battle_partitions": {r["battle_key"]: r["partition"] for r in rows}, "sources": [], "exclusions": {}, "balance": {}}
    write_json(path / "manifest.json", manifest)
    return rows, manifest


def test_fit_ignores_check_targets_and_dataset_hashes_detect_corruption(tmp_path):
    from battlemind.dataset import fit_predictor, read_dataset
    from battlemind.environment import sha256
    data = tmp_path / "data"
    rows, manifest = dataset_fixture(data)
    first = fit_predictor(data, tmp_path / "first.json")
    assert first["table"]["examples"] == 2 and first["table"]["switches"] == 1
    rows[2]["target"] = 0
    (data / "examples.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match="hash"):
        read_dataset(data)
    manifest["examples_sha256"] = sha256(data / "examples.jsonl")
    (data / "manifest.json").write_text(json.dumps(manifest))
    assert fit_predictor(data, tmp_path / "second.json")["table"] == first["table"]


def test_evaluation_rejects_fit_overlap_and_refitting_evaluation(tmp_path):
    from battlemind.dataset import fit_predictor
    from battlemind.prediction_report import evaluate_predictor
    data = tmp_path / "data"
    rows, manifest = dataset_fixture(data)
    model = tmp_path / "model.json"
    fit_predictor(data, model)
    report = evaluate_predictor(data, model, tmp_path / "valid", "development_check")
    assert report["balance"]["examples"] == 1
    with pytest.raises(ValueError, match="estimation partition"):
        evaluate_predictor(data, model, tmp_path / "bad", "development_fit")
    manifest["role"] = "evaluation"
    manifest["battle_partitions"] = {k: "evaluation" for k in manifest["battle_partitions"]}
    for row in rows:
        row["partition"] = "evaluation"
    from battlemind.environment import sha256
    (data / "examples.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    manifest["examples_sha256"] = sha256(data / "examples.jsonl")
    (data / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="overlaps"):
        evaluate_predictor(data, model, tmp_path / "overlap", "evaluation")
    with pytest.raises(ValueError, match="designated development"):
        fit_predictor(data, tmp_path / "refit.json")
