"""Retained-data arithmetic and descriptive audit; never fits or saves a policy.

Historical final snapshots are used for diagnosis, not future evaluation. Public
features and post-match commitment evidence are processed in separate sections.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
import csv
import json
from pathlib import Path
import re
import time

import numpy as np
import psutil

from battlemind.environment import ROOT, sha256
from battlemind.labels import read_jsonl, expected_engine_choice
from battlemind.schema import snapshot_from_dict
from battlemind.reinforce import features, load_checkpoint, SHAPE, STATE_NAMES, ACTION_NAMES
from battlemind.heuristic import Gen1HeuristicAgent, hp_fraction
from battlemind.adaptation_experiment import artifacts
from battlemind.learned_policy import LearnedScoreAgent

START = time.monotonic()
CPU = time.process_time()
RUN = ROOT / 'runs/reinforce-main'
OUT = ROOT / 'runs/reinforce-audit-20260909/diagnosis'
OUT.mkdir(exist_ok=False)
LEDGER = json.loads((RUN / 'ledger.json').read_text())
CPS = {k: load_checkpoint(RUN / f'checkpoints/c{k}.json') for k in range(13)}
W = {k: np.asarray(c.parameters.actor) for k, c in CPS.items()}
V = {k: np.asarray(c.parameters.value) for k, c in CPS.items()}
H = Gen1HeuristicAgent()
PREDICTOR, V5_CHECKPOINT = artifacts()
V5 = LearnedScoreAgent(PREDICTOR, V5_CHECKPOINT)
PEAK_RSS = 0


def save(name, data):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)


def stats(values):
    a = np.asarray(values, dtype=float)
    if not a.size:
        return {'n': 0}
    assert np.isfinite(a).all()
    return {'n': len(a), 'mean': float(a.mean()), 'sd': float(a.std()),
            **dict(zip(('min', 'p10', 'median', 'p90', 'max'),
                       (float(x) for x in np.quantile(a, [0, .1, .5, .9, 1]))))}


def soft(z):
    # Independent stable arithmetic, not production softmax().
    ez = np.exp(z - np.max(z))
    p = ez / sum(ez)
    assert np.isfinite(p).all() and (p > 0).all() and abs(sum(p) - 1) < 1e-12
    return p


def sample(p, u):
    # Independent strict-CDF loop matches production side='right'.
    c = 0.0
    for i, probability in enumerate(p):
        c += probability
        if u < c:
            return i
    return len(p) - 1


def common_disagreement(p, q):
    # Length of intervals where ordered inverse-CDF choices disagree; differs
    # from TV, the minimum disagreement achievable under *any* coupling.
    cp, cq = np.r_[0, np.cumsum(p)], np.r_[0, np.cumsum(q)]
    agreement = sum(max(0, min(cp[i+1], cq[i+1]) - max(cp[i], cq[i])) for i in range(len(p)))
    return max(0.0, 1 - agreement)


def category(action, obs):
    if action.kind == 'switch':
        return 'forced_switch' if obs.request_kind == 'forced_switch' else 'voluntary_switch'
    if action.kind == 'engine':
        return 'engine'
    if action.move_id in {'recover', 'softboiled', 'rest'}:
        return 'recovery'
    if action.move_id in {'swordsdance', 'amnesia', 'agility'}:
        return 'setup'
    if action.base_power and action.base_power > 0:
        return 'damaging_move'
    return 'status_or_other'


def situation(obs):
    if obs.request_kind == 'forced_switch':
        return 'forced'
    if any(a.kind == 'engine' for a in obs.legal_actions):
        return 'engine_singleton' if len(obs.legal_actions) == 1 else 'engine_with_alternatives'
    return 'ordinary'


def csv_rows(name, rows):
    if not rows:
        return
    with (OUT / name).open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


# Real stored weights are numeric; malformed-type loader defect did not occur.
coefficient_count = 0
for k in CPS:
    raw = json.loads((RUN / f'checkpoints/c{k}.json').read_text())
    coefficients = [n for row in raw['actor'] for n in row] + raw['value']
    assert all(type(n) in (int, float) and np.isfinite(n) for n in coefficients)
    coefficient_count += len(coefficients)
assert not np.any(W[0]) and not np.any(V[0])

movement = defaultdict(lambda: defaultdict(list))
reference = defaultdict(lambda: defaultdict(list))
mass = defaultdict(lambda: defaultdict(list))
collisions = Counter()
collision_examples = {}
cases = {}
final_rows = []
boundary_ties = 0
counterfactual_boundary_ties = 0
recorded_rf = 0
max_probability_error = 0.0
max_logit_error = 0.0
max_value_error = 0.0
state_min, state_max = np.full(SHAPE[0], np.inf), np.full(SHAPE[0], -np.inf)
action_min, action_max = np.full(SHAPE[1], np.inf), np.full(SHAPE[1], -np.inf)
batch_data = defaultdict(list)
episode_rows = []
excluded = []
training_steps = []
actor_by_timing = defaultdict(list)
value_values = defaultdict(list)


def record_case(name, row, obs, p0, p6, z6, prior, raw_scores, path, battle, next_obs):
    if name in cases:
        return
    # Use only this observer's public stream for the after-decision window.
    history = json.loads((path / f"privileged/{battle['match']:03d}-histories.json").read_text())['a']
    start = len(obs.public_history)
    assert history[:start] == row['observation']['public_history']
    end = len(next_obs['public_history']) if next_obs else len(history)
    v5 = V5.evaluate(obs)
    cases[name] = {'run': path.relative_to(ROOT).as_posix(), 'battle_key': f"{sha256(path/'run.json')}:{battle['match']}",
        'decision_id': row['decision_id'], 'snapshot_sha256': row['snapshot_sha256'],
        'selection_rule': name, 'observation': row['observation'], 'actual_chosen': row['chosen_action'],
        'draw': row['policy_evaluation']['draw'], 'c0_same_draw': obs.legal_actions[sample(p0,row['policy_evaluation']['draw'])].id,
        'c6_same_draw': obs.legal_actions[sample(p6,row['policy_evaluation']['draw'])].id,
        'v2_choice': H.choose(obs), 'v5_choice': v5.chosen_action, 'v5_evaluation': asdict(v5),
        'actions': [{'id': a.id, 'category': category(a,obs), 'v2_score': float(raw_scores[i]),
                     'initial_logit': float(prior[i]), 'c6_logit': float(z6[i]), 'p0': float(p0[i]), 'p6': float(p6[i])}
                    for i,a in enumerate(obs.legal_actions)],
        'after_public_events': history[start:end], 'terminal_status': battle['status'], 'terminal_winner': battle['winner'],
        'after_is_hindsight_not_a_policy_feature': True}


for run_record in LEDGER['runs']:
    path = RUN / run_record['path']
    phase = run_record['phase']
    rows = read_jsonl(path / 'decisions.jsonl')
    # Check *both* players and every phase for the report/sampler exact-boundary bug.
    for row in rows:
        ev = row.get('policy_evaluation', {})
        if ev.get('feature_version') == 'reinforce-bilinear-1':
            recorded_rf += 1
            boundary_ties += int(any(ev['draw'] == x for x in np.cumsum(ev['probabilities'])))
            assert row['chosen_action'] == ev['legal_ids'][sample(ev['probabilities'], ev['draw'])]
    if phase == 'selection':
        continue
    print(run_record['path'], flush=True)
    by_match = defaultdict(list)
    for row in rows:
        if row['player'] == 'a':
            by_match[row['match']].append(row)
    labels = {r['decision_id']: r for r in read_jsonl(path / 'privileged/labels.jsonl')}
    submissions = Counter((r['match'], r.get('request_id')) for r in read_jsonl(path / 'events.jsonl')
                          if r['kind'] == 'submitted' and r['player'] == 'a')
    opponent = run_record['opponent']['identity']
    parent = int(Path(run_record['candidate']).stem[1:]) if phase == 'training' else (0 if 'initial-' in path.name else 6)
    for battle in read_jsonl(path / 'battles.jsonl'):
        own_rows = by_match[battle['match']]
        key = f"{run_record['run_id']}:{battle['match']}"
        terminal_reward = {'a': 1, 'draw': 0, 'b': -1}.get(battle['winner']) if battle['status'] == 'completed' else None
        unknown = [r for r in own_rows if labels[r['decision_id']]['intended_kind'] == 'unknown']
        reason = battle['status'] if battle['status'] != 'completed' else 'unknown_commitment_episode' if unknown else None
        reward = terminal_reward if reason is None else None
        ep_grad = np.zeros(SHAPE)
        ep_nobase = np.zeros(SHAPE)
        ep_critic = np.zeros(SHAPE[0])
        ep_loss = ep_vloss = ep_entropy = 0.0
        thirds = [np.zeros(SHAPE) for _ in range(3)]
        grad_norm_sum = 0.0
        chosen_counts = Counter()
        ep_values = []
        first_mismatch = None
        for index, row in enumerate(own_rows):
            obs = snapshot_from_dict(row['observation'])
            s, x, prior = features(obs)
            raw_scores = np.asarray([a.score for a in H.scores(obs)])
            current_z = prior + x @ W[parent].T @ s
            p = soft(current_z)
            v = float(np.tanh(V[parent] @ s))
            ev = row['policy_evaluation']
            max_probability_error = max(max_probability_error, float(np.max(np.abs(p - ev['probabilities']))))
            max_logit_error = max(max_logit_error, float(np.max(np.abs(current_z - ev['logits']))))
            max_value_error = max(max_value_error, abs(v - ev['value']))
            assert row['chosen_action'] in row['legal_mapping']
            ci = ev['legal_ids'].index(row['chosen_action'])
            action = obs.legal_actions[ci]
            cat = category(action, obs)
            kind = situation(obs)
            chosen_counts[cat] += 1
            ep_values.append(v)
            if phase == 'training':
                if reward is not None:
                    advantage = reward - v
                    # Independent score-function gradient via d log p / d logits.
                    dz = -p.copy(); dz[ci] += 1
                    log_grad = np.einsum('i,j->ij', s, dz @ x)
                    g = -advantage * log_grad
                    ep_grad += g
                    ep_nobase -= reward * log_grad
                    ep_critic += (v - reward) * (1-v*v) * s
                    third = min(2, 3 * index // len(own_rows))
                    thirds[third] += g
                    grad_norm_sum += float(np.linalg.norm(g))
                    ep_loss -= advantage * np.log(p[ci])
                    ep_vloss += .5 * (v-reward)**2
                    ep_entropy -= float(p @ np.log(p))
                    training_steps.append({'batch': parent+1, 'opponent': opponent, 'battle_key': key,
                        'decision_id': row['decision_id'], 'request_index': index, 'length': len(own_rows),
                        'third': ('early','middle','late')[third], 'category': cat, 'situation': kind,
                        'reward': reward, 'value': v, 'advantage': advantage, 'error_squared': (v-reward)**2,
                        'entropy': float(-p @ np.log(p)), 'pmax': float(max(p)), 'chosen_probability': float(p[ci]),
                        'legal_count': len(p), 'gradient_contribution_norm': float(np.linalg.norm(g))})
                continue

            own = next(a for a in obs.own_team if a.active)
            hp = hp_fraction(own)
            hpbin = 'hp_low' if hp is not None and hp <= .35 else 'hp_mid' if hp is not None and hp <= .55 else 'hp_high_or_unknown'
            arm = 'initial' if parent == 0 else 'selected'
            groups = ('all', kind, 'nontrivial' if len(p)>1 else 'singleton', hpbin,
                      'status:' + own.status, 'opponent:' + opponent, 'arm:' + arm)
            state_min = np.minimum(state_min, s); state_max = np.maximum(state_max, s)
            action_min = np.minimum(action_min, x.min(axis=0)); action_max = np.maximum(action_max, x.max(axis=0))
            probs, logits = {}, {}
            for k in (0,3,6,9,12):
                logits[k] = prior + x @ W[k].T @ s
                probs[k] = soft(logits[k])
            p0, p6 = probs[0], probs[6]
            u = ev['draw']; idx0 = sample(p0,u); idx6 = sample(p6,u)
            counterfactual_boundary_ties += sum(int(any(u == b for b in np.cumsum(pk))) for pk in probs.values())
            tv6 = .5*float(np.abs(p0-p6).sum())
            for k, pk in probs.items():
                values = {'tv': .5*float(np.abs(p0-pk).sum()),
                    'kl_initial_to_checkpoint': float(p0 @ (np.log(p0)-np.log(pk))),
                    'kl_checkpoint_to_initial': float(pk @ (np.log(pk)-np.log(p0))),
                    'entropy': float(-pk @ np.log(pk)), 'pmax': float(pk.max()), 'alternative_mass': float(1-pk.max()),
                    'greedy_change': int(np.argmax(p0) != np.argmax(pk)),
                    'same_draw_change': int(idx0 != sample(pk,u)),
                    'expected_common_draw_disagreement': common_disagreement(p0,pk),
                    'centered_residual_range': float(np.ptp(logits[k]-prior)),
                    'prior_range': float(np.ptp(prior)), 'legal_count': len(p0)}
                for group in groups:
                    for metric, number in values.items():
                        movement[f'c{k}/{group}'][metric].append(number)
                for cc in sorted({category(a,obs) for a in obs.legal_actions}):
                    ids = [i for i,a in enumerate(obs.legal_actions) if category(a,obs)==cc]
                    mass[f'c{k}/{cc}']['probability_mass_when_available'].append(float(pk[ids].sum()))
                    mass[f'c{k}/{cc}']['mean_absolute_per_action_probability_change'].append(float(np.abs(pk[ids]-p0[ids]).mean()))
                    mass[f'c{k}/{cc}']['sampled_selected_when_available'].append(int(sample(pk,u) in ids))
            teacher = int(np.argmax(raw_scores))
            teacher_cat = category(obs.legal_actions[teacher], obs)
            for group in (*groups, 'v2_choice:' + teacher_cat):
                vals = {'p0_of_v2_choice': float(p0[teacher]), 'p6_of_v2_choice': float(p6[teacher]),
                    'initial_greedy_matches_v2': int(np.argmax(p0)==teacher), 'initial_sample_matches_v2': int(idx0==teacher),
                    'selected_sample_matches_v2': int(idx6==teacher),
                    'initial_mass_v2_tied_best': float(p0[raw_scores==max(raw_scores)].sum()),
                    'clipped_top_actions': int((raw_scores>150).sum()),
                    'v2_zero_move_mass0': float(sum(p0[i] for i,a in enumerate(obs.legal_actions) if a.kind=='move' and raw_scores[i]==0)),
                    'v2_disfavored_switch_mass0': float(sum(p0[i] for i,a in enumerate(obs.legal_actions) if a.kind=='switch' and raw_scores[i]==-1000))}
                for metric, number in vals.items():reference[group][metric].append(number)
            for i in range(len(p0)):
                for j in range(i):
                    if prior[i]==prior[j] and np.array_equal(x[i],x[j]):
                        pair = '|'.join(sorted((obs.legal_actions[i].id, obs.legal_actions[j].id)))
                        collisions[pair]+=1
                        collision_examples.setdefault(pair,{'run':run_record['path'],'decision_id':row['decision_id'],
                            'snapshot_sha256':row['snapshot_sha256'],'probability_each_initial':float(p0[i]),'probability_each_c6':float(p6[i]),
                            'action_row':x[i].tolist(),'prior':float(prior[i])})
            final_rows.append({'run':run_record['path'],'battle_key':key,'decision_id':row['decision_id'],
                'snapshot_sha256':row['snapshot_sha256'],'arm':arm,'opponent':opponent,'situation':kind,'own_status':own.status,
                'hpbin':hpbin,'legal_count':len(p0),'draw':u,'initial_choice':obs.legal_actions[idx0].id,
                'selected_choice':obs.legal_actions[idx6].id,'tv':tv6,'kl_initial_to_selected':float(p0@(np.log(p0)-np.log(p6))),
                'initial_entropy':float(-p0@np.log(p0)),'selected_entropy':float(-p6@np.log(p6))})
            if arm == 'selected':
                wanted=[]
                if opponent in ('v2','v5') and battle['winner']=='b' and index==0:wanted.append('first_loss_'+opponent)
                if idx0!=idx6:wanted.append('first_common_draw_disagreement')
                if cat in ('recovery','voluntary_switch','forced_switch','status_or_other','setup','engine'):
                    wanted.append('first_selected_'+cat)
                if action.move_id in ('recover','softboiled') and hp is not None and hp>.55:
                    wanted.append('first_recovery_above_threshold')
                for name in wanted:
                    record_case(name,row,obs,p0,p6,logits[6],prior,raw_scores,path,battle,
                                own_rows[index+1]['observation'] if index+1<len(own_rows) else None)

        if phase == 'training':
            submitted = sum(submissions[battle['match'],r['observation']['request_id']]==1 for r in own_rows)
            ep = {'batch':parent+1,'opponent':opponent,'opponent_group':opponent if opponent in ('v2','v5') else 'archive',
                  'run':run_record['path'],'battle_key':key,'match':battle['match'],
                  'team_pair':'-'.join(str(t) for t in sorted(battle['team_indices'].values())),
                  'own_team':battle['team_indices']['a'],'opponent_team':battle['team_indices']['b'],
                  'status':battle['status'],'terminal_reward':terminal_reward,'training_reward':reward,'exclusion':reason or 'admitted',
                  'turns':battle['turns'],'own_requests':len(own_rows),'submitted_once':submitted,
                  'verified_choices':len(own_rows)-len(unknown),'unknown_choices':len(unknown),
                  'mean_value':float(np.mean(ep_values)),'gradient_sum_norm':float(np.linalg.norm(ep_grad)) if reward is not None else None,
                  'individual_gradient_norm_sum':grad_norm_sum if reward is not None else None,
                  'selected_categories':dict(chosen_counts)}
            episode_rows.append(ep)
            if reason:
                # Privileged input evidence remains diagnostics only; not fed into
                # any feature or used to construct a training target/gradient.
                engine=json.loads((path/battle['engine_record']['path']).read_text()) if battle.get('engine_record') else {}
                stream=[]
                for line in engine.get('inputLog',[]):
                    m=re.fullmatch(r'>(p[12]) (move .+|switch \d+)',line)
                    if m and m[1]==battle['player_roles']['a']:stream.append(m[2])
                for i,r in enumerate(own_rows):
                    actual=stream[i] if i<len(stream) else None
                    expected=expected_engine_choice(r)
                    if actual!=expected:
                        first_mismatch={'index':i,'decision_id':r['decision_id'],'turn':r['observation']['turn'],
                            'selected':r['chosen_action'],'expected':expected,'engine_at_same_index':actual,
                            'legal_mapping':r['legal_mapping'],'maybe_locked':r['observation']['maybe_locked'],
                            'maybe_disabled':r['observation']['maybe_disabled'],
                            'public_history_tail':r['observation']['public_history'][-12:],
                            'raw_label':labels[r['decision_id']]}
                        break
                excluded.append({**ep,'input_count':len(stream),'input_count_equals_attempts':len(stream)==len(own_rows),
                    'first_literal_mismatch':first_mismatch,'unknown_reasons':dict(Counter(labels[r['decision_id']]['unknown_reason'] for r in unknown)),
                    'source_run_sha256':run_record['run_id'],'engine_sha256':battle.get('engine_record',{}).get('sha256'),
                    'terminal_detail':battle.get('detail')})
            else:
                batch_data[parent+1].append({'metadata':ep,'gradient':ep_grad,'nobase':ep_nobase,'critic':ep_critic,
                    'loss':ep_loss,'value_loss':ep_vloss,'entropy':ep_entropy,'thirds':thirds})
    PEAK_RSS=max(PEAK_RSS, psutil.Process().memory_info().rss)

assert recorded_rf==83170 and len(final_rows)==20389
assert max_probability_error<1e-12 and max_logit_error<1e-12 and max_value_error<1e-12
assert sum(e['exclusion']=='unknown_commitment_episode' for e in excluded)==70
assert len(excluded)==71 and len(episode_rows)==864

updates=[]
for batch, episodes in sorted(batch_data.items()):
    n=len(episodes);decisions=sum(e['metadata']['own_requests'] for e in episodes)
    ga=sum((e['gradient'] for e in episodes),start=np.zeros(SHAPE))/(n*100)
    gn=sum((e['nobase'] for e in episodes),start=np.zeros(SHAPE))/(n*100)
    gv=sum((e['critic'] for e in episodes),start=np.zeros(SHAPE[0]))/decisions
    next_w=W[batch-1]-30*ga/max(1,float(np.linalg.norm(ga)))
    next_w*=min(1,6/max(float(np.linalg.norm(next_w)),1e-30))
    next_v=V[batch-1]-.1*gv/max(1,float(np.linalg.norm(gv)))
    next_v*=min(1,3/max(float(np.linalg.norm(next_v)),1e-30))
    err=max(float(np.max(np.abs(next_w-W[batch]))),float(np.max(np.abs(next_v-V[batch]))))
    assert err<1e-12
    historical=json.loads((RUN/f'batches/update-{batch}.json').read_text())['metrics']
    calculated={'policy_loss':sum(e['loss'] for e in episodes)/(100*n),
                'value_loss':sum(e['value_loss'] for e in episodes)/decisions,
                'mean_entropy':sum(e['entropy'] for e in episodes)/decisions,
                'actor_gradient_norm':float(np.linalg.norm(ga)),'value_gradient_norm':float(np.linalg.norm(gv))}
    assert max(abs(historical[k]-v) for k,v in calculated.items())<1e-12
    thirds={name:float(np.linalg.norm(sum((e['thirds'][i] for e in episodes),start=np.zeros(SHAPE))/(100*n)))
            for i,name in enumerate(('early','middle','late'))}
    block=defaultdict(list)
    for e in episodes:block[(e['metadata']['run'],e['metadata']['match']//4)].append(e['gradient'])
    # Descriptive block-level noise scale: complete schedule blocks are clustered.
    # Not a formal CI: exclusion rates and changing policies differ across blocks.
    block_means=np.asarray([sum(values)/len(values)/100 for values in block.values()])
    noise=float(np.sqrt(np.var(block_means,axis=0,ddof=1).sum()/len(block_means)))
    updates.append({'batch':batch,'admitted':n,'decisions':decisions,**calculated,
        'independent_update_max_error':err,'third_gradient_norms':thirds,
        'opponent_pool':[e['identity'] for e in json.loads((RUN/f'batches/b{batch}.json').read_text())['opponents']],
        'actor_norm':float(np.linalg.norm(W[batch])),'value_norm':float(np.linalg.norm(V[batch])),
        'actor_delta_norm':float(np.linalg.norm(W[batch]-W[batch-1])),
        'actor_gradient_without_baseline_norm':float(np.linalg.norm(gn)),
        'baseline_gradient_difference_norm':float(np.linalg.norm(ga-gn)),
        'net_over_sum_episode_gradient_norm':float(np.linalg.norm(sum(e['gradient'] for e in episodes)))/sum(float(np.linalg.norm(e['gradient'])) for e in episodes),
        'descriptive_block_noise_scale':noise,'descriptive_signal_to_block_noise':float(np.linalg.norm(ga))/noise})


def value_summary(rows):
    r=np.asarray([s['reward'] for s in rows],dtype=float)
    v=np.asarray([s['value'] for s in rows],dtype=float)
    return {'n':len(rows),'reward':stats(r),'value':stats(v),'advantage':stats(r-v),
        'mse':float(np.mean((r-v)**2)),'zero_baseline_mse':float(np.mean(r*r)),
        'explained_variance':float(1-np.var(r-v)/np.var(r)) if np.var(r)>0 else None}


credit={'decision_weighted':value_summary(training_steps),'by_batch':{},'by_third':{},'by_opponent':{},'episode_weighted':{},'length':{}}
for field,key,values in (('batch','by_batch',range(1,13)),('third','by_third',('early','middle','late')),
                         ('opponent','by_opponent',sorted({r['opponent'] for r in training_steps}))):
    for value in values:
        subset=[r for r in training_steps if r[field]==value]
        credit[key][str(value)]={**value_summary(subset),'entropy':stats([r['entropy'] for r in subset]),
            'pmax':stats([r['pmax'] for r in subset]),'gradient_contribution_norm':stats([r['gradient_contribution_norm'] for r in subset]),
            'chosen_categories':dict(Counter(r['category'] for r in subset))}
admitted=[e for e in episode_rows if e['exclusion']=='admitted']
credit['episode_weighted']=value_summary([{'reward':e['training_reward'],'value':e['mean_value']} for e in admitted])
for lo,hi in ((0,25),(25,50),(50,100),(100,1000)):
    es=[e for e in admitted if lo<e['own_requests']<=hi]
    credit['length'][f'{lo+1}-{hi}']={'episodes':len(es),'gradient_sum_norm':stats([e['gradient_sum_norm'] for e in es]),
        'reward':stats([e['training_reward'] for e in es]),'requests':sum(e['own_requests'] for e in es)}
credit['length_gradient_correlation']=float(np.corrcoef([e['own_requests'] for e in admitted],[e['gradient_sum_norm'] for e in admitted])[0,1])

exclusion_groups={}
for field in ('opponent_group','opponent','batch','team_pair','own_team','opponent_team','exclusion'):
    groups={}
    for value in sorted({str(e[field]) for e in episode_rows}):
        es=[e for e in episode_rows if str(e[field])==value]
        groups[value]={'requested':len(es),'reasons':dict(Counter(e['exclusion'] for e in es)),
            'outcomes':dict(Counter(str(e['terminal_reward']) for e in es)),'requests':stats([e['own_requests'] for e in es]),
            'unknown_requests':sum(e['unknown_choices'] for e in es),'discarded_verified_requests':sum(e['verified_choices'] for e in es if e['exclusion']!='admitted')}
    exclusion_groups[field]=groups
mismatch_counts=Counter((e['first_literal_mismatch']['expected']+' -> '+str(e['first_literal_mismatch']['engine_at_same_index'])) if e['first_literal_mismatch'] else 'no literal mismatch' for e in excluded)

save('movement.json',{key:{m:stats(v) for m,v in metrics.items()} for key,metrics in movement.items()})
save('reference.json',{key:{m:stats(v) for m,v in metrics.items()} for key,metrics in reference.items()})
save('action-categories.json',{key:{m:stats(v) for m,v in metrics.items()} for key,metrics in mass.items()})
save('representation.json',{'identical_action_pair_counts':dict(collisions.most_common()),'examples':collision_examples,
    'state_feature_ranges':dict(zip(STATE_NAMES,zip(state_min.tolist(),state_max.tolist()))),
    'action_feature_ranges':dict(zip(ACTION_NAMES,zip(action_min.tolist(),action_max.tolist()))),
    'actor_action_bias_column_norm':{k:float(np.linalg.norm(W[k][:,0])) for k in W}})
save('updates.json',updates)
save('credit.json',credit)
save('exclusions.json',{'groups':exclusion_groups,'first_mismatch_counts':dict(mismatch_counts),
     'episodes':excluded,'all_excluded_sends_recorded_once':all(e['submitted_once']==e['own_requests'] for e in excluded)})
save('cases.json',cases)
csv_rows('final-snapshots.csv',final_rows)
csv_rows('training-steps.csv',training_steps)
csv_rows('training-episodes.csv',[{**e,'selected_categories':json.dumps(e['selected_categories'],sort_keys=True)} for e in episode_rows])
save('verification.json',{'new_battles':0,'historical_model_updates':0,'numeric_coefficients_checked':coefficient_count,
    'recorded_rf_decisions_boundary_checked':recorded_rf,'recorded_exact_cdf_boundary_ties':boundary_ties,
    'five_checkpoint_counterfactual_boundary_ties':counterfactual_boundary_ties,
    'independent_probability_max_error':max_probability_error,'independent_logit_max_error':max_logit_error,
    'independent_value_max_error':max_value_error,'independent_updates_checked':len(updates),
    'final_snapshots':len(final_rows),'training_episodes':len(episode_rows),'admitted_training_steps':len(training_steps),
    'representative_case_names':list(cases),'wall_seconds':time.monotonic()-START,'cpu_seconds':time.process_time()-CPU,
    'sampled_peak_rss_bytes':PEAK_RSS,'script_sha256':sha256(Path(__file__))})
print(json.dumps(json.loads((OUT/'verification.json').read_text()),indent=2),flush=True)
