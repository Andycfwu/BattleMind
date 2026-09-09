import copy
from dataclasses import FrozenInstanceError, asdict, replace
import json
import math

import pytest

from battlemind.adapter import snapshot_request
from battlemind.adaptation import AdaptedAgent, ARMS
from battlemind.adaptation_experiment import group_schedule
from battlemind.adaptation_ledger import AdaptationLedger
from battlemind.adaptation_report import cluster_interval
from battlemind.learned_policy import FrozenCheckpoint, LearnedScoreAgent, PolicyParameters
from battlemind.memory_runtime import EncounterController
from battlemind.opponent_memory import (HistorySummary, MemoryContext, ObserverMemory, encounter_evidence,
    public_switches, context_from_dict)
from battlemind.prediction import estimate_counts
from battlemind.schema import LegalAction, PublicEvent
from battlemind.supervised import LogisticModel, PredictorBundle, features_from_snapshot
from battlemind.supervised_training import fit_preprocessor


def bundle(obs):
    feature = features_from_snapshot(obs)
    prep = fit_preprocessor([feature])
    return PredictorBundle(estimate_counts([(feature.context, 0), (feature.context, 1)]),
        LogisticModel(prep, (0.0,) * len(prep.columns), 0.0, .1), "a" * 64)


def sequence(turn_request, tracker, switches=False):
    tracker = copy.deepcopy(tracker)
    observations = []
    for turn in range(1, 5):
        request = copy.deepcopy(turn_request)
        request["rqid"] = turn + 7
        tracker.feed(["", "turn", str(turn)])
        observations.append(snapshot_request(request, turn, tracker)[0])
        if switches:
            tracker.feed(["", "switch", "p2a: " + ("alternate" if turn % 2 else "secret-nickname"), "Starmie", "100/100"])
        else:
            tracker.feed(["", "move", "p2a: secret-nickname", "Psychic", "p1a: AliasA"])
    return tuple(observations), tuple(tracker.history)


def checkpoint():
    return FrozenCheckpoint(PolicyParameters(-.3, .3, .3, .3), "b" * 64)


def test_cold_start_and_none_exactly_preserve_v5_scoring(turn_request, tracker):
    obs = snapshot_request(turn_request, 1, tracker)[0]
    variants = (obs, replace(obs, opponent_revealed=(), opponent_unseen=None),
        replace(obs, request_kind="forced_switch", legal_actions=(LegalAction("switch:2", "switch", team_slot=2),)),
        replace(obs, legal_actions=(LegalAction("engine:recharge", "engine", "recharge"),)))
    for value in variants:
        model = bundle(value)
        expected = LearnedScoreAgent(model, checkpoint()).evaluate(value)
        for arm in ARMS:
            policy = AdaptedAgent(model, checkpoint(), MemoryContext(), arm)
            actual = policy.evaluate(value)
            assert actual.scores == expected.scores and actual.chosen_action == expected.chosen_action
            assert all(p == expected.prediction.probability for _, p in actual.shadow_probabilities)
            assert policy.policies[arm].parameters == checkpoint().parameters
    supported = MemoryContext(HistorySummary(8, 32, -4), HistorySummary(8, 32, 4))
    assert AdaptedAgent(bundle(obs), checkpoint(), supported, "none").evaluate(obs).scores == LearnedScoreAgent(bundle(obs), checkpoint()).evaluate(obs).scores


def test_identical_history_uses_identical_adjustment_and_scoring(turn_request, tracker):
    obs = snapshot_request(turn_request, 1, tracker)[0]
    summary = HistorySummary(3, 12, -.9)
    context = MemoryContext(summary, summary)
    model = bundle(obs)
    first = AdaptedAgent(model, checkpoint(), context, "pooled").evaluate(obs)
    second = AdaptedAgent(model, checkpoint(), context, "individual").evaluate(obs)
    assert first.scores == second.scores and first.chosen_action == second.chosen_action
    assert dict(first.shadow_probabilities)["pooled"] == dict(first.shadow_probabilities)["individual"] < first.base_probability
    assert context_from_dict(asdict(context)) == context
    with pytest.raises(FrozenInstanceError):
        context.individual.residual_sum = 4
    with pytest.raises(TypeError):
        AdaptedAgent(model, checkpoint(), context, "individual").evaluate(asdict(obs))


def test_hidden_opponent_mutation_does_not_change_adapted_observation_or_prediction(battle, tracker):
    from poke_env.battle import Move, Pokemon
    from battlemind.adapter import snapshot
    before, _ = snapshot(battle, tracker)
    context = MemoryContext(HistorySummary(3, 12, -.9), HistorySummary(3, 12, .6))
    agent = AdaptedAgent(bundle(before), checkpoint(), context, "individual")
    expected = agent.evaluate(before)
    battle.opponent_active_pokemon.moves["blizzard"] = Move("blizzard", gen=1)
    battle.opponent_active_pokemon._stats["spe"] = 999
    battle.opponent_team["p2: secret"] = Pokemon(gen=1, species="mewtwo")
    battle._opponent_username = "hidden-profile"
    battle._won = True
    after, _ = snapshot(battle, tracker)
    assert before == after and agent.evaluate(after) == expected


@pytest.mark.parametrize("summary", [HistorySummary(), HistorySummary(1, 4, 1), HistorySummary(100, 400, -100), HistorySummary(100, 400, 100)])
def test_probabilities_finite_bounded_and_shrunk(summary):
    for p in (0, .001, .2, .5, .999, 1):
        result = summary.probability(p)
        assert math.isfinite(result) and 0 <= result <= 1
        if summary.encounters < 2:
            assert result == p
        else:
            assert .01 <= result <= .99
    assert abs(summary.adjustment) <= .15


@pytest.mark.parametrize("args", [(True, 4, 0), (2, 3, 0), (0, 1, 0), (2, 8, float("nan")), (2, 8, 3)])
def test_bad_summary_rejected(args):
    with pytest.raises(ValueError):
        HistorySummary(*args)


def test_observer_evidence_changes_later_probabilities_not_current_battle(turn_request, tracker):
    snapshots, history = sequence(turn_request, tracker)
    model = bundle(snapshots[0])
    evidence = encounter_evidence(snapshots, history, model, True)
    assert evidence["admitted"] == 4 and evidence["encounter_residual"] == -.5
    manager = ObserverMemory()
    for ordinal in range(2):
        before = manager.begin("opaque", ordinal)
        assert before.individual.encounters == ordinal
        assert before.individual.probability(.5) == .5
        after = manager.finish("opaque", ordinal, evidence)
        assert before.individual.encounters == ordinal  # immutable before snapshot unchanged
    assert after.individual.probability(.5) == .4
    assert manager.begin("opaque", 2) == after
    # Four observations contribute one encounter, not four independent pseudo-counts.
    assert after.individual.encounters == 2 and after.individual.examples == 8


def test_session_routing_renaming_isolation_and_reset(turn_request, tracker):
    snapshots, history = sequence(turn_request, tracker, switches=True)
    evidence = encounter_evidence(snapshots, history, bundle(snapshots[0]), True)
    assert evidence["switch_proxies"] == 4
    left, right = ObserverMemory(), ObserverMemory()
    for i in range(3):
        assert left.begin("anonymous-1", i) == right.begin("renamed-key", i)
        assert left.finish("anonymous-1", i, evidence) == right.finish("renamed-key", i, evidence)
    new = left.begin("unknown-other", 3)
    assert new.individual == HistorySummary() and new.pooled.encounters == 3
    assert ObserverMemory().begin("anonymous-1", 0) == MemoryContext()
    with pytest.raises(ValueError):
        right.begin("renamed-key", 99)
    with pytest.raises(ValueError):
        left.finish("anonymous-1", 3, evidence)


def test_future_history_cutoffs_and_duplicate_requests_rejected(turn_request, tracker):
    snapshots, history = sequence(turn_request, tracker)
    model = bundle(snapshots[0])
    with pytest.raises(ValueError):
        encounter_evidence((replace(snapshots[0], public_history=history),) + snapshots[1:], history, model, True)
    with pytest.raises(ValueError):
        encounter_evidence((snapshots[0], snapshots[0]), history, model, True)
    with pytest.raises(ValueError):
        encounter_evidence(snapshots, history[::-1], model, True)
    with pytest.raises(TypeError):
        encounter_evidence(tuple(asdict(o) for o in snapshots), history, model, True)


def test_forced_ambiguous_unannounced_and_engine_actions_stay_distinct(turn_request, tracker):
    obs = snapshot_request(turn_request, 1, tracker)[0]
    model = bundle(obs)
    prefix = obs.public_history
    cases = [((PublicEvent(1, "faint", "opponent:1", ()), PublicEvent(1, "switch", "opponent:2", ("tauros", "100/100"))), "missing_announcement"),
        ((PublicEvent(1, "cant", "opponent:1", ("par",)),), "ambiguous_or_engine_event"),
        ((PublicEvent(1, "drag", "opponent:2", ("tauros", "100/100")),), "ambiguous_or_engine_event"),
        ((PublicEvent(1, "move", "opponent:1", ("wrap",)),), "public_lock_copy_charge_context"),
        ((PublicEvent(1, "move", "opponent:1", ("psychic",)), PublicEvent(1, "move", "opponent:1", ("surf",))), "multiple_announcements"),
        ((), "missing_announcement")]
    for events, reason in cases:
        result = encounter_evidence((obs,), prefix + events, model, True)
        assert result["records"][0]["proxy"] is None and result["records"][0]["reason"] == reason
    forced = prefix + cases[0][0]
    assert public_switches(forced)[len(forced) - 1] == "forced_replacement"
    move_then_faint = prefix + (PublicEvent(1, "move", "opponent:1", ("psychic",)),) + cases[0][0]
    result = encounter_evidence((obs,), move_then_faint, model, True)
    assert result["records"][0]["proxy"] == 0  # announced ordinary move, followed by a separate forced replacement
    result = encounter_evidence((replace(obs, request_kind="forced_switch"),), prefix, model, True)
    assert result["records"][0]["reason"] == "observer_forced_request"


def test_incomplete_encounter_never_updates_even_with_public_actions(turn_request, tracker):
    snapshots, history = sequence(turn_request, tracker, switches=True)
    result = encounter_evidence(snapshots, history, bundle(snapshots[0]), False)
    assert result["admitted"] == 0 and not result["update_eligible"]
    manager = ObserverMemory()
    before = manager.begin("session", 0)
    assert manager.finish("session", 0, result) == before


def test_controller_only_exports_own_public_inputs_and_frozen_summaries(tmp_path, turn_request, tracker):
    snapshots, history = sequence(turn_request, tracker)
    controller = EncounterController(ObserverMemory(), "opaque", "observer", "individual", bundle(snapshots[0]))
    before = controller.before(tmp_path, 0)
    controller.after(tmp_path, 0, snapshots, history, True)
    exported = json.loads((tmp_path / "observer/000.json").read_text())
    assert set(exported) == {"version", "observations", "public_history", "completed"}
    assert "opaque" not in json.dumps(exported)
    assert before == MemoryContext() and controller.manager.pooled.encounters == 1
    # Arbitrary private labels/end logs are not inputs to the evidence extractor.
    (tmp_path / "labels.json").write_text('{"future_target":1,"winner":"a"}')
    expected = encounter_evidence(snapshots, history, controller.predictor, True)
    (tmp_path / "labels.json").write_text('{"future_target":0,"private_team":"mewtwo"}')
    assert encounter_evidence(snapshots, history, controller.predictor, True) == expected


def test_budget_reservation_exhaustion_and_no_resume(tmp_path):
    now = [0.0]
    config = {"total_games": 8, "total_seconds": 50, "games": {"development": 4, "final": 4}, "seconds": {"development": 20, "final": 20}}
    ledger = AdaptationLedger(tmp_path, config, clock=lambda: now[0])
    assert ledger.state["final_reserved_before_development"]
    with pytest.raises(ValueError):
        ledger.begin("final")
    ledger.begin("development")
    i = ledger.reserve({"group": 0}, 4)
    ledger.dispatch(i)
    with pytest.raises(ValueError):
        ledger.reserve({}, 1)
    ledger.record(i, "hash", [{"match": n, "status": "completed"} for n in range(4)], {})
    ledger.finish_phase()
    ledger.begin("final")
    now[0] = 21
    with pytest.raises(ValueError):
        ledger.reserve({}, 4)
    ledger.finish("time exhausted")
    assert ledger.state["requested_games"] == 4 and ledger.state["status"] == "failed"
    with pytest.raises(FileExistsError):
        AdaptationLedger(tmp_path, config)


def test_schedule_interleaves_resets_balances_and_resamples_groups():
    from battlemind.adaptation_experiment import CONFIG
    config = json.loads(CONFIG.read_text())
    for group in range(4):
        schedule = list(group_schedule(config, "final", group))
        assert len(schedule) == 36
        for arm in ARMS:
            cells = [c for c in schedule if c["arm"] == arm]
            assert len({c["observer_key"] for c in cells}) == 1
            assert len({c["session_key"] for c in cells}) == 2
            assert all(a["target"] != b["target"] for a, b in zip(cells, cells[1:]))
            for target in config["targets"]:
                assert sorted(c["pair"] for c in cells if c["target"] == target) == list(range(6))
    assert not cluster_interval([(1, 4)] * 3)["available"]
    assert cluster_interval([(1, 4)] * 4)["interval_95"] == [.25, .25]
