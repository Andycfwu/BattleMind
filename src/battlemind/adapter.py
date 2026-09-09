"""Request legality plus a narrow public-protocol projection, not a simulator.

Opponent views are built only from received public messages. In particular we never
read battle.opponent_team: even an accidentally enriched wrapper cannot leak secrets.
"""

from dataclasses import dataclass, field
from typing import Any

from poke_env.battle import Battle
from poke_env.data import GenData, to_id_str

from .schema import DecisionSnapshot, Health, LegalAction, PokemonView, PublicEvent


def health_status(condition: str, own: bool) -> tuple[Health, str | None]:
    parts = condition.split()
    if "fnt" in parts:
        return Health(0, None, "fainted"), "fnt"
    hp = parts[0].split("/")
    return (
        Health(int(hp[0]), int(hp[1]) if len(hp) == 2 else None,
               "exact" if own else "public_scale"),
        parts[1] if len(parts) > 1 else "healthy",
    )


@dataclass
class _Seen:
    species: str
    health: Health
    status: str | None
    active: bool = True
    moves: list[str] = field(default_factory=list)
    boosts: dict[str, int] = field(default_factory=dict)


class PublicTracker:
    """Track revealed identity, raw HP scale, move IDs and displayed boost stages.

    This deliberately leaves Gen 1 effective stats/counters unknown. Nicknames are
    internal identity keys and never become features. Events are an allowlist.
    """

    def __init__(self):
        self.role: str | None = None
        self.turn = 0
        self.own_slots: dict[str, int] = {}
        self.own_boosts: dict[str, dict[str, int]] = {}
        self.seen: dict[str, _Seen] = {}
        self.team_sizes: dict[str, int] = {}
        self.history: list[PublicEvent] = []

    @staticmethod
    def key(ident: str) -> str:
        return ident[:2] + ":" + ident.split(":", 1)[1].strip()

    def request(self, request: dict[str, Any]) -> None:
        self.role = request["side"]["id"]
        # Showdown puts the active Pokemon first in later requests. Preserve original
        # team slots across that reordering, while commands use the current indices.
        for mon in request["side"]["pokemon"]:
            key = self.key(mon["ident"])
            if key not in self.own_slots:
                self.own_slots[key] = len(self.own_slots) + 1

    def actor(self, ident: str) -> str | None:
        if not ident.startswith(("p1", "p2")) or ":" not in ident:
            return None
        key = self.key(ident)
        if ident[:2] == self.role:
            slot = self.own_slots.get(key)
            return f"own:{slot}" if slot is not None else None
        keys = list(self.seen)
        return f"opponent:{keys.index(key) + 1}" if key in self.seen else None

    def feed(self, msg: list[str]) -> None:
        if len(msg) < 2:
            return
        kind, args = msg[1], msg[2:]
        if kind == "turn":
            self.turn = int(args[0])
            return
        if kind == "teamsize":
            self.team_sizes[args[0]] = int(args[1])
            return
        if not self.role:
            return
        values: tuple[str, ...]
        actor = self.actor(args[0]) if args else None
        key = self.key(args[0]) if args and args[0].startswith(("p1", "p2")) and ":" in args[0] else None
        own = bool(args and args[0][:2] == self.role)
        if kind in {"switch", "drag"}:
            species = to_id_str(args[1].split(",")[0])
            hp, status = health_status(args[2], own)
            if own:
                self.own_boosts.clear()
            else:
                for mon in self.seen.values():
                    mon.active = False
                    mon.boosts.clear()
                mon = self.seen.setdefault(key, _Seen(species, hp, status))
                mon.species, mon.health, mon.status, mon.active = species, hp, status, True
                mon.boosts.clear()
            actor = self.actor(args[0])
            values = (species, args[2])
        elif kind == "move":
            move = to_id_str(args[1])
            if key in self.seen and move not in self.seen[key].moves:
                self.seen[key].moves.append(move)
            values = (move,)
        elif kind in {"-damage", "-heal"}:
            if key in self.seen:
                self.seen[key].health, self.seen[key].status = health_status(args[1], False)
            values = (args[1],)
        elif kind in {"-status", "-curestatus"}:
            if key in self.seen:
                self.seen[key].status = args[1] if kind == "-status" else "healthy"
            values = (args[1],)
        elif kind == "faint":
            if key in self.seen:
                self.seen[key].health = Health(0, None, "fainted")
                self.seen[key].status = "fnt"
            values = ()
        elif kind in {"-boost", "-unboost", "-setboost"}:
            boosts = self.own_boosts.setdefault(key, {}) if own else self.seen[key].boosts if key in self.seen else {}
            stat, amount = args[1], int(args[2])
            boosts[stat] = amount if kind == "-setboost" else max(-6, min(6, boosts.get(stat, 0) + amount * (1 if kind == "-boost" else -1)))
            values = (stat, str(amount))
        elif kind == "-clearboost":
            if own:
                self.own_boosts[key] = {}
            elif key in self.seen:
                self.seen[key].boosts.clear()
            values = ()
        elif kind == "-clearallboost":
            self.own_boosts.clear()
            for mon in self.seen.values():
                mon.boosts.clear()
            values = ()
        elif kind in {"cant", "-activate", "-start", "-end", "-sidestart", "-sideend"}:
            # Drop trailing free text / nicknames. Retain only the public effect ID.
            values = (to_id_str(args[1]),) if len(args) > 1 else ()
        elif kind in {"-weather", "-fieldstart", "-fieldend"}:
            values = (to_id_str(args[0]),)
            actor = None
        else:
            return
        self.history.append(PublicEvent(self.turn, kind, actor, values))

    def opponents(self) -> tuple[PokemonView, ...]:
        return tuple(PokemonView(i, m.species, m.active, m.health, m.status,
                                 tuple(m.moves), False, tuple(sorted(m.boosts.items())))
                     for i, m in enumerate(self.seen.values(), 1))


def snapshot(battle: Battle, tracker: PublicTracker) -> tuple[DecisionSnapshot, dict[str, str]]:
    return snapshot_request(battle.last_request, battle.turn, tracker)


def snapshot_request(request: dict[str, Any], turn: int, tracker: PublicTracker) -> tuple[DecisionSnapshot, dict[str, str]]:
    """Commands are separate from policy inputs and tied to this request's rqid."""
    if request.get("wait") or request.get("teamPreview"):
        raise ValueError("No policy decision for wait/team-preview request in gen1ou")
    tracker.request(request)
    forced = bool(request.get("forceSwitch", [False])[0])
    active = request.get("active", [{}])[0]
    trapped = bool(active.get("trapped", False))
    if active.get("maybeTrapped"):
        raise ValueError("Unexpected uncertain trapping in gen1ou; do not guess legality")
    actions: list[LegalAction] = []
    mapping: dict[str, str] = {}
    if not forced:
        for index, move in enumerate(active.get("moves", []), 1):
            if move.get("disabled") or move.get("pp", 1) == 0:
                continue
            mid = to_id_str(move.get("id", move["move"]))
            # Gen 1 emits 'fight' while asleep/frozen, hiding the unusable move menu.
            engine = mid in {"recharge", "struggle", "fight"}
            action_id = f"{'engine' if engine else 'move'}:{mid}"
            data = GenData.from_gen(1).moves.get(mid)
            if not engine and data is None:
                raise ValueError(f"Missing Gen 1 move data: {mid}")
            power = int(data["basePower"]) if data is not None else None
            actions.append(LegalAction(action_id, "engine" if engine else "move", mid, base_power=power))
            mapping[action_id] = f"/choose move {index}|{request['rqid']}"
    own_team: list[PokemonView] = []
    for index, mon in enumerate(request["side"]["pokemon"], 1):
        key = tracker.key(mon["ident"])
        slot = tracker.own_slots[key]
        hp, status = health_status(mon["condition"], True)
        own_team.append(PokemonView(slot, to_id_str(mon["details"].split(",")[0]), mon["active"], hp, status,
                                   tuple(mon["moves"]), True, tuple(sorted(tracker.own_boosts.get(key, {}).items())),
                                   hidden_moves=()))
        if (forced or not trapped) and not mon["active"] and hp.current > 0:
            action_id = f"switch:{slot}"
            actions.append(LegalAction(action_id, "switch", team_slot=slot))
            mapping[action_id] = f"/choose switch {index}|{request['rqid']}"
    if not actions:
        raise ValueError("Actionable request has no supported legal choices; no silent default")
    # Moves retain request order; switches use stable original team slots.
    actions.sort(key=lambda a: (a.kind == "switch", a.team_slot or 0))
    if len(mapping) != len(actions):
        raise ValueError("Duplicate semantic action IDs")
    other_role = "p2" if tracker.role == "p1" else "p1"
    total = tracker.team_sizes.get(other_role)
    observation = DecisionSnapshot("1.1", "gen1ou", turn, int(request["rqid"]),
                                   "forced_switch" if forced else "move", trapped,
                                   tuple(sorted(own_team, key=lambda m: m.slot)), tracker.opponents(),
                                   total, None if total is None else total - len(tracker.seen),
                                   tuple(actions), tuple(tracker.history),
                                   maybe_locked=bool(active.get("maybeLocked")),
                                   maybe_disabled=bool(active.get("maybeDisabled")))
    return observation, mapping


def resolve_action(action_id: str, observation: DecisionSnapshot, mapping: dict[str, str]) -> str:
    if action_id not in {a.id for a in observation.legal_actions} or action_id not in mapping:
        raise ValueError(f"Policy chose an illegal action: {action_id}")
    command = mapping[action_id]
    if not command.endswith(f"|{observation.request_id}"):
        raise ValueError("Stale request mapping")
    return command
