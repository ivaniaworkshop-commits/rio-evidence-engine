"""Exact conditional binomial design, with explicitly OPTIMISTIC no-loss assumptions."""
import math

def probability_at_least(n,win_probability,minimum_wins=5):
    if type(n) is not int or not 0<=n<=500:
        raise ValueError("INVALID_N")
    if type(minimum_wins) is not int or not 0<=minimum_wins<=n:
        raise ValueError("INVALID_THRESHOLD")
    if type(win_probability) not in (float,int) or not math.isfinite(win_probability) or not 0<=win_probability<=1:
        raise ValueError("INVALID_P")
    p=win_probability
    return math.fsum(math.comb(n,k)*p**k*(1-p)**(n-k) for k in range(minimum_wins,n+1))

def minimum_n_for_power(p,target=0.8,minimum_wins=5,cap=500):
    if type(target) not in (float,int) or not 0<target<=1:
        raise ValueError("INVALID_TARGET")
    for n in range(minimum_wins,cap+1):
        if probability_at_least(n,p,minimum_wins)>=target:
            return n
    return None

def design_effect(n,cluster_size,rho):
    if type(n) is not int or type(cluster_size) is not int or n<=0 or cluster_size<=0 or n%cluster_size:
        raise ValueError("INVALID_CLUSTER_SIZE")
    if type(rho) not in (int,float) or not math.isfinite(rho) or not 0<=rho<=1:
        raise ValueError("INVALID_CORRELATION")
    multiplier=1+(cluster_size-1)*rho
    return {"design_effect":multiplier,"effective_n_heuristic":n/multiplier,
            "scope":"HEURISTIC_EQUAL_SIZE_EXCHANGEABLE_CORRELATION_NOT_OBSERVED"}
