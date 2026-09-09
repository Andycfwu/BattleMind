from dataclasses import FrozenInstanceError, asdict, replace
import json
import math
from pathlib import Path

from poke_env.battle import Move, Pokemon
import pytest

from battlemind.adapter import snapshot, snapshot_request, resolve_action
from battlemind.anticipation import SwitchAwareAgent
from battlemind.environment import ROOT, sha256
from battlemind.learned_policy import (FrozenCheckpoint, LearnedScoreAgent, PolicyParameters,
    load_checkpoint, save_checkpoint)
from battlemind.learning import frozen_opponents, verify_pool
from battlemind.learning_ledger import ExperimentLedger
from battlemind.learning_report import final_intervals, terminal_metrics
from battlemind.policy_search import complete_objective, outcome_update, propose, select_checkpoint
from battlemind.prediction import estimate_counts
from battlemind.schema import Health, LegalAction, PublicEvent
from battlemind.supervised import LogisticModel, PredictorBundle, features_from_snapshot
from battlemind.supervised_training import fit_preprocessor


def predictor(obs):
    features = features_from_snapshot(obs)
    prep = fit_preprocessor([features])
    table = estimate_counts([(features.context, 0), (features.context, 1)])
    model = LogisticModel(prep, (0.0,) * len(prep.columns), 0.0, 0.1)
    return PredictorBundle(table, model, "a" * 64)


def policy(obs, parameters=PolicyParameters()):
    return LearnedScoreAgent(predictor(obs), FrozenCheckpoint(parameters, "b" * 64))


def test_initial_scores_and_choices_exactly_match_v4_for_supported_requests(turn_request, tracker):
    original = snapshot_request(turn_request, 1, tracker)[0]
    variants = [original, replace(original, opponent_revealed=(), opponent_unseen=None),
        replace(original, own_team=(replace(original.own_team[0], health=Health(30, 100, "exact")),) + original.own_team[1:]),
        replace(original, request_kind="forced_switch", legal_actions=(LegalAction("switch:2", "switch", team_slot=2),)),
        replace(original, legal_actions=(LegalAction("engine:recharge", "engine", "recharge"),)),
        replace(original, legal_actions=(LegalAction("engine:fight", "engine", "fight"), LegalAction("switch:2", "switch", team_slot=2))),
        replace(original, legal_actions=(LegalAction("engine:struggle", "engine", "struggle", base_power=50),))]
    for obs in variants:
        bundle = predictor(obs)
        expected = SwitchAwareAgent(bundle, "logistic").evaluate(obs)
        actual = LearnedScoreAgent(bundle, FrozenCheckpoint(PolicyParameters(), "b" * 64)).evaluate(obs)
        assert actual.scores == expected.scores
        assert actual.chosen_action == expected.chosen_action == actual.initial_choice
        assert actual.prediction == expected.prediction


def test_hidden_mutations_do_not_change_learned_policy(battle, tracker):
    before, mapping = snapshot(battle, tracker)
    agent = policy(before, PolicyParameters(0.4, -0.3, 0.2, -0.5))
    original = agent.evaluate(before)
    foe = battle.opponent_active_pokemon
    foe.moves["blizzard"] = Move("blizzard", gen=1)
    foe._stats["spe"] = 999
    foe._current_hp = 17
    battle.opponent_team["p2: Secret"] = Pokemon(gen=1, species="mewtwo")
    battle._opponent_username = "file-id"
    battle._won = True
    after, new_mapping = snapshot(battle, tracker)
    assert before == after and mapping == new_mapping
    assert original == agent.evaluate(after)
    assert resolve_action(original.chosen_action, before, mapping) == mapping[original.chosen_action]
    with pytest.raises(TypeError):
        agent.evaluate(asdict(before))
    with pytest.raises(FrozenInstanceError):
        agent.parameters.anticipation = 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.01, 1.01, True, "0"])
def test_invalid_parameters_rejected(value):
    with pytest.raises(ValueError):
        PolicyParameters(anticipation=value)


def test_forced_engine_unknown_and_extreme_scores_stay_legal(turn_request, tracker):
    obs = snapshot_request(turn_request, 1, tracker)[0]
    for params in (PolicyParameters(1, 1, 1, 1), PolicyParameters(-1, -1, -1, -1)):
        for changed in (obs, replace(obs, opponent_revealed=()),
            replace(obs, request_kind="forced_switch", legal_actions=(LegalAction("switch:2", "switch", team_slot=2),)),
            replace(obs, legal_actions=(LegalAction("engine:fight", "engine", "fight"),))):
            before = asdict(changed)
            actual = policy(changed, params).evaluate(changed)
            assert all(math.isfinite(s.score) for s in actual.scores)
            assert actual.chosen_action in {a.id for a in changed.legal_actions}
            assert asdict(changed) == before
            if changed.request_kind == "forced_switch" or changed.legal_actions[0].kind == "engine":
                assert actual.scores == actual.initial_scores


def test_score_parameters_change_actions_without_changing_probability(turn_request, tracker):
    obs = snapshot_request(turn_request, 1, tracker)[0]
    own = replace(obs.own_team[0], health=Health(50, 100, "exact"))
    obs = replace(obs, own_team=(own,) + obs.own_team[1:], legal_actions=obs.legal_actions[:2])
    high = policy(obs, PolicyParameters(recovery=1)).evaluate(obs)
    low = policy(obs, PolicyParameters(recovery=-1)).evaluate(obs)
    assert high.prediction == low.prediction
    assert high.chosen_action == "move:recover" and low.chosen_action == "move:psychic"
    assert high.scores[1].score - low.scores[1].score == pytest.approx(200)
    full = replace(obs, own_team=(replace(own, health=Health(100, 100, "exact")),) + obs.own_team[1:])
    assert policy(full, PolicyParameters(recovery=1)).evaluate(full).scores[1].score == 0


def test_switch_threshold_reuses_visible_gain_and_cooldown(turn_request, tracker):
    from battlemind.heuristic import Gen1HeuristicAgent
    obs = snapshot_request(turn_request, 1, tracker)[0]
    # Equal health and moves but different matchups can be supplied without private opponent fields.
    agent = policy(obs, PolicyParameters(switch_threshold=-1))
    recent = replace(obs, turn=4, public_history=(PublicEvent(3, "switch", "own:1", ()),))
    assert agent.evaluate(recent).scores[-1].score == -1000
    original = Gen1HeuristicAgent().scores(obs)
    assert all(s.score == o.stay_score for s, o in zip(original, agent.evaluate(obs).initial_scores))


def outcomes(winners, status="completed"):
    return [{"match": i, "status": status, "winner": winner, "invalid_actions": 0} for i, winner in enumerate(winners)]


def test_actual_outcome_update_not_selection_among_existing_bots():
    proposal = propose(PolicyParameters(), 51501)
    params, log = outcome_update(proposal, outcomes(["a", "a", "draw", "b"]), outcomes(["b", "b", "a", "b"]), 4)
    assert log["plus_objective"] == 0.625 and log["minus_objective"] == 0.25
    assert params != proposal.parent and params not in (proposal.plus, proposal.minus)
    expected = 2 * (0.625 - 0.25) / 0.8
    assert params.values == tuple(expected * v for v in proposal.direction)
    reverse, _ = outcome_update(proposal, outcomes(["b"] * 4), outcomes(["a"] * 4), 4)
    assert reverse.values == tuple(float(-v) for v in proposal.direction)
    tie, log = outcome_update(proposal, outcomes(["draw"] * 4), outcomes(["draw"] * 4), 4)
    assert tie == PolicyParameters() and not log["changed"]
    assert propose(proposal.parent, proposal.seed) == proposal


@pytest.mark.parametrize("status", ["truncated", "timeout", "crash", "cancelled", "not_started"])
def test_incomplete_cleanup_wins_never_supply_a_reward(status):
    rows = outcomes(["a"], status)
    with pytest.raises(ValueError, match="ineligible"):
        complete_objective(rows, 1)
    with pytest.raises(ValueError):
        outcome_update(propose(PolicyParameters(), 1), outcomes(["a"]), rows, 1)
    summary = terminal_metrics(rows, 1)
    assert summary["a_wins"] == summary["completed"] == 0
    assert summary["mean_terminal_reward"] is None
    with pytest.raises(ValueError):
        complete_objective([], 1)


def test_checkpoint_roundtrip_frozen_inference_and_compatibility(tmp_path, turn_request, tracker):
    obs = snapshot_request(turn_request, 1, tracker)[0]
    bundle = predictor(obs)
    params = PolicyParameters(0.2, -0.1, 0.3, 0.5)
    path = tmp_path / "checkpoint.json"
    artifact = save_checkpoint(path, params, bundle, {"parent": "offline-only", "opponent": "not-a-feature"})
    _, checkpoint = load_checkpoint(path, bundle)
    before = sha256(path)
    agent = LearnedScoreAgent(bundle, checkpoint)
    expected = agent.evaluate(obs)
    for _ in range(5):
        assert agent.evaluate(obs) == expected
    assert sha256(path) == before and checkpoint.parameters == params
    assert "provenance" not in asdict(checkpoint)
    with pytest.raises(FileExistsError):
        save_checkpoint(path, params, bundle, {})
    for i, modified in enumerate(({**artifact, "frozen": False},
        {**artifact, "parameters": {**artifact["parameters"], "status": 9}},
        {**artifact, "compatibility": {**artifact["compatibility"], "feature_version": "future"}},
        {**artifact, "compatibility": {**artifact["compatibility"], "predictor_sha256": "c" * 64}})):
        bad = tmp_path / f"bad-{i}.json"
        bad.write_text(json.dumps(modified))
        with pytest.raises(ValueError):
            load_checkpoint(bad, bundle)
    with pytest.raises(ValueError):
        load_checkpoint(path, replace(bundle, sha256="c" * 64))


def test_round_opponents_frozen_and_earlier_checkpoint_retained(tmp_path):
    checkpoints = {name: tmp_path / f"{name}.json" for name in ("c0", "c1")}
    for path in checkpoints.values():
        path.write_text("parameters")
    first, second = frozen_opponents(checkpoints, 1), frozen_opponents(checkpoints, 2)
    assert [p.identity for p in first] == ["v2", "active", "c0"]
    assert [p.identity for p in second] == ["v2", "active", "c0", "c1"]
    verify_pool(second)
    with pytest.raises(FrozenInstanceError):
        second[0].identity = "replacement"
    checkpoints["c1"].write_text("changed parameters")
    with pytest.raises(ValueError, match="changed inside"):
        verify_pool(second)


def ledger_configuration():
    return {"total_games": 12, "total_seconds": 90, "phase_games": {p: 4 for p in ("training", "selection", "final")},
        "phase_seconds": {p: 20 for p in ("training", "selection", "final")}}


def test_phase_reservations_overlap_budget_and_no_resume(tmp_path):
    clock = [0.0]
    ledger = ExperimentLedger(tmp_path, ledger_configuration(), clock=lambda: clock[0])
    assert ledger.state["phases"]["final"]["game_allocation"] == 4
    with pytest.raises(ValueError, match="phase order"):
        ledger.begin("final")
    ledger.begin("training")
    index = ledger.reserve_run(4, {"path": "training/first"})
    ledger.finish_run(index, "run", [0, 1, 2, 3], {}, {})
    with pytest.raises(ValueError, match="budget exhausted"):
        ledger.reserve_run(4, {})
    ledger.finish_phase()
    ledger.begin("selection")
    index = ledger.reserve_run(4, {"path": "selection/first"})
    with pytest.raises(ValueError, match="overlap"):
        ledger.finish_run(index, "run", [0, 1, 2, 3], {}, {})
    ledger.finish_run(index, "fresh", [0, 1, 2, 3], {}, {})
    ledger.finish_phase()
    ledger.begin("final")
    clock[0] = 25
    with pytest.raises(ValueError, match="budget exhausted"):
        ledger.reserve_run(4, {})
    ledger.finish("time budget")
    assert ledger.state["status"] == "failed"
    with pytest.raises(FileExistsError):
        ExperimentLedger(tmp_path, ledger_configuration())


def test_selection_ties_prefer_initial_and_bootstrap_uses_games_not_turns():
    initial, changed = PolicyParameters(), PolicyParameters(0.1)
    assert select_checkpoint([("c0", initial, 0.5), ("c1", changed, 0.5)]) == "c0"
    assert select_checkpoint([("c0", initial, 0.5), ("c1", changed, 0.6)]) == "c1"
    arms = {"initial": {"op": outcomes(["b"] * 24)}, "selected": {"op": outcomes(["a"] * 24)}}
    result = final_intervals(arms)
    assert result["games_per_arm"] == 24
    assert result["point"] == {"mean_reward": 1, "win_rate": 1}
    assert result["interval_95"]["mean_reward"] == [1, 1]
    arms["selected"]["op"][0]["status"] = "truncated"
    assert not final_intervals(arms)["available"]
