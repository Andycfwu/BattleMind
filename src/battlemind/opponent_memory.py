"""Observer-only cross-encounter evidence. No recorder, labels, or winner input."""

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math

from .schema import DecisionSnapshot, PublicEvent
from .supervised import PredictorBundle

MEMORY_VERSION = "public-encounter-residual-v1"
PRIOR = 8
MIN_ENCOUNTERS = 2
MIN_EXAMPLES = 4
MAX_ADJUSTMENT = 0.15
FLOOR = 0.01
UNCERTAIN_MOVES = frozenset(("wrap", "bind", "clamp", "firespin", "hyperbeam", "bide", "rage",
    "thrash", "petaldance", "metronome", "mirrormove", "transform", "dig", "fly", "solarbeam",
    "razorwind", "skullbash", "skyattack", "fight", "recharge", "struggle"))


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class HistorySummary:
    encounters: int = 0
    examples: int = 0
    residual_sum: float = 0.0
    version: str = MEMORY_VERSION

    def __post_init__(self):
        if (self.version != MEMORY_VERSION or type(self.encounters) is not int or type(self.examples) is not int
            or not 0 <= self.encounters <= 10000 or not self.encounters * MIN_EXAMPLES <= self.examples <= 10000000
            or type(self.residual_sum) not in {int, float} or not math.isfinite(self.residual_sum)
            or abs(self.residual_sum) > self.encounters or (not self.encounters and self.examples)):
            raise ValueError("Invalid immutable public memory summary")

    @property
    def adjustment(self) -> float:
        return max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, self.residual_sum / (PRIOR + self.encounters))) if self.encounters >= MIN_ENCOUNTERS else 0.0

    def probability(self, base: float) -> float:
        if not math.isfinite(base) or not 0 <= base <= 1:
            raise ValueError("Invalid frozen probability")
        return base if self.encounters < MIN_ENCOUNTERS else max(FLOOR, min(1 - FLOOR, base + self.adjustment))


@dataclass(frozen=True, slots=True)
class MemoryContext:
    pooled: HistorySummary = HistorySummary()
    individual: HistorySummary = HistorySummary()

    def __post_init__(self):
        if not isinstance(self.pooled, HistorySummary) or not isinstance(self.individual, HistorySummary):
            raise TypeError("Memory context requires frozen numeric summaries")

    @property
    def sha256(self) -> str:
        return digest(asdict(self))


def context_from_dict(data: dict) -> MemoryContext:
    if set(data) != {"pooled", "individual"}:
        raise ValueError("Unexpected memory context fields")
    return MemoryContext(**{k: HistorySummary(**v) for k, v in data.items()})


def public_switches(history: tuple[PublicEvent, ...]) -> dict[int, str]:
    """A faint replacement is distinguishable without the opposing private request."""
    active, alive, acted_turn = None, False, -1
    result = {}
    for i, event in enumerate(history):
        if not (event.actor or "").startswith("opponent:"):
            continue
        if event.kind in {"switch", "drag"}:
            result[i] = ("game_effect_drag" if event.kind == "drag" else "initial_sendout" if active is None
                         else "forced_replacement" if not alive else "ambiguous_after_action" if acted_turn == event.turn
                         else "voluntary_public_switch")
            active = event.actor
            alive = bool(event.values and "fnt" not in event.values[-1] and not event.values[-1].startswith("0/"))
        elif event.actor == active:
            if event.kind == "faint" or (event.kind == "-damage" and event.values and
                ("fnt" in event.values[0] or event.values[0].startswith("0/"))):
                alive = False
            if event.kind in {"move", "cant"}:
                acted_turn = event.turn
    return result


def encounter_evidence(observations: tuple[DecisionSnapshot, ...], history: tuple[PublicEvent, ...],
                       predictor: PredictorBundle, completed: bool) -> dict:
    if (not isinstance(observations, tuple) or any(not isinstance(o, DecisionSnapshot) for o in observations)
        or not isinstance(history, tuple) or any(not isinstance(e, PublicEvent) for e in history)
        or type(completed) is not bool):
        raise TypeError("Evidence accepts frozen observer snapshots/public events and a completion flag only")
    if any(a.turn > b.turn for a, b in zip(history, history[1:])):
        raise ValueError("Public event chronology reversed")
    previous_turn, previous_request, previous_length = -1, -1, 0
    for obs in observations:
        length = len(obs.public_history)
        if (obs.turn < previous_turn or obs.request_id <= previous_request or length < previous_length
            or history[:length] != obs.public_history or any(e.turn > obs.turn for e in obs.public_history)):
            raise ValueError("Future encounter/event or invalid snapshot/history cutoff")
        previous_turn, previous_request, previous_length = obs.turn, obs.request_id, length
    switches = public_switches(history)
    ordinary_per_turn = Counter(o.turn for o in observations if o.request_kind == "move")
    records = []
    for i, obs in enumerate(observations):
        start = len(obs.public_history)
        end = len(observations[i + 1].public_history) if i + 1 < len(observations) else len(history)
        window = list(enumerate(history[start:end], start))
        foe = next((p for p in obs.opponent_revealed if p.active), None)
        reason, proxy = None, None
        actions = [(j, e) for j, e in window if (e.actor or "").startswith("opponent:") and
                   (e.kind == "move" or (e.kind == "switch" and switches.get(j) == "voluntary_public_switch"))]
        possible = obs.opponent_unseen is None or obs.opponent_unseen > 0 or any(
            not p.active and p.health.current > 0 for p in obs.opponent_revealed)
        uncertain = any(e.kind == "move" and e.values and e.values[0] in UNCERTAIN_MOVES
                        and obs.turn - 2 <= e.turn <= obs.turn for e in history[:end])
        if not completed:
            reason = "incomplete_encounter"
        elif obs.request_kind != "move":
            reason = "observer_forced_request"
        elif obs.turn < 1 or ordinary_per_turn[obs.turn] != 1:
            reason = "initial_or_ambiguous_request"
        elif not any(a.kind == "move" for a in obs.legal_actions) or obs.maybe_locked or obs.maybe_disabled:
            reason = "observer_engine_or_uncertain_request"
        elif foe is None or foe.health.current <= 0:
            reason = "opponent_absent_or_fainted"
        elif foe.status in {None, "slp", "frz", "fnt"}:
            reason = "opponent_unknown_or_engine_status"
        elif not possible:
            reason = "no_public_alternative"
        elif uncertain:
            reason = "public_lock_copy_charge_context"
        elif any((e.actor or "").startswith("opponent:") and (e.kind in {"cant", "drag"}
                 or switches.get(j) == "ambiguous_after_action") for j, e in window):
            reason = "ambiguous_or_engine_event"
        elif any(e.turn != obs.turn for _, e in actions):
            reason = "action_outside_decision_turn"
        elif len(actions) != 1:
            reason = "missing_announcement" if not actions else "multiple_announcements"
        else:
            proxy = int(actions[0][1].kind == "switch")
        base = predictor.logistic.predict(obs)
        records.append({"request_id": obs.request_id, "turn": obs.turn, "snapshot_sha256": digest(asdict(obs)),
            "history_start": start, "history_end": end, "proxy": proxy, "reason": reason,
            "base_probability": base, "action_event_indices": [j for j, _ in actions],
            "switch_events": [{"index": j, "classification": switches[j]} for j, _ in window if j in switches]})
    admitted = [r for r in records if r["proxy"] is not None]
    residual = sum(r["proxy"] - r["base_probability"] for r in admitted) / len(admitted) if len(admitted) >= MIN_EXAMPLES else None
    return {"version": MEMORY_VERSION, "completed": completed, "history_sha256": digest([asdict(e) for e in history]),
        "records": records, "admitted": len(admitted), "switch_proxies": sum(r["proxy"] for r in admitted),
        "skipped": dict(Counter(r["reason"] for r in records if r["proxy"] is None)),
        "encounter_residual": residual, "update_eligible": completed and residual is not None,
        "no_update_reason": None if completed and residual is not None else "incomplete_encounter" if not completed else "fewer_than_four_proxy_examples"}


def add_evidence(summary: HistorySummary, evidence: dict) -> HistorySummary:
    if not evidence["update_eligible"]:
        return summary
    return HistorySummary(summary.encounters + 1, summary.examples + evidence["admitted"],
                          summary.residual_sum + evidence["encounter_residual"])


class ObserverMemory:
    """One observer registry. Opaque keys never leave this routing layer."""
    def __init__(self):
        self.pooled = HistorySummary()
        self.sessions: dict[str, HistorySummary] = {}
        self.encounters: dict[str, int] = {}
        self.next_ordinal = 0
        self.pending = None

    def begin(self, key: str, ordinal: int) -> MemoryContext:
        if not isinstance(key, str) or not key or ordinal != self.next_ordinal or self.pending is not None:
            raise ValueError("Invalid encounter order/session or overlapping encounter")
        self.pending = (key, ordinal)
        return MemoryContext(self.pooled, self.sessions.get(key, HistorySummary()))

    def finish(self, key: str, ordinal: int, evidence: dict) -> MemoryContext:
        if self.pending != (key, ordinal):
            raise ValueError("Memory update crossed an encounter/session cutoff")
        self.pooled = add_evidence(self.pooled, evidence)
        self.sessions[key] = add_evidence(self.sessions.get(key, HistorySummary()), evidence)
        self.encounters[key] = self.encounters.get(key, 0) + 1
        self.next_ordinal += 1
        self.pending = None
        return MemoryContext(self.pooled, self.sessions[key])
