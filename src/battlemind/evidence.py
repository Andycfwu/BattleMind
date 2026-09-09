"""Read-only consolidation of retained evidence, without a cross-version ranking."""

from collections import Counter
import json
from pathlib import Path
import time

from .demo_bundle import safe_path, write
from .environment import ROOT, sha256, source_manifest
from .labels import read_jsonl
from .reporting import summarize

SOURCES = (
    ('V1','runs/milestone1-final-20','pipeline','docs/MILESTONE1.md'),
    ('V2','runs/m2-comparison-random','restricted comparison','docs/HEURISTIC.md'),
    ('V2','runs/m2-comparison-max-base-power','restricted comparison','docs/HEURISTIC.md'),
    ('V3','runs/v3-acceptance','final fixed mixture','docs/MILESTONE3.md'),
    ('V4','runs/v4-development','development','docs/V4-EXPERIMENT.md'),
    ('V4','runs/v4-acceptance','final fixed mixture','docs/MILESTONE4.md'),
    ('V5','runs/v5-acceptance','training / selection / final','docs/V5-EXPERIMENT.md'),
    ('V6-first','runs/v6-acceptance','incomplete development only','docs/V6-EXPERIMENT.md'),
    ('V6-repair','runs/v6-acceptance-repair','development / incomplete final','docs/V6-ACCEPTANCE-REPAIR.md'),
)
CLAIMS = {
    'V1':('Legal bounded local matches and auditable pre-decision records.','No competitive-strength conclusion; V1 predates verified commitment labels.'),
    'V2':('Transparent strategy and conservative intended-choice recording against restricted baselines.','No general strength claim; unknown commitment mismatch suffixes remain unknown.'),
    'V3':('Conditional counts influenced choices. Probability estimates worsened against the constant reference.','No established battle benefit or learned classifier in V3.'),
    'V4':('Supervised logistic prediction improved probability quality on its declared opponent mixture.','Battle benefit inconclusive; not isolated history benefit or human generalization.'),
    'V5':('Actual outcome-driven parameter updates included archived self-play; checkpoints can be frozen and evaluated.','Final improvement inconclusive; parameter search is not gradient-based RL.'),
    'V6-first':('Public memory worked technically. 96 completed development games; development budget exhausted; zero final games.','Acceptance incomplete. Partial development differences are not final evidence.'),
    'V6-repair':('Accounting was repaired without scientific tuning. Development completed; final stopped on a frozen-opponent turn cap.','Acceptance incomplete; only one complete final reset group. Battle benefit unestablished.'),
}


def file_ref(path: Path) -> dict:
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha256(path),'bytes':path.stat().st_size}


def check_manifest(root: Path) -> dict:
    path=root/'artifact-hashes.json'
    if not path.exists():
        return {'available':False,'verified_files':0,'limitations':['No frozen artifact manifest retained at this scope. Current hashes establish only present identity.']}
    entries=json.loads(path.read_text());errors=[]
    for name,expected in entries.items():
        p=safe_path(root,name)
        if not p.exists() or sha256(p)!=expected: errors.append(name)
    return {'available':True,'manifest':file_ref(path),'verified_files':len(entries)-len(errors),'errors':errors}


def cell_record(root: Path) -> dict:
    meta=json.loads((root/'run.json').read_text())
    rows=read_jsonl(root/'battles.jsonl')
    computed=summarize(rows,meta['config']['battles'])
    saved=json.loads((root/'summary.json').read_text())
    errors=[k for k in computed if k in saved and computed[k]!=saved[k] and k not in {'claim_scope'}]
    if any(r['status']!='completed' and r.get('winner') is not None for r in rows):errors.append('incomplete_winner')
    missing=[k for k in ('requested','completed','a_wins','b_wins','draws') if k not in saved]
    config=meta['config']
    return {'run':file_ref(root/'run.json'),'summary':file_ref(root/'summary.json'),
        'battle_records':file_ref(root/'battles.jsonl'),'computed_outcomes':computed,
        'inconsistent_fields':errors,'missing_fields':missing,
        'policies':meta.get('policies'), 'predictor':meta.get('predictor'),
        'checkpoints':meta.get('policy_checkpoints'), 'teams':meta.get('environment',{}).get('teams'),
        'format':config['format'],'policy_seed':config['seed'],'randomness':meta.get('randomness'),
        'runtime':meta.get('environment',{}).get('versions'),
        'actual_schedule':dict(Counter(f"a{r['team_indices']['a']}:b{r['team_indices']['b']}:challenger-{r['challenger']}" for r in rows if 'team_indices' in r)),
        'recorded_labels':saved.get('labels'),
        'warnings':{k:saved.get(k) for k in ('client_warning_records','known_gen1_annotation_warnings','unexpected_client_warning_records','server_crash_reports')},
        'resources':json.loads((root/'resources.json').read_text()) if (root/'resources.json').exists() else None,
        'retained_uncertainty':{'wilson':saved.get('a_win_rate_wilson_95'),'scope':saved.get('interval_scope')},
        'source_compatibility':{'full_source_matches_current':meta.get('code_sha256')==source_manifest(),
            'note':'Historical complete-source audits are unchanged. Different current source is not an integrity failure or permission to weaken an old audit.'}}


def build_catalog(output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();entries=[];issues=[]
    for version,name,population,spec in SOURCES:
        root=ROOT/name
        if not (root/'summary.json').exists():issues.append({'path':name,'error':'missing summary'});continue
        print('Inspecting retained evidence: '+name,flush=True)
        summary=json.loads((root/'summary.json').read_text())
        paths=[root] if (root/'run.json').exists() else sorted(p.parent for p in root.rglob('run.json'))
        cells=[cell_record(p) for p in paths if (p/'battles.jsonl').exists()]
        integrity=check_manifest(root)
        if integrity.get('errors'):issues.append({'path':name,'error':'historical artifact hash mismatch','files':integrity['errors']})
        for cell in cells:
            if cell['inconsistent_fields'] or cell['missing_fields']:
                issues.append({'path':cell['run']['path'],'inconsistent':cell['inconsistent_fields'],'missing':cell['missing_fields']})
        totals={k:sum(c['computed_outcomes'][k] for c in cells) for k in ('requested','completed','truncated','timeout','crash','cancelled','not_started','unrecorded','a_wins','b_wins','draws','invalid_action_incidents')}
        planned=summary.get('planned_games',summary.get('accounting',{}).get('planned_games',totals['requested']))
        if version.startswith('V6'):planned=720
        completed_declared=summary.get('completed_games',summary.get('completed'))
        if completed_declared is not None and completed_declared!=totals['completed']:
            issues.append({'path':name,'error':'completed count disagrees with terminal records'})
        declared_requests=summary.get('requested_games',summary.get('requested'))
        if declared_requests is not None and declared_requests!=totals['requested']:
            issues.append({'path':name,'error':'requested count disagrees with run manifests'})
        phase_counts={}
        for c in cells:
            rel=Path(c['run']['path']).relative_to(name).parts
            phase=rel[0] if rel[0] in {'development','training','selection','final'} else population
            d=phase_counts.setdefault(phase,Counter())
            d.update({k:c['computed_outcomes'][k] for k in totals})
        if version=='V6-first': phase_counts['final']=Counter({k:0 for k in totals})
        scientific_keys=('probability_quality','final_probability','final_battles','battle_differences','final','final_uncertainty','choice_comparison','updates','selection','phases','labels','warnings','warning_and_label_counts','resources','timing','consumed_seconds','total_wall_seconds','wall_seconds_including_audits','failure','audit','audits')
        refs=[file_ref(p) for p in [root/'summary.json',root/'freeze.json',root/'ledger.json',ROOT/spec] if p.exists()]
        entry={'version':version,'root':name,'population':population,'claim':CLAIMS[version][0],
            'unsupported':CLAIMS[version][1],'references':refs,
            'planned_games':planned,'actual_requested_games':totals['requested'],'never_requested_games':planned-totals['requested'],
            'reserved_games':summary.get('accounting',{}).get('reserved_games'),
            'actual_terminal_totals':totals,'phase_terminal_totals':phase_counts,
            'acceptance_status':summary.get('status',summary.get('ledger_status','complete' if totals['completed']==planned else 'incomplete')),
            'artifact_integrity':integrity,'cells':cells,
            'retained_scientific_report':{k:summary[k] for k in scientific_keys if k in summary},
            'audit_coverage':{'terminal_accounting':'Recomputed read-only from every terminal row and checked against saved cell summaries.',
                'semantic_replay':'Historical audit results retained and hash-checked when covered by an original artifact manifest; no claim that V7 reran every historical private audit.',
                'source_compatibility':'Current full source differs. Original loaders still separately enforce exact scientific checkpoint compatibility.'},
            'limitations':['Policies, targets, team mixtures and phases differ across versions. No pooled league table. Simulator randomness was not matched.']}
        if version=='V6-first':
            entry['limitations'] += ['Old schema charged reporting to a stopped development clock; collection stop was 165.731s, total 181.465s.',
                'Original empty final arm grids contain planned slots. Actual final requests are zero; those slots are not missing requested games or losses.']
        entries.append(entry)
    catalog={'schema_version':'v7-evidence-1','entries':entries,'issues':issues,'ok':not issues,
             'method':'Read-only retained evidence; no games/training, no cross-version ranking.',
             'elapsed_seconds':time.monotonic()-start,'source':source_manifest()}
    write(output/'catalog.json',catalog)
    lines=['# BattleMind retained evidence','',catalog['method'],'',
           'Integrity, semantic replay coverage and compatibility are reported separately. Missing fields are unknown, not zero.','',
           '| Evidence | Planned / requested / completed | A wins / B wins / draws | Caps / failures | Never requested |',
           '|---|---:|---:|---:|---:|']
    for e in entries:
        t=e['actual_terminal_totals']; failures=t['timeout']+t['crash']+t['cancelled']
        lines.append(f"| {e['version']} · {e['population']} | {e['planned_games']} / {t['requested']} / {t['completed']} | {t['a_wins']} / {t['b_wins']} / {t['draws']} | {t['truncated']} / {failures} | {e['never_requested_games']} |")
    lines += ['','A/B totals mix roles within some experiments and are accounting only, not a policy ranking. Win denominators are completed games; caps/cleanup are excluded.','']
    for e in entries:
        lines += ['## '+e['version']+' — '+e['population'],'',e['claim'],'',e['unsupported'],'',
            'Source: `'+e['root']+'`. Artifact integrity verified files: '+str(e['artifact_integrity']['verified_files'])+'.',
            'Complete metric, target/arm, calibration, exclusion, uncertainty, resource, phase and hash records: `catalog.json` → this entry → `retained_scientific_report` and `cells`.','']
        # Preserve structured original estimates rather than inventing a common metric.
        report=e['retained_scientific_report']
        quality=report.get('probability_quality') or report.get('final_probability')
        if quality and isinstance(quality,dict) and quality.get('metrics'):
            lines += ['### Probability quality on identical eligible snapshots','',
                '| Variant | Examples | Switches | Brier | Log loss |','|---|---:|---:|---:|---:|']
            for name,metrics in quality['metrics'].items():
                brier = 'unavailable' if metrics.get('brier') is None else f"{metrics['brier']:.6f}"
                loss = 'unavailable' if metrics.get('log_loss') is None else f"{metrics['log_loss']:.6f}"
                lines.append(f"| {name} | {metrics.get('examples','unknown')} | {metrics.get('switches','unknown')} | {brier} | {loss} |")
            if e['version']=='V6-first':lines += ['','Zero final examples: no final probability estimate exists.']
            if e['version']=='V6-repair':lines += ['','These are partial final observations, never completed acceptance. Individual switch-active log loss regressed despite the lower aggregate Brier score.']
            lines += ['']
        if e['version']=='V5':
            lines += ['### Frozen final controls','', '| Arm | Wins | Losses | Draws | Completed |','|---|---:|---:|---:|---:|']
            for arm,value in report['final'].items():
                t=value['overall'];lines.append(f"| {arm} | {t['a_wins']} | {t['b_wins']} | {t['draws']} | {t['completed']} |")
            lines += ['','Improvement remained inconclusive under the predeclared block uncertainty method.','']
        for key in ('final_uncertainty','choice_comparison'):
            if report.get(key): lines += ['### Retained '+key.replace('_',' '),'','```json',json.dumps(report[key],indent=2),'```','']
        lines += ['### Actual phase accounting','', '| Phase | Requested | Completed | Caps | A/B/draw |','|---|---:|---:|---:|---:|']
        for phase,t in e['phase_terminal_totals'].items():
            lines.append(f"| {phase} | {t['requested']} | {t['completed']} | {t['truncated']} | {t['a_wins']}/{t['b_wins']}/{t['draws']} |")
        lines += ['']
    lines += ['## Validation issues','',json.dumps(issues,indent=2),'',
        'V6 is not complete: original 96 development games and zero final; replacement 144 development, 251 completed final plus one cap. Only one complete final reset group is available. No four-group uncertainty or confirmed adaptation benefit.']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write(output/'hashes.json',{p.name:sha256(p) for p in output.iterdir() if p.is_file()})
    return {'ok':catalog['ok'],'issues':issues,'entries':len(entries),'output':str(output),'catalog_sha256':sha256(output/'catalog.json')}
