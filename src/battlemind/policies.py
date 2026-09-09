"""Policies own only sanitized snapshots and their RNG, never live Players."""

import random
from typing import Protocol

from .schema import DecisionSnapshot


class Policy(Protocol):
    version: str

    def choose(self, observation: DecisionSnapshot) -> str: ...


class RandomLegalAgent:
    version = "random-legal-v1"

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def choose(self, observation: DecisionSnapshot) -> str:
        if not observation.legal_actions:
            raise ValueError("Policy received no legal actions")
        return self.rng.choice(observation.legal_actions).id


class MaxBasePowerAgent:
    version = "max-base-power-v1"

    def choose(self, observation: DecisionSnapshot) -> str:
        actions = observation.legal_actions
        if not actions:
            raise ValueError("Policy received no legal actions")
        moves = [a for a in actions if a.kind == "move" and a.base_power is not None]
        # First in request order wins ties, including all-zero status/fixed-damage moves.
        if moves:
            return max(moves, key=lambda a: a.base_power).id
        # Forced switch: first legal team slot. Engine-only request: its sole action.
        return actions[0].id


def make_policy(name: str, seed: int) -> Policy:
    if name == "gen1-heuristic":
        from .heuristic import Gen1HeuristicAgent
        return Gen1HeuristicAgent()
    if name == "random":
        return RandomLegalAgent(seed)
    if name == "max-base-power":
        return MaxBasePowerAgent()
    raise ValueError(f"Unknown policy: {name}")
