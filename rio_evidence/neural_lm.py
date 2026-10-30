"""Optional small byte-level neural language model, not a large language model."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import time


def runtime():
    import torch
    torch.set_num_threads(2)
    return torch


def make_model(torch):
    class ByteGRU(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding=torch.nn.Embedding(256,16)
            self.gru=torch.nn.GRU(16,32,batch_first=True)
            self.output=torch.nn.Linear(32,256)
        def forward(self,x):
            embedded=self.embedding(x)
            hidden,_=self.gru(embedded)
            return self.output(hidden)
    return ByteGRU()


def corpus(path):
    groups={'practice':[], 'holdout':[]}
    for line in Path(path).read_text().splitlines():
        case=json.loads(line)
        a=case['reference']
        text='Case: '+case['topology']+' '+json.dumps(case['durations'],sort_keys=True)+'\nAnswer: '+a['explanation']+'\n\n'
        groups[case['split']].append(text)
    return {k:''.join(v).encode('utf-8') for k,v in groups.items()}


def evaluate(torch,model,data):
    model.eval();total=0.;tokens=0
    with torch.no_grad():
        for start in range(0,len(data)-1,128):
            segment=data[start:start+129]
            x=torch.tensor([list(segment[:-1])],dtype=torch.long)
            y=torch.tensor(list(segment[1:]),dtype=torch.long)
            if not len(y):continue
            loss=torch.nn.functional.cross_entropy(model(x).reshape(-1,256),y,reduction='sum')
            total+=loss.item();tokens+=len(y)
    return total/tokens


def train(root,steps=250):
    if type(steps) is not int or not 1<=steps<=10000:
        raise ValueError('steps must be 1..10000')
    torch=runtime();torch.manual_seed(731);random.seed(731)
    model=make_model(torch);data=corpus(root/'training/answer_matrix.jsonl')
    before=evaluate(torch,model,data['holdout'])
    optimizer=torch.optim.AdamW(model.parameters(),lr=.005)
    rng=random.Random(731);history=[];start=time.perf_counter()
    model.train()
    for step in range(steps):
        starts=[rng.randrange(len(data['practice'])-129) for _ in range(16)]
        chunks=[list(data['practice'][s:s+129]) for s in starts]
        batch=torch.tensor(chunks,dtype=torch.long)
        logits=model(batch[:,:-1]);loss=torch.nn.functional.cross_entropy(logits.reshape(-1,256),batch[:,1:].reshape(-1))
        optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        if step%50==0 or step==steps-1:history.append({'step':step+1,'training_batch_loss':loss.item()})
    after=evaluate(torch,model,data['holdout'])
    checkpoint=root/'model/byte_gru.pt'
    torch.save({'state_dict':model.state_dict(),'architecture':'embedding16_gru32_byte256_v1'},checkpoint)
    restored=make_model(torch);restored.load_state_dict(torch.load(checkpoint,weights_only=True)['state_dict']);restored.eval()
    repeat=evaluate(torch,restored,data['holdout'])
    if after!=repeat:raise ValueError('checkpoint readback changed evaluation')
    sample=generate(root,'Case: parallel',120)
    report={'status':'SMALL_NEURAL_LM_TRAINED_AND_RELOADED_NOT_LLM','torch_version':torch.__version__,
      'architecture':'byte embedding16 -> GRU32 -> 256 logits','parameters':sum(p.numel() for p in model.parameters()),
      'seed':731,'steps':steps,'training_bytes':len(data['practice']),'evaluation_bytes':len(data['holdout']),
      'uniform_byte_loss':math.log(256),'initial_holdout_loss':before,'final_holdout_loss':after,
      'initial_holdout_perplexity':math.exp(before),'final_holdout_perplexity':math.exp(after),
      'checkpoint_reload_loss_equal':after==repeat,'elapsed_seconds':time.perf_counter()-start,
      'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
      'corpus_sha256':hashlib.sha256((root/'training/answer_matrix.jsonl').read_bytes()).hexdigest(),
      'training_history':history,'generated_sample':sample,
      'limits':['Public synthetic holdout shares templates with training; not unseen task generalization.',
      'Next-byte loss does not establish scheduling correctness or human mastery.',
      'Small GRU is not a transformer or large language model.','Generated text is untrusted; deterministic engine remains authoritative.',
      'Exact training reproducibility across machines or library versions is not established.']}
    (root/'model/TRAINING_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def generate(root,prompt,max_bytes=120):
    if not isinstance(max_bytes,int) or not 1<=max_bytes<=512:raise ValueError('max_bytes must be 1..512')
    torch=runtime();model=make_model(torch)
    state=torch.load(root/'model/byte_gru.pt',weights_only=True)
    model.load_state_dict(state['state_dict']);model.eval()
    values=list(prompt.encode('utf-8'))[-128:] or [10];out=[]
    with torch.no_grad():
        for _ in range(max_bytes):
            logits=model(torch.tensor([values[-128:]],dtype=torch.long))
            token=int(logits[0,-1].argmax());values.append(token);out.append(token)
    return bytes(out).decode('utf-8',errors='replace')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['train','generate']);p.add_argument('--prompt',default='Case: parallel');p.add_argument('--steps',type=int,default=250);p.add_argument('--max-bytes',type=int,default=120)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    print(json.dumps(train(root,a.steps) if a.mode=='train' else {'generated_untrusted_text':generate(root,a.prompt,a.max_bytes)},indent=2))

if __name__=='__main__':main()
