"""Injected clocks/readers and tiny subprocesses only; no servers or games."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from diagnostics import acceptance_live_verify as live
from diagnostics.acceptance_preflight import DeadlineIO, DeadlineExpired, required_inputs, supervise, verify_inventory


def test_expired_hash_does_not_even_open_file(tmp_path):
    opened=[]
    with pytest.raises(DeadlineExpired):
        DeadlineIO(0,clock=lambda:0,opener=lambda *a:opened.append(a)).hash(tmp_path/'unused')
    assert opened==[]


def test_large_file_interrupted_between_chunks_and_honest_overrun(tmp_path):
    now=[0.];reads=[];progress=[]
    class SlowFile(io.BytesIO):
        def read(self,n):
            reads.append(n);now[0]+=.75
            return super().read(n)
    reader=SlowFile(b'x'*(4*1024*1024))
    bounded=DeadlineIO(1,clock=lambda:now[0],opener=lambda *a:reader,progress=progress.append)
    with pytest.raises(DeadlineExpired):bounded.hash(tmp_path/'large')
    assert reads==[1024*1024,1024*1024] and reader.closed
    assert progress[-1]['elapsed_seconds']==1.5  # Never clipped to the allocation.
    assert progress[-1]['bytes_hashed']==1024*1024 and progress[-1]['sha256'] is None


def test_deadline_between_files_prevents_next_open(tmp_path):
    now=[0.];opened=[]
    for name in ('a','b'):(tmp_path/name).write_bytes(b'abc')
    def opening(p,mode):opened.append(p.name);return p.open(mode)
    def progress(row):now[0]+=1
    inventory={'files':{n:hashlib.sha256(b'abc').hexdigest() for n in ('a','b')}}
    with pytest.raises(DeadlineExpired):
        verify_inventory(tmp_path,inventory,DeadlineIO(1,clock=lambda:now[0],opener=opening,progress=progress))
    assert opened==['a']


def test_small_manifest_hashes_every_input_and_detects_new_or_changed_files(tmp_path):
    (tmp_path/'runtime').mkdir();(tmp_path/'runtime/dep').write_bytes(b'dep')
    inventory={'files':{'runtime/dep':hashlib.sha256(b'dep').hexdigest()},'exact_trees':['runtime']}
    (tmp_path/'inventory.json').write_text(json.dumps(inventory))
    (tmp_path/'source.py').write_text('source')
    manifest={'schema':'bm-acceptance-required-inputs-1','project_files':['source.py'],
        'pinned_files':{'inventory.json':hashlib.sha256((tmp_path/'inventory.json').read_bytes()).hexdigest()},
        'inventory_files':['inventory.json']}
    p=tmp_path/'manifest.json';p.write_text(json.dumps(manifest));progress=[]
    bounded=DeadlineIO(10,clock=lambda:0,progress=progress.append)
    result=required_inputs(p,bounded,tmp_path)
    assert set(result)=={'source.py','runtime/dep','inventory.json'} and len(progress)==3
    (tmp_path/'runtime/new').write_text('unreviewed')
    with pytest.raises(ValueError,match='membership'):required_inputs(p,bounded,tmp_path)
    (tmp_path/'runtime/dep').write_text('tampered')
    with pytest.raises(ValueError,match='changed'):required_inputs(p,bounded,tmp_path)


def test_subprocess_wait_has_remaining_deadline_and_kills_on_timeout(monkeypatch):
    from diagnostics import acceptance_preflight as module
    calls=[]
    class Child:
        pid=123;returncode=None
        def communicate(self,stdin,timeout):calls.append(timeout);raise subprocess.TimeoutExpired('fixture',timeout)
        def wait(self,timeout):calls.append(('reap',timeout))
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:Child())
    monkeypatch.setattr(module,'process_env',lambda:{})
    monkeypatch.setattr(module,'stop_process_tree',lambda pid:calls.append(('stop',pid)))
    with pytest.raises(subprocess.TimeoutExpired):DeadlineIO(11,clock=lambda:10).command(['fixture'])
    assert calls==[1,('stop',123),('reap',2)]


def test_watchdog_stops_a_blocked_worker_without_starting_another(tmp_path):
    import time
    started=time.monotonic()
    with (tmp_path/'worker.log').open('w') as log:
        with pytest.raises((subprocess.TimeoutExpired,DeadlineExpired)):
            supervise([sys.executable,'-B','-c','import time;time.sleep(5)'],DeadlineIO(started+.1),log)
    assert time.monotonic()-started<3


@pytest.mark.parametrize('failure',[DeadlineExpired('slow hash'),KeyboardInterrupt('cancelled'),ValueError('strict checkpoint rejection')])
def test_failed_preflight_never_starts_server_phase_or_requests_games(tmp_path,monkeypatch,failure):
    root=tmp_path/'fresh';calls=[]
    monkeypatch.setattr(live,'OUTPUT',root)
    monkeypatch.setattr(live,'validate_spec',lambda spec:None)  # Scheduling test; real spec tested separately.
    def run(root,name,budget,env=None):calls.append(name);raise failure
    monkeypatch.setattr(live,'run_worker',run)
    assert live.main(root) is False and calls==['preflight','reporting']
    ledger=json.loads((root/'ledger.json').read_text());report=json.loads((root/'report.json').read_text())
    assert ledger['state']=='stopped' and ledger['preflight']['state']=='stopped'
    for p in report['phases'].values():
        assert p['planned']==p['reserved']==p['never_requested']==24
        assert p['requested']==p['completed']==p['unrecorded']==0
    before=(root/'ledger.json').read_bytes()
    before_report=(root/'report.json').read_bytes()
    assert live.read_report(root)==live.read_report(root)
    live.finalize(root,live.Budget(root),'again')
    assert (root/'ledger.json').read_bytes()==before
    assert (root/'report.json').read_bytes()==before_report
    with pytest.raises(FileExistsError):live.main(root)


def test_preflight_success_with_small_fixtures_preserves_required_validation_calls(tmp_path,monkeypatch):
    root=tmp_path/'project';root.mkdir();out=root/'out';out.mkdir()
    spec=json.loads(live.SPEC.read_text())
    for name in ['model.json','source.py',*spec['teams'],*live.READINESS_INPUTS]:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    spec['checkpoint']='model.json';spec['checkpoint_sha256']='retained';(root/'specification.json').write_text(json.dumps(spec))
    manifest=root/'manifest.json';manifest.write_text(json.dumps({'project_files':['source.py']}))
    spec['input_manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
    (root/'specification.json').write_text(json.dumps(spec))
    derived=root/'derived';derived.mkdir();(derived/'acceptance-build.json').write_text(json.dumps({'build_id':spec['instrumented_build_id']}))
    monkeypatch.setattr(live,'ROOT',root);monkeypatch.setattr(live,'INPUTS',manifest);monkeypatch.setattr(live,'DERIVED',derived)
    monkeypatch.setattr(live,'SPEC',root/'specification.json')
    monkeypatch.setattr(live,'validate_spec',lambda spec:None)
    calls=[]
    monkeypatch.setattr(live,'required_inputs',lambda *a: {'source.py':hashlib.sha256(b'{}').hexdigest()})
    from types import SimpleNamespace
    monkeypatch.setattr(live,'load_checkpoint',lambda p: calls.append('c0') or SimpleNamespace(sha256='retained'))
    from battlemind import adaptation_experiment
    monkeypatch.setattr(adaptation_experiment,'artifacts',lambda: calls.append('V4/V5'))
    monkeypatch.setattr(live,'inspect_server',lambda *a: calls.append('original doctor') or {'validation':{},'teams':[]})
    def recording(engine,path,io):
        calls.append('derived build/runtime');path.mkdir(parents=True)
        return {'BATTLEMIND_ACCEPTANCE_BUILD':spec['instrumented_build_id'],'SECRET_NOT_TO_PERSIST':'ignored'}
    monkeypatch.setattr(live,'recording_environment',recording)
    monkeypatch.setattr(live,'operational_preflight',lambda *a: calls.append('derived readiness'))
    bounded=DeadlineIO(10,clock=lambda:0)
    monkeypatch.setattr(bounded,'command',lambda *a: calls.append('derived rules') or '{}')
    live.preflight(out,bounded)
    assert calls==['c0','V4/V5','original doctor','derived build/runtime','derived rules','derived readiness']
    assert (out/'freeze.json').exists() and not (out/'original').exists()
    assert 'SECRET_NOT_TO_PERSIST' not in (out/'privileged/worker-environment.json').read_text()


def test_required_manifest_includes_all_retained_models_and_runtime_inventories():
    manifest=json.loads(live.INPUTS.read_text())
    assert {'runs/reinforce-main/checkpoints/c0.json','models/v4-supervised.json','runs/v5-acceptance/selected.json'}<=manifest['pinned_files'].keys()
    assert 'src/battlemind/schema.py' in manifest['project_files']
    assert 'configs/acceptance-runtime-inputs.json' in manifest['pinned_files']
    assert '.local/pokemon-showdown-acceptance-v1-r3/acceptance-build.json' in manifest['pinned_files']


def test_partial_actual_request_is_missing_but_unstarted_slots_are_not(tmp_path,monkeypatch):
    root=tmp_path/'partial';calls=[]
    monkeypatch.setattr(live,'OUTPUT',root)
    def run(root,name,budget,env=None):
        calls.append(name)
        if name=='original':
            budget.request(name,0)
            raise ValueError('fixture stops after request, before terminal record')
        if name=='reporting':live.reporting(root,DeadlineIO(budget.deadline(name)))
    monkeypatch.setattr(live,'run_worker',run)
    assert live.main(root) is False and calls==['preflight','original','reporting']
    report=json.loads((root/'report.json').read_text())
    assert report['phases']['original']['requested']==report['phases']['original']['unrecorded']==1
    assert report['phases']['original']['never_requested']==23
    assert report['phases']['instrumented']['requested']==report['phases']['instrumented']['unrecorded']==0
    assert report['phases']['instrumented']['never_requested']==24


def test_optional_archive_scan_small_fixture_and_no_resume(tmp_path):
    from diagnostics.acceptance_preflight import archive_scan
    (tmp_path/'artifact').write_bytes(b'historical')
    inventory=tmp_path/'inventory.json'
    inventory.write_text(json.dumps({'hashes':{'artifact':hashlib.sha256(b'historical').hexdigest()}}))
    result=archive_scan(inventory,tmp_path/'new',2,root=tmp_path)
    assert result['full_scan_passed'] and result['completed_files']==1 and result['games_requested']==0
    assert (tmp_path/'artifact').read_bytes()==b'historical'
    with pytest.raises(FileExistsError):archive_scan(inventory,tmp_path/'new',2,root=tmp_path)


def test_empty_archive_inventory_is_not_a_verified_archive(tmp_path):
    from diagnostics.acceptance_preflight import archive_scan
    inventory=tmp_path/'inventory.json';inventory.write_text('{}')
    result=archive_scan(inventory,tmp_path/'out',2,root=tmp_path)
    assert not result['full_scan_passed'] and result['failure'] and result['completed_files']==0


def test_dependency_scope_manifest_is_pinned_by_the_new_specification():
    spec=json.loads(live.SPEC.read_text())
    assert hashlib.sha256(live.INPUTS.read_bytes()).hexdigest()==spec['input_manifest_sha256']
