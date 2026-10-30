"""Experimental task-specific byte GRU. Candidate weights are never auto-promoted."""
import argparse,json
from pathlib import Path
from .neural_lm import runtime,make_model
from .streaming import validate_request
PROMPT_PREFIX='Extract task graph JSON or ABSTAIN.\n'
PROMPT_SUFFIX='\nAnswer: '
EOS=0


def encode_example(row):
    prompt=(PROMPT_PREFIX+row['text']+PROMPT_SUFFIX).encode('utf-8')
    target=row['target'].encode('utf-8')+bytes([EOS])
    if bytes([EOS]) in prompt or bytes([EOS]) in target[:-1]:raise ValueError('NUL reserved for EOS')
    if len(prompt)>4096 or len(target)>512:raise ValueError('example exceeds task budgets')
    sequence=prompt+target
    return list(sequence[:-1]),[-100]*(len(prompt)-1)+list(target)


def batch(torch,examples):
    length=max(len(x) for x,y in examples)
    x=torch.zeros((len(examples),length),dtype=torch.long)
    y=torch.full((len(examples),length),-100,dtype=torch.long)
    for i,(xs,ys) in enumerate(examples):
        x[i,:len(xs)]=torch.tensor(xs);y[i,:len(ys)]=torch.tensor(ys)
    return x,y


class Extractor:
    def __init__(self,checkpoint):
        self.torch=runtime();self.model=make_model(self.torch)
        state=self.torch.load(checkpoint,weights_only=True)
        self.model.load_state_dict(state['state_dict']);self.model.eval()
    def generate(self,text,max_bytes=512):
        prompt=PROMPT_PREFIX+text+PROMPT_SUFFIX
        encoded=validate_request(prompt,max_bytes)
        if bytes([EOS]) in encoded:raise ValueError('NUL reserved for EOS')
        torch=self.torch;hidden=None;out=[];stopped=False
        with torch.no_grad():
            for start in range(0,len(encoded),128):
                x=torch.tensor([list(encoded[start:start+128])],dtype=torch.long)
                states,hidden=self.model.gru(self.model.embedding(x),hidden)
                logits=self.model.output(states[:,-1])
            for i in range(max_bytes):
                token=int(logits[0].argmax())
                if token==EOS:stopped=True;break
                out.append(token)
                if i+1<max_bytes:
                    states,hidden=self.model.gru(self.model.embedding(torch.tensor([[token]],dtype=torch.long)),hidden)
                    logits=self.model.output(states[:,-1])
        return {'text':bytes(out).decode('utf-8',errors='replace'),'eos_observed':stopped,
                'generated_bytes':len(out),'prompt_bytes_processed':len(encoded)}


def main(argv=None):
    from .json_io import load
    from .semantic_gate import canonical
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',help='JSON object with text field');a=p.parse_args(argv)
    try:
        payload=load(a.input)
        if not isinstance(payload,dict) or set(payload)!={'text'} or not isinstance(payload['text'],str):raise ValueError('expected text field only')
        validate_request(PROMPT_PREFIX+payload['text']+PROMPT_SUFFIX,512)
        root=Path(__file__).resolve().parents[1]
        output=Extractor(root/'model/extraction_gru.pt').generate(payload['text'])
        if output['text'].strip()=='ABSTAIN':accepted=None;status='MODEL_ABSTAINED_NOT_SEMANTICALLY_VERIFIED'
        else:
            from .json_io import loads
            try:accepted=canonical(loads(output['text']));status='STRUCTURALLY_VALID_SEMANTICS_UNVERIFIED'
            except (ValueError,TypeError,KeyError,OverflowError):accepted=None;status='INVALID_OUTPUT_REJECTED'
        print(json.dumps({'candidate_only':True,'status':status,'graph':accepted,'raw_generation':output,
              'warning':'Schema validation does not prove the graph matches the input. No task execution authorized.'}));return 0
    except (ValueError,TypeError,OSError,RuntimeError,ImportError) as error:
        print(json.dumps({'error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
