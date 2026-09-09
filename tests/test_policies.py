from dataclasses import replace
import random

import pytest

from battlemind.adapter import snapshot_request
from battlemind.policies import MaxBasePowerAgent, RandomLegalAgent
from battlemind.schema import LegalAction


def test_seeded_randomness_independent_of_global_rng(turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    first, second = RandomLegalAgent(42), RandomLegalAgent(42)
    choices = [first.choose(obs) for _ in range(100)]
    random.seed(9123)
    for _ in range(300):
        random.random()
    assert choices == [second.choose(obs) for _ in range(100)]
    assert len(set(choices)) == len(obs.legal_actions)
    other = RandomLegalAgent(43)
    assert choices != [other.choose(obs) for _ in range(100)]


def test_base_power_ties_and_fallbacks(turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    policy = MaxBasePowerAgent()
    assert policy.choose(obs) == "move:psychic"
    actions = (LegalAction("move:icebeam", "move", "icebeam", base_power=95),
               LegalAction("move:thunderbolt", "move", "thunderbolt", base_power=95))
    assert policy.choose(replace(obs, legal_actions=actions)) == "move:icebeam"
    assert policy.choose(replace(obs, legal_actions=tuple(replace(a, base_power=0) for a in actions))) == "move:icebeam"
    for actions in ((LegalAction("switch:2", "switch", team_slot=2),),
                    (LegalAction("engine:recharge", "engine", "recharge"),)):
        assert policy.choose(replace(obs, legal_actions=actions)) == actions[0].id


@pytest.mark.parametrize("policy", [RandomLegalAgent(1), MaxBasePowerAgent()])
def test_empty_choices_are_an_error(policy, turn_request, tracker):
    obs, _ = snapshot_request(turn_request, 1, tracker)
    with pytest.raises(ValueError):
        policy.choose(replace(obs, legal_actions=()))
