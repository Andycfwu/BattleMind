"""Isolated manifest/path regressions; real retained build verification is separate."""
import json
from pathlib import Path

import pytest

from battlemind import acceptance_build as module
from battlemind.environment import sha256


@pytest.fixture
def build_fixture(tmp_path,monkeypatch):
    root=tmp_path;source=root/'.local/original';target=root/'.local/derived';config=root/'configs'
    source.mkdir(parents=True);target.mkdir();config.mkdir()
    helper=config/'helper.ts';helper.write_text('reviewed helper')
    (config/'versions.json').write_text('{"showdown_commit":"pinned"}')
    (config/'showdown.config.js').write_text('reviewed binding')
    (config/'showdown-pnpm-lock.yaml').write_text('pinned lock')
    (source/'file.ts').write_text('upstream')
    for name,value in {'file.ts':'patched','config/config.js':'reviewed binding','pnpm-lock.yaml':'pinned lock',
        'dist/file.js':'built','acceptance.patch':'reviewed diff','node_modules/dependency.js':'copied dependency'}.items():
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
    original={'file.ts':sha256(source/'file.ts')}
    monkeypatch.setattr(module,'ROOT',root);monkeypatch.setattr(module,'HELPER',helper)
    monkeypatch.setattr(module,'upstream_files',lambda path,**kwargs:original)
    monkeypatch.setattr(module,'patched_sources',lambda path,**kwargs:{'file.ts':'patched'})
    manifest={'schema':module.VERSION,'upstream_commit':'pinned','upstream_source':original,
        'patch_sha256':sha256(target/'acceptance.patch'),'helper_sha256':sha256(helper),
        'versions':{'showdown_commit':'pinned'},'files':{n:sha256(target/n) for n in ('file.ts','config/config.js','pnpm-lock.yaml','dist/file.js')},
        'configuration_sha256':sha256(config/'showdown.config.js'),
        'dependency_lock_sha256':sha256(config/'showdown-pnpm-lock.yaml'),
        'dependencies':{'node_modules/dependency.js':sha256(target/'node_modules/dependency.js')}}
    manifest['build_id']=module.canonical_hash(manifest)
    (target/'acceptance-build.json').write_text(json.dumps(manifest))
    return target


@pytest.mark.parametrize('name',['file.ts','dist/file.js','config/config.js','acceptance.patch','pnpm-lock.yaml','node_modules/dependency.js'])
def test_build_content_mutations_are_rejected(build_fixture,name):
    assert module.verify_build(build_fixture)['schema']==module.VERSION
    (build_fixture/name).write_text('tampered')
    with pytest.raises(ValueError):module.verify_build(build_fixture)


def test_fresh_private_environment_requires_compatible_build_and_ignored_path(build_fixture,monkeypatch):
    monkeypatch.setattr(module,'process_env',lambda:{'PATH':'untouched'})
    monkeypatch.setattr(module,'verify_recording_runtime',lambda expected:None)
    root=module.ROOT
    with pytest.raises(ValueError,match='privileged'):module.recording_environment(build_fixture,root/'public')
    folder=root/'runs/new/privileged/acceptance';env=module.recording_environment(build_fixture,folder)
    assert env['PATH']=='untouched' and env['BATTLEMIND_ACCEPTANCE_DIR']==str(folder.resolve())
    assert json.loads((folder/'session.json').read_text())['build']==env['BATTLEMIND_ACCEPTANCE_BUILD']
    with pytest.raises(FileExistsError):module.recording_environment(build_fixture,folder)


def test_wrong_runtime_fails_before_recording_directory_creation(build_fixture,monkeypatch):
    def reject(expected):raise ValueError('Pinned recording runtime mismatch')
    monkeypatch.setattr(module,'verify_recording_runtime',reject)
    folder=module.ROOT/'runs/new/privileged/acceptance'
    with pytest.raises(ValueError,match='runtime'):module.recording_environment(build_fixture,folder)
    assert not folder.exists()


@pytest.mark.parametrize('name',['file.ts','dist/file.js','config/config.js','acceptance.patch','pnpm-lock.yaml','node_modules/dependency.js'])
def test_bounded_verifier_preserves_all_content_checks(build_fixture,name):
    from diagnostics.acceptance_preflight import DeadlineIO
    io=DeadlineIO(10,clock=lambda:0)
    assert module.verify_build(build_fixture,io=io)==module.verify_build(build_fixture)
    (build_fixture/name).write_text('tampered')
    with pytest.raises(ValueError):module.verify_build(build_fixture,io=io)


def test_build_validation_stops_between_hashes(build_fixture):
    from diagnostics.acceptance_preflight import DeadlineIO, DeadlineExpired
    now=[0.];seen=[]
    def progress(row):seen.append(row);now[0]+=1
    with pytest.raises(DeadlineExpired):module.verify_build(build_fixture,io=DeadlineIO(2,clock=lambda:now[0],progress=progress))
    assert len([r for r in seen if r['sha256']])==2


def test_new_build_installs_pinned_packages_in_derived_cwd_and_utf8_log(build_fixture,monkeypatch):
    from diagnostics.acceptance_preflight import DeadlineIO
    root=module.ROOT;source=root/'.local/pokemon-showdown';source.mkdir()
    (source/'file.ts').write_text('upstream')
    (source/'config').mkdir();(source/'config/config-example.js').write_text('official example')
    original={name:sha256(source/name) for name in ('file.ts','config/config-example.js')}
    monkeypatch.setattr(module,'upstream_files',lambda path,**kwargs:original)
    versions={'showdown_commit':'pinned','node':'v24.19.0','pnpm':'11.19.0'}
    (root/'configs/versions.json').write_text(json.dumps(versions))
    output=root/'.local/fresh';calls=[]
    monkeypatch.setattr(module,'executable',lambda name:name)
    monkeypatch.setattr(module.shutil,'copytree',lambda *a,**k:pytest.fail('Never copy node_modules'))
    def command(self,args,cwd=None,**kwargs):
        calls.append((args,cwd))
        if args==['node','--version']:return versions['node']
        if args==['pnpm','--version']:return versions['pnpm']
        assert cwd==output and kwargs['max_seconds']==120
        if args[0]=='pnpm':
            (output/'node_modules').mkdir();(output/'node_modules/dependency.js').write_text('installed')
        if args==['node','build']:
            (output/'dist').mkdir();(output/'dist/file.js').write_text('built')
        return '\u2713 pinned command completed'  # Windows cp1252 cannot encode this.
    monkeypatch.setattr(DeadlineIO,'command',command)
    result=module.build(output)
    assert result['schema']==module.INSTALLED_VERSION
    assert [a for a,_ in calls][-3:]==[['pnpm',*module.INSTALL_ARGS],
        ['node','node_modules/esbuild/install.js'],['node','build']]
    assert '\u2713' in (output/'acceptance-build.log').read_text(encoding='utf-8')
    assert module.verify_build(output)['build_id']==result['build_id']
