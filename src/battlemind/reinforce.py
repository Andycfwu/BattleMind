"""Action-conditioned softmax with a frozen V2 prior; no learning during play.

This is a bilinear/log-linear model, not a neural-network framework. Features
are supported visible quantities, not an attempted simulator or exact damage.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random

import numpy as np
from poke_env.data import GenData

from .environment import ROOT, sha256
from .heuristic import Gen1HeuristicAgent, hp_fraction, nominal_accuracy, species_types, effectiveness
from .schema import DecisionSnapshot

VERSION = 'reinforce-bilinear-1'
STATUSES = ('healthy','par','slp','frz','brn','psn','tox','unknown')
STATE_NAMES = ('bias','own_hp','own_hp_unknown','foe_hp','foe_hp_unknown',
    'own_alive','revealed_foe_alive','unseen_foes','unseen_unknown','forced','trapped',
    'engine_available','lock_uncertain','disable_uncertain','turn_scaled',
    'own_displayed_atk','own_displayed_spa','own_displayed_spe',
    'foe_displayed_atk','foe_displayed_spa','foe_displayed_spe') + tuple(
        side+'_'+status for side in ('own','foe') for status in STATUSES)
ACTION_NAMES = ('bias','move','switch','engine','power','accuracy','damaging','healing',
    'sleep','paralysis','setup','self_ko','recharge','stab','type_multiplier','type_unknown',
    'switch_hp','switch_hp_unknown','switch_frozen','switch_asleep','position_gain','prior')
SHAPE = (len(STATE_NAMES), len(ACTION_NAMES))
ACTOR_NORM = 6.0
VALUE_NORM = 3.0


def features(obs: DecisionSnapshot) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not isinstance(obs, DecisionSnapshot) or obs.format != 'gen1ou':
        raise TypeError('REINFORCE consumes frozen Gen 1 DecisionSnapshot values only')
    actions=obs.legal_actions
    if not actions or len({a.id for a in actions}) != len(actions):
        raise ValueError('Empty/duplicate legal action set')
    own=next((p for p in obs.own_team if p.active),None)
    foe=next((p for p in obs.opponent_revealed if p.active),None)
    if own is None: raise ValueError('Missing own active Pokemon')
    oh=hp_fraction(own); fh=hp_fraction(foe) if foe else None
    def number(value): return 0.0 if value is None else float(value)
    s=[1,number(oh),oh is None,number(fh),fh is None,
       sum(p.health.current>0 for p in obs.own_team)/6,
       sum(p.health.current>0 for p in obs.opponent_revealed)/6,
       number(obs.opponent_unseen)/6,obs.opponent_unseen is None,
       obs.request_kind=='forced_switch',obs.trapped,any(a.kind=='engine' for a in actions),
       obs.maybe_locked,obs.maybe_disabled,min(obs.turn,300)/300]
    for mon in (own,foe):
        boosts=dict(mon.boosts) if mon else {}
        s.extend(boosts.get(name,0)/6 for name in ('atk','spa','spe'))
    for mon in (own,foe):
        status=mon.status if mon and mon.status in STATUSES else 'unknown'
        s.extend(status==name for name in STATUSES)
    heuristic=Gen1HeuristicAgent()
    prior=np.clip(np.array([v.score for v in heuristic.scores(obs)],dtype=np.float64)/50,-3,3)
    rows=[]
    for action,base in zip(actions,prior):
        if action.kind not in {'move','switch','engine'} or (action.kind=='move' and not action.move_id):
            raise ValueError('Unsupported request-backed action')
        move=GenData.from_gen(1).moves.get(action.move_id,{}) if action.kind=='move' else {}
        target=next((p for p in obs.own_team if p.slot==action.team_slot),None) if action.kind=='switch' else None
        if action.kind=='switch' and (target is None or target.active or target.health.current<=0):
            raise ValueError('Invalid legal switch target')
        th=hp_fraction(target) if target else None
        attack_type=move.get('type')
        known_type=bool(attack_type and foe and species_types(foe.species))
        rows.append([1,action.kind=='move',action.kind=='switch',action.kind=='engine',
            min(move.get('basePower',0),200)/200,nominal_accuracy(move) if move else 0,
            move.get('basePower',0)>0,action.move_id in {'recover','softboiled','rest'},
            move.get('status')=='slp',move.get('status')=='par',
            action.move_id in {'swordsdance','amnesia','agility'},bool(move.get('selfdestruct')),
            action.move_id=='hyperbeam',bool(attack_type and attack_type in species_types(own.species)),
            effectiveness(attack_type,species_types(foe.species))/4 if known_type else 0,not known_type,
            number(th),th is None,bool(target and target.status=='frz'),bool(target and target.status=='slp'),
            np.clip((heuristic.position_score(target,foe)-heuristic.position_score(own,foe))/200,-1,1) if target else 0,
            base/3])
    state=np.asarray(s,dtype=np.float64)
    action=np.asarray(rows,dtype=np.float64)
    if state.shape!=(SHAPE[0],) or action.shape!=(len(actions),SHAPE[1]): raise ValueError('Feature shape mismatch')
    if not all(np.isfinite(x).all() for x in (state,action,prior)): raise ValueError('Nonfinite visible features')
    # Fixed normalization, never estimated using training/selection/evaluation data.
    return state / math.sqrt(SHAPE[0]), action, prior


def softmax(logits: np.ndarray) -> np.ndarray:
    if logits.ndim!=1 or not len(logits) or not np.isfinite(logits).all(): raise ValueError('Invalid model logits')
    shifted=logits-logits.max()
    if shifted.min() < -700: raise ValueError('Numerically degenerate policy; no fallback')
    p=np.exp(shifted); p/=p.sum()
    if not np.isfinite(p).all() or (p<=0).any(): raise ValueError('Invalid action probabilities')
    return p


@dataclass(frozen=True, slots=True)
class Parameters:
    actor: tuple[tuple[float,...],...]
    value: tuple[float,...]

    def __post_init__(self):
        if not isinstance(self.actor,tuple) or not all(isinstance(r,tuple) for r in self.actor) or not isinstance(self.value,tuple):
            raise TypeError('Parameters must be deeply immutable')
        for data,shape,bound in ((self.actor,SHAPE,ACTOR_NORM),(self.value,(SHAPE[0],),VALUE_NORM)):
            a=np.asarray(data,dtype=np.float64)
            if a.shape!=shape or not np.isfinite(a).all() or np.linalg.norm(a)>bound+1e-10:
                raise ValueError('Parameter shape, finite value or norm bound violated')

    @classmethod
    def initial(cls):
        return cls(tuple((0.0,)*SHAPE[1] for _ in STATE_NAMES),(0.0,)*SHAPE[0])


@dataclass(frozen=True, slots=True)
class Checkpoint:
    parameters: Parameters
    sha256: str

    def __post_init__(self):
        if not isinstance(self.parameters,Parameters) or len(self.sha256)!=64 or any(c not in '0123456789abcdef' for c in self.sha256):
            raise ValueError('Invalid frozen checkpoint')


def compatibility() -> dict:
    return {'version':VERSION,'snapshot':'1.1','state_features':STATE_NAMES,'action_features':ACTION_NAMES,
        'actor_shape':SHAPE,'value_shape':(SHAPE[0],),'prior':'frozen V2 score / 50 clipped [-3,3]',
        'actor_norm':ACTOR_NORM,'value_norm':VALUE_NORM,'dtype':'float64',
        'source_hashes':{name:sha256(ROOT/'src/battlemind'/name) for name in ('reinforce.py','heuristic.py','schema.py')},
        'versions_sha256':sha256(ROOT/'configs/versions.json')}


def save_checkpoint(path: Path, parameters: Parameters, provenance: dict) -> Checkpoint:
    path.parent.mkdir(parents=True,exist_ok=True)
    artifact={'schema_version':'reinforce-checkpoint-1','compatibility':compatibility(),
        'actor':parameters.actor,'value':parameters.value,'provenance':provenance}
    with path.open('x',encoding='utf-8') as f: json.dump(artifact,f,indent=2,allow_nan=False)
    return load_checkpoint(path)


def _compatible_checkpoint(recorded: dict) -> bool:
    current=json.loads(json.dumps(compatibility()))
    if recorded==current:
        return True
    # Only the reviewed validation-only source revision may read original v1
    # artifacts. Every other source/feature/runtime field must still match.
    profile=json.loads((ROOT/'configs/reinforce-loader-compatibility.json').read_text())
    original=profile['original_checkpoint_compatibility']
    repaired=json.loads(json.dumps(original))
    repaired['source_hashes']['reinforce.py']=profile['repaired_reinforce_sha256']
    return recorded==original and current==repaired


def load_checkpoint(path: Path) -> Checkpoint:
    if path.stat().st_size>1_000_000: raise ValueError('Oversized policy checkpoint')
    data=json.loads(path.read_text())
    if set(data)!={'schema_version','compatibility','actor','value','provenance'} or data['schema_version']!='reinforce-checkpoint-1':
        raise ValueError('Unsupported policy checkpoint')
    if not _compatible_checkpoint(data['compatibility']): raise ValueError('Incompatible policy features/source')
    if (not isinstance(data['actor'],list) or not all(isinstance(row,list) for row in data['actor'])
        or not isinstance(data['value'],list)):
        raise ValueError('Checkpoint coefficients must be numeric arrays')
    # Do not let NumPy's float coercion validate strings/bools that remain in
    # the immutable tuples and then fail (or change meaning) during inference.
    if any(type(v) not in (int,float) for row in [*data['actor'],data['value']] for v in row):
        raise ValueError('Checkpoint coefficients must be JSON numbers')
    return Checkpoint(Parameters(tuple(tuple(r) for r in data['actor']),tuple(data['value'])),sha256(path))


def distribution(obs: DecisionSnapshot, params: Parameters):
    state,actions,prior=features(obs)
    logits=prior+actions@np.asarray(params.actor).T@state
    value=float(np.tanh(state@np.asarray(params.value)))
    return softmax(logits),value,logits,state,actions


@dataclass(frozen=True, slots=True)
class ActionEvaluation:
    chosen_action: str
    legal_ids: tuple[str,...]
    probabilities: tuple[float,...]
    logits: tuple[float,...]
    value: float
    draw: float
    checkpoint_sha256: str
    feature_version: str = VERSION


class ReinforceAgent:
    version=VERSION

    def __init__(self, checkpoint: Checkpoint, seed: int):
        if not isinstance(checkpoint,Checkpoint): raise TypeError('Frozen REINFORCE checkpoint required')
        self.parameters=checkpoint.parameters
        self.checkpoint_sha256=checkpoint.sha256
        self.rng=random.Random(seed)

    def act(self, observation: DecisionSnapshot) -> ActionEvaluation:
        p,value,logits,_,_=distribution(observation,self.parameters)
        draw=self.rng.random()
        index=min(int(np.searchsorted(np.cumsum(p),draw,side='right')),len(p)-1)
        return ActionEvaluation(observation.legal_actions[index].id,tuple(a.id for a in observation.legal_actions),
            tuple(float(v) for v in p),tuple(float(v) for v in logits),value,draw,self.checkpoint_sha256)

    def choose(self, observation: DecisionSnapshot) -> str:
        return self.act(observation).chosen_action
