"""Offline random-direction updates using complete terminal outcomes only."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from .learned_policy import PolicyParameters

SIGMA = 0.4
ALPHA = 2.0


@dataclass(frozen=True, slots=True)
class Proposal:
    parent: PolicyParameters
    seed: int
    direction: tuple[int, ...]
    plus: PolicyParameters
    minus: PolicyParameters


def propose(parent: PolicyParameters, seed: int) -> Proposal:
    rng = np.random.default_rng(seed)
    direction = tuple(int(x) for x in rng.choice((-1, 1), size=4))
    def candidate(sign):
        return PolicyParameters(*(float(np.clip(p + sign * SIGMA * e, -1, 1)) for p, e in zip(parent.values, direction)))
    return Proposal(parent, seed, direction, candidate(1), candidate(-1))


def complete_objective(battles: list[dict], requested: int) -> float:
    """No reward for a missing/incomplete game, even when cleanup produced a winner."""
    if (requested < 1 or len(battles) != requested or any(b.get("status") != "completed"
        or b.get("winner") not in {"a", "b", "draw"} or b.get("invalid_actions", 0) for b in battles)):
        raise ValueError("Incomplete candidate block is ineligible for reward/update/selection")
    return sum(1 if b["winner"] == "a" else 0.5 if b["winner"] == "draw" else 0 for b in battles) / requested


def outcome_update(proposal: Proposal, plus: list[dict], minus: list[dict], requested: int) -> tuple[PolicyParameters, dict]:
    positive, negative = complete_objective(plus, requested), complete_objective(minus, requested)
    contrast = (positive - negative) / (2 * SIGMA)
    values = tuple(float(np.clip(p + ALPHA * contrast * e, -1, 1)) for p, e in zip(proposal.parent.values, proposal.direction))
    result = PolicyParameters(*values)
    return result, {"plus_objective": positive, "minus_objective": negative, "contrast": contrast,
        "sigma": SIGMA, "alpha": ALPHA, "updated_parameters": asdict(result),
        "parameter_delta": [v - p for v, p in zip(values, proposal.parent.values)],
        "changed": result != proposal.parent, "rule": "projected antithetic random-direction outcome update; not a promotion guarantee"}


def select_checkpoint(entries: list[tuple[str, PolicyParameters, float]]) -> str:
    if not entries or any(not math.isfinite(score) or not 0 <= score <= 1 for _, _, score in entries):
        raise ValueError("Selection requires eligible finite checkpoint objectives")
    # Caller supplies declared creation order c0,c1,c2. Python min keeps first exact tie.
    return min(entries, key=lambda row: (-row[2], sum(x * x for x in row[1].values)))[0]
