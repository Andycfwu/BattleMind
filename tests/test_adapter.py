import copy
from dataclasses import FrozenInstanceError, asdict
import json

from poke_env.battle import Move, Pokemon
import pytest

from battlemind.adapter import resolve_action, snapshot, snapshot_request


def test_immutable_snapshot_does_not_fill_in_future(turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    before = json.dumps(asdict(obs), sort_keys=True)
    tracker.feed("|move|p2a: secret-nickname|Surf|p1a: AliasA".split("|"))
    tracker.feed("|-damage|p2a: secret-nickname|51/100 par".split("|"))
    turn_request["side"]["pokemon"][0]["moves"].append("thunderwave")
    assert json.dumps(asdict(obs), sort_keys=True) == before
    assert obs.opponent_revealed[0].moves == ()
    assert obs.opponent_unseen == 5
    assert obs.opponent_revealed[0].effective_stats is None
    assert obs.own_team[0].hidden_moves == ()
    assert obs.own_team[0].status == "healthy"
    assert obs.opponent_revealed[0].hidden_moves is None
    with pytest.raises(FrozenInstanceError):
        obs.turn = 100


def test_hidden_information_isolation_uses_real_wrapper(battle, tracker):
    before, _ = snapshot(battle, tracker)
    opponent = battle.opponent_active_pokemon
    opponent.moves["blizzard"] = Move("blizzard", gen=1)
    opponent._stats["spe"] = 999
    opponent._current_hp = 17
    battle.opponent_team["p2: Unseen"] = Pokemon(gen=1, species="mewtwo")
    battle._opponent_username = "a-team-file-id-shortcut"
    battle._won = True
    after, _ = snapshot(battle, tracker)
    assert before == after
    from battlemind.heuristic import Gen1HeuristicAgent
    assert Gen1HeuristicAgent().choose(before) == Gen1HeuristicAgent().choose(after)
    assert len(after.opponent_revealed) == 1


def test_public_reveal_and_precision(turn_request, tracker):
    tracker.feed("|move|p2a: secret-nickname|Blizzard|p1a: AliasA".split("|"))
    tracker.feed("|-damage|p2a: secret-nickname|49/100 par".split("|"))
    tracker.feed("|-boost|p2a: secret-nickname|spa|1".split("|"))
    obs, _ = snapshot_request(turn_request, 2, tracker)
    mon = obs.opponent_revealed[0]
    assert mon.moves == ("blizzard",)
    assert not mon.moves_complete
    assert (mon.health.current, mon.health.maximum, mon.health.precision) == (49, 100, "public_scale")
    assert mon.status == "par" and mon.boosts == (("spa", 1),)
    assert mon.effective_stats is None and obs.gen1_derived_counters is None
    text = json.dumps(asdict(obs))
    for forbidden in ("secret-nickname", "private-own-name", "AliasA", "AliasB"):
        assert forbidden not in text


def test_current_request_move_indices_and_unavailable_moves(turn_request, tracker):
    turn_request["active"][0]["moves"][0]["disabled"] = True
    obs, mapping = snapshot_request(turn_request, 1, tracker)
    assert [a.id for a in obs.legal_actions] == ["move:recover", "switch:2"]
    assert resolve_action("move:recover", obs, mapping) == "/choose move 2|7"
    turn_request["active"][0]["moves"][1]["pp"] = 0
    obs, _ = snapshot_request(turn_request, 1, tracker)
    assert [a.id for a in obs.legal_actions] == ["switch:2"]


def test_stable_team_slot_survives_request_reordering(turn_request, tracker):
    turn_request["side"]["pokemon"].reverse()
    for index, mon in enumerate(turn_request["side"]["pokemon"]):
        mon["active"] = index == 0
    obs, mapping = snapshot_request(turn_request, 2, tracker)
    assert [m.species for m in obs.own_team] == ["alakazam", "tauros"]
    assert resolve_action("switch:1", obs, mapping) == "/choose switch 2|7"


def test_forced_switch_and_fainted_bench(turn_request, tracker):
    turn_request["forceSwitch"] = [True]
    turn_request.pop("active")
    turn_request["side"]["pokemon"][0]["condition"] = "0 fnt"
    obs, mapping = snapshot_request(turn_request, 5, tracker)
    assert obs.request_kind == "forced_switch"
    assert [a.id for a in obs.legal_actions] == ["switch:2"]
    assert mapping["switch:2"] == "/choose switch 2|7"
    turn_request["side"]["pokemon"][1]["condition"] = "0 fnt"
    with pytest.raises(ValueError, match="no supported legal choices"):
        snapshot_request(turn_request, 5, tracker)


@pytest.mark.parametrize("mid", ["fight", "recharge", "struggle"])
def test_engine_actions_from_request(mid, turn_request, tracker, battle):
    turn_request["active"] = [{"moves": [{"move": mid.title(), "id": mid}], "trapped": True}]
    battle.parse_request(copy.deepcopy(turn_request))
    obs, mapping = snapshot(battle, tracker)
    assert [a.id for a in obs.legal_actions] == [f"engine:{mid}"]
    assert mapping[f"engine:{mid}"] == "/choose move 1|7"


def test_trapping_does_not_allow_switches(turn_request, tracker):
    turn_request["active"][0]["trapped"] = True
    obs, _ = snapshot_request(turn_request, 1, tracker)
    assert all(a.kind == "move" for a in obs.legal_actions)


@pytest.mark.parametrize("field", ["wait", "teamPreview"])
def test_nondecisions_are_rejected(field, turn_request, tracker):
    turn_request[field] = True
    with pytest.raises(ValueError, match="No policy decision"):
        snapshot_request(turn_request, 1, tracker)


def test_illegal_and_stale_mapping_rejected(turn_request, tracker):
    obs, mapping = snapshot_request(turn_request, 1, tracker)
    with pytest.raises(ValueError, match="illegal action"):
        resolve_action("move:explosion", obs, mapping)
    mapping["move:psychic"] = "/choose move 1|6"
    with pytest.raises(ValueError, match="Stale"):
        resolve_action("move:psychic", obs, mapping)


def test_boosts_reset_on_public_switch(turn_request, tracker):
    tracker.feed("|-boost|p2a: secret-nickname|atk|2".split("|"))
    tracker.feed("|switch|p2a: next-hidden-nickname|Tauros|100/100".split("|"))
    obs, _ = snapshot_request(turn_request, 2, tracker)
    assert all(not mon.boosts for mon in obs.opponent_revealed)
    assert obs.opponent_unseen == 4


def test_unknown_total_is_not_assumed_six(turn_request, tracker):
    tracker.team_sizes.clear()
    obs, _ = snapshot_request(turn_request, 1, tracker)
    assert obs.opponent_team_size is None and obs.opponent_unseen is None
