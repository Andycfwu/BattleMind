"""One controlled actor-only step contrast; historical gradients stay unchanged."""
import numpy as np

from .reinforce import ACTOR_NORM, VALUE_NORM, Parameters, Checkpoint
from .reinforce_training import Episode, gradients

VERSION = 'actor-step-update-1'


def controlled_update(checkpoint: Checkpoint, episodes: list[Episode], multiplier: int):
    if type(multiplier) is not int or multiplier not in (1, 10):
        raise ValueError('Actor multiplier must be exactly 1 or 10')
    ga, gv, metrics = gradients(checkpoint.parameters, episodes, checkpoint.sha256)
    if not all(np.isfinite(v) for v in metrics.values()):
        raise ValueError('Nonfinite rollout loss or metric')

    def step(current, gradient, rate, bound):
        norm = float(np.linalg.norm(gradient))
        clipped = gradient / max(1, norm)
        proposal = np.asarray(current) - rate * clipped
        proposal_norm = float(np.linalg.norm(proposal))
        result = proposal * min(1, bound / max(proposal_norm, 1e-30))
        return result, norm, proposal_norm > bound, float(np.linalg.norm(rate * clipped))

    # Preserve /100 episode averaging and norm-one clipping. The sole treatment
    # is the actor step multiplier AFTER clipping and BEFORE norm-six projection.
    actor, an, ap, astep = step(checkpoint.parameters.actor, ga, 30.0 * multiplier, ACTOR_NORM)
    value, vn, vp, vstep = step(checkpoint.parameters.value, gv, .1, VALUE_NORM)
    result = Parameters(tuple(tuple(float(x) for x in row) for row in actor), tuple(float(x) for x in value))
    control_actor, *_ = step(checkpoint.parameters.actor, ga, 30.0, ACTOR_NORM)
    control_delta = float(np.linalg.norm(control_actor - np.asarray(checkpoint.parameters.actor)))
    applied_delta = float(np.linalg.norm(actor - np.asarray(checkpoint.parameters.actor)))
    values = np.array([s.value for e in episodes for s in e.steps])
    returns = np.array([e.reward for e in episodes for _ in e.steps])
    advantages = returns - values
    def stats(data):
        return {'mean': float(data.mean()), 'std': float(data.std()),
                'quantiles_0_25_50_75_100': np.quantile(data, [0, .25, .5, .75, 1]).tolist()}
    # Original keys remain comparable with historical update() under multiplier 1.
    return result, {**metrics, 'actor_gradient_norm': an, 'value_gradient_norm': vn,
        'actor_lr': 30.0, 'value_lr': .1,
        'actor_delta_l2': applied_delta,
        'value_delta_l2': float(np.linalg.norm(value - np.asarray(checkpoint.parameters.value))),
        'training_battle_keys': [e.battle_key for e in episodes],
        'update_version': VERSION, 'actor_multiplier': multiplier,
        'actor_gradient_clipped': an > 1, 'value_gradient_clipped': vn > 1,
        'actor_projected': ap, 'value_projected': vp,
        'actor_preprojection_step_l2': astep, 'value_preprojection_step_l2': vstep,
        'same_input_control_actor_delta_l2': control_delta,
        'applied_vs_same_input_control_delta_ratio': applied_delta/control_delta if control_delta else None,
        'actor_norm': float(np.linalg.norm(actor)), 'value_norm': float(np.linalg.norm(value)),
        'advantages': stats(advantages), 'values': stats(values),
        'value_errors': stats(values - returns), 'value_mse': float(np.mean((values-returns)**2)),
        'value_explained_variance': float(1-np.var(values-returns)/np.var(returns)) if np.var(returns) else None}
