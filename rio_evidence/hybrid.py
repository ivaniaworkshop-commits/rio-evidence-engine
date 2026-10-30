"""Exact schedule calculation with optional neural ranking of grounded templates."""
import argparse
import json
import math
from pathlib import Path
from .core import critical_path
from .json_io import load


def candidates(result):
    path=' -> '.join(result['path']) or '(empty graph)'
    critical=str(result['minutes']);serial=str(result['single_worker_minutes'])
    assumptions='This lower bound assumes enough workers, fixed durations and no coordination overhead.'
    return [
        f'The critical path is {path}, taking {critical} minutes. Total single-worker work is {serial} minutes. {assumptions}',
        f'With sufficient parallel workers, the critical-path duration is {critical} minutes via {path}. One worker needs {serial} minutes of total work. {assumptions}',
        f'Total single-worker work: {serial} minutes. Critical path: {path}. Critical-path duration: {critical} minutes. {assumptions}',
    ]


class NeuralRanker:
    """Average next-byte log likelihood; not a truth or quality confidence score."""
    def __init__(self, checkpoint):
        from .neural_lm import runtime,make_model
        self.torch=runtime();self.model=make_model(self.torch)
        self.model.load_state_dict(self.torch.load(checkpoint,weights_only=True)['state_dict'])
        self.model.eval()

    def __call__(self,texts):
        scores=[]
        with self.torch.no_grad():
            for text in texts:
                data=text.encode('utf-8');total=0.;tokens=0
                for start in range(0,len(data)-1,128):
                    segment=data[start:start+129]
                    x=self.torch.tensor([list(segment[:-1])],dtype=self.torch.long)
                    y=self.torch.tensor(list(segment[1:]),dtype=self.torch.long)
                    if len(y):
                        total+=self.torch.nn.functional.cross_entropy(self.model(x).reshape(-1,256),y,reduction='sum').item();tokens+=len(y)
                scores.append(-total/tokens)
        return scores


def solve(payload,ranker=None):
    if not isinstance(payload,dict):raise ValueError('input must be an object')
    result=critical_path(payload['tasks'],payload['durations'])
    texts=candidates(result);selected=0;scores=None;status='NOT_REQUESTED_DETERMINISTIC_TEMPLATE'
    if ranker is not None:
        try:
            scores=ranker(texts)
            if len(scores)!=len(texts) or any(type(x) not in (int,float) or not math.isfinite(x) for x in scores):
                raise ValueError('invalid ranker scores')
            selected=max(range(len(scores)),key=lambda i:(scores[i],-i));status='NEURAL_TEMPLATE_RANKING_OBSERVED'
        except Exception as error:
            scores=None;status='RANKER_FAILED_DETERMINISTIC_FALLBACK';selected=0
    return {'schedule':result,'explanation':texts[selected],'selection':{'status':status,
            'candidate_index':selected,'mean_byte_log_likelihoods':scores},
            'authority':'NUMBERS_AND_TEMPLATES_FROM_DETERMINISTIC_CODE_NOT_NEURAL_ARITHMETIC',
            'limits':'Neural ranking does not establish better prose, truth confidence or human mastery.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--neural',action='store_true');args=p.parse_args(argv)
    try:
        ranker=None;load_failure=False
        if args.neural:
            try:ranker=NeuralRanker(Path(__file__).resolve().parents[1]/'model/byte_gru.pt')
            except (ImportError,OSError,RuntimeError,ValueError,KeyError):load_failure=True
        result=solve(load(args.input),ranker)
        if load_failure:result['selection']['status']='MODEL_UNAVAILABLE_DETERMINISTIC_FALLBACK'
        print(json.dumps(result,allow_nan=False));return 0
    except (ValueError,TypeError,KeyError,OSError,OverflowError) as error:
        print(json.dumps({'error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
