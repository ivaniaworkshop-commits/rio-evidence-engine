"""Experimental closed-grammar decoder; grammar validity is not semantic correctness."""
import argparse,itertools,json
from pathlib import Path
from .extraction_model import Extractor,PROMPT_PREFIX,PROMPT_SUFFIX
from .streaming import validate_request
from .semantic_gate import canonical


class ConstrainedExtractor(Extractor):
    def generate(self,text,max_bytes=512,duration_values=None):
        if max_bytes!=512:raise ValueError('closed grammar uses a fixed 512-byte output budget')
        if duration_values is not None:
            if not isinstance(duration_values,dict) or set(duration_values)!=set('ABCD') or any(type(v) is not int or not 1<=v<=24 for v in duration_values.values()):
                raise ValueError('copied durations must contain A-D integer values in 1..24')
        prompt=PROMPT_PREFIX+text+PROMPT_SUFFIX
        encoded=validate_request(prompt,max_bytes)
        if b'\0' in encoded:raise ValueError('NUL reserved for EOS')
        torch=self.torch;hidden=None;out=bytearray();trace=[]
        with torch.no_grad():
            for start in range(0,len(encoded),128):
                states,hidden=self.model.gru(self.model.embedding(torch.tensor([list(encoded[start:start+128])],dtype=torch.long)),hidden)
                logits=self.model.output(states[:,-1])
            def advance(data,state,prediction):
                score=0.
                for value in data:
                    score+=float(torch.log_softmax(prediction[0],dim=-1)[value])
                    states,next_state=self.model.gru(self.model.embedding(torch.tensor([[value]],dtype=torch.long)),state)
                    state=next_state;prediction=self.model.output(states[:,-1])
                return score/len(data),state,prediction
            def emit(text):
                nonlocal hidden,logits
                data=text.encode();_,hidden,logits=advance(data,hidden,logits);out.extend(data)
            def choose(options,label):
                nonlocal hidden,logits
                if len(options)==1:emit(options[0]);return options[0]
                scored=[advance(option.encode(),hidden,logits) for option in options]
                index=max(range(len(options)),key=lambda i:(scored[i][0],-i))
                _,hidden,logits=scored[index];out.extend(options[index].encode())
                trace.append({'slot':label,'selected':options[index],'candidate_count':len(options),
                              'mean_byte_log_likelihood':scored[index][0]})
                return options[index]
            # First-byte branch avoids comparing different-length complete answers.
            branch='ABSTAIN' if float(logits[0,ord('A')])>float(logits[0,ord('{')]) else 'GRAPH'
            if branch=='ABSTAIN':emit('ABSTAIN')
            else:
                emit('{"durations":{')
                for i,key in enumerate('ABCD'):
                    emit(json.dumps(key)+':')
                    if duration_values is None:choose([str(n) for n in range(1,25)],'duration_'+key)
                    else:emit(str(duration_values[key]))
                    emit(',' if i<3 else '}')
                emit(',"tasks":[')
                for i,key in enumerate('ABCD'):
                    emit('{"depends_on":')
                    previous=list('ABCD'[:i]);subsets=[list(c) for n in range(len(previous)+1) for c in itertools.combinations(previous,n)]
                    choose([json.dumps(c,separators=(',',':')) for c in subsets],'dependencies_'+key)
                    emit(',"id":'+json.dumps(key)+'}');emit(',' if i<3 else ']}')
        if len(out)>512:raise ValueError('output budget exceeded')
        result=out.decode()
        if branch=='GRAPH':canonical(json.loads(result))
        return {'text':result,'grammar_completed':True,'generated_bytes':len(out),'prompt_bytes_processed':len(encoded),
                'branch':branch,'slot_choices':trace,'schema_authority':'CODE_CONSTRUCTED_CLOSED_GRAMMAR',
                'scope':'FOUR_TASKS_A_TO_D_DURATIONS_1_TO_24_FORWARD_EDGES_ONLY',
                'duration_authority':'MODEL_SLOT_SELECTION' if duration_values is None else 'CALLER_SUPPLIED_VALUES_NOT_LEARNED',
                'warning':'No inference of semantic correctness. Forced grammar is not learned syntax or successful extraction.'}


def main(argv=None):
    from .json_io import load
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',help='JSON containing only text');a=p.parse_args(argv)
    try:
        row=load(a.input)
        if not isinstance(row,dict) or set(row)!={'text'} or not isinstance(row['text'],str):raise ValueError('expected text field only')
        validate_request(PROMPT_PREFIX+row['text']+PROMPT_SUFFIX,512)
        output=ConstrainedExtractor(Path(__file__).resolve().parents[1]/'model/extraction_gru.pt').generate(row['text'])
        print(json.dumps({'candidate_only':True,'promotion':'BLOCKED','semantics':'UNVERIFIED','generation':output}));return 0
    except (ValueError,TypeError,OSError,RuntimeError,ImportError) as error:
        print(json.dumps({'error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
