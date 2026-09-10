"""Post-replay descriptive selection analysis; never changes eligibility."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from battlemind.environment import ROOT
from battlemind.labels import read_jsonl

OUT=ROOT/'runs/trajectory-contract-audit-20260910'


def main():
    episodes=list(csv.DictReader((OUT/'episodes.csv').open()))
    byrun=defaultdict(dict)
    for ep in episodes:byrun[ep['run']][int(ep['match'])]=ep
    action_counts=defaultdict(Counter);flags=defaultdict(Counter);normalizations=[]
    for name,eps in byrun.items():
        for ep in eps.values():
            key=(ep['experiment'],ep['arm'],'some_maybe_locked' if int(ep['maybe_locked_decisions']) else 'no_maybe_locked')
            flags[key]['episodes']+=1;flags[key]['excluded']+=bool(ep['exclusion'])
        for row in read_jsonl(ROOT/name/'decisions.jsonl'):
            if row['player']!='a':continue
            ep=eps[row['match']];obs=row['observation']
            chosen=next(a for a in obs['legal_actions'] if a['id']==row['chosen_action'])
            for dimension,value in (('sampled',row['chosen_action']),('kind',chosen['kind']),
                                    ('request_kind',obs['request_kind']),('maybe_locked',str(obs['maybe_locked']))):
                key=(ep['experiment'],ep['arm'],dimension,value)
                action_counts[key]['decisions']+=1
                action_counts[key]['in_excluded_episode']+=bool(ep['exclusion'])
    discrepancies=list(csv.DictReader((OUT/'excluded-decisions.csv').open()))
    firsts=[r for r in discrepancies if r['category']=='first_normalization_candidate']
    for row in firsts:
        # Read the exact pre-recorded decision ID, not a reconstructed state.
        original=next(r for r in read_jsonl(ROOT/row['run']/f"privileged/attempts/{int(row['match']):03d}-a.jsonl")
                      if r['decision_id']==row['decision_id'])
        moves=[a['id'] for a in original['observation']['legal_actions'] if a['kind']=='move']
        normalizations.append({k:row[k] for k in ('run','match','decision_id','index','expected','ordinal_engine_choice',
                              'active_species','active_status','maybe_locked','maybe_disabled')} | {
            'legal_move_ids':moves,'move_probability_mass':sum(p for a,p in zip(original['observation']['legal_actions'],
                original['policy_evaluation']['probabilities']) if a['kind']=='move'),
            'classification':'source-supported conditional many-to-one branch candidate; acceptance not newly certified'})
    result={'schema_version':'trajectory-exclusion-description-1',
        'interpretation':'Decision exposures are correlated and postselected by the whole episode. Descriptive only; no independent-turn intervals or causal estimates.',
        'episode_public_context':[dict(zip(('experiment','arm','context'),k))|dict(v) for k,v in flags.items()],
        'decision_exposures':[dict(zip(('experiment','arm','dimension','value'),k))|dict(v) for k,v in action_counts.items()],
        'first_candidates':normalizations,
        'firsts_by_species':dict(Counter(r['active_species'] for r in firsts)),
        'firsts_by_status':dict(Counter(r['active_status'] for r in firsts)),
        'firsts_with_multiple_legal_moves':sum(len(r['legal_move_ids'])>1 for r in normalizations),
        'candidate_preimages_are_not_verified_counterfactuals':True}
    with (OUT/'selection-description.json').open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)


if __name__=='__main__':main()
