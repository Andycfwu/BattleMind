"""Fixed development opponents. V2's original implementation stays unchanged."""

from .heuristic import ActionScore, Gen1HeuristicAgent
from .schema import DecisionSnapshot


class SwitchingHeuristicAgent(Gen1HeuristicAgent):
    def __init__(self, threshold: int):
        if threshold not in {0, 40}:
            raise ValueError("Fixed opponents support thresholds 0 and 40 only")
        self.threshold = threshold
        self.version = f"fixed-switch-threshold-{threshold}-v1"

    def scores(self, obs: DecisionSnapshot) -> tuple[ActionScore, ...]:
        if not isinstance(obs, DecisionSnapshot):
            raise TypeError("Fixed opponent requires a frozen DecisionSnapshot")
        original = super().scores(obs)
        if obs.request_kind == "forced_switch":
            return original
        own = next(p for p in obs.own_team if p.active)
        foe = next((p for p in obs.opponent_revealed if p.active), None)
        best_move = max((s.score for a, s in zip(obs.legal_actions, original) if a.kind != "switch"), default=0)
        recent = any(e.kind in {"switch", "drag"} and (e.actor or "").startswith("own:")
                     and e.turn > 0 and obs.turn - e.turn <= 2 for e in obs.public_history)
        result = []
        for action, score in zip(obs.legal_actions, original):
            if action.kind == "switch":
                target = next(p for p in obs.own_team if p.slot == action.team_slot)
                gain = self.position_score(target, foe) - self.position_score(own, foe)
                score = ActionScore(action.id, best_move + gain - self.threshold
                                    if gain > self.threshold and not recent else -1000,
                                    f"fixed switch gain={gain:.2f}, threshold>{self.threshold}, cooldown={recent}")
            result.append(score)
        return tuple(result)
