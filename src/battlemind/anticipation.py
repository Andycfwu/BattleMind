"""One scoring policy, with interchangeable frozen estimates of switching probability."""

from dataclasses import dataclass, fields, replace

from .heuristic import Gen1HeuristicAgent, attack_score
from .prediction import CountPredictor, CountTable, Prediction
from .schema import DecisionSnapshot
from .supervised import PredictorBundle, features_from_snapshot


@dataclass(frozen=True, slots=True)
class CandidateScore:
    action_id: str
    stay_score: float
    switch_score: float
    score: float
    reason: str


@dataclass(frozen=True, slots=True)
class PredictedDecision:
    chosen_action: str
    prediction: Prediction
    applied: bool
    revealed_destination_slots: tuple[int, ...]
    anonymous_destination_weight: int
    scores: tuple[CandidateScore, ...]
    constant_choice: str
    conditional_choice: str
    v2_choice: str


@dataclass(frozen=True, slots=True)
class SupervisedDecision(PredictedDecision):
    logistic_choice: str
    predictor_version: str
    predictor_sha256: str
    alternate_probabilities: tuple[tuple[str, float], ...]


class SwitchAwareAgent:
    version = "switch-aware-v1"

    def __init__(self, counts: CountTable | PredictorBundle, mode: str):
        self.bundle = counts if isinstance(counts, PredictorBundle) else None
        self.mode = mode
        if mode == "logistic" and not self.bundle:
            raise ValueError("Logistic policy requires a supervised artifact")
        self.predictor = CountPredictor(self.bundle.table if self.bundle else counts,
                                        "constant" if mode == "logistic" else mode)
        if self.bundle:
            self.version = "switch-aware-v1-supervised-sources-v1"

    def evaluate(self, obs: DecisionSnapshot) -> PredictedDecision:
        prediction = self.predictor.predict(obs)
        logistic_probability = self.bundle.logistic.probability(features_from_snapshot(obs)) if self.bundle else None
        if self.mode == "logistic":
            prediction = replace(prediction, probability=logistic_probability, mode="logistic", fallback=None)
        base = Gen1HeuristicAgent().scores(obs)  # V2 weights and switching rules remain frozen
        own = next(p for p in obs.own_team if p.active)
        destinations = tuple(p for p in obs.opponent_revealed if not p.active and p.health.current > 0)
        # Anonymous alternatives carry no invented species/HP/moves in the observation.
        anonymous = obs.opponent_unseen if obs.opponent_unseen is not None else 1
        weight = len(destinations) + anonymous
        applied = obs.request_kind == "move" and any(a.kind == "move" for a in obs.legal_actions) and weight > 0
        scores = []
        for action, original in zip(obs.legal_actions, base):
            switch_score = original.score
            if applied and action.kind == "move" and action.base_power:
                switch_score = (sum(attack_score(action.move_id, own, p) for p in destinations)
                                + anonymous * attack_score(action.move_id, own, None)) / weight
            value = (1 - prediction.probability) * original.score + prediction.probability * switch_score
            scores.append(CandidateScore(action.id, original.score, switch_score, value,
                "mixture of current target and uniform public/anonymous destinations" if switch_score != original.score else original.reason))

        def choice(probability: float) -> str:
            return max(scores, key=lambda c: (1 - probability) * c.stay_score + probability * c.switch_score).action_id

        constant = CountPredictor(self.predictor.table, "constant").predict_context(prediction.context)
        conditional = CountPredictor(self.predictor.table, "conditional").predict_context(prediction.context)
        result = PredictedDecision(choice(prediction.probability), prediction, applied,
            tuple(p.slot for p in destinations), anonymous, tuple(scores),
            choice(constant.probability), choice(conditional.probability), max(base, key=lambda c: c.score).action_id)
        if self.bundle:
            return SupervisedDecision(**{f.name: getattr(result, f.name) for f in fields(PredictedDecision)},
                logistic_choice=choice(logistic_probability), predictor_version=self.bundle.version,
                predictor_sha256=self.bundle.sha256, alternate_probabilities=(("constant", constant.probability),
                    ("conditional", conditional.probability), ("logistic", logistic_probability)))
        return result

    def choose(self, observation: DecisionSnapshot) -> str:
        return self.evaluate(observation).chosen_action
