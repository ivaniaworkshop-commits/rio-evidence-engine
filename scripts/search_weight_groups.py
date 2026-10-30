"""Bounded weight-group ablation and seeded scaling search; no forced positive ROI."""
import hashlib,importlib.util,json,math,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.neural_lm import runtime,make_model
from rio_evidence.extraction_model import encode_example,Extractor
from rio_evidence.semantic_gate import grade
spec=importlib.util.spec_from_file_location('train_extraction',ROOT/'scripts/train_extraction.py')
trainer=importlib.util.module_from_spec(spec);spec.loader.exec_module(trainer)


def scaled_state(base,multipliers):
    if set(base)!=set(multipliers):raise ValueError('all weight groups must have multipliers')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=2 for v in multipliers.values()):
        raise ValueError('multipliers must be finite in 0..2')
    return {name:value*multipliers[name] for name,value in base.items()}


def draw_vectors(names,seed=7301,count=96):
    rng=random.Random(seed);faces=[.9,.95,1.,1.05,1.1]
    return [{name:rng.choice(faces) for name in names} for _ in range(count)]


def main():
    torch=runtime();torch.manual_seed(7301);start=time.perf_counter()
    checkpoint=ROOT/'model/extraction_gru.pt';base_hash=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    state=torch.load(checkpoint,weights_only=True)['state_dict'];names=list(state)
    rows=[json.loads(s) for s in (ROOT/'training/extraction_train.jsonl').read_text().splitlines()]
    # Selection is based only on a fixed train subset, never dev or public evaluation.
    positive=[r for r in rows if r['kind']=='supported'];negative=[r for r in rows if r['kind']=='unsupported']
    selected=positive[::max(1,len(positive)//12)][:12]+negative[::max(1,len(negative)//4)][:4]
    examples=[encode_example(r) for r in selected];model=make_model(torch)
    identity={name:1. for name in names};model.load_state_dict(state);baseline=trainer.loss_on(torch,model,examples)
    ablations=[]
    for name in names:
        multipliers=dict(identity);multipliers[name]=0.
        model.load_state_dict(scaled_state(state,multipliers));loss=trainer.loss_on(torch,model,examples)
        ablations.append({'group':name,'parameters':state[name].numel(),'ablated_train_loss':loss,'loss_increase':loss-baseline})
    vectors=draw_vectors(names)
    if vectors!=draw_vectors(names):raise ValueError('seeded vectors did not replay')
    trials=[];best_loss=baseline;best=dict(identity)
    for i,multipliers in enumerate(vectors):
        model.load_state_dict(scaled_state(state,multipliers));loss=trainer.loss_on(torch,model,examples)
        trials.append({'trial':i+1,'multipliers':multipliers,'train_subset_masked_loss':loss})
        if loss<best_loss:best_loss=loss;best=dict(multipliers)
    model.load_state_dict(scaled_state(state,best))
    candidate=ROOT/'model/weighted_extraction_gru.pt'
    torch.save({'state_dict':model.state_dict(),'architecture':'embedding16_gru32_byte256_v1','task':'WEIGHT_SCALING_EXPERIMENT_NOT_PROMOTED','eos_byte':0},candidate)
    loaded=Extractor(candidate);reload_loss=trainer.loss_on(torch,loaded.model,examples)
    if reload_loss!=best_loss:raise ValueError('programmed weight reload mismatch')
    dev=[json.loads(s) for s in (ROOT/'training/extraction_dev.jsonl').read_text().splitlines()];outputs=[]
    for row in dev:
        generation=loaded.generate(row['text']);outputs.append({'case_id':row['case_id'],'kind':row['kind'],
           'grade':grade(generation['text'],row['expected']),'generation':generation})
    supported=[r for r in outputs if r['kind']=='supported'];neg=[r for r in outputs if r['kind']=='unsupported']
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=base_hash:raise ValueError('base candidate changed')
    report={'scope':'WEIGHT_GROUP_SENSITIVITY_AND_TRAIN_LOSS_SEARCH_NOT_PROVEN_TASK_UTILITY','seed':7301,
      'groups':names,'faces':[.9,.95,1.,1.05,1.1],'trials':trials,'trial_count':len(trials),
      'train_selection_case_ids':[r['case_id'] for r in selected],'selection_uses_dev':False,
      'base_train_subset_loss':baseline,'best_train_subset_loss':best_loss,'chosen_multipliers':best,
      'ablation_ranking':sorted(ablations,key=lambda r:r['loss_increase'],reverse=True),
      'candidate_checkpoint_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),'base_checkpoint_sha256':base_hash,
      'fixed_seed_vector_replay_equal':True,'checkpoint_reload_loss_equal':reload_loss==best_loss,
      'dev_exact_graph_matches':sum(r['grade']['status']=='EXACT_GRAPH_MATCH' for r in supported),'dev_supported_cases':len(supported),
      'dev_correct_abstentions':sum(r['grade']['status']=='CORRECT_ABSTENTION' for r in neg),'dev_negative_cases':len(neg),
      'invalid_outputs':sum(r['grade']['status']=='INVALID_GRAPH_OUTPUT' for r in outputs),'dev_outputs':outputs,
      'elapsed_seconds':time.perf_counter()-start,'candidate_promoted':False,
      'limits':['Ablation measures sensitivity to zeroing whole groups, not per-neuron causal value or Shapley attribution.',
       'Train-subset loss selection can overfit; dev task scoring is reported afterward.',
       'Finite 96-trial search does not cover all weights or prove global optimality.',
       'Lower loss does not imply better answers, calibrated uncertainty or positive ROI.',
       'The code baseline already has 94/94 correct decisions in this scope; there is no accuracy headroom here.']}
    (ROOT/'model/WEIGHT_SEARCH_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['trial_count','base_train_subset_loss','best_train_subset_loss','chosen_multipliers','dev_exact_graph_matches','dev_supported_cases','dev_correct_abstentions','dev_negative_cases','invalid_outputs','elapsed_seconds']},indent=2))
    print(json.dumps(report['ablation_ranking'],indent=2))

if __name__=='__main__':main()
