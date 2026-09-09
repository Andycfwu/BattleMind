"""Monte Carlo policy gradient with a pre-batch observer-only value baseline.

Analytic derivatives for one bilinear softmax and tanh linear regressor. This is
not a general neural network/optimizer implementation. No shaping or replay buffer.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np

from .environment import sha256
from .labels import read_jsonl
from .prediction_report import audit_predictions
from .reinforce import (Parameters, Checkpoint, ReinforceAgent, distribution,
    load_checkpoint, ACTOR_NORM, VALUE_NORM)
from .runner import policy_seed, scheduled_match
from .schema import snapshot_from_dict


@dataclass(frozen=True)
class Step:
    state: np.ndarray
    actions: np.ndarray
    prior: np.ndarray
    chosen: int
    probabilities: np.ndarray
    value: float


@dataclass(frozen=True)
class Episode:
    battle_key: str
    checkpoint_sha256: str
    reward: float
    steps: tuple[Step,...]
    phase: str


def audit_run(path: Path) -> dict:
    """Private commitment audit stays separate; policy reconstruction reads snapshots."""
    base=audit_predictions(path)
    meta=json.loads((path/'run.json').read_text())
    checkpoints={side:load_checkpoint(path/record['path']) for side,record in meta.get('reinforce_checkpoints',{}).items()}
    for side,model in checkpoints.items():
        if model.sha256!=meta['reinforce_checkpoints'][side]['sha256']: raise ValueError('Rollout checkpoint hash changed')
    policies={};count=0
    for row in read_jsonl(path/'decisions.jsonl'):
        side=row['player']
        if meta['policies'][side]['name']!='reinforce':continue
        key=(row['match'],side)
        if key not in policies: policies[key]=ReinforceAgent(checkpoints[side],policy_seed(meta['config']['seed'],*key))
        result=policies[key].act(snapshot_from_dict(row['observation']))
        if json.loads(json.dumps(asdict(result)))!=row.get('policy_evaluation') or result.chosen_action!=row['chosen_action']:
            raise ValueError('Stale/corrupt action probability, value, RNG or choice')
        count+=1
    rows=read_jsonl(path/'battles.jsonl')
    if len(rows)!=meta['config']['battles']: raise ValueError('Missing requested battles')
    for row in rows:
        if row['status']=='not_started':continue
        assignments,challenger=scheduled_match(row['match']+meta['config']['schedule_offset'],len(meta['config']['teams']))
        if row['team_indices']!=assignments or row['challenger']!=challenger: raise ValueError('Unbalanced/corrupt team schedule')
    return {**base,'reinforce_decisions':count}


def trajectories(path: Path, checkpoint: Checkpoint, phase: str) -> tuple[list[Episode], list[dict]]:
    """Join terminal targets only after play. Exclude entire unknown-commitment episodes."""
    meta=json.loads((path/'run.json').read_text())
    if meta['policies']['a']['name']!='reinforce' or meta['reinforce_checkpoints']['a']['sha256']!=checkpoint.sha256:
        raise ValueError('Trajectories are not from the frozen learner')
    run_id=sha256(path/'run.json')
    decisions={}; labels={r['decision_id']:r for r in read_jsonl(path/'privileged/labels.jsonl')}
    for row in read_jsonl(path/'decisions.jsonl'):
        if row['player']=='a':decisions.setdefault(row['match'],[]).append(row)
    episodes=[];targets=[];decisions_hash=sha256(path/'decisions.jsonl')
    for battle in read_jsonl(path/'battles.jsonl'):
        rows=decisions.get(battle['match'],[])
        reason=None
        if battle['status']!='completed':reason=battle['status']
        elif not rows:reason='missing_trajectory'
        elif any(labels[r['decision_id']]['intended_kind']=='unknown' for r in rows):reason='unknown_commitment_episode'
        reward=None if reason else {'a':1.0,'draw':0.0,'b':-1.0}[battle['winner']]
        key=f"{run_id}:{battle['match']}"
        targets.append({'battle_key':key,'phase':phase,'checkpoint_sha256':checkpoint.sha256,
            'reward':reward,'exclusion':reason,'decision_ids':[r['decision_id'] for r in rows],
            'decisions_sha256':decisions_hash})
        if reason:continue
        steps=[]
        for row in rows:
            obs=snapshot_from_dict(row['observation'])
            p,v,logits,s,a=distribution(obs,checkpoint.parameters)
            record=row['policy_evaluation']
            if record['checkpoint_sha256']!=checkpoint.sha256 or not np.array_equal(p,record['probabilities']) or v!=record['value']:
                raise ValueError('On-policy trajectory incompatibility')
            index=[action.id for action in obs.legal_actions].index(row['chosen_action'])
            prior=logits-a@np.asarray(checkpoint.parameters.actor).T@s
            steps.append(Step(s,a,prior,index,p,v))
        episodes.append(Episode(key,checkpoint.sha256,reward,tuple(steps),phase))
    return episodes,targets


def gradients(parameters: Parameters, episodes: list[Episode], checkpoint_sha256: str):
    if not episodes or len({e.battle_key for e in episodes})!=len(episodes): raise ValueError('Empty or duplicated rollout episodes')
    if any(e.phase!='training' or e.checkpoint_sha256!=checkpoint_sha256 or e.reward not in {-1,0,1} or not e.steps for e in episodes):
        raise ValueError('Only compatible completed training episodes may update')
    actor=np.zeros_like(parameters.actor,dtype=np.float64);critic=np.zeros_like(parameters.value,dtype=np.float64)
    policy_loss=value_loss=entropy=0.0;decisions=0
    for episode in episodes:
        for step in episode.steps:
            if not np.isfinite(step.probabilities).all() or not np.isclose(step.probabilities.sum(),1): raise ValueError('Invalid rollout probabilities')
            # Baseline/probabilities are frozen from before this batch, no reward leakage.
            advantage=episode.reward-step.value
            delta=step.actions[step.chosen]-step.probabilities@step.actions
            actor-=advantage*np.outer(step.state,delta)
            critic+=(step.value-episode.reward)*(1-step.value**2)*step.state
            policy_loss-=advantage*np.log(step.probabilities[step.chosen])
            value_loss+=0.5*(step.value-episode.reward)**2
            entropy-=float(step.probabilities@np.log(step.probabilities));decisions+=1
    # Sum within each episode; fixed 1/100 rescales the learning rate, not by length.
    actor/=len(episodes)*100
    critic/=decisions
    if not np.isfinite(actor).all() or not np.isfinite(critic).all(): raise ValueError('Nonfinite gradient')
    return actor,critic,{'policy_loss':policy_loss/(len(episodes)*100),'value_loss':value_loss/decisions,
        'mean_entropy':entropy/decisions,'episodes':len(episodes),'decisions':decisions,
        'mean_reward':float(np.mean([e.reward for e in episodes]))}


def update(checkpoint: Checkpoint, episodes: list[Episode], actor_lr: float=.3, value_lr: float=.1):
    if not 0<actor_lr<=30 or not 0<value_lr<=1: raise ValueError('Invalid learning rate')
    ga,gv,metrics=gradients(checkpoint.parameters,episodes,checkpoint.sha256)
    def step(current,gradient,rate,bound):
        norm=float(np.linalg.norm(gradient)); clipped=gradient/max(1,norm)
        new=np.asarray(current)-rate*clipped
        new*=min(1,bound/max(float(np.linalg.norm(new)),1e-30))
        return new,norm
    actor,an=step(checkpoint.parameters.actor,ga,actor_lr,ACTOR_NORM)
    value,vn=step(checkpoint.parameters.value,gv,value_lr,VALUE_NORM)
    result=Parameters(tuple(tuple(float(x) for x in r) for r in actor),tuple(float(x) for x in value))
    return result,{**metrics,'actor_gradient_norm':an,'value_gradient_norm':vn,'actor_lr':actor_lr,'value_lr':value_lr,
        'actor_delta_l2':float(np.linalg.norm(actor-np.asarray(checkpoint.parameters.actor))),
        'value_delta_l2':float(np.linalg.norm(value-np.asarray(checkpoint.parameters.value))),
        'training_battle_keys':[e.battle_key for e in episodes]}
