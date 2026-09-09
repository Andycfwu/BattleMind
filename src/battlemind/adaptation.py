"""Same frozen V5 scoring for all arms; only the probability summary differs."""

from dataclasses import asdict, dataclass, fields, replace

from .learned_policy import FrozenCheckpoint, LearnedDecision, LearnedScoreAgent
from .opponent_memory import HistorySummary, MemoryContext
from .schema import DecisionSnapshot
from .supervised import LogisticModel, PredictorBundle, VisibleFeatures

ARMS = ("none", "pooled", "individual")


@dataclass(frozen=True, slots=True)
class AdjustedLogistic(LogisticModel):
    history: HistorySummary = HistorySummary()

    def probability(self, features: VisibleFeatures) -> float:
        # Explicit base-class call avoids dataclass(slots=True) zero-argument super issues.
        return self.history.probability(LogisticModel.probability(self, features))


@dataclass(frozen=True, slots=True)
class AdaptationDecision(LearnedDecision):
    memory_version: str
    memory_sha256: str
    memory_context: MemoryContext
    memory_mode: str
    base_probability: float
    shadow_probabilities: tuple[tuple[str, float], ...]
    shadow_choices: tuple[tuple[str, str], ...]
    memory_fallbacks: tuple[tuple[str, str | None], ...]


class AdaptedAgent:
    version = "v6-public-memory-1"

    def __init__(self, predictor: PredictorBundle, checkpoint: FrozenCheckpoint, context: MemoryContext, mode: str):
        if mode not in ARMS or not isinstance(context, MemoryContext):
            raise ValueError("Adaptation requires an arm and immutable observer summary")
        self.context, self.mode = context, mode
        self.policies = {"none": LearnedScoreAgent(predictor, checkpoint)}
        for name in ARMS[1:]:
            model = AdjustedLogistic(**{f.name: getattr(predictor.logistic, f.name) for f in fields(LogisticModel)}, history=getattr(context, name))
            # Identical coefficients/preprocessing and digest; a separate frozen adjustment.
            self.policies[name] = LearnedScoreAgent(replace(predictor, logistic=model), checkpoint)

    def evaluate(self, obs: DecisionSnapshot) -> AdaptationDecision:
        if not isinstance(obs, DecisionSnapshot):
            raise TypeError("Adapted policies consume only frozen DecisionSnapshot values")
        evaluations = {name: policy.evaluate(obs) for name, policy in self.policies.items()}
        chosen = evaluations[self.mode]
        return AdaptationDecision(**{f.name: getattr(chosen, f.name) for f in fields(LearnedDecision)},
            memory_version=self.context.pooled.version, memory_sha256=self.context.sha256,
            memory_context=self.context, memory_mode=self.mode,
            base_probability=evaluations["none"].prediction.probability,
            shadow_probabilities=tuple((name, result.prediction.probability) for name, result in evaluations.items()),
            shadow_choices=tuple((name, result.chosen_action) for name, result in evaluations.items()),
            memory_fallbacks=tuple((name, "cold_or_sparse_encounters" if getattr(self.context, name).encounters < 2 else None) for name in ARMS[1:]))

    def choose(self, obs: DecisionSnapshot) -> str:
        return self.evaluate(obs).chosen_action
