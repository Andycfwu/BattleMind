"""Opt-in derived engine build. Never starts a server or modifies the pinned tree."""
import argparse
import difflib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
import uuid

from .environment import ROOT, executable, process_env, sha256

VERSION = 'bm-acceptance-build-1'
INSTALLED_VERSION = 'bm-acceptance-build-2'
INSTALL_ARGS = ['install', '--prod', '--no-optional', '--ignore-scripts',
                '--frozen-lockfile', '--package-import-method=copy',
                '--registry=https://registry.npmjs.org']
HELPER = ROOT/'configs/acceptance/battlemind-acceptance.ts'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Pinned patch anchor count changed: {old[:80]!r}')
    return text.replace(old, new, 1)


def patched_sources(upstream: Path, *, io=None) -> dict[str, str]:
    read = io.read_text if io else lambda p: p.read_text(encoding='utf-8')
    result={}
    for name in ('server/room-battle.ts','sim/battle-stream.ts','sim/battle.ts','sim/side.ts'):
        text=read(upstream/name)
        text="import * as BME from '../lib/battlemind-acceptance';\n"+text
        if name=='server/room-battle.ts':
            for method,next_method,op in (('choose','undo','choose'),('undo','joinGame','undo')):
                start=text.index(f'\toverride {method}(user: User, data: string) {{')
                end=text.index(f'\toverride {next_method}(',start)
                block=text[start:end]
                head,body=block.split('\n',1)
                assert body.endswith('\t}\n')
                wrapped=head+f"\n\t\treturn BME.roomCall(this, user, data, '{op}', () => {{\n"+body[:-3]+'\t\t});\n\t}\n'
                text=text[:start]+wrapped+text[end:]
            text=replace_once(text,'void this.stream.write(`>${player.slot} ${choice}`);','void this.stream.write(BME.forward(this, player.slot, choice));')
            text=replace_once(text,'void this.stream.write(`>${player.slot} undo`);',"void this.stream.write(BME.forward(this, player.slot, 'undo'));")
            text=replace_once(text,'player?.sendRoom(`|request|${requestJSON}`);','BME.roomRequest(this, slot, requestJSON);\n\t\t\t\tplayer?.sendRoom(`|request|${requestJSON}`);')
            text=replace_once(text,"\t\tcase 'end':\n\t\t\tthis.logData", "\t\tcase 'end':\n\t\t\tBME.roomEnd(this);\n\t\t\tthis.logData")
        elif name=='sim/battle-stream.ts':
            text=replace_once(text,'\t_writeLine(type: string, message: string) {','\t_writeLine(type: string, message: string) {\n\t\tif (type === \'bmaccept\') { BME.envelope(this, message); return; }')
            old="\t\t\tif (message === 'undo') {\n\t\t\t\tthis.battle!.undoChoice(type);\n\t\t\t} else {\n\t\t\t\tthis.battle!.choose(type, message);\n\t\t\t}"
            text=replace_once(text,old,"\t\t\tBME.input(this, type, message, () => {\n"+old+"\n\t\t\t});")
            text=replace_once(text,'\tpushMessage(type: string, data: string) {',"\tpushMessage(type: string, data: string) {\n\t\tif (type === 'end') BME.engineEnd(this);")
        elif name=='sim/battle.ts':
            text=replace_once(text,'\t\tif (!side.choose(input)) {','\t\tconst bmParsed = side.choose(input);\n\t\tBME.parsed(this, side, bmParsed);\n\t\tif (!bmParsed) {')
            text=replace_once(text,'\t\tif (this.allChoicesDone()) this.commitChoices();\n\t\treturn true;', '\t\tBME.accepted(this, side);\n\t\tif (this.allChoicesDone()) this.commitChoices();\n\t\treturn true;')
            text=replace_once(text,'\t\t\tif (choice) this.inputLog.push(`>${side.id} ${choice}`);','\t\t\tif (choice) {\n\t\t\t\tthis.inputLog.push(`>${side.id} ${choice}`);\n\t\t\t\tBME.committed(this, side, choice, this.inputLog.length - 1);\n\t\t\t}')
            text=replace_once(text,'\t\tside.clearChoice();\n\n\t\tif (updated)', '\t\tside.clearChoice();\n\t\tBME.cancelled(this, side);\n\n\t\tif (updated)')
        else:
            text=replace_once(text,'\t\tconst type = `[${updated ? \'Unavailable\' : \'Invalid\'} choice]`;','\t\tconst type = `[${updated ? \'Unavailable\' : \'Invalid\'} choice]`;\n\t\tBME.choiceError(this, updated ? \'unavailable\' : \'invalid\');')
            text=replace_once(text,"\t\tthis.battle.send('sideupdate', `${this.id}\\n|request|${JSON.stringify(update)}`);", "\t\tBME.engineRequest(this, update);\n\t\tthis.battle.send('sideupdate', `${this.id}\\n|request|${JSON.stringify(update)}`);")
            text=replace_once(text,'\t\tif (lockedMove) {\n\t\t\tlet lockedMoveTargetLoc',"\t\tif (lockedMove) {\n\t\t\tBME.branch(this, 'locked_move');\n\t\t\tlet lockedMoveTargetLoc")
            text=replace_once(text,"(['frz', 'slp'].includes(pokemon.status) || pokemon.volatiles['partiallytrapped'])) {", "(['frz', 'slp'].includes(pokemon.status) || pokemon.volatiles['partiallytrapped'])) {\n\t\t\tBME.branch(this, 'gen1_fight');")
            text=replace_once(text,'\t\t} else if (!moves.length) {','\t\t} else if (!moves.length) {\n\t\t\tBME.branch(this, \'no_enabled_moves\');')
        result[name]=text
    result['lib/battlemind-acceptance.ts']=read(HELPER)
    return result


def canonical_hash(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def upstream_files(upstream, *, io=None):
    read = io.read_text if io else lambda p: p.read_text()
    digest = io.hash if io else sha256
    expected=json.loads(read(ROOT/'configs/versions.json'))
    def git(*args):
        command=[executable('git'),'-C',str(upstream),*args]
        return io.command(command) if io else subprocess.check_output(command,text=True,timeout=30).strip()
    if git('rev-parse','HEAD')!=expected['showdown_commit']:raise ValueError('Wrong upstream commit')
    if git('diff','HEAD','--','.',':(exclude)pnpm-lock.yaml').strip():raise ValueError('Modified upstream source')
    names=git('ls-files').splitlines()
    return {n:digest(upstream/n) for n in names}


def dependency_links(output: Path, *, io=None):
    """Record pnpm links without following them; reject external or broken targets.

    File identity alone misses the realpath ancestry Node uses for dependencies.
    Preserve v1 byte inventories, adding this independent layout check for v2.
    """
    links={}
    def walk(directory):
        if io: io.check('dependency layout '+str(directory))
        with os.scandir(directory) as entries:
            for entry in entries:
                if io: io.check('dependency layout entry')
                p=Path(entry.path)
                if p.is_symlink() or p.is_junction():
                    target=p.resolve(strict=True)
                    if not target.is_relative_to(output/'node_modules'):
                        raise ValueError('Dependency link escapes its private install: '+str(p))
                    links[p.relative_to(output).as_posix()]=target.relative_to(output).as_posix()
                elif entry.is_dir(follow_symlinks=False):walk(p)
    walk(output/'node_modules')
    return dict(sorted(links.items()))


def dependency_files(directory: Path, *, io=None):
    """Hash physical package files once; links have their own checked inventory."""
    if io: io.check('dependency files '+str(directory))
    with os.scandir(directory) as entries:
        for entry in entries:
            if io: io.check('dependency file entry')
            p=Path(entry.path)
            if p.is_symlink() or p.is_junction():continue
            if entry.is_dir(follow_symlinks=False):yield from dependency_files(p,io=io)
            elif entry.is_file(follow_symlinks=False):yield p


def build(output: Path):
    # This opt-in build has no server side effects. The package manager builds its
    # own links; copying their dereferenced contents breaks Node resolution.
    from diagnostics.acceptance_preflight import DeadlineIO
    io=DeadlineIO(time.monotonic()+300)
    upstream=ROOT/'.local/pokemon-showdown'; output=output.resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==upstream.resolve():
        raise ValueError('Derived build must be separate under ignored .local')
    versions=json.loads((ROOT/'configs/versions.json').read_text())
    if io.command([executable('node'),'--version'])!=versions['node']:raise ValueError('Load scripts/env.ps1: wrong Node')
    if io.command([executable('pnpm'),'--version'])!=versions['pnpm']:raise ValueError('Wrong pnpm version')
    original=upstream_files(upstream,io=io); patched=patched_sources(upstream,io=io)
    output.mkdir(parents=True,exist_ok=False)
    for name in original:
        target=output/name; io.copy(upstream/name,target)
    patch=''
    for name,text in patched.items():
        old=(upstream/name).read_text(encoding='utf-8') if (upstream/name).is_file() else ''
        patch+=''.join(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
        (output/name).write_text(text,encoding='utf-8',newline='\n')
    (output/'acceptance.patch').write_text(patch,encoding='utf-8',newline='\n')
    shutil.copyfile(ROOT/'configs/showdown.config.js',output/'config/config.js')
    shutil.copyfile(ROOT/'configs/showdown-pnpm-lock.yaml',output/'pnpm-lock.yaml')
    setup={'method':'pnpm frozen production install; copied store imports, package-manager links',
           'pnpm':versions['pnpm'],'install_args':INSTALL_ARGS,
           'post_install':['node node_modules/esbuild/install.js','node build']}
    with (output/'acceptance-build.log').open('x',encoding='utf-8') as log:
        for args in ([executable('pnpm'),*INSTALL_ARGS],
                     [executable('node'),'node_modules/esbuild/install.js'],[executable('node'),'build']):
            log.write(json.dumps(args)+'\n');log.flush()
            log.write(io.command(args,output,max_seconds=120)+'\n');log.flush()
    names=set(original)|set(patched)|{'config/config.js','pnpm-lock.yaml'}
    names|={p.relative_to(output).as_posix() for p in io.files(output/'dist')}
    manifest={'schema':INSTALLED_VERSION,'dependency_setup':setup,
        'dependency_links':dependency_links(output,io=io),
        'build_tool_sha256':io.hash(Path(__file__)),
        'upstream_commit':versions['showdown_commit'],'upstream_source':original,
        'patch_sha256':io.hash(output/'acceptance.patch'),'helper_sha256':io.hash(HELPER),
        'versions':versions,'files':{n:io.hash(output/n) for n in sorted(names)},
        'configuration_sha256':io.hash(ROOT/'configs/showdown.config.js'),
        'dependency_lock_sha256':io.hash(ROOT/'configs/showdown-pnpm-lock.yaml')}
    manifest['dependencies']={p.relative_to(output).as_posix():io.hash(p) for p in dependency_files(output/'node_modules',io=io)}
    manifest['build_id']=canonical_hash(manifest)
    (output/'acceptance-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def verify_build(output: Path, *, io=None) -> dict:
    digest = io.hash if io else sha256
    read = io.read_text if io else lambda p: p.read_text(encoding='utf-8')
    files = io.files if io else lambda p: (q for q in p.rglob('*') if q.is_file())
    if io: io.check('verify derived build')
    output=output.resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local/pokemon-showdown').resolve():raise ValueError('Not a derived local build')
    m=json.loads(read(output/'acceptance-build.json'));body={k:v for k,v in m.items() if k!='build_id'}
    if m['schema'] not in (VERSION,INSTALLED_VERSION) or canonical_hash(body)!=m['build_id']:raise ValueError('Invalid build manifest')
    original=upstream_files(ROOT/'.local/pokemon-showdown', **({'io':io} if io else {}))
    if m['upstream_source']!=original or m['helper_sha256']!=digest(HELPER):raise ValueError('Incompatible instrumented source')
    if m['versions']!=json.loads(read(ROOT/'configs/versions.json')):raise ValueError('Version mismatch')
    if m['upstream_commit']!=m['versions']['showdown_commit']:raise ValueError('Upstream provenance mismatch')
    if digest(output/'acceptance.patch')!=m['patch_sha256']:raise ValueError('Patch mismatch')
    for name,expected_digest in m['files'].items():
        p=(output/name).resolve()
        if not p.is_relative_to(output) or digest(p)!=expected_digest:raise ValueError('Build content mismatch: '+name)
    patched=patched_sources(ROOT/'.local/pokemon-showdown', **({'io':io} if io else {}))
    required=set(original)|set(patched)|{'config/config.js','pnpm-lock.yaml'}
    required|={p.relative_to(output).as_posix() for p in files(output/'dist')}
    if set(m['files'])!=required:raise ValueError('Incomplete build inventory')
    for name,original_hash in original.items():
        if name not in patched and name!='pnpm-lock.yaml' and digest(output/name)!=original_hash:raise ValueError('Unreviewed source change: '+name)
    for name,text in patched.items():
        if read(output/name)!=text:raise ValueError('Unexpected patch: '+name)
    if digest(output/'config/config.js')!=digest(ROOT/'configs/showdown.config.js'):raise ValueError('Binding differs')
    if m['configuration_sha256']!=digest(ROOT/'configs/showdown.config.js'):raise ValueError('Configuration provenance mismatch')
    lock_hash=digest(ROOT/'configs/showdown-pnpm-lock.yaml')
    if m['dependency_lock_sha256']!=lock_hash or digest(output/'pnpm-lock.yaml')!=lock_hash:raise ValueError('Dependency lock mismatch')
    if m['schema']==INSTALLED_VERSION:
        expected_setup={'method':'pnpm frozen production install; copied store imports, package-manager links',
            'pnpm':m['versions']['pnpm'],'install_args':INSTALL_ARGS,
            'post_install':['node node_modules/esbuild/install.js','node build']}
        if m.get('dependency_setup')!=expected_setup:raise ValueError('Unreviewed dependency setup')
        if dependency_links(output,io=io)!=m.get('dependency_links'):raise ValueError('Dependency link layout mismatch')
    package_files=dependency_files(output/'node_modules',io=io) if m['schema']==INSTALLED_VERSION else files(output/'node_modules')
    dependencies={p.relative_to(output).as_posix():digest(p) for p in package_files}
    if dependencies!=m['dependencies']:raise ValueError('Dependency content mismatch')
    return m


def verify_recording_runtime(expected: dict, *, io=None) -> None:
    actual={'python':platform.python_version(),'poke_env':importlib.metadata.version('poke-env'),
            'node':io.command([executable('node'),'--version']) if io else subprocess.check_output([executable('node'),'--version'],text=True,timeout=30).strip()}
    for name,value in actual.items():
        if value!=expected[name]:raise ValueError(f'Pinned recording runtime mismatch: {name}={value}')


def recording_environment(output: Path, private_directory: Path, *, io=None) -> dict[str,str]:
    """Explicit future-harness setup, not a server launcher or global env mutation.

    Pass this environment to the derived server process only. Give each player a
    separate ClientRecorder with its session/build identity; keep this directory
    outside viewer exports. Existing battle/doctor commands remain unchanged.
    """
    kwargs={'io':io} if io else {}
    manifest=verify_build(output, **kwargs)
    verify_recording_runtime(manifest['versions'], **kwargs)
    if io: io.check('create recording metadata')
    private_directory=private_directory.resolve()
    if not private_directory.is_relative_to((ROOT/'runs').resolve()) or 'privileged' not in private_directory.relative_to(ROOT/'runs').parts:
        raise ValueError('Evidence must be under ignored runs/.../privileged/...')
    private_directory.mkdir(parents=True,exist_ok=False)
    session=uuid.uuid4().hex
    metadata={'schema':'bm-acceptance-session-1','session':session,'build':manifest['build_id'],
              'build_manifest_sha256':(io.hash if io else sha256)(output/'acceptance-build.json'),
              'lifecycle':'Fresh recording clients per battle; post-match joins after close_acceptance_players only.'}
    (private_directory/'session.json').write_text(json.dumps(metadata,indent=2)+'\n')
    env=process_env()
    env.update(BATTLEMIND_ACCEPTANCE_DIR=str(private_directory),BATTLEMIND_ACCEPTANCE_SESSION=session,
               BATTLEMIND_ACCEPTANCE_BUILD=manifest['build_id'])
    return env


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify',action='store_true')
    args=parser.parse_args(); print(json.dumps(verify_build(args.output) if args.verify else build(args.output),indent=2))
