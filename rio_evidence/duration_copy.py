"""Narrow explicit-duration recovery with character-offset evidence; not general NLP."""
import argparse,json,re
from pathlib import Path
from .json_io import load
PATTERNS=[
 ('task_lasts',r'\bTask (?P<id>[A-Z]) lasts (?P<n>[0-9]+) minutes(?:\.| and)'),
 ('bracket_duration',r'\[(?P<id>[A-Z])\] duration=(?P<n>[0-9]+) minutes;'),
 ('before_starting',r'Before starting (?P<id>[A-Z]) \(duration (?P<n>[0-9]+) minutes\),'),
 ('runs_for',r'\b(?P<id>[A-Z]) runs for (?P<n>[0-9]+) minutes and may begin'),
 ('declared_duration',r'\bTask (?P<id>[A-Z]) (?:also )?has duration (?P<n>[0-9]+) minutes\.'),
]


def extract_durations(text):
    if not isinstance(text,str):raise ValueError('text must be a string')
    if len(text.encode('utf-8'))>4096:raise ValueError('duration text exceeds 4096 UTF-8 bytes')
    evidence=[];found={};issues=[]
    for family,pattern in PATTERNS:
        for match in re.finditer(pattern,text):
            key=match['id'];raw=match['n']
            if key not in 'ABCD':issues.append('UNSUPPORTED_TASK_ID');continue
            if len(raw)>8:issues.append('UNSUPPORTED_DURATION_RANGE');continue
            number=int(raw)
            if number>1000000:issues.append('UNSUPPORTED_DURATION_RANGE');continue
            found.setdefault(key,set()).add(number)
            evidence.append({'task_id':key,'duration_minutes':number,'number_text':raw,
             'number_start':match.start('n'),'number_end':match.end('n'),
             'source_start':match.start(),'source_end':match.end(),'source_text':match.group(),
             'offset_units':'PYTHON_UNICODE_CHARACTER_INDEX','pattern':family})
    if any(len(v)>1 for v in found.values()):issues.append('CONFLICTING_DURATIONS')
    missing=[k for k in 'ABCD' if k not in found]
    if missing:issues.append('MISSING_DURATIONS')
    # Durations are never silently inferred; partial observations are evidence only.
    durations={k:next(iter(found[k])) for k in 'ABCD' if k in found and len(found[k])==1}
    return {'status':'ABSTAIN' if issues else 'EXPLICIT_DURATIONS_RECOVERED',
            'durations':durations,'issues':sorted(set(issues)),'missing_task_ids':missing,
            'evidence':sorted(evidence,key=lambda e:(e['source_start'],e['source_end'])),
            'scope':'CLOSED_IDS_A_TO_D_EXPLICIT_INTEGER_MINUTES_RECOGNIZED_PATTERNS_ONLY',
            'limits':'Does not extract or verify dependencies. Matching durations is not complete task understanding.'}


def grounded_generate(text,decoder):
    copied=extract_durations(text)
    if copied['status']=='ABSTAIN':
        return {'text':'ABSTAIN','status':'CODE_DURATION_GATE_ABSTENTION','duration_evidence':copied,'neural_inference':False}
    if any(not 1<=v<=24 for v in copied['durations'].values()):
        return {'text':'ABSTAIN','status':'CODE_DECODER_RANGE_ABSTENTION','duration_evidence':copied,'neural_inference':False}
    output=decoder.generate(text,duration_values=copied['durations'])
    return {'text':output['text'],'status':'DURATIONS_FROM_CODE_DEPENDENCIES_UNVERIFIED',
            'duration_evidence':copied,'neural_inference':True,'generation':output,
            'warning':'Neither copied values nor grammar authorize execution or prove dependencies match the text.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',help='JSON object with text only');a=p.parse_args(argv)
    try:
        row=load(a.input)
        if not isinstance(row,dict) or set(row)!={'text'}:raise ValueError('expected text field only')
        print(json.dumps(extract_durations(row['text'])));return 0
    except (ValueError,TypeError,OSError) as error:print(json.dumps({'error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
