"""Zero-battle server readiness used by opt-in preflight, never by policies."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil
from battlemind.environment import ROOT, LocalServer, executable, healthcheck
from diagnostics.acceptance_preflight import DeadlineIO, supervise


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def resolve_modules(engine, io):
    engine=engine.resolve()
    return json.loads(io.command([executable('node'),str(ROOT/'scripts/inspect-acceptance-runtime.cjs'),
        str(engine/'pokemon-showdown')],cwd=engine,max_seconds=15))


def listeners(port):
    return [{'pid':c.pid,'host':c.laddr.ip,'port':c.laddr.port}
            for c in psutil.net_connections(kind='tcp')
            if c.status==psutil.CONN_LISTEN and c.laddr.port==port]


async def lifecycle(engine, output, port, io):
    """One startup attempt. LocalServer owns cleanup, including failed __aenter__."""
    started=io.clock(); owned={}; samples=[]; failure=None; handshake=None
    # Checking before constructing a server prevents taking over any listener,
    # including non-loopback addresses. No process is killed by this check.
    existing=listeners(port)
    if existing:raise ValueError(f'Occupied port; no takeover: {existing}')
    server=LocalServer(engine,port,output/'server.log',output/'privileged/engine')
    async def sample():
        while True:
            if server.process:
                try:
                    parent=psutil.Process(server.process.pid)
                    processes=[parent,*parent.children(recursive=True)]
                    for process in processes:
                        owned[process.pid]=process.create_time()
                        samples.append({'pid':process.pid,'rss':process.memory_info().rss,
                            'cpu_seconds':sum(process.cpu_times()[:2])})
                except psutil.NoSuchProcess:pass
            await asyncio.sleep(.05)
    sampler=asyncio.create_task(sample())
    loaded_at=None;cleanup_started=None
    try:
        async with asyncio.timeout(min(25,io.remaining('startup')-8)):
            async with server:
                loaded_at=io.clock()
                handshake=await healthcheck(port)
                active=listeners(port)
                if not active or any(c['host']!='127.0.0.1' for c in active):
                    raise ValueError(f'Unexpected server binding: {active}')
                io.check('handshake completed')
                cleanup_started=io.clock()
    except BaseException as exc:
        failure=f'{type(exc).__name__}: {exc}'
    finally:
        sampler.cancel()
        await asyncio.gather(sampler,return_exceptions=True)
    remaining=[]
    for pid,created in owned.items():
        try:
            if psutil.Process(pid).create_time()==created:remaining.append(pid)
        except psutil.NoSuchProcess:pass
    remaining_listeners=listeners(port)
    if remaining or remaining_listeners:failure=f'Cleanup failed: {remaining}, {remaining_listeners}; {failure}'
    if io.clock()>io.until:failure=failure or 'Lifecycle deadline exceeded'
    result={'schema':'bm-acceptance-readiness-1','failure':failure,'games_requested':0,
        'handshake':handshake,'started_monotonic':started,'elapsed_seconds':io.clock()-started,
        'startup_seconds':loaded_at-started if loaded_at else None,
        'cleanup_seconds':io.clock()-cleanup_started if cleanup_started else None,
        'owned_processes':owned,'remaining_owned_pids':remaining,'remaining_listeners':remaining_listeners,
        'resource_samples':samples,'scope':'dependency loading and normal handshake only; no battle equivalence'}
    save(output/'lifecycle.json',result)
    if failure:raise ValueError(failure)
    return result


def operational_preflight(engine, env, output, io, port=8000):
    """Integrity/model checks remain in the caller. No game may start until return."""
    io.check('operational readiness');output.mkdir(parents=True,exist_ok=False)
    private=Path(env['BATTLEMIND_ACCEPTANCE_DIR']).resolve()
    if not private.is_relative_to(ROOT/'runs') or 'privileged' not in private.relative_to(ROOT/'runs').parts:
        raise ValueError('Readiness requires a private recording path')
    session=json.loads(io.read_text(private/'session.json'))
    if session['session']!=env['BATTLEMIND_ACCEPTANCE_SESSION'] or session['build']!=env['BATTLEMIND_ACCEPTANCE_BUILD']:
        raise ValueError('Readiness recording identity mismatch')
    # Open exclusively to prove the actual evidence directory is writable.
    save(private/'readiness-path-check.json',{'games_requested':0,'scope':'path writability'})
    resolution=resolve_modules(engine,io)
    save(output/'resolution.json',resolution)
    io.command([executable('node'),'--check',str(engine.resolve()/'pokemon-showdown')],cwd=engine)
    # Reserve eight seconds within this worker's budget for owned-process cleanup.
    if io.remaining('readiness reservation')<35:raise ValueError('Insufficient startup/cleanup reservation')
    until=min(io.until-5,io.clock()+40)
    with (output/'console.txt').open('x') as log:
        supervise([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',
            '--engine',str(engine.resolve()),'--output',str(output.resolve()),'--port',str(port),
            '--until',str(until)],DeadlineIO(until),log,env=env,
            record=lambda row:save(output/'process.json',row))
    result=json.loads(io.read_text(output/'lifecycle.json'))
    if result['failure']:raise ValueError('Readiness did not pass')
    io.check('readiness complete')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true',required=True)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--until',type=float,required=True)
    args=parser.parse_args()
    # This internal worker is not a battle runner and cannot reserve any games.
    asyncio.run(lifecycle(args.engine,args.output,args.port,DeadlineIO(args.until)))
