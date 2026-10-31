"""Verified selectable checkpoints. Loading candidates is not merging or promotion."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHECKPOINTS={
 'base':('byte_gru.pt','TRAINING_RESULT.json','checkpoint_sha256',False),
 'extraction':('extraction_gru.pt','EXTRACTION_TRAINING_RESULT.json','candidate_checkpoint_sha256',True),
 'weighted_extraction':('weighted_extraction_gru.pt','WEIGHT_SEARCH_RESULT.json','candidate_checkpoint_sha256',True),
}

def metadata(name,root=ROOT):
    if name not in CHECKPOINTS:raise ValueError('UNKNOWN_CHECKPOINT')
    filename,reportname,key,experimental=CHECKPOINTS[name];root=Path(root)
    path=root/'model'/filename;report=json.loads((root/'model'/reportname).read_text())
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=report[key]:raise ValueError('CHECKPOINT_EVIDENCE_MISMATCH')
    return {'name':name,'path':str(path),'sha256':digest,'experimental':experimental,'source_report':'model/'+reportname}

def load_checkpoint(name='base',root=ROOT,allow_experimental=False):
    if name not in CHECKPOINTS:raise ValueError('UNKNOWN_CHECKPOINT')
    if CHECKPOINTS[name][3] and allow_experimental is not True:raise ValueError('EXPLICIT_EXPERIMENTAL_OPT_IN_REQUIRED')
    info=metadata(name,root)
    from .neural_lm import runtime,make_model
    torch=runtime();model=make_model(torch)
    payload=torch.load(info['path'],weights_only=True,map_location='cpu')
    state=payload['state_dict'];expected=model.state_dict()
    if set(state)!=set(expected):raise ValueError('INCOMPLETE_OR_UNKNOWN_WEIGHT_GROUPS')
    for key,value in state.items():
        if not isinstance(value,torch.Tensor) or value.shape!=expected[key].shape or value.dtype!=expected[key].dtype or not bool(torch.isfinite(value).all()):
            raise ValueError('INVALID_WEIGHT_TENSOR:'+key)
    model.load_state_dict(state,strict=True);model.eval()
    info.update({'groups_loaded':len(state),'parameters_loaded':sum(v.numel() for v in state.values()),
                 'mode':'SELECTABLE_CHECKPOINT_NOT_MERGED_OR_PROMOTED'})
    return model,info

def prewarm_all(root=ROOT,allow_experimental=False):
    if allow_experimental is not True:raise ValueError('EXPLICIT_EXPERIMENTAL_OPT_IN_REQUIRED')
    models={};records=[]
    for name in CHECKPOINTS:
        model,info=load_checkpoint(name,root,True);models[name]=model;records.append(info)
    return models,records

def probe(root=ROOT):
    from .neural_lm import runtime
    torch=runtime();models,records=prewarm_all(root,True)
    with torch.no_grad():
        prompt=torch.tensor([list(b'Case: parallel')],dtype=torch.long)
        for record in records:
            model=models[record['name']];first=model(prompt);second=model(prompt)
            if not bool(torch.isfinite(first).all()) or not torch.equal(first,second):raise ValueError('NONFINITE_OR_NONREPEATING_SMOKE_OUTPUT')
            record['finite_forward_pass']=True;record['same_process_forward_repeat_equal']=True
            record.pop('path')
    return {'schema':'RIO_WEIGHT_REGISTRY_V1','torch_version':torch.__version__,'checkpoints':records,
      'models_loaded':len(models),'parameter_values_loaded_across_versions':sum(r['parameters_loaded'] for r in records),
      'default_checkpoint':'base','weights_modified':False,'candidate_promoted':False,
      'limits':['Separate checkpoints are not one larger model or an ensemble.',
                'Finite repeatable inference does not establish semantic correctness.',
                'Experimental candidates retain their failed capability evaluations.',
                'This registry covers three repository checkpoints; unavailable weights are not invented.']}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkpoint',choices=CHECKPOINTS,default='base');p.add_argument('--prewarm-all',action='store_true');p.add_argument('--allow-experimental',action='store_true');args=p.parse_args(argv)
    if args.prewarm_all:
        if not args.allow_experimental:p.error('--prewarm-all requires --allow-experimental')
        print(json.dumps(probe(),indent=2));return 0
    _,info=load_checkpoint(args.checkpoint,allow_experimental=args.allow_experimental);print(json.dumps(info));return 0
if __name__=='__main__':raise SystemExit(main())
