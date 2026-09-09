import copy
import logging

from poke_env.battle import Battle
import pytest

from battlemind.adapter import PublicTracker


@pytest.fixture
def turn_request():
    return {"rqid": 7, "active": [{"moves": [
        {"move": "Psychic", "id": "psychic", "pp": 16, "maxpp": 16, "target": "normal", "disabled": False},
        {"move": "Recover", "id": "recover", "pp": 32, "maxpp": 32, "target": "self", "disabled": False},
    ]}], "side": {"name": "private-own-name", "id": "p1", "pokemon": [
        {"ident": "p1: AliasA", "details": "Alakazam", "condition": "313/313", "active": True,
         "stats": {"atk": 198, "def": 188, "spa": 368, "spd": 368, "spe": 338},
         "moves": ["psychic", "recover"], "baseAbility": "noability", "item": "", "pokeball": "pokeball"},
        {"ident": "p1: AliasB", "details": "Tauros", "condition": "353/353", "active": False,
         "stats": {"atk": 298, "def": 288, "spa": 238, "spd": 238, "spe": 318},
         "moves": ["bodyslam", "hyperbeam"], "baseAbility": "noability", "item": "", "pokeball": "pokeball"},
    ]}}


@pytest.fixture
def tracker(turn_request):
    value = PublicTracker()
    value.request(turn_request)
    for event in ("|teamsize|p1|2", "|teamsize|p2|6", "|switch|p1a: AliasA|Alakazam|313/313",
                  "|switch|p2a: secret-nickname|Starmie|100/100", "|turn|1"):
        value.feed(event.split("|"))
    return value


@pytest.fixture
def battle(turn_request):
    value = Battle("battle-gen1ou-fixture", "private-own-name", logging.getLogger("test"), gen=1)
    value.parse_request(copy.deepcopy(turn_request))
    value.parse_message(["", "switch", "p2a: secret-nickname", "Starmie", "100/100"])
    return value
