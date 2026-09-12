"""Single-use zero-battle readiness check; no game or training invocation."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from battlemind.environment import ROOT, executable, inspect_server
from battlemind.acceptance_build import recording_environment
from battlemind.reinforce import load_checkpoint
from battlemind.adaptation_experiment import artifacts
from diagnostics.acceptance_preflight import DeadlineIO, supervise, verify_inventory
from diagnostics.acceptance_readiness import operational_preflight, save

SPEC=ROOT/'configs/acceptance-zero-battle-readiness.json'


def prepare(root, io):
    spec=json.loads(io.read_text(root/'specification.json'))
    engine=ROOT/spec['engine']
    inventory=ROOT/spec['required_inventory']
    if io.hash(inventory)!=spec['required_inventory_sha256']:raise ValueError('Runtime inventory changed')
    checked=verify_inventory(ROOT,json.loads(io.read_text(inventory)),io)
    manifest=json.loads(io.read_text(ROOT/spec['source_inventory']))
    checked.update({name:io.hash(ROOT/name) for name in [*manifest['project_files'],*spec['additional_sources']]})
    for name in ('checkpoint','predictor','v5_checkpoint'):
        path=ROOT/spec[name]
        if io.hash(path)!=spec[name+'_sha256']:raise ValueError('Required model changed: '+name)
        checked[spec[name]]=spec[name+'_sha256']
    if load_checkpoint(ROOT/spec['checkpoint']).sha256!=spec['checkpoint_sha256']:raise ValueError('Wrong initialization')
    artifacts();io.check('strict model compatibility')
    original=inspect_server(ROOT/'.local/pokemon-showdown',[ROOT/p for p in spec['teams']],spec['port'])
    io.check('original source/runtime/config/team check')
    env=recording_environment(engine,root/'privileged/recording',io=io)
    if env['BATTLEMIND_ACCEPTANCE_BUILD']!=spec['build_id']:raise ValueError('Wrong derived build')
    payload={'format':'gen1ou','teams':[{'path':str(ROOT/p),'text':io.read_text(ROOT/p)} for p in spec['teams']]}
    validation=json.loads(io.command([executable('node'),str(ROOT/'scripts/inspect-server.cjs')],engine,json.dumps(payload)))
    if validation!=original['validation']:raise ValueError('Derived rule/team validation differs')
    freeze={'schema':'bm-acceptance-zero-battle-freeze-1','files':checked,
        'specification_sha256':io.hash(root/'specification.json'),
        'build_id':spec['build_id'],'build_manifest_sha256':io.hash(engine/'acceptance-build.json'),
        'strict_compatibility':'c0/V4/V5 passed','rule_validation_equal':True,
        'full_historical_archive_scan':False}
    save(root/'freeze.json',freeze)
    result=operational_preflight(engine,env,root/'readiness',io,spec['port'])
    # Source and model preservation after the probe; full runtime bytes were
    # verified before it. Engine config prohibits source/dependency writes.
    for name in [*manifest['project_files'],*spec['additional_sources'],spec['checkpoint'],spec['predictor'],spec['v5_checkpoint']]:
        if io.hash(ROOT/name)!=checked[name]:raise ValueError('Input changed during probe: '+name)
    private_files=[p.relative_to(root).as_posix() for p in io.files(root/'privileged')]
    if set(private_files)!={'privileged/recording/session.json','privileged/recording/readiness-path-check.json'}:
        raise ValueError('Unexpected battle evidence in zero-battle probe')
    if list(io.files(root/'readiness/privileged/engine')):raise ValueError('Unexpected end logs without a battle')
    save(root/'verification.json',{'ok':True,'games_requested':0,'source_and_model_preservation':True,
        'private_files':private_files,'lifecycle_seconds':result['elapsed_seconds']})


def report(root, io):
    ledger=json.loads(io.read_text(root/'ledger.json'))
    result={'schema':'bm-acceptance-zero-battle-report-1','games_requested':0,'failure':ledger.get('failure'),
        'scope':'load, handshake and cleanup only; request/acceptance/normalization remain unverified',
        'optional_forensics_performed':False}
    for name,file in [('verification','verification.json'),('lifecycle','readiness/lifecycle.json'),('worker_cleanup','probe-process.json')]:
        path=root/file
        result[name]=json.loads(io.read_text(path)) if path.exists() else None
    save(root/'report.json',result)
    text=('# Zero-battle readiness\n\n'
        f'Failure: {result["failure"] or "none"}. Games requested: 0.\n\n'
        f'Lifecycle: {result["lifecycle"] and result["lifecycle"]["elapsed_seconds"]} seconds.\n\n'
        'The sealed ledger contains all phase and aggregate durations. No battles, '
        'training or eligibility changes. Request-bound recording is not live-verified.\n')
    io.check('mandatory probe Markdown')
    with (root/'REPORT.md').open('x',encoding='utf-8') as stream:stream.write(text)
    io.check('finish probe report')


def main():
    started=time.monotonic();spec=json.loads(SPEC.read_text())
    if (spec['maximum_games'],spec['maximum_probes_this_command'],spec['maximum_wall_seconds'])!=(0,1,120):
        raise ValueError('Unauthorized probe budget')
    if spec['host']!='127.0.0.1' or spec['concurrency']!=1 or spec['retry'] or spec['resume']:
        raise ValueError('Unsafe probe specification')
    if spec['phases']!={'integrity_and_lifecycle':90,'mandatory_reporting':10,'cleanup_and_closure':20}:
        raise ValueError('Unexpected reserved allocations')
    root=ROOT/spec['output'];root.mkdir(parents=True,exist_ok=False)
    ledger={'schema':'bm-acceptance-zero-battle-ledger-1','state':'running','started_monotonic':started,
        'maximum_seconds':120,'maximum_games':0,'planned_games':0,'reserved_games':0,'requested_games':0,
        'maximum_probes':1,'probes_scheduled':1,'phases':{},'failure':None}
    def write():
        pending=root/'ledger.pending';pending.write_text(json.dumps(ledger,indent=2));pending.replace(root/'ledger.json')
    write();DeadlineIO(started+90).copy(SPEC,root/'specification.json')
    for name,limit in [('probe',90),('report',10)]:
        began=time.monotonic();until=min(began+limit,started+100)
        ledger['phases'][name]={'state':'running','start':began,'deadline':until,'allocated_seconds':limit};write()
        try:
            with (root/(name+'-console.txt')).open('x') as log:
                supervise([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',name,'--output',str(root),'--until',str(until)],
                    DeadlineIO(until),log,env=dict(os.environ),record=lambda row:save(root/(name+'-process.json'),row))
        except BaseException as exc:
            ledger['failure']=ledger['failure'] or f'{name}: {type(exc).__name__}: {exc}'
            ledger['phases'][name]['failure']=str(exc)
        stopped=time.monotonic()
        ledger['phases'][name].update(state='stopped' if 'failure' in ledger['phases'][name] else 'finished',
            stop=stopped,seconds=stopped-began,overrun_seconds=max(0,stopped-until));write()
    closed=time.monotonic();elapsed=closed-started
    if elapsed>120:ledger['failure']=ledger['failure'] or 'Aggregate deadline exceeded'
    ledger.update(state='stopped' if ledger['failure'] else 'finished',stop_monotonic=closed,total_seconds=elapsed,
        closure_seconds=closed-ledger['phases']['report']['stop'],overrun_seconds=max(0,elapsed-120))
    write();print(json.dumps(ledger,indent=2))
    return not ledger['failure']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',choices=['probe','report']);parser.add_argument('--output',type=Path)
    parser.add_argument('--until',type=float);args=parser.parse_args()
    if args.worker:
        if args.output is None or args.until is None:parser.error('Internal worker requires reservation')
        ledger=json.loads((args.output/'ledger.json').read_text())
        if ledger['state']!='running' or ledger['phases'][args.worker]['deadline']!=args.until:raise ValueError('Consumed/missing worker reservation')
        with (args.output/(args.worker+'-io.jsonl')).open('x',encoding='utf-8') as stream:
            def progress(row):stream.write(json.dumps(row)+'\n');stream.flush()
            (prepare if args.worker=='probe' else report)(args.output,DeadlineIO(args.until,progress=progress))
    else:raise SystemExit(0 if main() else 1)
