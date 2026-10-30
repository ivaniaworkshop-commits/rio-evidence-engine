"""Closed-pattern graph extraction with complete line coverage and source spans."""
import argparse,json,re
from .duration_copy import extract_durations
from .semantic_gate import canonical
from .core import critical_path
from .json_io import load
IDS=r'[A-Z]'
DEPS=r'none|[A-Z](?: and [A-Z])*'
RULES=[
 ('task_sentences',rf'Task (?P<id>{IDS}) lasts (?P<n>[0-9]+) minutes\. Prerequisites: (?P<deps>{DEPS})\.'),
 ('bracket_records',rf'\[(?P<id>{IDS})\] duration=(?P<n>[0-9]+) minutes; requires=(?P<deps>{DEPS})\.'),
 ('before_starting',rf'Before starting (?P<id>{IDS}) \(duration (?P<n>[0-9]+) minutes\), finish (?P<deps>{DEPS})\.'),
 ('root_start',rf'(?P<id>{IDS}) runs for (?P<n>[0-9]+) minutes and may begin without waiting for another task\.'),
]


def extract_graph(text):
    duration=extract_durations(text);issues=list(duration['issues']);definitions={};evidence=[];offset=0
    for raw in text.splitlines(keepends=True):
        line=raw.rstrip('\r\n')
        if not line.strip():offset+=len(raw);continue
        matches=[(name,re.fullmatch(pattern,line)) for name,pattern in RULES]
        matches=[(name,m) for name,m in matches if m is not None]
        if len(matches)!=1:issues.append('UNRECOGNIZED_OR_AMBIGUOUS_LINE');offset+=len(raw);continue
        name,m=matches[0];key=m['id']
        deps_text=m.groupdict().get('deps','none')
        deps=[] if deps_text=='none' else deps_text.split(' and ')
        if key not in 'ABCD' or any(d not in 'ABCD' for d in deps):issues.append('UNSUPPORTED_TASK_ID')
        if key in definitions:issues.append('DUPLICATE_TASK_DECLARATION')
        definitions[key]=deps
        evidence.append({'task_id':key,'depends_on':deps,'pattern':name,'source_start':offset,
          'source_end':offset+len(line),'source_text':line,'offset_units':'PYTHON_UNICODE_CHARACTER_INDEX',
          'dependency_start':offset+m.start('deps') if 'deps' in m.groupdict() else None,
          'dependency_end':offset+m.end('deps') if 'deps' in m.groupdict() else None})
        offset+=len(raw)
    if set(definitions)!=set('ABCD'):issues.append('MISSING_OR_UNSUPPORTED_TASKS')
    graph=None;schedule=None
    if not issues:
        try:
            graph=canonical({'tasks':[{'id':key,'depends_on':definitions[key]} for key in 'ABCD'],'durations':duration['durations']})
            schedule=critical_path(graph['tasks'],graph['durations'])
        except (ValueError,TypeError,KeyError,OverflowError):issues.append('INVALID_DEPENDENCY_GRAPH');graph=None
    return {'status':'ABSTAIN' if issues else 'CLOSED_PATTERN_GRAPH_RECOVERED','graph':graph,'schedule':schedule,
       'issues':sorted(set(issues)),'duration_evidence':duration['evidence'],'dependency_evidence':evidence,
       'authority':'DETERMINISTIC_CODE_MATCHING_EXPLICIT_TEXT_NOT_NEURAL_COMPREHENSION',
       'scope':'FOUR_TASK_IDS_A_TO_D_INTEGER_MINUTES_RECOGNIZED_FULL_LINE_PATTERNS_ONLY',
       'uncertainty':'No probability assigned. Unrecognized or contradictory input is rejected; broader language coverage unverified.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',help='JSON object with text only');a=p.parse_args(argv)
    try:
        row=load(a.input)
        if not isinstance(row,dict) or set(row)!={'text'}:raise ValueError('expected text field only')
        print(json.dumps(extract_graph(row['text']),allow_nan=False));return 0
    except (ValueError,TypeError,OSError) as error:print(json.dumps({'error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
