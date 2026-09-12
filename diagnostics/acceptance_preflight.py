"""Bounded I/O for the opt-in acceptance harness, not battle/policy machinery.

Chunk checks handle ordinary slow reads. The live parent also supervises each
worker, because a Python deadline cannot interrupt an OS read or directory call.
No deadline result is a reusable validation cache.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import psutil

from battlemind.environment import ROOT, process_env, stop_process_tree


class DeadlineExpired(ValueError):
    pass


def supervise(args, io, log, *, env=None, record=None):
    """One worker; deadline includes startup. Cleanup is charged, not hidden."""
    io.check('worker startup')
    started=io.clock()
    child=subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    error=None;owned=[child.pid]
    try:
        child.wait(timeout=io.remaining('worker wait'))
        io.check('worker completion')
        if child.returncode:raise ValueError(f'Worker failed with exit code {child.returncode}')
        return child.pid
    except BaseException as exc:
        error=f'{type(exc).__name__}: {exc}'
        try:owned += [p.pid for p in psutil.Process(child.pid).children(recursive=True)]
        except psutil.NoSuchProcess:pass
        stop_process_tree(child.pid)
        child.wait(timeout=2)
        raise
    finally:
        remaining=[pid for pid in owned if psutil.pid_exists(pid)]
        if record:record({'worker_pid':child.pid,'owned_at_stop':owned,'remaining_owned_pids':remaining,
            'error':error,'elapsed_seconds':io.clock()-started,'deadline_monotonic':io.until})
        if remaining:raise ValueError(f'Worker cleanup failed: {remaining}')


class DeadlineIO:
    def __init__(self, until, *, clock=time.monotonic, opener=None, progress=None):
        self.until = until
        self.clock = clock
        self.opener = opener or (lambda p, mode: p.open(mode))
        self.progress = progress

    def remaining(self, operation):
        remaining = self.until - self.clock()
        if remaining <= 0:
            raise DeadlineExpired(f'Deadline exhausted: {operation}')
        return remaining

    def check(self, operation):
        self.remaining(operation)

    def chunks(self, path):
        self.check(f'open {path}')
        with self.opener(path, 'rb') as stream:
            while True:
                self.check(f'read {path}')
                block = stream.read(1024 * 1024)
                self.check(f'after read {path}')
                if not block:
                    break
                yield block

    def hash(self, path):
        started = self.clock(); size = 0; digest = hashlib.sha256()
        try:
            for block in self.chunks(path):
                digest.update(block); size += len(block)
            self.check(f'finish hash {path}')
        except BaseException as exc:
            self.record(path, started, size, None, f'{type(exc).__name__}: {exc}')
            raise
        value = digest.hexdigest()
        self.record(path, started, size, value, None)
        return value

    def record(self, path, started, size, value, error):
        if self.progress:
            self.progress({'path':str(path), 'bytes_hashed':size, 'sha256':value,
                           'elapsed_seconds':self.clock()-started, 'error':error})

    def read_text(self, path):
        return b''.join(self.chunks(path)).decode('utf-8').replace('\r\n', '\n')

    def copy(self, source, target):
        self.check(f'copy {source}'); target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as out:
            for block in self.chunks(source):
                out.write(block); self.check(f'write {target}')

    def files(self, directory):
        self.check(f'list {directory}')
        with os.scandir(directory) as entries:
            for entry in entries:
                self.check(f'entry {entry.path}')
                if entry.is_symlink():
                    raise ValueError(f'Symlink not allowed in input inventory: {entry.path}')
                if entry.is_dir():
                    yield from self.files(Path(entry.path))
                elif entry.is_file():
                    yield Path(entry.path)
        self.check(f'after list {directory}')

    def command(self, args, cwd=None, stdin=None, max_seconds=30):
        self.check(f'start command {args[0]}')
        child = subprocess.Popen(args, cwd=cwd, env=process_env(), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            out, err = child.communicate(stdin, timeout=min(max_seconds, self.remaining('command wait')))
            self.check(f'after command {args[0]}')
            if child.returncode:
                raise ValueError(f'Command failed ({child.returncode}): {args}\n{err}\n{out}')
            return out.strip()
        except BaseException:
            stop_process_tree(child.pid)
            child.wait(timeout=2)
            raise


def contained(root, name):
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Input escapes project: {name}')
    return path


def verify_inventory(root, inventory, io):
    """No cache: each named file is freshly hashed, and additions are checked."""
    checked = {}
    for name, expected in inventory['files'].items():
        io.check(f'next input {name}')
        actual = io.hash(contained(root, name))
        if actual != expected:
            raise ValueError('Required input changed: '+name)
        checked[name] = actual
    for tree in inventory.get('exact_trees', []):
        prefix = tree.rstrip('/')+'/'
        actual = {p.relative_to(root).as_posix() for p in io.files(contained(root, tree))
                  if '__pycache__' not in p.parts and p.suffix != '.pyc'}
        expected = {n for n in checked if n.startswith(prefix)}
        if actual != expected:
            raise ValueError('Input tree membership changed: '+tree)
    return checked


def required_inputs(manifest_path, io, root=ROOT):
    manifest = json.loads(io.read_text(manifest_path))
    if manifest['schema'] != 'bm-acceptance-required-inputs-1':
        raise ValueError('Unsupported input manifest')
    checked = verify_inventory(root, {'files':manifest['pinned_files']}, io)
    for name in manifest['inventory_files']:
        inventory = json.loads(io.read_text(contained(root, name)))
        checked.update(verify_inventory(root, inventory, io))
    for name in manifest['project_files']:
        checked[name] = io.hash(contained(root, name))
    return checked


def archive_scan(inventory_path, output, seconds, root=ROOT):
    """Optional offline preservation scan; never part of live critical preflight."""
    if not 0 < seconds <= 600:
        raise ValueError('Archive scan requires an explicit 0 < seconds <= 600 budget')
    output.mkdir(parents=True, exist_ok=False)
    started=time.monotonic(); failure=None; checked={}
    with (output/'checked.jsonl').open('x', encoding='utf-8') as stream:
        def progress(row):
            stream.write(json.dumps(row)+'\n');stream.flush()
        io=DeadlineIO(started+seconds, progress=progress)
        try:
            inventory=json.loads(io.read_text(inventory_path))
            entries=inventory.get('hashes', inventory.get('files'))
            if not isinstance(entries,dict) or not entries:raise ValueError('Archive inventory must explicitly name files')
            for name, expected in entries.items():
                actual=io.hash(contained(root, name));checked[name]=actual
                if actual!=expected:raise ValueError('Historical input differs: '+name)
        except BaseException as exc:failure=f'{type(exc).__name__}: {exc}'
    result={'schema':'bm-acceptance-archive-scan-1','maximum_seconds':seconds,
        'elapsed_seconds':time.monotonic()-started,'failure':failure,'completed_files':len(checked),
        'scope':str(inventory_path),'full_scan_passed':failure is None,'games_requested':0}
    (output/'report.json').write_text(json.dumps(result,indent=2))
    return result


def archive_main(inventory, output, seconds):
    """Separate single-use offline budget with its own process watchdog."""
    import sys
    if not 10 < seconds <= 600:raise ValueError('Explicit archive budget must be >10 and <=600 seconds')
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();failure=None
    ledger={'schema':'bm-acceptance-archive-ledger-1','maximum_seconds':seconds,
        'cleanup_and_accounting_reserve_seconds':10,'games_requested':0,'started_monotonic':started,
        'state':'running','inventory':str(inventory.resolve())}
    path=output/'ledger.json';path.write_text(json.dumps(ledger,indent=2))
    try:
        with (output/'console.txt').open('x') as log:
            supervise([sys.executable,'-B','-m','diagnostics.acceptance_preflight','--archive-worker',
                '--inventory',str(inventory.resolve()),'--output',str((output/'scan').resolve()),
                '--until',str(started+seconds-10)],DeadlineIO(started+seconds-10),log)
    except BaseException as exc:failure=f'{type(exc).__name__}: {exc}'
    ledger.update(state='stopped' if failure else 'finished',failure=failure,
                  stopped_monotonic=time.monotonic(),elapsed_seconds=time.monotonic()-started)
    path.write_text(json.dumps(ledger,indent=2))
    return ledger


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Optional offline archive preservation scan; zero games.')
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=float)
    parser.add_argument('--archive-worker',action='store_true')
    parser.add_argument('--until',type=float)
    args=parser.parse_args()
    if args.archive_worker:
        if args.until is None:parser.error('--until required')
        result=archive_scan(args.inventory,args.output,DeadlineIO(args.until).remaining('archive worker'))
        raise SystemExit(1 if result['failure'] else 0)
    if args.seconds is None:parser.error('--seconds is mandatory; there is no unbounded default')
    result=archive_main(args.inventory,args.output,args.seconds)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['state']=='finished' else 1)
