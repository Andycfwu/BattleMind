"""One fixed offline algorithm suite; no Pokémon games or historical fitting."""
from dataclasses import asdict
import json
from pathlib import Path
import time
import numpy as np
from battlemind.environment import ROOT,sha256
from battlemind.reinforce import Parameters,Checkpoint,SHAPE,load_checkpoint,distribution
from battlemind.reinforce_training import Step,Episode,gradients,update
from battlemind.schema import snapshot_from_dict

out=ROOT/'runs/reinforce-audit-20260909/synthetic';out.mkdir(exist_ok=False)
start=time.monotonic();cpu=time.process_time();results=[]
rng=np.random.default_rng(460901)
def guard():
    if time.monotonic()-start>100 or time.process_time()-cpu>100:raise TimeoutError('Synthetic allocation stopped; no retry')
def persist():
    data={'schema_version':'reinforce-offline-tests-1','seed':460901,'new_battles':0,'historical_models_updated':0,
        'maximum_seconds':120,'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,'results':results}
    (out/'results.json').write_text(json.dumps(data,indent=2,allow_nan=False))
def test(name,fn):
    guard();t=time.monotonic()
    try:result=fn();results.append({'name':name,'status':'passed',**result,'seconds':time.monotonic()-t})
    except Exception as exc:results.append({'name':name,'status':'failed','error':repr(exc),'seconds':time.monotonic()-t})
    persist();print(results[-1],flush=True)

def state(context=0):
    s=np.zeros(SHAPE[0]);s[0]=1
    if context:s[1]=context
    return s
def action_matrix(ids):
    x=np.zeros((len(ids),SHAPE[1]));x[np.arange(len(ids)),np.asarray(ids)]=1
    return x
def independent(params,s,x,prior):
    z=prior+np.einsum('i,ij,kj->k',s,np.asarray(params.actor),x)
    e=np.exp(z-np.max(z));p=e/e.sum()
    return p,float(np.tanh(np.dot(params.value,s)))
def step(model,context,ids,random):
    s=state(context);x=action_matrix(ids);prior=np.zeros(len(ids))
    p,v=independent(model.parameters,s,x,prior)
    chosen=int(random.choice(len(ids),p=p))
    return Step(s,x,prior,chosen,p,v),ids[chosen]

def finite_differences():
    w=np.zeros(SHAPE);w[:2,:3]=rng.normal(0,.2,(2,3));v=np.zeros(SHAPE[0]);v[:2]=[.17,-.09]
    params=Parameters(tuple(map(tuple,w)),tuple(v));episodes=[]
    for i,reward in enumerate((-1.,0.,1.,-1.,1.)):
        steps=[]
        for t in range(i+1):
            s=state((-1 if i%2 else 1)*.7);ids=tuple(range(1+(t+i)%3));x=action_matrix(ids)
            prior=np.linspace(-.3,.5,len(ids));p,value=independent(params,s,x,prior)
            steps.append(Step(s,x,prior,t%len(ids),p,value))
        episodes.append(Episode(str(i),'0'*64,reward,tuple(steps),'training'))
    ga,gv,metrics=gradients(params,episodes,'0'*64)
    def actor_loss(weights):
        loss=0
        for e in episodes:
            for st in e.steps:
                z=st.prior+np.einsum('i,ij,kj->k',st.state,weights,st.actions)
                m=max(z);logsum=m+np.log(np.exp(z-m).sum())
                loss-=(e.reward-st.value)*(z[st.chosen]-logsum)
        return loss/(100*len(episodes))
    def value_loss(weights):
        errors=[.5*(np.tanh(weights@st.state)-e.reward)**2 for e in episodes for st in e.steps]
        return np.mean(errors)
    eps=1e-6;errors=[]
    for i in range(2):
        for j in range(3):
            wp,wm=w.copy(),w.copy();wp[i,j]+=eps;wm[i,j]-=eps
            errors.append(abs((actor_loss(wp)-actor_loss(wm))/(2*eps)-ga[i,j]))
    for i in range(2):
        vp,vm=v.copy(),v.copy();vp[i]+=eps;vm[i]-=eps
        errors.append(abs((value_loss(vp)-value_loss(vm))/(2*eps)-gv[i]))
    assert max(errors)<1e-8,errors
    assert abs(actor_loss(w)-metrics['policy_loss'])<1e-12
    assert abs(value_loss(v)-metrics['value_loss'])<1e-12
    return {'max_gradient_absolute_error':max(errors),'nonzero_weights':True,'variable_lengths':[1,2,3,4,5],
        'baseline_detached_in_actor_loss':True,'actor_and_value_parameters_disjoint':True}

def learn(task,seed,threshold):
    random=np.random.default_rng(seed);model=Checkpoint(Parameters.initial(),'0'*64);curve=[]
    for batch in range(80):
        guard();episodes=[]
        for i in range(32):
            if task=='context':context=1 if i%2 else -1;ids=(0,1)
            elif task=='variable':context=0;ids=((0,1),(1,2),(0,2))[i%3]
            else:context=0 if task=='constant' else 1;ids=(0,1)
            st,chosen=step(model,context,ids,random);steps=[st]
            goal=0 if task in ('constant','delayed') else 0 if context==1 else 1
            if task=='variable':goal=max(ids)
            reward=1. if chosen==goal else -1.
            if task=='delayed':
                # No intermediate rewards. Three distractor steps do not cause reward.
                for _ in range(3):steps.append(step(model,-1,(0,1),random)[0])
            episodes.append(Episode(f'{task}:{batch}:{i}',model.sha256,reward,tuple(steps),'training'))
        params,metrics=update(model,episodes,30,.1)
        assert np.isfinite(np.asarray(params.actor)).all()
        model=Checkpoint(params,f'{batch+1:064x}')
        curve.append({k:metrics[k] for k in ('mean_reward','policy_loss','value_loss','actor_delta_l2')})
    if task=='context':situations=[(1,(0,1),0),(-1,(0,1),1)]
    elif task=='variable':situations=[(0,ids,max(ids)) for ids in ((0,1),(1,2),(0,2))]
    else:situations=[(0 if task=='constant' else 1,(0,1),0)]
    probabilities=[float(independent(model.parameters,state(c),action_matrix(ids),np.zeros(len(ids)))[0][ids.index(goal)]) for c,ids,goal in situations]
    (out/f'{task}-curve.json').write_text(json.dumps(curve,indent=2))
    (out/f'{task}-toy-coefficients.json').write_text(json.dumps({'synthetic_only':True,'actor_active_2x3':np.asarray(model.parameters.actor)[:2,:3].tolist(),'value_active_2':model.parameters.value[:2]}))
    assert min(probabilities)>threshold,(probabilities,threshold)
    return {'correct_action_probabilities':probabilities,'predeclared_threshold':threshold,'batches':80,'episodes':2560,
        'actor_norm':float(np.linalg.norm(model.parameters.actor)),'terminal_reward_only':True}

def opposite_returns():
    model=Checkpoint(Parameters.initial(),'0'*64)
    s=state();x=action_matrix((0,1));p,v=independent(model.parameters,s,x,np.zeros(2))
    st=Step(s,x,np.zeros(2),0,p,v)
    won=Episode('a','0'*64,1.,(st,),'training');lost=Episode('b','0'*64,-1.,(st,),'training')
    wa,_=update(model,[won],30,.1);wb,_=update(model,[lost],30,.1)
    assert np.array_equal(np.asarray(wa.actor),-np.asarray(wb.actor))
    pa=independent(wa,s,x,np.zeros(2))[0][0];pb=independent(wb,s,x,np.zeros(2))[0][0]
    assert pa>.5>pb
    return {'winning_player_same_action_probability':float(pa),'losing_player_same_action_probability':float(pb),'same_selected_action_opposite_gradients':True}

def clipping():
    model=Checkpoint(Parameters.initial(),'0'*64);s=state()*100;x=action_matrix((0,1))*100
    st=Step(s,x,np.zeros(2),0,np.array([.5,.5]),0.)
    ep=Episode('large','0'*64,1.,(st,),'training');ga,gv,_=gradients(model.parameters,[ep],'0'*64)
    params,_=update(model,[ep],30,.1)
    expected=-30*ga/max(1,np.linalg.norm(ga));expected*=min(1,6/np.linalg.norm(expected))
    assert np.allclose(params.actor,expected) and np.isclose(np.linalg.norm(params.actor),6)
    assert np.linalg.norm(params.value)<=3
    return {'actor_gradient_norm_before_clip':float(np.linalg.norm(ga)),'actor_norm_after_projection':float(np.linalg.norm(params.actor))}

def loader_and_cdf_findings():
    original=ROOT/'runs/reinforce-main/checkpoints/c0.json';data=json.loads(original.read_text())
    data['actor'][0][0]='0.1';path=out/'malformed-string-coefficient.json';path.write_text(json.dumps(data))
    accepted=False;error=None
    try:
        cp=load_checkpoint(path);accepted=True
        with (ROOT/'runs/reinforce-main/final/initial-r0-vs-v2/decisions.jsonl').open() as stream:obs=snapshot_from_dict(json.loads(next(stream))['observation'])
        try:distribution(obs,cp.parameters)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
    except Exception as exc:error='load: '+type(exc).__name__+': '+str(exc)
    cdf=np.array([.5,1.]);draw=.5
    return {'loader_accepts_string_numeric_coefficient':accepted,'subsequent_inference_error':error,
        'sampler_right_boundary_index':int(np.searchsorted(cdf,draw,side='right')),
        'comparison_report_left_boundary_index':int(np.searchsorted(cdf,draw)),
        'classification':'Defect reproductions, not repairs; historical artifacts use numeric values.'}

try:
    test('independent_finite_differences',finite_differences)
    for i,(task,threshold) in enumerate((('constant',.85),('context',.80),('variable',.80),('delayed',.80))):
        test(task,lambda task=task,i=i,threshold=threshold:learn(task,460902+i,threshold))
    test('opposite_player_outcomes',opposite_returns)
    test('gradient_clipping_parameter_projection',clipping)
    test('loader_and_cdf_defect_reproductions',loader_and_cdf_findings)
finally:persist()
