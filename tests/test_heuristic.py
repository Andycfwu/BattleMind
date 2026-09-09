from dataclasses import asdict, replace
import json

import pytest

from battlemind.adapter import snapshot_request
from battlemind.heuristic import Gen1HeuristicAgent, attack_score, effectiveness, recovery_failure
from battlemind.schema import Health, LegalAction, PokemonView, PublicEvent


def mon(species, *, slot=1, active=True, hp=100, maximum=100, moves=(), status="healthy"):
    return PokemonView(slot, species, active, Health(hp, maximum, "exact"), status, moves, True, ())


def test_gen1_type_chart_and_fixed_damage_exceptions():
    assert effectiveness("Ghost", ("Psychic",)) == 0
    assert effectiveness("Bug", ("Poison",)) == 2
    assert effectiveness("Ice", ("Fire",)) == 1
    assert effectiveness("Electric", ("Ground", "Rock")) == 0
    assert attack_score("seismictoss", mon("alakazam"), mon("gengar")) == 90
    assert attack_score("nightshade", mon("gengar"), mon("chansey")) == 90
    assert attack_score("bodyslam", mon("tauros"), mon("gengar")) == 0


def test_effective_attack_recovery_and_no_suicide_at_full_health(turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    user = mon("starmie", moves=("surf", "thunderbolt"))
    foe = mon("rhydon")
    actions = (LegalAction("move:thunderbolt", "move", "thunderbolt", base_power=95),
               LegalAction("move:surf", "move", "surf", base_power=95))
    obs = replace(obs, own_team=(user,), opponent_revealed=(foe,), legal_actions=actions)
    policy = Gen1HeuristicAgent()
    assert policy.choose(obs) == "move:surf"
    obs = replace(obs, own_team=(replace(user, health=Health(25, 100, "exact")),),
                  opponent_revealed=(mon("starmie"),), legal_actions=(
                      LegalAction("move:surf", "move", "surf", base_power=95),
                      LegalAction("move:recover", "move", "recover", base_power=0)))
    assert policy.choose(obs) == "move:recover"
    assert attack_score("explosion", mon("exeggutor"), mon("starmie")) < attack_score("psychic", mon("exeggutor"), mon("starmie"))


def test_recovery_bug_and_modulo_exception():
    assert recovery_failure(mon("chansey", hp=200, maximum=455))
    assert not recovery_failure(mon("chansey", hp=256, maximum=511))
    assert recovery_failure(mon("chansey", hp=100, maximum=611))


def test_status_eligibility_and_setup_use_only_displayed_stage(turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    policy = Gen1HeuristicAgent()
    user = mon("exeggutor")
    foe = mon("rhydon")
    assert policy.move_score("thunderwave", user, foe, obs)[0] == 0
    assert policy.move_score("stunspore", user, foe, obs)[0] > 0
    assert policy.move_score("sleeppowder", user, replace(foe, status="par"), obs)[0] == 0
    sleeping_foe = replace(obs, opponent_revealed=(mon("jynx", status="slp", active=False),))
    assert policy.move_score("sleeppowder", user, foe, sleeping_foe)[0] == 0
    assert policy.move_score("amnesia", user, foe, obs)[0] == 95
    assert policy.move_score("amnesia", replace(user, boosts=(("spa", 2),)), foe, obs)[0] == 0


def test_switch_gain_cooldown_and_forced_replacement(turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 5, tracker)
    own = (mon("starmie", hp=20, moves=("surf",)),
           mon("rhydon", slot=2, active=False, moves=("earthquake",)),
           mon("gyarados", slot=3, active=False, moves=("surf",)))
    foe = mon("jolteon", moves=("thunderbolt",))
    actions = (LegalAction("move:surf", "move", "surf", base_power=95),
               LegalAction("switch:2", "switch", team_slot=2),
               LegalAction("switch:3", "switch", team_slot=3))
    obs = replace(obs, own_team=own, opponent_revealed=(foe,), legal_actions=actions, public_history=())
    policy = Gen1HeuristicAgent()
    assert policy.choose(obs) == "switch:2"
    cooldown = replace(obs, public_history=(PublicEvent(4, "switch", "own:1", ("starmie", "20/100")),))
    assert policy.choose(cooldown) == "move:surf"
    forced = replace(cooldown, request_kind="forced_switch", legal_actions=actions[1:])
    assert policy.choose(forced) == "switch:2"


def test_scoring_does_not_mutate_unknowns_or_raw_hp(turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    before = json.dumps(asdict(obs), sort_keys=True)
    policy = Gen1HeuristicAgent()
    assert policy.choose(obs) == policy.choose(obs)
    assert json.dumps(asdict(obs), sort_keys=True) == before
    assert obs.opponent_revealed[0].effective_stats is None
    assert obs.gen1_derived_counters is None
    assert obs.opponent_revealed[0].health.precision == "public_scale"


@pytest.mark.parametrize("mid", ["fight", "recharge", "struggle"])
def test_engine_fallback(mid, turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    obs = replace(obs, legal_actions=(LegalAction(f"engine:{mid}", "engine", mid),))
    assert Gen1HeuristicAgent().choose(obs) == f"engine:{mid}"
