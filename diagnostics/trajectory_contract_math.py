"""Tiny exact estimator examples; no BattleMind model, rollout, or optimizer."""
import numpy as np


def softmax(theta):
    z=np.exp(np.asarray(theta)-max(theta))
    return z/z.sum()


def finite_difference(function, theta, epsilon=1e-5):
    theta=np.asarray(theta,dtype=float)
    result=[]
    for j in range(len(theta)):
        offset=np.zeros_like(theta);offset[j]=epsilon
        result.append((function(theta+offset)-function(theta-offset))/(2*epsilon))
    return np.array(result)


def score_estimator(theta, rewards, keep=None, baseline=0):
    p=softmax(theta)
    keep=np.ones(len(p)) if keep is None else np.asarray(keep)
    return sum(p[a]*keep[a]*(rewards[a]-baseline)*(np.eye(len(p))[a]-p)
               for a in range(len(p)))/(p@keep)


def cases():
    theta=np.array([.3,-.2,.1]);p=softmax(theta)
    rewards=np.array([2.,-1.,.5])
    one=score_estimator(theta,rewards)
    one_fd=finite_difference(lambda t:softmax(t)@rewards,theta)
    # Latent a0 and a1 map to environment X; a2 maps to Y.
    mapped=np.array([2.,2.,-1.])
    many=score_estimator(theta,mapped)
    many_fd=finite_difference(lambda t:softmax(t)@mapped,theta)
    q=p[:2].sum()
    marginal_score_x=(sum(p[i]*(np.eye(3)[i]-p) for i in (0,1)))/q
    marginal=q*2*marginal_score_x + p[2]*(-1)*(np.eye(3)[2]-p)
    # Wrong representation: assign canonical X the log probability of a0 alone.
    wrong=q*2*(np.eye(3)[0]-p) + p[2]*(-1)*(np.eye(3)[2]-p)
    # Hidden pre-action state: 40% forced mapping to constant reward, 60% ordinary.
    forced=.4*score_estimator(theta,[.7,.7,.7])+.6*one
    forced_fd=finite_difference(lambda t:.4*.7+.6*(softmax(t)@rewards),theta)
    # A rejected input is an explicit transition here (not an assumed accepted move).
    rejected_rewards=np.array([1.,-.5,2.])
    rejected=score_estimator(theta,rejected_rewards)
    rejected_fd=finite_difference(lambda t:softmax(t)@rejected_rewards,theta)
    # If the transition of action 1 is missing, these incompatible worlds fit the
    # retained rewards of actions 0 and 2 equally well, but have different gradients.
    missing_worlds=[score_estimator(theta,[1.,r,2.]) for r in (-.5,1.5)]
    t2=np.array([0.,0.]);r2=np.array([2.,-1.]);keep=np.array([1.,0.])
    filtered=score_estimator(t2,r2,keep)
    full=score_estimator(t2,r2)
    conditional_fd=finite_difference(lambda t:(softmax(t)*keep)@r2/(softmax(t)@keep),t2)
    # Two independent Bernoulli actions share scalar theta. R=a0+2*a1.
    t=.4;prob=1/(1+np.exp(-t));prefix=total=0.
    for a0 in (0,1):
        for a1 in (0,1):
            mass=(prob if a0 else 1-prob)*(prob if a1 else 1-prob)
            reward=a0+2*a1
            prefix+=mass*reward*(a0-prob)
            total+=mass*reward*((a0-prob)+(a1-prob))
    prefix_fd=(3/(1+np.exp(-(t+1e-5)))-3/(1+np.exp(-(t-1e-5))))/2e-5
    return {'one_to_one':{'estimator':one.tolist(),'finite_difference':one_fd.tolist()},
        'many_to_one':{'sampled_id_estimator':many.tolist(),'marginal_estimator':marginal.tolist(),
                       'finite_difference':many_fd.tolist(),'wrong_canonical_estimator':wrong.tolist()},
        'state_dependent_forcing':{'estimator':forced.tolist(),'finite_difference':forced_fd.tolist(),
            'all_aliases_forced':score_estimator(theta,[1,1,1]).tolist(),
            'singleton':score_estimator([0],[1]).tolist()},
        'rejection':{'estimator':rejected.tolist(),'finite_difference':rejected_fd.tolist(),
                     'missing_evidence_worlds':[v.tolist() for v in missing_worlds]},
        'exclusion':{'full':full.tolist(),'filtered':filtered.tolist(),'conditional_objective_gradient':conditional_fd.tolist(),
                     'full_with_baseline':score_estimator(t2,r2,baseline=.7).tolist(),
                     'filtered_with_baseline':score_estimator(t2,r2,keep,baseline=.7).tolist()},
        'verified_prefix':{'prefix_only':float(prefix),'full':float(total),'finite_difference':float(prefix_fd),
                           'terminal_reward_known':True}}


if __name__=='__main__':
    import json
    import time
    from pathlib import Path
    start=time.monotonic()
    output=Path(__file__).resolve().parents[1]/'runs/trajectory-contract-audit-20260910/synthetic-arithmetic.json'
    with output.open('x') as stream:
        json.dump({'cases':cases(),'seconds':time.monotonic()-start,'games':0,'model_updates':0},stream,indent=2,allow_nan=False)
