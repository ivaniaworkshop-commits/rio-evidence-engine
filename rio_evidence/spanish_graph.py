"""Opt-in additive closed Spanish grammar; frozen H14 remains unchanged."""
import argparse,json,re
from .candidate_v1 import extract_candidate_v1
from .core import critical_path
from .semantic_gate import canonical
from .json_io import load
PATTERN=re.compile(r'(?P<id>[A-D]) dura (?P<n>0|[1-9][0-9]{0,6}) minutos (?:(?P<root>sin requisitos)|después de (?P<after>[A-D](?: y [A-D])*)|y espera a (?P<wait>[A-D](?: y [A-D])*))\.')

def extract_spanish_graph(text):
    incumbent=extract_candidate_v1(text) # Enforces type/UTF-8 bound and preserves existing behavior.
    if incumbent['graph'] is not None:return dict(incumbent,language_route='INCUMBENT_PRESERVED')
    definitions={};durations={};evidence=[];issues=[];cursor=0
    while cursor<len(text):
        whitespace=re.match(r'\s*',text[cursor:]);cursor+=whitespace.end()
        if cursor==len(text):break
        match=PATTERN.match(text,cursor)
        if match is None:
            issues.append('UNRECOGNIZED_SOURCE_TEXT');break
        key=match['id'];number=int(match['n']);deps_text=match['after'] or match['wait']
        deps=deps_text.split(' y ') if deps_text else []
        if key in definitions:issues.append('DUPLICATE_TASK_DECLARATION')
        if len(set(deps))!=len(deps):issues.append('DUPLICATE_DEPENDENCY')
        if number>1000000:issues.append('DURATION_OUT_OF_RANGE')
        definitions[key]=deps;durations[key]=number
        field='after' if match['after'] else ('wait' if match['wait'] else 'root')
        evidence.append({'task_id':key,'source_start':cursor,'source_end':match.end(),'source_text':match.group(),
             'duration_start':match.start('n'),'duration_end':match.end('n'),
             'dependency_start':match.start(field),'dependency_end':match.end(field),
             'offset_units':'PYTHON_UNICODE_CHARACTER_INDEX'})
        cursor=match.end()
    if set(definitions)!=set('ABCD'):issues.append('REQUIRES_EXACTLY_FOUR_TASKS_A_TO_D')
    graph=schedule=None
    if not issues:
        try:
            graph=canonical({'tasks':[{'id':k,'depends_on':definitions[k]} for k in 'ABCD'],'durations':durations})
            schedule=critical_path(graph['tasks'],graph['durations'])
        except (ValueError,TypeError,KeyError,OverflowError):
            issues.append('INVALID_DEPENDENCY_GRAPH');graph=schedule=None
    return {'status':'ABSTAIN' if issues else 'EXPLICIT_GRAPH_RECOVERED','graph':graph,'schedule':schedule,
        'issues':sorted(set(issues)),'evidence':evidence,'neural_calls':0,
        'authority':'DETERMINISTIC_CLOSED_SPANISH_GRAMMAR_NOT_NEURAL_COMPREHENSION',
        'scope':'FOUR_TASKS_A_TO_D_EXPLICIT_INTEGER_MINUTES_0_TO_1M_FULL_TEXT_COVERAGE',
        'language_route':'SPANISH_EXPLICIT_V1'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');args=p.parse_args(argv)
    try:
        obj=load(args.input)
        if not isinstance(obj,dict) or set(obj)!={'text'}:raise ValueError('EXPECTED_TEXT_FIELD_ONLY')
        print(json.dumps(extract_spanish_graph(obj['text']),ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,TypeError,OSError) as error:
        print(json.dumps({'error':str(error)}));return 2
if __name__=='__main__':raise SystemExit(main())
