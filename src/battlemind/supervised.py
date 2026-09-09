"""Observer-only features and immutable, JSON-serializable logistic inference.

No recorder metadata is accepted here. Training lives in supervised_training.py.
"""

from dataclasses import asdict, dataclass
import math

from poke_env.data import GenData

from .heuristic import attack_score, hp_fraction
from .prediction import Context, CountTable, context_from_snapshot
from .schema import DecisionSnapshot

FEATURE_VERSION = "visible-logistic-v1"
CATEGORICAL = ("opponent_hp", "opponent_status", "type_pressure", "own_status")
NUMERIC = ("own_hp_fraction", "opponent_hp_fraction", "own_attack_utility",
           "revealed_foe_attack_utility", "own_recent_switch", "foe_recent_switch")
FEATURE_DEFINITIONS = {
    "categorical": list(CATEGORICAL), "numeric": list(NUMERIC),
    "context": "V3 visible-context-v1 categories; own status healthy/impaired/unknown",
    "hp": "displayed current/maximum fraction; missing if maximum/active Pokemon unknown; no private reconstruction",
    "attack": "best own legal ordinary attack / best publicly revealed foe attack using unchanged V2 utility; cap 300, divide by 100; missing if no such attack",
    "recent_switch": "public switch or drag for that side at turn>0 within last two turns; not a claim of voluntary intent",
}


@dataclass(frozen=True, slots=True)
class VisibleFeatures:
    categories: tuple[str, ...]
    numbers: tuple[float | None, ...]

    def __post_init__(self):
        if (not isinstance(self.categories, tuple) or not isinstance(self.numbers, tuple)
            or len(self.categories) != len(CATEGORICAL) or len(self.numbers) != len(NUMERIC)
            or any(not isinstance(x, str) or not x or x == "__unseen__" for x in self.categories)
            or any(x is not None and (type(x) not in {float, int} or not math.isfinite(x)) for x in self.numbers)):
            raise ValueError("Invalid visible feature vector")
        Context(*self.categories[:3])
        if self.categories[3] not in {"healthy", "impaired", "unknown"}:
            raise ValueError("Invalid own status feature")

    @property
    def context(self) -> Context:
        return Context(*self.categories[:3])


def features_from_snapshot(obs: DecisionSnapshot) -> VisibleFeatures:
    context = context_from_snapshot(obs)  # checks frozen snapshot type and format
    own = next((p for p in obs.own_team if p.active), None)
    foe = next((p for p in obs.opponent_revealed if p.active), None)
    status = "unknown" if own is None or own.status is None else "healthy" if own.status == "healthy" else "impaired"
    outgoing = [attack_score(a.move_id, own, foe) for a in obs.legal_actions
                if own and foe and a.kind == "move" and a.base_power]
    incoming = [attack_score(m, foe, own) for m in foe.moves
                if own and GenData.from_gen(1).moves.get(m, {}).get("basePower")] if foe else []

    def recent(side: str) -> float:
        return float(any(e.kind in {"switch", "drag"} and (e.actor or "").startswith(side + ":")
                         and e.turn > 0 and 0 <= obs.turn - e.turn <= 2 for e in obs.public_history))

    return VisibleFeatures(tuple(asdict(context).values()) + (status,),
        (hp_fraction(own) if own else None, hp_fraction(foe) if foe else None,
         min(max(outgoing), 300) / 100 if outgoing else None,
         min(max(incoming), 300) / 100 if incoming else None, recent("own"), recent("opponent")))


def features_from_dict(data: dict) -> VisibleFeatures:
    if set(data) != {"categories", "numbers"}:
        raise ValueError("Unexpected feature fields")
    return VisibleFeatures(tuple(data["categories"]), tuple(data["numbers"]))


@dataclass(frozen=True, slots=True)
class Preprocessor:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    vocabulary: tuple[tuple[str, ...], ...]

    def __post_init__(self):
        if (not isinstance(self.means, tuple) or not isinstance(self.scales, tuple)
            or not isinstance(self.vocabulary, tuple) or len(self.means) != len(NUMERIC)
            or len(self.scales) != len(NUMERIC) or len(self.vocabulary) != len(CATEGORICAL)
            or any(not math.isfinite(x) for x in self.means + self.scales)
            or any(x <= 0 for x in self.scales)
            or any(not isinstance(v, tuple) or tuple(sorted(set(v))) != v or "__unseen__" in v
                   or any(not isinstance(x, str) or not x for x in v) for v in self.vocabulary)):
            raise ValueError("Invalid frozen preprocessing")

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(x for name in NUMERIC for x in (name + ":z", name + ":missing")) + tuple(
            name + "=" + category for name, vocabulary in zip(CATEGORICAL, self.vocabulary)
            for category in vocabulary + ("__unseen__",))

    def transform(self, features: VisibleFeatures) -> tuple[float, ...]:
        result = []
        for x, mean, scale in zip(features.numbers, self.means, self.scales):
            result.extend((0.0 if x is None else (x - mean) / scale, float(x is None)))
        for value, vocabulary in zip(features.categories, self.vocabulary):
            result.extend(float(value == category) for category in vocabulary)
            result.append(float(value not in vocabulary))
        if any(not math.isfinite(x) for x in result):
            raise ValueError("Nonfinite transformed features")
        return tuple(result)


def sigmoid(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("Nonfinite logistic score")
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


@dataclass(frozen=True, slots=True)
class LogisticModel:
    preprocessing: Preprocessor
    coefficients: tuple[float, ...]
    intercept: float
    regularization: float
    feature_version: str = FEATURE_VERSION

    def __post_init__(self):
        if (self.feature_version != FEATURE_VERSION or not isinstance(self.coefficients, tuple)
            or len(self.coefficients) != len(self.preprocessing.columns)
            or any(not math.isfinite(x) for x in self.coefficients + (self.intercept, self.regularization))
            or self.regularization <= 0):
            raise ValueError("Incompatible/nonfinite logistic model")

    def probability(self, features: VisibleFeatures) -> float:
        return sigmoid(self.intercept + sum(w * x for w, x in zip(self.coefficients, self.preprocessing.transform(features))))

    def predict(self, obs: DecisionSnapshot) -> float:
        return self.probability(features_from_snapshot(obs))


@dataclass(frozen=True, slots=True)
class PredictorBundle:
    """Only fitted parameters and a content digest cross into the policy, no provenance IDs."""
    table: CountTable
    logistic: LogisticModel
    sha256: str
    version: str = "v4-supervised-1"


def model_from_dict(data: dict) -> LogisticModel:
    prep = data["preprocessing"]
    return LogisticModel(**{**data, "preprocessing": Preprocessor(tuple(prep["means"]), tuple(prep["scales"]),
        tuple(tuple(v) for v in prep["vocabulary"])), "coefficients": tuple(data["coefficients"])})
