"""Offline only: tiny package layouts, fake servers, and bounded process fixtures."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest

from battlemind.environment import ROOT, executable, sha256
from battlemind import acceptance_build as build
from diagnostics import acceptance_readiness as ready
from diagnostics import acceptance_live_verify as live
from diagnostics.acceptance_preflight import DeadlineIO, DeadlineExpired


def package(root,name,dependencies,code):
    root.mkdir(parents=True,exist_ok=True)
    (root/'package.json').write_text(json.dumps({'name':name,'version':'1.0.0','main':'index.js','dependencies':dependencies}))
    (root/'index.js').write_text(code)


def junction(source,target):
    if os.name=='nt':
        # Native mklink is only used for this explicit temporary test junction.
        subprocess.run(['cmd','/c','mklink','/J',str(source),str(target)],check=True,capture_output=True,timeout=5)
    else:source.symlink_to(target,target_is_directory=True)


def test_identical_package_bytes_broken_ancestry_fails_actual_entry_resolution(tmp_path):
    linked=tmp_path/'linked';linked.mkdir()
    package(linked,'pokemon-showdown',{'sockjs':'1.0.0'},'')
    (linked/'pokemon-showdown').write_text('// real entry')
    store=linked/'node_modules/.pnpm/sockjs@1/node_modules'
    package(store/'sockjs','sockjs',{'fixture-transitive':'1.0.0'},"module.exports = require('fixture-transitive');")
    package(store/'fixture-transitive','fixture-transitive',{},'module.exports = 42;')
    junction(linked/'node_modules/sockjs',store/'sockjs')
    good=ready.resolve_modules(linked,DeadlineIO(time.monotonic()+10))
    assert good['cwd']==str(linked.resolve()) and good['entry']==str(linked/'pokemon-showdown')
    broken=tmp_path/'broken';shutil.copytree(linked,broken)
    # This is exactly the old byte-only inventory: every followed path hashes equal.
    hashes=lambda d:{p.relative_to(d).as_posix():sha256(p) for p in d.rglob('*') if p.is_file()}
    assert hashes(linked)==hashes(broken)
    with pytest.raises(ValueError,match='fixture-transitive'):
        ready.resolve_modules(broken,DeadlineIO(time.monotonic()+10))
    assert good['server_started'] is False
    with pytest.raises(ValueError,match='real server cwd'):
        DeadlineIO(time.monotonic()+10).command([executable('node'),str(ROOT/'scripts/inspect-acceptance-runtime.cjs'),
            str(linked/'pokemon-showdown')],cwd=broken)


def test_link_manifest_detects_dereferenced_layout_and_rejects_external_targets(tmp_path):
    tree=tmp_path/'engine';(tree/'node_modules/physical').mkdir(parents=True)
    junction(tree/'node_modules/alias',tree/'node_modules/physical')
    assert build.dependency_links(tree)=={'node_modules/alias':'node_modules/physical'}
    copy=tmp_path/'copy';shutil.copytree(tree,copy)
    assert build.dependency_links(copy)=={}
    outside=tmp_path/'outside';outside.mkdir();junction(tree/'node_modules/escape',outside)
    with pytest.raises(ValueError,match='escapes'):build.dependency_links(tree)


def test_readiness_failure_cannot_begin_a_game_phase(tmp_path,monkeypatch):
    output=tmp_path/'out';monkeypatch.setattr(live,'OUTPUT',output);calls=[]
    def worker(root,name,budget,env=None):
        calls.append(name)
        if name=='preflight':raise ValueError('Required dependency does not resolve from entry')
        assert name=='reporting'
        live.reporting(root,DeadlineIO(budget.deadline(name)))
    monkeypatch.setattr(live,'run_worker',worker)
    assert not live.main(output) and calls==['preflight','reporting']
    result=live.read_report(output)
    assert all(p['requested']==p['completed']==0 for p in result['report']['phases'].values())
    assert (output/'REPORT.md').exists()


def test_operational_failure_does_not_launch_lifecycle_worker(tmp_path,monkeypatch):
    monkeypatch.setattr(ready,'ROOT',tmp_path)
    private=tmp_path/'runs/test/privileged/recording';private.mkdir(parents=True)
    (private/'session.json').write_text('{"session":"session","build":"build"}')
    env={'BATTLEMIND_ACCEPTANCE_DIR':str(private),'BATTLEMIND_ACCEPTANCE_SESSION':'session','BATTLEMIND_ACCEPTANCE_BUILD':'build'}
    def fail(*a):raise ValueError('broken layout')
    monkeypatch.setattr(ready,'resolve_modules',fail)
    monkeypatch.setattr(ready,'supervise',lambda *a,**k:pytest.fail('must not launch after resolution failure'))
    with pytest.raises(ValueError,match='broken layout'):
        ready.operational_preflight(tmp_path/'engine',env,tmp_path/'out',DeadlineIO(time.monotonic()+60))


def test_occupied_port_does_not_create_or_terminate_server(tmp_path,monkeypatch):
    monkeypatch.setattr(ready,'listeners',lambda port:[{'pid':123,'host':'127.0.0.1'}])
    monkeypatch.setattr(ready,'LocalServer',lambda *a:pytest.fail('occupied port is never owned'))
    with pytest.raises(ValueError,match='Occupied port'):
        asyncio.run(ready.lifecycle(tmp_path,tmp_path,8000,DeadlineIO(time.monotonic()+10)))


def test_startup_timeout_runs_context_cleanup_and_reports_no_game(tmp_path,monkeypatch):
    calls=[]
    class Server:
        process=None
        def __init__(self,*a):pass
        async def __aenter__(self):calls.append('start');return self
        async def __aexit__(self,*a):calls.append('cleanup')
    async def handshake(port):await asyncio.sleep(1)
    monkeypatch.setattr(ready,'LocalServer',Server);monkeypatch.setattr(ready,'healthcheck',handshake)
    monkeypatch.setattr(ready,'listeners',lambda port:[])
    started=time.monotonic()
    with pytest.raises(ValueError,match='TimeoutError'):
        asyncio.run(ready.lifecycle(tmp_path,tmp_path,8000,DeadlineIO(started+8.05)))
    assert calls==['start','cleanup'] and time.monotonic()-started<1
    report=json.loads((tmp_path/'lifecycle.json').read_text())
    assert report['games_requested']==0 and report['remaining_owned_pids']==[]


def test_reporting_watchdog_failure_keeps_closed_ledger_stable(tmp_path,monkeypatch):
    now=[0.];root=tmp_path/'run';root.mkdir()
    budget=live.Budget.create(root,json.loads(live.SPEC.read_text()),clock=lambda:now[0])
    budget.preflight_done(False,'fixture preflight failure');budget.begin_reporting()
    now[0]=61.;budget.finish_reporting(False,'worker deadline')
    live.finalize(root,budget,'worker deadline')
    before={p.name:p.read_bytes() for p in root.iterdir()}
    now[0]=1000.;live.finalize(root,budget,'late report')
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before
    assert budget.data['reporting']['seconds']==61 and budget.data['total_seconds']==61


def test_report_deadline_leaves_no_fabricated_completed_counts(tmp_path):
    budget=live.Budget.create(tmp_path,json.loads(live.SPEC.read_text()))
    budget.preflight_done(True);budget.begin('original');budget.request('original',0)
    budget.finish('original',False,'blocked');budget.stop_work('blocked');budget.begin_reporting()
    with pytest.raises(DeadlineExpired):live.reporting(tmp_path,DeadlineIO(0))
    budget.finish_reporting(False,'expired');live.finalize(tmp_path,budget,'expired')
    report=json.loads((tmp_path/'report.json').read_text())
    assert report['phases']['original']['completed'] is None
    assert report['phases']['instrumented']['completed']==0


def test_dependency_install_keeps_existing_safeguards():
    assert {'--frozen-lockfile','--ignore-scripts','--prod','--no-optional',
            '--package-import-method=copy','--registry=https://registry.npmjs.org'}<=set(build.INSTALL_ARGS)


def test_zero_battle_controller_closes_after_failed_probe_without_retry(tmp_path,monkeypatch):
    from diagnostics import acceptance_zero_battle as probe
    spec=json.loads(probe.SPEC.read_text());spec['output']='run'
    path=tmp_path/'spec.json';path.write_text(json.dumps(spec))
    monkeypatch.setattr(probe,'ROOT',tmp_path);monkeypatch.setattr(probe,'SPEC',path)
    calls=[]
    def supervised(args,io,log,**kwargs):
        name=args[args.index('--worker')+1];calls.append(name)
        if name=='probe':raise ValueError('fixture dependency failure before startup')
        probe.report(tmp_path/'run',io)
    monkeypatch.setattr(probe,'supervise',supervised)
    assert not probe.main() and calls==['probe','report']
    ledger=tmp_path/'run/ledger.json';before=ledger.read_bytes()
    assert json.loads(before)['requested_games']==0
    assert json.loads(before)['phases']['report']['state']=='finished'
    with pytest.raises(FileExistsError):probe.main()
    assert ledger.read_bytes()==before
