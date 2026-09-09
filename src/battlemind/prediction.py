"""Frozen smoothed frequencies. No labels, recorder, identities or live battle inputs."""

from collections import Counter
from dataclasses import dataclass
import math
from typing import Iterable, Literal

from poke_env.data import GenData

from .heuristic import effectiveness, hp_fraction, species_types
from .schema import DecisionSnapshot

FEATURE_VERSION = "visible-context-v1"
FEATURE_DEFINITIONS = {
    "opponent_hp": "low: displayed fraction <=1/3; other: >1/3; unknown: no active foe/fraction",
    "opponent_status": "healthy; impaired: publicly known non-healthy status; unknown",
    "type_pressure": "best Gen1 type multiplier among our legal ordinary damaging moves: resisted <1, neutral =1, super >1; unknown if no eligible move/foe; fixed-damage moves excluded",
}


@dataclass(frozen=True, slots=True, order=True)
class Context:
    opponent_hp: str
    opponent_status: str
    type_pressure: str

    def __post_init__(self):
        if (self.opponent_hp not in {"low", "other", "unknown"}
            or self.opponent_status not in {"healthy", "impaired", "unknown"}
            or self.type_pressure not in {"resisted", "neutral", "super", "unknown"}):
            raise ValueError("Invalid visible context category")


def context_from_snapshot(obs: DecisionSnapshot) -> Context:
    if not isinstance(obs, DecisionSnapshot) or obs.format != "gen1ou":
        raise TypeError("Prediction requires a frozen Gen 1 DecisionSnapshot")
    foe = next((p for p in obs.opponent_revealed if p.active), None)
    hp = hp_fraction(foe) if foe else None
    hp_bin = "unknown" if hp is None else "low" if hp <= 1 / 3 else "other"
    status = "unknown" if foe is None or foe.status is None else "healthy" if foe.status == "healthy" else "impaired"
    multipliers = []
    for action in obs.legal_actions:
        if foe and action.kind == "move" and action.base_power and action.move_id not in {"seismictoss", "nightshade", "superfang"}:
            move = GenData.from_gen(1).moves[action.move_id]
            multipliers.append(effectiveness(move["type"], species_types(foe.species)))
    maximum = max(multipliers, default=None)
    pressure = "unknown" if maximum is None else "resisted" if maximum < 1 else "neutral" if maximum == 1 else "super"
    return Context(hp_bin, status, pressure)


@dataclass(frozen=True, slots=True)
class Cell:
    context: Context
    examples: int
    switches: int

    def __post_init__(self):
        if type(self.examples) is not int or type(self.switches) is not int or not 0 <= self.switches <= self.examples:
            raise ValueError("Invalid frequency counts")


@dataclass(frozen=True, slots=True)
class CountTable:
    examples: int
    switches: int
    cells: tuple[Cell, ...]
    prior_strength: float = 12.0
    min_context: int = 5
    feature_version: str = FEATURE_VERSION

    def __post_init__(self):
        if (self.feature_version != FEATURE_VERSION or self.examples < 1
            or not math.isfinite(self.prior_strength) or self.prior_strength <= 0
            or type(self.min_context) is not int or self.min_context < 1
            or not isinstance(self.cells, tuple)):
            raise ValueError("Invalid count predictor configuration")
        if (sum(c.examples for c in self.cells) != self.examples
            or sum(c.switches for c in self.cells) != self.switches
            or len({c.context for c in self.cells}) != len(self.cells)):
            raise ValueError("Count table totals/contexts disagree")

    @property
    def frequency(self) -> float:
        return (self.switches + 1) / (self.examples + 2)  # Beta(1,1) smoothing


@dataclass(frozen=True, slots=True)
class Prediction:
    probability: float
    mode: str
    context: Context
    context_examples: int
    context_switches: int
    global_examples: int
    global_switches: int
    global_probability: float
    prior_strength: float
    fallback: str | None
    scope: str = "P(voluntary switch | meaningful choice); opponent eligibility unknown during play"


@dataclass(frozen=True, slots=True)
class CountPredictor:
    table: CountTable
    mode: Literal["constant", "conditional"]

    def __post_init__(self):
        if self.mode not in {"constant", "conditional"}:
            raise ValueError("Unknown count predictor mode")

    def predict_context(self, context: Context) -> Prediction:
        cell = next((c for c in self.table.cells if c.context == context), Cell(context, 0, 0))
        prior = self.table.frequency
        if self.mode == "constant":
            probability, fallback = prior, "constant_baseline"
        elif cell.examples < self.table.min_context:
            probability = prior
            fallback = "unseen_context" if not cell.examples else "sparse_context"
        else:
            probability = (cell.switches + self.table.prior_strength * prior) / (cell.examples + self.table.prior_strength)
            fallback = None
        return Prediction(probability, self.mode, context, cell.examples, cell.switches,
            self.table.examples, self.table.switches, prior, self.table.prior_strength, fallback)

    def predict(self, observation: DecisionSnapshot) -> Prediction:
        return self.predict_context(context_from_snapshot(observation))


def estimate_counts(examples: Iterable[tuple[Context, int]], *, prior_strength: float = 12, min_context: int = 5) -> CountTable:
    counts, switches = Counter(), Counter()
    for context, target in examples:
        if type(target) is not int or target not in {0, 1}:
            raise ValueError("Binary target must be 0 or 1")
        counts[context] += 1
        switches[context] += target
    return CountTable(sum(counts.values()), sum(switches.values()),
        tuple(Cell(context, count, switches[context]) for context, count in sorted(counts.items())), prior_strength, min_context)


def table_from_dict(data: dict) -> CountTable:
    return CountTable(**{**data, "cells": tuple(Cell(Context(**c["context"]), c["examples"], c["switches"]) for c in data["cells"])})
