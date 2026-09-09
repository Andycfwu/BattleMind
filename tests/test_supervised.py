from dataclasses import FrozenInstanceError, asdict, replace
import json
import math

import numpy as np
import pytest

from battlemind.adapter import snapshot_request
from battlemind.anticipation import SwitchAwareAgent
from battlemind.dataset import write_json
from battlemind.environment import sha256
from battlemind.opponents import SwitchingHeuristicAgent
from battlemind.prediction import estimate_counts
from battlemind.schema import Health, PublicEvent
from battlemind.supervised import (FEATURE_VERSION, FEATURE_DEFINITIONS, LogisticModel, PredictorBundle,
    VisibleFeatures, features_from_snapshot, features_from_dict, model_from_dict)
from battlemind.supervised_data import load_bundle, read_supervised_dataset
from battlemind.supervised_report import check_evaluation_partition
from battlemind.supervised_training import fit_logistic, fit_preprocessor, objective_gradient_hessian, train_bundle
from test_prediction import switch_example, dataset_fixture


def data():
    return [VisibleFeatures(("low", "healthy", "super", "healthy"),
        (i / 19, None if i % 3 == 0 else 0.8, 1.2, None, 0.0, float(i % 2))) for i in range(20)]


def test_features_preserve_unknown_precision_and_do_not_accept_metadata(turn_request, tracker):
    obs = snapshot_request(turn_request, 1, tracker)[0]
    before = asdict(obs)
    features = features_from_snapshot(obs)
    changed = replace(obs, opponent_revealed=(), public_history=())
    unknown = features_from_snapshot(changed)
    assert unknown.categories[:3] == ("unknown", "unknown", "unknown")
    assert unknown.numbers[1:4] == (None, None, None)
    foe = replace(obs.opponent_revealed[0], health=Health(33, 100, "public_scale"))
    assert features_from_snapshot(replace(obs, opponent_revealed=(foe,))).numbers[1] == 0.33
    # Request IDs and raw displayed boosts are deliberately not model features.
    assert features_from_snapshot(replace(obs, request_id=999)) == features
    own = replace(obs.own_team[0], boosts=(("atk", 6),), effective_stats=None)
    assert features_from_snapshot(replace(obs, own_team=(own,) + obs.own_team[1:])) == features
    with pytest.raises(TypeError):
        features_from_snapshot({**asdict(obs), "opponent_choice": "switch 2"})
    assert asdict(obs) == before
    with pytest.raises(FrozenInstanceError):
        features.numbers = ()


def test_recent_public_switch_is_not_a_privileged_voluntary_label(turn_request, tracker):
    obs = replace(snapshot_request(turn_request, 1, tracker)[0], turn=10,
        public_history=(PublicEvent(9, "drag", "opponent:1", ()), PublicEvent(7, "switch", "own:1", ())))
    assert features_from_snapshot(obs).numbers[-2:] == (0.0, 1.0)


def test_training_only_means_scale_vocabulary_and_unseen_handling():
    features = data()
    prep = fit_preprocessor(features)
    assert prep.means[0] == pytest.approx(0.5)
    assert prep.means[3] == 0 and prep.scales[3] == 1
    unseen = VisibleFeatures(("unknown", "unknown", "unknown", "unknown"), (None,) * 6)
    transformed = prep.transform(unseen)
    assert transformed[:12] == (0.0, 1.0) * 6
    assert sum(transformed[12:]) == 4  # four explicit unseen buckets
    assert prep == fit_preprocessor(features)  # inference has not learned from unseen values
    assert all(math.isfinite(x) for x in transformed)


def test_objective_gradient_and_hessian_match_finite_differences():
    x = np.array([[1, 0.2, -1], [1, 1, 0.4], [1, -0.5, 0.3]])
    y, w, strength = np.array([0, 1, 1]), np.array([0.1, 0.3, -0.2]), 0.1
    _, grad, hessian = objective_gradient_hessian(x, y, w, strength)
    step = 1e-5
    for i in range(3):
        delta = np.eye(3)[i] * step
        plus = objective_gradient_hessian(x, y, w + delta, strength)
        minus = objective_gradient_hessian(x, y, w - delta, strength)
        assert grad[i] == pytest.approx((plus[0] - minus[0]) / (2 * step), abs=1e-8)
        assert np.allclose(hessian[:, i], (plus[1] - minus[1]) / (2 * step), atol=1e-8)


def test_actual_optimizer_learns_reproducibly_and_inference_is_frozen():
    features = data()
    prep = fit_preprocessor(features)
    targets = [int(i >= 10) for i in range(20)]
    model, convergence = fit_logistic(features, targets, prep, 0.01)
    assert convergence["converged"] and convergence["iterations"] > 0
    assert model.probability(features[0]) < 0.15 < 0.85 < model.probability(features[-1])
    assert fit_logistic(features, targets, prep, 0.01)[0] == model
    frozen = asdict(model)
    for f in features:
        assert 0 <= model.probability(f) <= 1
    assert frozen == asdict(model)
    assert model_from_dict(json.loads(json.dumps(frozen))) == model
    with pytest.raises(FrozenInstanceError):
        model.intercept = 3
    with pytest.raises(ValueError, match="both binary classes"):
        fit_logistic(features, [0] * 20, prep, 0.1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_reject_nonfinite_artifact_and_features(bad):
    prep = fit_preprocessor(data())
    with pytest.raises(ValueError):
        LogisticModel(prep, (0.0,) * len(prep.columns), bad, 0.1)
    with pytest.raises(ValueError):
        replace(data()[0], numbers=(bad,) + data()[0].numbers[1:])


def test_all_probability_sources_share_scoring_and_classifier_changes_legal_choice(turn_request, tracker):
    obs = switch_example(turn_request, tracker)
    f = features_from_snapshot(obs)
    prep = fit_preprocessor([f])
    table = estimate_counts([(f.context, 0)] * 100)
    model = LogisticModel(prep, (0.0,) * len(prep.columns), 5.0, 0.1)
    bundle = PredictorBundle(table, model, "a" * 64)
    decisions = [SwitchAwareAgent(bundle, mode).evaluate(obs) for mode in ("constant", "conditional", "logistic")]
    assert decisions[0].chosen_action == "move:thunderbolt"
    assert decisions[2].chosen_action == "move:surf"
    assert all(d.chosen_action in {a.id for a in obs.legal_actions} for d in decisions)
    assert all([(s.stay_score, s.switch_score) for s in d.scores] ==
               [(s.stay_score, s.switch_score) for s in decisions[0].scores] for d in decisions)
    assert all(d.logistic_choice == decisions[2].chosen_action for d in decisions)
    assert decisions[2].predictor_sha256 == "a" * 64


def test_fixed_opponents_preserve_forced_choices_and_cooldown(turn_request, tracker):
    from battlemind.heuristic import Gen1HeuristicAgent
    obs = snapshot_request(turn_request, 1, tracker)[0]
    for threshold in (0, 40):
        policy = SwitchingHeuristicAgent(threshold)
        forced = replace(obs, request_kind="forced_switch", legal_actions=tuple(a for a in obs.legal_actions if a.kind == "switch"))
        assert policy.scores(forced) == Gen1HeuristicAgent().scores(forced)
        recent = replace(obs, turn=4, public_history=(PublicEvent(3, "switch", "own:1", ()),))
        assert all(s.score == -1000 for s in policy.scores(recent) if s.action_id.startswith("switch:"))


def test_fixed_opponents_thresholds_act_on_the_same_visible_gain(turn_request, tracker):
    from battlemind.schema import LegalAction
    from battlemind.adapter import resolve_action
    obs = snapshot_request(turn_request, 1, tracker)[0]
    own = replace(obs.own_team[0], health=Health(50, 100, "exact"))
    bench = replace(own, slot=2, active=False, health=Health(100, 100, "exact"))
    obs = replace(obs, own_team=(own, bench), public_history=(), legal_actions=(
        LegalAction("move:psychic", "move", "psychic", base_power=90), LegalAction("switch:2", "switch", team_slot=2)))
    # Same species/moves and public matchup, exactly +20 health utility on the bench.
    assert SwitchingHeuristicAgent(0).choose(obs) == "switch:2"
    assert SwitchingHeuristicAgent(40).choose(obs) == "move:psychic"
    mapping = {"move:psychic": f"/choose move 1|{obs.request_id}", "switch:2": f"/choose switch 2|{obs.request_id}"}
    assert resolve_action(SwitchingHeuristicAgent(0).choose(obs), obs, mapping) == mapping["switch:2"]


def test_no_recorder_metadata_can_be_embedded_in_feature_vector():
    with pytest.raises(ValueError, match="Unexpected feature fields"):
        features_from_dict({**asdict(data()[0]), "opponent_policy": "switch-active", "label": 1})


def test_intercept_only_training_recovers_observed_prevalence():
    features = [data()[0]] * 10
    prep = fit_preprocessor(features)
    model, _ = fit_logistic(features, [1] * 3 + [0] * 7, prep, 0.1)
    assert model.probability(features[0]) == pytest.approx(0.3, abs=1e-7)


def supervised_fixture(path):
    path.mkdir()
    rows, base = dataset_fixture(path / "audited-context")
    for i, row in enumerate(rows):
        row["match"] = i
    root = path / "audited-context"
    (root / "examples.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    base["examples_sha256"] = sha256(root / "examples.jsonl")
    (root / "manifest.json").write_text(json.dumps(base))
    enriched = [{**row, "features": asdict(data()[i]), "target_player": "b", "observer_policy": "random"} for i, row in enumerate(rows)]
    (path / "examples.jsonl").write_text("\n".join(json.dumps(r) for r in enriched))
    (path / "exclusions.jsonl").write_text("")
    manifest = {**base, "schema_version": "v4-dataset-1", "feature_version": FEATURE_VERSION,
        "feature_definitions": FEATURE_DEFINITIONS, "examples_sha256": sha256(path / "examples.jsonl"),
        "audited_context_manifest_sha256": sha256(root / "manifest.json")}
    write_json(path / "manifest.json", manifest)
    return enriched, manifest


def test_training_selection_never_fits_validation_preprocessing_or_counts(tmp_path):
    data_path = tmp_path / "data"
    rows, manifest = supervised_fixture(data_path)
    first = train_bundle(data_path, tmp_path / "first.json")
    assert first["fit_balance"]["examples"] == 2
    assert first["table"]["examples"] == 2 and first["table"]["switches"] == 1
    assert first["logistic"]["preprocessing"]["means"][0] == pytest.approx(1 / 38)
    rows[2]["features"]["numbers"] = (100.0,) + tuple(rows[2]["features"]["numbers"])[1:]
    (data_path / "examples.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match="hash"):
        read_supervised_dataset(data_path)
    manifest["examples_sha256"] = sha256(data_path / "examples.jsonl")
    (data_path / "manifest.json").write_text(json.dumps(manifest))
    second = train_bundle(data_path, tmp_path / "second.json")
    assert first["logistic"]["preprocessing"] == second["logistic"]["preprocessing"]
    assert first["table"] == second["table"]
    assert first["fit_examples_sha256"] == second["fit_examples_sha256"]


def test_artifact_and_evaluation_overlap_checks(tmp_path):
    path = tmp_path / "data"
    supervised_fixture(path)
    model = tmp_path / "model.json"
    artifact = train_bundle(path, model)
    assert load_bundle(model)[1].table.examples == 2
    for key in artifact["development_battle_keys"]:
        with pytest.raises(ValueError, match="overlaps"):
            check_evaluation_partition({"role": "evaluation", "battle_partitions": {key: "evaluation"}}, artifact, "evaluation")
    check_evaluation_partition({"role": "evaluation", "battle_partitions": {"fresh:0": "evaluation"}}, artifact, "evaluation")
    for changes in ({"feature_version": "future"}, {"frozen": False}, {"validation_battle_keys": artifact["fit_battle_keys"]}):
        broken = tmp_path / ("bad" + str(len(list(tmp_path.glob("bad*")))) + ".json")
        write_json(broken, {**artifact, **changes})
        with pytest.raises(ValueError):
            load_bundle(broken)


def test_aggregate_experiment_budget_is_single_use_and_bounded(tmp_path):
    import importlib.util
    from battlemind.environment import ROOT
    spec = importlib.util.spec_from_file_location("experiment_v4", ROOT / "scripts/experiment-v4.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "budget.json"
    ledger = module.begin_budget(path, "collect", 144, tmp_path / "collect")
    with pytest.raises(ValueError, match="already reserved"):
        module.begin_budget(path, "collect", 144, tmp_path / "retry")
    with pytest.raises(ValueError, match="interrupted"):
        module.begin_budget(path, "final", 288, tmp_path / "final")
    ledger["phases"]["collect"].update(status="finished", wall_seconds=20)
    path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match="exhausted"):
        module.begin_budget(path, "final", 480, tmp_path / "too-many")
    ledger["phases"]["collect"]["wall_seconds"] = 880
    path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match="exhausted"):
        module.begin_budget(path, "final", 288, tmp_path / "too-long")
