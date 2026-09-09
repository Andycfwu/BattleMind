import copy
import json
from pathlib import Path
import zipfile

import pytest

from battlemind.demo_bundle import import_bundle, safe_path
from battlemind.demo_server import can_launch
from battlemind.evidence import check_manifest, cell_record
from battlemind.viewer_records import historical_replay, public_line, validate_replay


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


@pytest.fixture
def public_run(tmp_path):
    from battlemind.environment import ROOT
    # Artifact references use a workspace root; use monkeypatch in tests below.
    histories={'a':[{'turn':0,'kind':'switch','actor':None,'values':['alakazam','313/313']},
                    {'turn':0,'kind':'switch','actor':'opponent:1','values':['starmie','51/100']}],
               'b':[{'turn':0,'kind':'switch','actor':'opponent:1','values':['alakazam','100/100']},
                    {'turn':0,'kind':'switch','actor':None,'values':['starmie','164/323']}]}
    dump(tmp_path/'privileged/000-histories.json',histories)
    dump(tmp_path/'run.json',{'config':{'battles':1,'format':'gen1ou','seed':42}})
    row={'match':0,'status':'completed','winner':'a','player_roles':{'a':'p1','b':'p2'}}
    (tmp_path/'battles.jsonl').write_text(json.dumps(row)+'\n')
    return tmp_path


def test_public_projection_ignores_private_hp_and_end_logs(public_run):
    a=historical_replay(public_run,0,'test','test')
    h=json.loads((public_run/'privileged/000-histories.json').read_text())
    h['a'][0]['values'][1]='1/999';h['b'][1]['values'][1]='1/999'
    dump(public_run/'privileged/000-histories.json',h)
    dump(public_run/'privileged/000-engine.json',{'seed':'secret','team':['hidden'],'inputLog':['private']})
    b=historical_replay(public_run,0,'test','test')
    assert a['lines']==b['lines']
    assert '51/100' in '\n'.join(a['lines'])
    assert '999' not in json.dumps(b['lines'])


def test_public_alignment_rejects_different_chronology(public_run):
    h=json.loads((public_run/'privileged/000-histories.json').read_text());h['b'][1]['turn']=2
    dump(public_run/'privileged/000-histories.json',h)
    with pytest.raises(ValueError,match='chronology'): historical_replay(public_run,0,'test','test')


@pytest.mark.parametrize('status',['truncated','timeout','crash','cancelled','not_started'])
def test_cleanup_results_cannot_become_viewer_wins(public_run,status):
    row={'match':0,'status':status,'winner':None,'terminal_results':{'a':'loss','b':'win'},'player_roles':{'a':'p1','b':'p2'}}
    (public_run/'battles.jsonl').write_text(json.dumps(row)+'\n')
    record=historical_replay(public_run,0,'test','test')
    assert record['outcome'] is None and not any(l.startswith('|win|') for l in record['lines'])
    record['lines'].append('|win|Side 2')
    with pytest.raises(ValueError,match='victory'):validate_replay(record)


@pytest.mark.parametrize('line',['|request|{}','|showteam|p1|hidden','|split|p1','|inputlog|seed', '|-damage|p1a: Test|21/313'])
def test_private_protocol_rejected(line):
    with pytest.raises(ValueError):public_line(line)


def test_public_allowlist_drops_account_chat_html_and_uncommitted_outcome():
    for s in ('|c|name|message','|raw|<script>bad</script>','|win|private-account','|choice|move 2'):
        assert public_line(s) is None
    assert public_line('|player|p1|account-name|123')=='|player|p1|Side 1|unknown'
    assert public_line('|cant|p1a: A1|frz')=='|cant|p1a: A1|frz'


def test_budget_guard_counts_consumed_requests_and_wall():
    base={'state':'idle','requested':0,'maximum_games':2,'run_seconds':0,'maximum_run_seconds':300}
    assert can_launch(base)
    for update in ({'state':'queued'},{'state':'failed'},{'state':'cancelled'},{'requested':2},{'run_seconds':225.01}):
        assert not can_launch({**base,**update})
    assert can_launch({**base,'run_seconds':225})


@pytest.mark.parametrize('name',['../model.json','/absolute','C:/secrets','assets/../../x','a\\b','a/./b','CON:stream'])
def test_bundle_paths_reject_traversal(tmp_path,name):
    with pytest.raises(ValueError):safe_path(tmp_path,name)


def test_zip_import_checks_before_destination_mutation(tmp_path):
    archive=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside.json','{}')
    with pytest.raises(ValueError):import_bundle(archive,tmp_path/'out')
    assert not (tmp_path/'out').exists() and not (tmp_path/'outside.json').exists()


def test_catalog_detects_inconsistent_counts_without_rewriting(public_run,monkeypatch):
    import battlemind.evidence as evidence
    monkeypatch.setattr(evidence,'ROOT',public_run.parent)
    dump(public_run/'summary.json',{'requested':1,'completed':0,'a_wins':0,'b_wins':0,'draws':0})
    before=(public_run/'summary.json').read_bytes()
    record=cell_record(public_run)
    assert 'completed' in record['inconsistent_fields'] and 'a_wins' in record['inconsistent_fields']
    assert (public_run/'summary.json').read_bytes()==before


def test_catalog_zero_final_examples_remain_unavailable(tmp_path, monkeypatch):
    import battlemind.evidence as evidence
    root=tmp_path/'original'
    summary={'requested_games':0,'completed_games':0,'status':'incomplete',
        'final_probability':{'metrics':{'none':{'examples':0,'switches':0,'brier':None,'log_loss':None}}}}
    dump(root/'summary.json',summary)
    before=(root/'summary.json').read_bytes()
    monkeypatch.setattr(evidence,'ROOT',tmp_path)
    monkeypatch.setattr(evidence,'SOURCES',[('V6-first','original','incomplete','absent.md')])
    result=evidence.build_catalog(tmp_path/'report')
    assert result['ok']
    text=(tmp_path/'report/REPORT.md').read_text()
    assert '| none | 0 | 0 | unavailable | unavailable |' in text
    assert 'Zero final examples' in text
    assert (root/'summary.json').read_bytes()==before


def test_explanation_cannot_contain_private_snapshot(public_run):
    data=historical_replay(public_run,0,'test','test')
    data['explanations']=[{'observation':{'private':'forbidden'}}]
    with pytest.raises(ValueError,match='explanation'):validate_replay(data)


def test_spectator_failure_does_not_duplicate_completed_battle(tmp_path, monkeypatch):
    import asyncio
    import battlemind.runner as runner

    class FailedSpectator:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def terminal(self,row): raise ValueError('test spectator failure')

    async def handshake(port): pass
    async def completed(*args):
        return {'match':0,'status':'completed','winner':'a','team_indices':{'a':0,'b':1},'challenger':'a'}

    monkeypatch.setattr(runner,'inspect_server',lambda *a:{})
    monkeypatch.setattr(runner,'healthcheck',handshake)
    monkeypatch.setattr(runner,'play_match',completed)
    result=asyncio.run(runner.run(runner.RunConfig(battles=2),tmp_path/'run',spectator=FailedSpectator()))
    rows=runner.read_jsonl(tmp_path/'run/battles.jsonl')
    assert [(r['match'],r['status']) for r in rows]==[(0,'completed'),(1,'not_started')]
    assert result['requested']==2 and result['completed']==1 and result['not_started']==1
    assert 'test spectator failure' in (tmp_path/'run/events.jsonl').read_text()


def test_retained_bundle_roundtrip_and_tamper_rejection(tmp_path):
    from battlemind.demo_bundle import export_bundle, verify
    from battlemind.environment import ROOT, sha256
    bundle=ROOT/'runs/v7-release-bundle'
    if not bundle.exists():pytest.skip('Requires the retained demo bundle; source-only unit suite covers unsafe paths separately')
    original=verify(bundle)
    export_bundle(bundle,tmp_path/'bundle.zip')
    imported=import_bundle(tmp_path/'bundle.zip',tmp_path/'isolated')
    assert imported['manifest_sha256']==original['manifest_sha256']
    assert imported['observer_decisions_replayed']==98
    assert imported['changed_probability_decisions']>0
    copied=tmp_path/'isolated'
    before=sha256(copied/'checkpoint.json')
    verify(copied)
    assert sha256(copied/'checkpoint.json')==before
    model=json.loads((copied/'checkpoint.json').read_text());model['parameters']['status']=100
    dump(copied/'checkpoint.json',model)
    with pytest.raises(ValueError,match='hash mismatch'):verify(copied)
