"""A transparent Gen 1 utility heuristic. Scores are NOT damage or win probabilities.

Only the snapshot and public, pinned species/move/type tables are consulted. Displayed
boosts gate setup moves; they are never converted into supposedly exact Gen 1 stats.
"""

from dataclasses import dataclass
from math import prod

from poke_env.data import GenData

from .schema import DecisionSnapshot, PokemonView

GEN1_TYPES = ("Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting",
              "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon")


def species_types(species: str) -> tuple[str, ...]:
    return tuple(GenData.from_gen(1).pokedex.get(species, {}).get("types", ()))


def effectiveness(attack_type: str, defender_types: tuple[str, ...]) -> float:
    chart = GenData.from_gen(1).type_chart  # indexed DEFENDING type, then attacking type
    return prod(chart[t.upper()][attack_type.upper()] for t in defender_types)


def hp_fraction(mon: PokemonView) -> float | None:
    # A public fraction is a coarse displayed fraction, never reconstructed private HP.
    if mon.health.current == 0:
        return 0.0
    if not mon.health.maximum:
        return None
    return mon.health.current / mon.health.maximum


def nominal_accuracy(move: dict) -> float:
    accuracy = move.get("accuracy", True)
    return 1.0 if accuracy is True else float(accuracy) / 100


def recovery_failure(mon: PokemonView) -> bool:
    missing = None if mon.health.maximum is None else mon.health.maximum - mon.health.current
    return missing in {255, 511} and mon.health.current % 256 != 0


def attack_score(mid: str, user: PokemonView, target: PokemonView | None) -> float:
    data = GenData.from_gen(1).moves.get(mid, {})
    power = data.get("basePower", 0)
    if not power:
        return 0.0
    target_types = species_types(target.species) if target else ()
    multiplier = effectiveness(data["type"], target_types)
    # Gen 1 fixed damage ignores type immunity for these moves (engine-verified).
    if mid in {"seismictoss", "nightshade"}:
        return 90 * nominal_accuracy(data)  # utility constant, NOT predicted HP damage
    if mid == "superfang":
        return 70 * nominal_accuracy(data)
    stab = 1.5 if data["type"] in species_types(user.species) else 1.0
    hits = data.get("multihit", 1)
    hits = hits if isinstance(hits, int) else 1  # variable hit counts remain unmodeled
    score = power * hits * nominal_accuracy(data) * stab * multiplier
    if mid == "hyperbeam":
        score *= 0.7  # conservative recharge cost; no KO prediction or exact turn cost
    if data.get("selfdestruct"):
        hp = hp_fraction(user)
        score *= 0.25 + 0.65 * (1 - (hp if hp is not None else 1))
    return score


@dataclass(frozen=True, slots=True)
class ActionScore:
    action_id: str
    score: float
    reason: str


class Gen1HeuristicAgent:
    version = "gen1-heuristic-v1"

    def move_score(self, mid: str, user: PokemonView, foe: PokemonView | None,
                   obs: DecisionSnapshot) -> tuple[float, str]:
        move = GenData.from_gen(1).moves.get(mid, {})
        damage_utility = attack_score(mid, user, foe)
        if move.get("basePower", 0):
            return damage_utility, "listed power × nominal accuracy × STAB × type; explicit move penalties"
        hp = hp_fraction(user)
        if mid in {"recover", "softboiled"}:
            # Includes the known Gen 1 255/511 HP recovery failure, from exact own HP.
            usable = hp is not None and hp <= 0.55 and not recovery_failure(user)
            return (45 + 170 * (1 - hp) if usable else 0), "recover below 55% HP; avoid known recovery failure"
        if mid == "rest":
            hurt_status = user.status in {"par", "brn", "psn", "tox"}
            usable = hp is not None and not recovery_failure(user) and (hp <= 0.35 or (hurt_status and hp < 0.75))
            return (140 * (1 - hp) + 35 * hurt_status if usable else 0), "Rest only when badly hurt or curing status"
        if foe and foe.status == "healthy":
            if move.get("status") == "slp":
                # Conservative Sleep Clause rule: don't infer who caused an existing sleep.
                asleep = any(p.status == "slp" for p in obs.opponent_revealed)
                return (0 if asleep else 140 * nominal_accuracy(move)), "sleep only a healthy target with no revealed sleeper"
            if move.get("status") == "par":
                immune = mid == "thunderwave" and "Ground" in species_types(foe.species)
                return (0 if immune else 95 * nominal_accuracy(move)), "paralyze healthy target; Thunder Wave respects Ground immunity"
        setups = {"swordsdance": "atk", "amnesia": "spa", "agility": "spe"}
        if mid in setups:
            stages = dict(user.boosts)
            healthy = hp is not None and hp >= 0.7
            return (95 if healthy and stages.get(setups[mid], 0) < 2 else 0), "setup once at high HP, using displayed stage only"
        return 0, "unsupported status utility; legal fallback only"

    def position_score(self, user: PokemonView, foe: PokemonView | None) -> float:
        offense = max((attack_score(m, user, foe) for m in user.moves), default=0)
        revealed_attacks = [attack_score(m, foe, user) for m in foe.moves
                            if GenData.from_gen(1).moves.get(m, {}).get("basePower", 0)] if foe else []
        # No invented hidden moves. Unknown incoming pressure is a fixed neutral utility.
        pressure = max(revealed_attacks, default=80)
        hp = hp_fraction(user)
        status_cost = 70 if user.status in {"slp", "frz"} else 15 if user.status in {"par", "brn"} else 0
        return min(offense, 200) - 0.6 * min(pressure, 300) + 40 * (hp if hp is not None else 0.5) - status_cost

    def scores(self, obs: DecisionSnapshot) -> tuple[ActionScore, ...]:
        user = next((p for p in obs.own_team if p.active), None)
        foe = next((p for p in obs.opponent_revealed if p.active), None)
        if user is None or not obs.legal_actions:
            raise ValueError("Heuristic needs an active Pokemon and legal choices")
        result: list[ActionScore] = []
        for action in obs.legal_actions:
            if action.kind == "move":
                score, reason = self.move_score(action.move_id, user, foe, obs)
                result.append(ActionScore(action.id, score, reason))
            elif action.kind == "engine":
                result.append(ActionScore(action.id, 40 if action.move_id == "struggle" else 0, "engine-requested action"))
        best_move = max((a.score for a in result), default=0)
        current = self.position_score(user, foe)
        recent_switch = any(e.kind in {"switch", "drag"} and (e.actor or "").startswith("own:")
                            and e.turn > 0 and obs.turn - e.turn <= 2 for e in obs.public_history)
        for action in obs.legal_actions:
            if action.kind != "switch":
                continue
            target = next(p for p in obs.own_team if p.slot == action.team_slot)
            quality = self.position_score(target, foe)
            if obs.request_kind == "forced_switch":
                score, reason = quality, "forced replacement: best visible matchup/health utility"
            else:
                gain = quality - current
                allowed = gain > 80 and not recent_switch
                score = best_move + gain - 80 if allowed else -1000
                reason = f"switch gain={gain:.2f}, threshold>80, recent-switch cooldown={recent_switch}"
            result.append(ActionScore(action.id, score, reason))
        # Preserve legal request order for every tie.
        by_id = {a.action_id: a for a in result}
        return tuple(by_id[a.id] for a in obs.legal_actions)

    def choose(self, observation: DecisionSnapshot) -> str:
        return max(self.scores(observation), key=lambda a: a.score).action_id
