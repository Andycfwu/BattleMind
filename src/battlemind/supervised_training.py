"""Small deterministic L2 logistic regression: Newton optimization, not a simulator.

Standard likelihood/IRLS algorithm; see docs/PREDICTION.md for attribution/objective.
NumPy was already pinned for poke-env; no new dependency download is required.
"""

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import platform
import time

import numpy as np
import psutil

from .dataset import balance, write_json
from .environment import sha256, source_manifest
from .prediction import FEATURE_DEFINITIONS as COUNT_FEATURES, estimate_counts
from .prediction_report import probability_metrics
from .supervised import (CATEGORICAL, NUMERIC, FEATURE_VERSION, FEATURE_DEFINITIONS,
                         LogisticModel, Preprocessor, VisibleFeatures, features_from_dict)

REGULARIZATIONS = (0.01, 0.1, 1.0)


def fit_preprocessor(features: list[VisibleFeatures]) -> Preprocessor:
    if not features:
        raise ValueError("Preprocessing requires training examples")
    means, scales = [], []
    for i in range(len(NUMERIC)):
        observed = [f.numbers[i] for f in features if f.numbers[i] is not None]
        mean = float(np.mean(observed)) if observed else 0.0
        scale = float(np.std(observed)) if observed else 1.0
        means.append(mean)
        scales.append(scale if scale > 1e-12 else 1.0)
    vocabulary = tuple(tuple(sorted({f.categories[i] for f in features})) for i in range(len(CATEGORICAL)))
    return Preprocessor(tuple(means), tuple(scales), vocabulary)


def objective_gradient_hessian(x, y, weights, regularization):
    """x includes intercept column; intercept is not penalized. Mean-loss convention."""
    logits = x @ weights
    probabilities = np.exp(-np.logaddexp(0, -logits))
    penalty = np.full(len(weights), regularization)
    penalty[0] = 0.0
    objective = float(np.mean(np.logaddexp(0, logits) - y * logits) + np.dot(penalty, weights * weights) / 2)
    gradient = x.T @ (probabilities - y) / len(y) + penalty * weights
    hessian = (x.T * (probabilities * (1 - probabilities))) @ x / len(y) + np.diag(penalty)
    return objective, gradient, hessian


def fit_logistic(features: list[VisibleFeatures], targets: list[int], preprocessing: Preprocessor,
                 regularization: float) -> tuple[LogisticModel, dict]:
    if (not features or len(features) != len(targets) or set(targets) != {0, 1}
        or any(type(y) is not int for y in targets) or not math.isfinite(regularization) or regularization <= 0):
        raise ValueError("Logistic training needs aligned data, both binary classes and positive regularization")
    x = np.array([(1.0,) + preprocessing.transform(f) for f in features], dtype=np.float64)
    y = np.array(targets, dtype=np.float64)
    weights = np.zeros(x.shape[1], dtype=np.float64)
    for iteration in range(101):
        loss, gradient, hessian = objective_gradient_hessian(x, y, weights, regularization)
        norm = float(np.max(np.abs(gradient)))
        if norm < 1e-8:
            return LogisticModel(preprocessing, tuple(float(w) for w in weights[1:]), float(weights[0]), regularization), {
                "iterations": iteration, "objective": loss, "gradient_inf_norm": norm, "converged": True}
        if iteration == 100:
            break
        direction = np.linalg.solve(hessian, gradient)
        step = 1.0
        for _ in range(40):
            candidate = weights - step * direction
            trial = objective_gradient_hessian(x, y, candidate, regularization)[0]
            if math.isfinite(trial) and trial <= loss - 1e-4 * step * float(gradient @ direction):
                weights = candidate
                break
            step /= 2
        else:
            raise ValueError("Logistic line search did not converge")
    raise ValueError("Logistic training exceeded its 100-iteration budget")


def train_bundle(dataset: Path, output: Path) -> dict:
    from .supervised_data import read_supervised_dataset
    if output.exists():
        raise ValueError("Model output must be fresh")
    started, cpu = time.monotonic(), time.process_time()
    manifest, rows = read_supervised_dataset(dataset)
    if manifest["role"] != "development":
        raise ValueError("Training requires a development dataset")
    selected = [r for r in rows if r["target_player"] == "b"]
    train = [r for r in selected if r["partition"] == "development_fit"]
    validation = [r for r in selected if r["partition"] == "development_check"]
    if not validation:
        raise ValueError("Regularization selection needs validation battles")
    features = [features_from_dict(r["features"]) for r in train]
    targets = [r["target"] for r in train]
    preprocessing = fit_preprocessor(features)  # only training values determine any parameter
    counts = estimate_counts((f.context, y) for f, y in zip(features, targets))
    candidates = []
    models = []
    for strength in REGULARIZATIONS:
        model, convergence = fit_logistic(features, targets, preprocessing, strength)
        metrics = probability_metrics([r["target"] for r in validation],
            [model.probability(features_from_dict(r["features"])) for r in validation])
        candidates.append({"regularization": strength, "validation_metrics": metrics, **convergence})
        models.append(model)
    best = min(range(len(candidates)), key=lambda i: (candidates[i]["validation_metrics"]["log_loss"],
        candidates[i]["validation_metrics"]["brier"], -candidates[i]["regularization"]))
    artifact = {"schema_version": "v4-supervised-1", "frozen": True,
        "feature_version": FEATURE_VERSION, "feature_definitions": FEATURE_DEFINITIONS,
        "count_feature_definitions": COUNT_FEATURES, "table": asdict(counts), "logistic": asdict(models[best]),
        "columns": list(preprocessing.columns), "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "dataset_path": str(dataset.resolve()), "development_battle_keys": sorted(manifest["battle_partitions"]),
        "fit_battle_keys": sorted(k for k, v in manifest["battle_partitions"].items() if v == "development_fit"),
        "validation_battle_keys": sorted(k for k, v in manifest["battle_partitions"].items() if v == "development_check"),
        "fit_balance": balance(train), "validation_balance": balance(validation), "target_player": "b",
        "fit_examples_sha256": hashlib.sha256(json.dumps(train, sort_keys=True).encode()).hexdigest(),
        "selection": {"criterion": "validation log loss, then Brier, then larger lambda; no refit", "candidates": candidates,
                      "selected_regularization": models[best].regularization},
        "training": {"objective": "mean log loss + lambda/2 * sum(w^2); unpenalized intercept",
            "algorithm": "full-batch Newton with Armijo backtracking", "initialization": "all zeros; no stochastic optimizer",
            "seed": 20260909, "seed_used_by_optimizer": False, "max_iterations": 100, "gradient_tolerance": 1e-8,
            "class_weight": None, "resampling": None, "calibration": None, "feature_selection": None},
        "software": {"python": platform.python_version(), "numpy": np.__version__}, "code_sha256": source_manifest(),
        "resources": {"wall_seconds": time.monotonic() - started, "python_cpu_seconds": time.process_time() - cpu,
                      "python_rss_at_completion_bytes": psutil.Process().memory_info().rss}}
    write_json(output, artifact)
    return artifact
