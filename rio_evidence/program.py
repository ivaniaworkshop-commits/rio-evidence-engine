"""One bounded program for verified parsers and separately selectable checkpoints."""
import argparse,json
from pathlib import Path
from .candidate_v1 import extract_candidate_v1
from .spanish_graph import extract_spanish_graph
from .weight_registry import CHECKPOINTS,load_checkpoint,metadata
from .extraction_model import Extractor,PROMPT_PREFIX,PROMPT_SUFFIX
from .streaming import validate_request
from .json_io import load
ROOT=Path(__file__).resolve().parents[1]

class LoadedExtractor(Extractor):
    def __init__(self,model):
        from .neural_lm import runtime
        self.torch=runtime();self.model=model

class ReconciledProgram:
    def __init__(self,root=ROOT,allow_experimental=False):
        self.root=Path(root);self.allow_experimental=allow_experimental is True
        self.models={};self.records={}
    def _authorize(self,names):
        if not isinstance(names,(list,tuple)) or len(names)!=len(set(names)):raise ValueError('UNIQUE_CHECKPOINT_LIST_REQUIRED')
        if any(n not in CHECKPOINTS for n in names):raise ValueError('UNKNOWN_CHECKPOINT')
        if any(CHECKPOINTS[n][3] for n in names) and not self.allow_experimental:raise ValueError('EXPLICIT_EXPERIMENTAL_OPT_IN_REQUIRED')
    def prewarm(self,names):
        self._authorize(names);models={};records={}
        for name in names:
            info=metadata(name,self.root)
            if name in self.models:
                if info['sha256']!=self.records[name]['sha256']:raise ValueError('LOADED_CHECKPOINT_CHANGED_RESTART_REQUIRED')
                models[name]=self.models[name];records[name]=self.records[name]
            else:models[name],records[name]=load_checkpoint(name,self.root,self.allow_experimental)
        self.models.update(models);self.records.update(records)
        return [dict(self.records[n]) for n in names]
    def run(self,text,route='incumbent',checkpoints=(),max_bytes=32,expected_task_count=None):
        if route not in ('incumbent','spanish'):raise ValueError('UNKNOWN_ROUTE')
        self._authorize(checkpoints)
        if expected_task_count is not None and (type(expected_task_count) is not int or not 1<=expected_task_count<=8):raise ValueError('INVALID_EXPECTED_TASK_COUNT')
        if checkpoints:validate_request(PROMPT_PREFIX+text+PROMPT_SUFFIX,max_bytes)
        decision=(extract_candidate_v1 if route=='incumbent' else extract_spanish_graph)(text)
        if expected_task_count is not None:
            decision=dict(decision,declared_expected_count=expected_task_count,count_authority='UNAUTHENTICATED_CALLER_DECLARATION')
            if decision['graph'] is not None and len(decision['graph']['tasks'])!=expected_task_count:
                decision.update(status='ABSTAIN',graph=None,schedule=None,issues=['DECLARED_TASK_COUNT_MISMATCH'])
        self.prewarm(checkpoints)
        observations=[]
        for name in checkpoints:
            generation=LoadedExtractor(self.models[name]).generate(text,max_bytes)
            observations.append({'checkpoint':name,'checkpoint_sha256':self.records[name]['sha256'],
                'generation':generation,'authority':'EXPERIMENTAL_TEXT_NOT_ACCEPTED_AS_GRAPH_OR_ACTION'})
        return {'schema':'RIO_RECONCILED_PROGRAM_V1','route':route,'decision':decision,
          'neural_observations':observations,'loaded_checkpoints':list(self.models),
          'reconciliation':'DETERMINISTIC_GRAPH_AND_COUNT_GUARD_AUTHORITATIVE_NEURAL_OUTPUTS_RETAINED_SEPARATELY',
          'weights_merged':False,'candidate_promoted':False,'default_changed':False}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--route',choices=['incumbent','spanish'],default='incumbent')
    p.add_argument('--checkpoints',nargs='+',choices=list(CHECKPOINTS),default=[]);p.add_argument('--all-checkpoints',action='store_true')
    p.add_argument('--allow-experimental',action='store_true');p.add_argument('--max-bytes',type=int,default=32);args=p.parse_args(argv)
    try:
        row=load(args.input)
        if not isinstance(row,dict) or set(row)-{'text','expected_task_count'} or 'text' not in row or not isinstance(row['text'],str):raise ValueError('EXPECTED_TEXT_AND_OPTIONAL_TASK_COUNT')
        if args.all_checkpoints and args.checkpoints:raise ValueError('SELECT_ALL_OR_NAMED_CHECKPOINTS')
        names=list(CHECKPOINTS) if args.all_checkpoints else args.checkpoints
        result=ReconciledProgram(allow_experimental=args.allow_experimental).run(row['text'],args.route,names,args.max_bytes,row.get('expected_task_count'))
        print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,TypeError,OSError,KeyError) as error:
        print(json.dumps({'status':'HOLD','error':str(error)}));return 2
if __name__=='__main__':raise SystemExit(main())
