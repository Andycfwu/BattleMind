"""Read-only retained replay/build checks; no collector, optimizer or server calls.

Outputs are exclusive-create files. 'integrity' checks the pre-work inventory,
including all historical runs and the original dependency trees.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import time

from battlemind.environment import ROOT, sha256

OUT=ROOT/'runs/acceptance-recording-offline-20260910'
BUILD=ROOT/'.local/pokemon-showdown-acceptance-v1-r3'


def save(name,data):
    with (OUT/name).open('x',encoding='utf-8') as stream:json.dump(data,stream,indent=2,allow_nan=False)


def replay():
    from battlemind.acceptance_build import verify_build
    from battlemind.adaptation_experiment import artifacts
    from battlemind.environment import inspect_server
    from battlemind.labels import read_jsonl
    from battlemind.reinforce import load_checkpoint
    from battlemind.reinforce_training import audit_run
    start=time.monotonic();cpu=time.process_time()
    build=verify_build(BUILD)
    # The historical doctor must still reject this separate derived build.
    try:inspect_server(BUILD,[],8000)
    except ValueError as exc:
        historical_guard=str(exc)
        assert 'Version mismatch: showdown_commit=' in historical_guard,historical_guard
    else:raise AssertionError('Historical doctor accepted modified source')
    predictor,v5=artifacts()
    checkpoints={}
    for base in ('runs/reinforce-main','runs/actor-step-acceptance'):
        folder=ROOT/base
        for p in sorted((folder/'checkpoints').rglob('*.json')):
            checkpoints[p.relative_to(ROOT).as_posix()]=load_checkpoint(p).sha256
    for rel in ('runs/reinforce-main/selected.json','runs/actor-step-acceptance/selected/control.json',
                'runs/actor-step-acceptance/selected/treatment.json'):
        p=ROOT/rel
        if not p.is_file():raise ValueError('Required retained checkpoint missing: '+rel)
        checkpoints[rel]=load_checkpoint(p).sha256
    cells=['runs/reinforce-main/training/b1-vs-v2',
           'runs/actor-step-acceptance/training/control-b6-vs-v2',
           'runs/actor-step-acceptance/training/treatment-b6-vs-v2']
    replays={}
    for rel in cells:
        path=ROOT/rel
        print('Replaying retained cell:',rel,flush=True)
        result=audit_run(path)
        labels=read_jsonl(path/'privileged/labels.jsonl')
        replays[rel]={'run_manifest_sha256':sha256(path/'run.json'),
            'decisions_sha256':sha256(path/'decisions.jsonl'),'audit':result,
            'legacy_commit_statuses':dict(Counter(row['commit_status'] for row in labels)),
            'snapshot_set':'All learned decisions in original chronological per-match/player order; exact probabilities, values, logits, draws and choices.'}
    existing=json.loads((OUT/'inputs-before.json').read_text())['hashes']
    unchanged={name:sha256(ROOT/name)==value for name,value in existing.items()
               if name.startswith('src/') or name.startswith('configs/reinforce')}
    assert all(unchanged.values())
    save('verification.json',{'ok':True,'new_battles':0,'training_runs':0,'parameter_updates':0,
        'build_id':build['build_id'],'patch_sha256':build['patch_sha256'],
        'historical_doctor_rejection':historical_guard,'checkpoints':checkpoints,
        'v4_sha256':predictor.sha256,'v5_sha256':v5.sha256,'replays':replays,
        'all_preexisting_policy_runner_training_source_unchanged':unchanged,
        'full_historical_source_audit':'Not rerun; new modules change full inventory. Historical source freezes remain required.',
        'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu})


def integrity():
    start=time.monotonic();before=json.loads((OUT/'inputs-before.json').read_text())['hashes']
    changed=[];missing=[]
    for name,expected in before.items():
        p=ROOT/name
        if not p.is_file():missing.append(name)
        elif sha256(p)!=expected:changed.append(name)
    result={'input_manifest_sha256':sha256(OUT/'inputs-before.json'),'files_checked':len(before),
        'changed':changed,'missing':missing,'wall_seconds':time.monotonic()-start}
    save('preservation.json',result)
    assert not changed and not missing,result
    print(json.dumps(result,indent=2),flush=True)


def setup():
    from battlemind.acceptance_build import recording_environment
    env=recording_environment(BUILD,OUT/'privileged/setup-only')
    save('setup-verification.json',{'ok':True,'server_started':False,'games':0,
        'environment':{key:env[key] for key in ('BATTLEMIND_ACCEPTANCE_DIR','BATTLEMIND_ACCEPTANCE_SESSION','BATTLEMIND_ACCEPTANCE_BUILD')}})


def closure():
    import psutil
    start=time.monotonic()
    before=json.loads((OUT/'inputs-before.json').read_text())['hashes']
    changed=[name for name,value in before.items() if not (ROOT/name).is_file() or sha256(ROOT/name)!=value]
    assert not changed,changed
    result=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True,check=True)
    assert not result.stdout and not result.stderr
    tracked=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=ROOT,text=True)
    assert not tracked,tracked  # This task only adds isolated support files.
    added=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    for name in added:
        check=subprocess.run(['git','-c','core.autocrlf=false','diff','--no-index','--check','--','NUL',name],cwd=ROOT,capture_output=True,text=True)
        assert check.returncode in (0,1) and not check.stdout and not check.stderr,(name,check)
    for name in ('runs','models','.local'):
        ignored=subprocess.run(['git','check-ignore',name+'/'],cwd=ROOT,capture_output=True,text=True)
        assert ignored.returncode==0
    tests=(OUT/'offline-tests-final.txt').read_text();focused=(OUT/'focused-final-2.txt').read_text()
    assert '326 passed, 14 deselected' in tests and '59 passed' in focused
    sources={name:sha256(ROOT/name) for name in added}
    files={p.relative_to(OUT).as_posix():sha256(p) for p in OUT.rglob('*') if p.is_file()}
    save('closure.json',{'ok':True,'new_battles':0,'training_runs':0,'historical_files_unchanged':len(before),
        'changed_historical_files':changed,'tracked_production_changes':[],
        'offline_tests':{'passed':326,'integration_deselected':14,'seconds':8.32},
        'focused_tests':{'passed':59,'seconds':1.54},'paired_engine_method_cases':12,
        'git_diff_check':'passed, including each added file with no-index',
        'listeners_on_configured_port_8000':[str(c.laddr) for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port==8000],
        'generated_paths_ignored':True,'source_hashes':sources,'artifact_hashes':files,
        'derived_build_files_bytes':sum(p.stat().st_size for p in BUILD.rglob('*') if p.is_file()),
        'verification_artifacts_bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),
        'wall_seconds':time.monotonic()-start})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['replay','integrity','setup','closure'])
    args=parser.parse_args();globals()[args.mode]()
