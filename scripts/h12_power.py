"""H12 exact probabilities plus seeded Monte Carlo; NO observed model power."""
import json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.power_bounds import probability_at_least,minimum_n_for_power,design_effect

def run():
    rows=[]
    draws=20000
    for j,p in enumerate((0.05,0.10,0.15,0.20)):
        rng=random.Random(20261030+j)
        n80=minimum_n_for_power(p)
        trials=0
        for _ in range(draws):
            wins=sum(rng.random()<p for i in range(30))
            trials+=wins>=5
        exact=probability_at_least(30,p,5)
        mc=trials/draws
        if abs(mc-exact)>0.02:
            raise ValueError("SIMULATION_REPLAY_DISCORDANCE")
        rows.append({"assumed_single_case_win_probability":p,
          "exact_probability_of_at_least_five_wins_in_30":exact,
          "n_for_at_least_80pct_under_assumptions":n80,
          "monte_carlo_30_cases_20000_draws":mc})
    return {"status":"DETERMINISTIC_CONDITIONAL_DESIGN_NOT_EMPIRICAL_CAPABILITY",
       "models":"Independent Bernoulli candidate wins; ZERO candidate losses; no clustered observations",
       "null_five_wins_zero_losses_p":2**-5,
       "design_effect_example":design_effect(40,5,0.5),
       "seed_start":20261030,"monte_carlo_draws_per_scenario":draws,"rows":rows,
       "source":"MATHEMATICAL_ASSUMPTIONS_NOT_DATA","candidate_promoted":False}
if __name__=="__main__":print(json.dumps(run(),sort_keys=True,indent=2))
