"""Four bounded score controls over unchanged V4 inference; no learning during play."""

from dataclasses import asdict, dataclass, fields, replace
import json
import math
from pathlib import Path

from .anticipation import CandidateScore, SupervisedDecision, SwitchAwareAgent
from .dataset import write_json
from .environment import ROOT, sha256
from .heuristic import Gen1HeuristicAgent
from .schema import DecisionSnapshot
from .supervised import FEATURE_VERSION, PredictorBundle

PREDICTOR_SHA256 = "44a403e1771cf15f31987a08d31c7856900f04d3fc2eca2c957a23704f04a252"
SCORING_VERSION = "v5-residual-scores-1"
PARAMETER_NAMES = ("anticipation", "recovery", "status", "switch_threshold")
PARAMETER_DEFINITIONS = {
    "anticipation": "add theta*p*(switch-stay) to ordinary damaging move utility",
    "recovery": "add 100*theta to supported positive-utility recover/softboiled/rest",
    "status": "add 100*theta to other positive-utility ordinary zero-power moves",
    "switch_threshold": "threshold 80+40*theta; unchanged V2 position utility and two-turn cooldown",
    "bounds": [-1.0, 1.0], "initial": [0.0, 0.0, 0.0, 0.0],
}


@dataclass(frozen=True, slots=True)
class PolicyParameters:
    anticipation: float = 0.0
    recovery: float = 0.0
    status: float = 0.0
    switch_threshold: float = 0.0

    def __post_init__(self):
        if any(type(v) not in {float, int} or not math.isfinite(v) or not -1 <= v <= 1 for v in self.values):
            raise ValueError("Policy parameters must be four finite numbers within [-1,1]")

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(getattr(self, name) for name in PARAMETER_NAMES)


@dataclass(frozen=True, slots=True)
class FrozenCheckpoint:
    parameters: PolicyParameters
    sha256: str

    def __post_init__(self):
        if (not isinstance(self.parameters, PolicyParameters) or not isinstance(self.sha256, str)
            or len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256)):
            raise ValueError("Checkpoint boundary requires immutable parameters and a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class LearnedDecision(SupervisedDecision):
    parameters: PolicyParameters
    checkpoint_sha256: str
    scoring_version: str
    initial_choice: str
    initial_scores: tuple[CandidateScore, ...]


class LearnedScoreAgent:
    version = SCORING_VERSION

    def __init__(self, predictor: PredictorBundle, checkpoint: FrozenCheckpoint):
        if not isinstance(predictor, PredictorBundle) or not isinstance(checkpoint, FrozenCheckpoint):
            raise TypeError("Learned policy requires a frozen predictor and parameter checkpoint")
        self.parameters = checkpoint.parameters
        self.checkpoint_sha256 = checkpoint.sha256
        self.base = SwitchAwareAgent(predictor, "logistic")

    def evaluate(self, obs: DecisionSnapshot) -> LearnedDecision:
        if not isinstance(obs, DecisionSnapshot):
            raise TypeError("Learned policy consumes only a frozen DecisionSnapshot")
        baseline = self.base.evaluate(obs)
        params = self.parameters
        scores = baseline.scores
        # Direct passthrough proves bit-for-bit initialization/forced-score equivalence.
        if params != PolicyParameters() and obs.request_kind != "forced_switch":
            own = next(p for p in obs.own_team if p.active)
            foe = next((p for p in obs.opponent_revealed if p.active), None)
            heuristic = Gen1HeuristicAgent()
            best_move = max((s.stay_score for a, s in zip(obs.legal_actions, scores) if a.kind != "switch"), default=0)
            recent = any(e.kind in {"switch", "drag"} and (e.actor or "").startswith("own:")
                         and e.turn > 0 and obs.turn - e.turn <= 2 for e in obs.public_history)
            changed = []
            for action, original in zip(obs.legal_actions, scores):
                value = original.score
                if action.kind == "move":
                    if action.base_power:
                        value += params.anticipation * baseline.prediction.probability * (original.switch_score - original.stay_score)
                    elif original.stay_score > 0:
                        bias = params.recovery if action.move_id in {"recover", "softboiled", "rest"} else params.status
                        value += 100 * bias
                elif action.kind == "switch" and params.switch_threshold:
                    target = next(p for p in obs.own_team if p.slot == action.team_slot)
                    gain = heuristic.position_score(target, foe) - heuristic.position_score(own, foe)
                    threshold = 80 + 40 * params.switch_threshold
                    value = best_move + gain - threshold if gain > threshold and not recent else -1000
                if not math.isfinite(value):
                    raise ValueError("Nonfinite learned action score")
                changed.append(replace(original, score=value,
                    reason=original.reason if value == original.score else original.reason + "; V5 bounded score adjustment"))
            scores = tuple(changed)
        if any(not math.isfinite(s.score) for s in scores):
            raise ValueError("Nonfinite learned action score")
        chosen = max(scores, key=lambda s: s.score).action_id
        return LearnedDecision(**{f.name: getattr(baseline, f.name) for f in fields(SupervisedDecision)
                                   if f.name not in {"chosen_action", "scores"}},
            chosen_action=chosen, scores=scores, parameters=params, checkpoint_sha256=self.checkpoint_sha256,
            scoring_version=self.version, initial_choice=baseline.chosen_action, initial_scores=baseline.scores)

    def choose(self, observation: DecisionSnapshot) -> str:
        return self.evaluate(observation).chosen_action


def compatibility(predictor: PredictorBundle) -> dict:
    names = ("learned_policy", "anticipation", "heuristic", "prediction", "supervised", "schema")
    return {"scoring_version": SCORING_VERSION, "feature_version": FEATURE_VERSION,
        "snapshot_version": "1.1", "format": "gen1ou", "predictor_sha256": predictor.sha256,
        "parameter_definitions": PARAMETER_DEFINITIONS,
        "scoring_sources_sha256": {name: sha256(ROOT / f"src/battlemind/{name}.py") for name in names},
        "versions_sha256": sha256(ROOT / "configs/versions.json")}


def save_checkpoint(path: Path, params: PolicyParameters, predictor: PredictorBundle, provenance: dict) -> dict:
    artifact = {"schema_version": "v5-policy-1", "frozen": True, "parameters": asdict(params),
                "compatibility": compatibility(predictor), "provenance": provenance}
    write_json(path, artifact)
    return artifact


def load_checkpoint(path: Path, predictor: PredictorBundle) -> tuple[dict, FrozenCheckpoint]:
    data = json.loads(path.read_text())
    if (set(data) != {"schema_version", "frozen", "parameters", "compatibility", "provenance"}
        or data["schema_version"] != "v5-policy-1" or data["frozen"] is not True
        or data["compatibility"] != compatibility(predictor) or not isinstance(data["provenance"], dict)
        or set(data["parameters"]) != set(PARAMETER_NAMES)):
        raise ValueError("Malformed or incompatible frozen policy checkpoint")
    return data, FrozenCheckpoint(PolicyParameters(**data["parameters"]), sha256(path))
