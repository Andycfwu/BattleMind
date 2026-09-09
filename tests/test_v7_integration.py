"""Exactly one real functional game; no training or acceptance-experiment imports."""

import asyncio
import json
import time
import uuid

import pytest

from battlemind.demo_bundle import write
from battlemind.demo_server import Spectator
from battlemind.environment import ROOT, sha256
from battlemind.prediction_report import audit_predictions
from battlemind.runner import RunConfig, run
from battlemind.viewer_records import VERSION, validate_replay


@pytest.mark.integration
def test_v7_real_public_spectator_and_frozen_policy():
    path=ROOT/'runs'/('integration-v7-'+uuid.uuid4().hex[:10])
    public={'schema_version':VERSION,'id':'integration','title':'One functional test',
        'origin':'live spectator stream; delayed playback','status':'running','outcome':None,
        'detail':None,'lines':[],'explanations':[],'provenance':{},'limitations':[]}
    async def check():
        start=time.monotonic()
        config=RunConfig(agent_a='learned-score',agent_b='max-base-power',battles=1,seed=71901,
            timeout=60,run_timeout=75,turn_cap=300,predictor='models/v4-supervised.json',
            checkpoint_a='runs/v5-acceptance/selected.json')
        summary=await run(config,path,True,spectator=Spectator(config.port,public))
        assert summary['completed']+summary['truncated']==1
        assert not any(summary[k] for k in ('crash','cancelled','timeout','not_started','invalid_action_incidents'))
        assert not summary.get('unexpected_client_warning_records')
        audit=audit_predictions(path)
        validate_replay(public)
        assert public['status'] in {'completed','truncated'}
        assert any(s.startswith('|move|') for s in public['lines'])
        assert any(s.startswith('|switch|') for s in public['lines'])
        assert not any(s.startswith(('|request|','|showteam|','|split|')) for s in public['lines'])
        assert all('bm' not in s for s in public['lines'] if s.startswith('|player|'))
        elapsed=time.monotonic()-start
        write(path/'public-replay.json',public)
        write(path/'functional-verification.json',{'purpose':'one V7 functional test, not experiment metrics',
            'requested_games':1,'elapsed_including_audit':elapsed,'maximum_seconds':75,
            'summary':summary,'audit':audit,'public_sha256':sha256(path/'public-replay.json')})
        assert elapsed<75
        print('V7 functional test artifact:',path)
    asyncio.run(check())
