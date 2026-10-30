"""Evaluation contracts for English-to-task-graph extraction; not a general parser."""
import re
from .core import critical_path
from .json_io import loads


def canonical(payload):
    if not isinstance(payload,dict) or set(payload)!={'tasks','durations'}:
        raise ValueError('expected tasks and durations only')
    critical_path(payload['tasks'],payload['durations'])
    tasks=[]
    for t in payload['tasks']:
        if set(t)-{'id','depends_on'}:raise ValueError('unknown task fields')
        tasks.append({'id':t['id'],'depends_on':sorted(t.get('depends_on',[]))})
    return {'tasks':sorted(tasks,key=lambda t:t['id']), 'durations':payload['durations']}


def rule_baseline(text):
    """Deliberately limited, full-match rule for one authored wording family."""
    pattern=r'([A-D]) takes (\d+) minutes and depends on (none|[A-D](?: and [A-D])*)\.'
    parts=text.split('\n');tasks=[];durations={}
    for part in parts:
        match=re.fullmatch(pattern,part)
        if match is None:return None
        key,n,deps=match.groups()
        if key in durations:return None
        durations[key]=int(n);tasks.append({'id':key,'depends_on':[] if deps=='none' else deps.split(' and ')})
    try:return canonical({'tasks':tasks,'durations':durations})
    except (ValueError,TypeError,KeyError):return None


def grade(raw,expected):
    if raw is None or (isinstance(raw,str) and raw.strip()=='ABSTAIN'):
        return {'status':'CORRECT_ABSTENTION' if expected is None else 'ABSTAINED_ON_SUPPORTED_INPUT','pass':expected is None}
    try:
        observed=canonical(loads(raw) if isinstance(raw,str) else raw)
    except (ValueError,TypeError,KeyError,OverflowError):
        return {'status':'INVALID_GRAPH_OUTPUT','pass':False}
    if expected is None:return {'status':'UNSUPPORTED_INFERENCE','pass':False}
    exact=observed==canonical(expected)
    return {'status':'EXACT_GRAPH_MATCH' if exact else 'WRONG_GRAPH','pass':exact}
