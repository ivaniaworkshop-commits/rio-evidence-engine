"""Response-only SFT experiment, separate checkpoint, no evaluation-fixture access."""
from pathlib import Path
import hashlib,json,random,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.extraction_model import encode_example,batch,Extractor
from rio_evidence.neural_lm import runtime,make_model
from rio_evidence.semantic_gate import grade,rule_baseline


def loss_on(torch,model,examples):
    model.eval();total=0.;count=0
    with torch.no_grad():
        for start in range(0,len(examples),16):
            x,y=batch(torch,examples[start:start+16]);logits=model(x)
            total+=torch.nn.functional.cross_entropy(logits.reshape(-1,256),y.reshape(-1),ignore_index=-100,reduction='sum').item()
            count+=int((y!=-100).sum())
    return total/count


def main(steps=500):
    if type(steps) is not int or not 1<=steps<=2000:raise ValueError('steps must be 1..2000')
    torch=runtime();torch.manual_seed(129);rng=random.Random(129)
    original=ROOT/'model/byte_gru.pt';original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    data={s:[json.loads(line) for line in (ROOT/f'training/extraction_{s}.jsonl').read_text().splitlines()] for s in ['train','dev']}
    encoded={s:[encode_example(row) for row in rows] for s,rows in data.items()}
    model=make_model(torch);model.load_state_dict(torch.load(original,weights_only=True)['state_dict'])
    before=loss_on(torch,model,encoded['dev']);optimizer=torch.optim.AdamW(model.parameters(),lr=.003)
    history=[];begin=time.perf_counter();model.train()
    for step in range(steps):
        selected=[rng.choice(encoded['train']) for _ in range(12)]
        x,y=batch(torch,selected);loss=torch.nn.functional.cross_entropy(model(x).reshape(-1,256),y.reshape(-1),ignore_index=-100)
        optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        if step%100==0 or step+1==steps:history.append({'step':step+1,'masked_training_batch_loss':loss.item()})
    after=loss_on(torch,model,encoded['dev'])
    checkpoint=ROOT/'model/extraction_gru.pt';torch.save({'state_dict':model.state_dict(),'architecture':'embedding16_gru32_byte256_v1','task':'EXPERIMENTAL_GRAPH_EXTRACTION_SFT','eos_byte':0},checkpoint)
    extractor=Extractor(checkpoint);reloaded=loss_on(torch,extractor.model,encoded['dev'])
    if after!=reloaded:raise ValueError('reload loss mismatch')
    rows=[]
    for c in data['dev']:
        output=extractor.generate(c['text']);baseline=rule_baseline(c['text'])
        rows.append({'case_id':c['case_id'],'kind':c['kind'],'grade':grade(output['text'],c['expected']),
            'rule_grade':grade(baseline,c['expected']),'generation':output})
    supported=[r for r in rows if r['kind']=='supported'];negative=[r for r in rows if r['kind']=='unsupported']
    if hashlib.sha256(original.read_bytes()).hexdigest()!=original_hash:raise ValueError('original checkpoint changed')
    report={'status':'EXTRACTION_SFT_CANDIDATE_NOT_PROMOTED','seed':129,'steps':steps,'parameters':sum(p.numel() for p in model.parameters()),
     'torch_version':torch.__version__,'prompt_loss_masked':True,'eos_byte':0,'initial_dev_masked_loss':before,'final_dev_masked_loss':after,
     'checkpoint_reload_loss_equal':after==reloaded,'training_rows':len(data['train']),'dev_rows':len(data['dev']),
     'base_checkpoint_sha256':original_hash,'candidate_checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
     'train_data_sha256':hashlib.sha256((ROOT/'training/extraction_train.jsonl').read_bytes()).hexdigest(),
     'dev_data_sha256':hashlib.sha256((ROOT/'training/extraction_dev.jsonl').read_bytes()).hexdigest(),
     'elapsed_seconds':time.perf_counter()-begin,'history':history,
     'dev_exact_graph_matches':sum(r['grade']['status']=='EXACT_GRAPH_MATCH' for r in supported),'dev_supported_cases':len(supported),
     'dev_correct_abstentions':sum(r['grade']['status']=='CORRECT_ABSTENTION' for r in negative),'dev_negative_cases':len(negative),
     'invalid_outputs':sum(r['grade']['status']=='INVALID_GRAPH_OUTPUT' for r in rows),
     'rule_exact_graph_matches':sum(r['rule_grade']['status']=='EXACT_GRAPH_MATCH' for r in supported),
     'rule_correct_abstentions':sum(r['rule_grade']['status']=='CORRECT_ABSTENTION' for r in negative),'dev_outputs':rows,
     'limits':['Synthetic authored data; no claim of natural-language or human generalization.',
       'Dev used for reporting only, no optimizer updates or best-checkpoint selection.',
       'Public 28-case evaluation fixture not read by this training/evaluation script.',
       'No automatic model promotion. Lower loss does not prove extraction correctness.']}
    (ROOT/'model/EXTRACTION_TRAINING_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','steps','initial_dev_masked_loss','final_dev_masked_loss','dev_exact_graph_matches','dev_supported_cases','dev_correct_abstentions','dev_negative_cases','invalid_outputs','elapsed_seconds']},indent=2))

if __name__=='__main__':main()
