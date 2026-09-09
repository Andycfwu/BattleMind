"""Immutable policy boundary. None means unknown, never zero or nonexistent."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Health:
    # Preserve the numerator/denominator the player received, not estimated exact HP.
    current: int
    maximum: int | None
    precision: Literal["exact", "public_scale", "fainted"]


@dataclass(frozen=True, slots=True)
class PokemonView:
    slot: int  # own request slot, or opponent reveal-order index (NOT private team slot)
    species: str
    active: bool
    health: Health
    status: str | None
    moves: tuple[str, ...]
    moves_complete: bool
    boosts: tuple[tuple[str, int], ...]
    effective_stats: None = None
    hidden_moves: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class PublicEvent:
    turn: int
    kind: str
    actor: str | None
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LegalAction:
    id: str
    kind: Literal["move", "switch", "engine"]
    move_id: str | None = None
    team_slot: int | None = None
    base_power: int | None = None


@dataclass(frozen=True, slots=True)
class DecisionSnapshot:
    schema_version: str
    format: str
    turn: int
    request_id: int
    request_kind: Literal["move", "forced_switch"]
    trapped: bool
    own_team: tuple[PokemonView, ...]
    opponent_revealed: tuple[PokemonView, ...]
    opponent_team_size: int | None
    opponent_unseen: int | None
    legal_actions: tuple[LegalAction, ...]
    public_history: tuple[PublicEvent, ...]
    # Public stages are not effective Gen 1 stats. These quantities are unsupported.
    gen1_derived_counters: None = None
    maybe_locked: bool = False
    maybe_disabled: bool = False


def snapshot_from_dict(data: dict) -> DecisionSnapshot:
    """Restore the frozen policy boundary from an audited observation, not a log row."""
    def pokemon(value: dict) -> PokemonView:
        return PokemonView(**{**value, "health": Health(**value["health"]),
            "moves": tuple(value["moves"]), "boosts": tuple(tuple(b) for b in value["boosts"]),
            "hidden_moves": None if value["hidden_moves"] is None else tuple(value["hidden_moves"])})

    if data["schema_version"] not in {"1.0", "1.1"} or data["format"] != "gen1ou":
        raise ValueError("Unsupported observation schema or format")
    return DecisionSnapshot(**{**data,
        "own_team": tuple(pokemon(p) for p in data["own_team"]),
        "opponent_revealed": tuple(pokemon(p) for p in data["opponent_revealed"]),
        "legal_actions": tuple(LegalAction(**a) for a in data["legal_actions"]),
        "public_history": tuple(PublicEvent(**{**e, "values": tuple(e["values"])}) for e in data["public_history"])})
