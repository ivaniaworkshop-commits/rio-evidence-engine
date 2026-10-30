"""Create authored extraction training/dev data, structurally separated from public evaluation."""
import hashlib,itertools,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.semantic_gate import canonical


def graph_signature(payload):
    tasks=payload['tasks'];ids=sorted(t['id'] for t in tasks)
    edges={(dep,t['id']) for t in tasks for dep in t.get('depends_on',[])}
    forms=[]
    for perm in itertools.permutations(range(len(ids))):
        labels=dict(zip(ids,perm))
        forms.append(tuple(sorted((labels[a],labels[b]) for a,b in edges)))
    return json.dumps([len(ids),min(forms)],separators=(',',':'))


def normalized(text):return ' '.join(text.casefold().split())


def build(root=ROOT):
    fixture=(root/'evaluation/semantic_fixture.jsonl').read_bytes()
    evaluated=[json.loads(line) for line in fixture.decode().splitlines()]
    excluded={graph_signature(c['expected']) for c in evaluated if c['expected'] is not None}
    possible=[(a,b) for i,a in enumerate('ABCD') for b in 'ABCD'[i+1:]]
    candidates=[]
    for mask in range(1<<len(possible)):
        edges=[edge for i,edge in enumerate(possible) if mask&(1<<i)]
        payload={'tasks':[{'id':key,'depends_on':[a for a,b in edges if b==key]} for key in 'ABCD'],
                 'durations':{key:1 for key in 'ABCD'}}
        sig=graph_signature(payload)
        if sig not in excluded:candidates.append((mask,payload,sig))
    signatures=sorted({sig for _,_,sig in candidates})
    dev_signatures=set(signatures[::5])
    rng=random.Random(1947);rows=[]
    for mask,base,sig in candidates:
        split='dev' if sig in dev_signatures else 'train'
        for family in ['task_sentences','bracket_records','before_starting']:
            for variation in range(2):
                expected={'tasks':base['tasks'],'durations':{k:rng.randint(1,24) for k in 'ABCD'}}
                parts=[]
                for t in expected['tasks']:
                    k=t['id'];n=expected['durations'][k];deps=t['depends_on'];need=' and '.join(deps) if deps else 'none'
                    if family=='task_sentences':text=f'Task {k} lasts {n} minutes. Prerequisites: {need}.'
                    elif family=='bracket_records':text=f'[{k}] duration={n} minutes; requires={need}.'
                    else:text=(f'Before starting {k} (duration {n} minutes), finish '+need+'.' if deps else f'{k} runs for {n} minutes and may begin without waiting for another task.')
                    parts.append(text)
                canonical(expected)
                rows.append({'case_id':f'EXTRACT-{len(rows)+1:04d}','split':split,'kind':'supported',
                 'family':family,'text':'\n'.join(parts),'expected':expected,
                 'target':json.dumps(canonical(expected),sort_keys=True,separators=(',',':')),
                 'graph_signature':sig,'provenance':'AUTHORED_SYNTHETIC_NOT_HUMAN_USAGE'})
    for reason in ['unknown_duration','unknown_predecessors','cycle','conflicting_duration']:
        split='dev' if reason=='conflicting_duration' else 'train'
        for i in range(16):
            n=i+1
            texts={'unknown_duration':f'Task A has an unspecified duration. Task B runs for {n} minutes after A.',
             'unknown_predecessors':f'Task A lasts {n} minutes. No predecessor information is available for task B, which lasts 9 minutes.',
             'cycle':f'Task A lasts {n} minutes and requires B to finish. Task B lasts 9 minutes and requires A to finish.',
             'conflicting_duration':f'Task A has duration {n} minutes. Task A also has duration {n+7} minutes. No rule resolves the conflict.'}
            rows.append({'case_id':f'EXTRACT-{len(rows)+1:04d}','split':split,'kind':'unsupported',
             'family':reason,'text':texts[reason],'expected':None,'target':'ABSTAIN',
             'graph_signature':None,'provenance':'AUTHORED_SYNTHETIC_NEGATIVE'})
    return rows,fixture,excluded


def audit(rows,fixture,excluded):
    evaluation=[json.loads(line) for line in fixture.decode().splitlines()]
    texts={split:{normalized(c['text']) for c in rows if c['split']==split} for split in ['train','dev']}
    fixture_texts={normalized(c['text']) for c in evaluation}
    signatures={split:{c['graph_signature'] for c in rows if c['split']==split and c['graph_signature'] is not None} for split in ['train','dev']}
    duplicates=len(rows)-len({normalized(c['text']) for c in rows})
    overlap={'normalized_text_train_dev':len(texts['train']&texts['dev']),
       'normalized_text_with_evaluation':len((texts['train']|texts['dev'])&fixture_texts),
       'isomorphic_graph_train_dev':len(signatures['train']&signatures['dev']),
       'isomorphic_graph_with_evaluation':len((signatures['train']|signatures['dev'])&excluded),
       'duplicate_texts_within_generated_data':duplicates}
    if any(overlap.values()):raise ValueError('data overlap detected: '+str(overlap))
    return {'scope':'STRUCTURAL_AND_TEXT_SEPARATION_NOT_PROOF_OF_INDEPENDENCE','seed':1947,
       'evaluation_fixture_sha256':hashlib.sha256(fixture).hexdigest(),'evaluation_fixture_bytes':len(fixture),
       'rows':len(rows),'counts':{s:{k:sum(c['split']==s and c['kind']==k for c in rows) for k in ['supported','unsupported']} for s in ['train','dev']},
       'unique_graph_structures':{s:len(v) for s,v in signatures.items()},'overlap':overlap,
       'limits':['All data is synthetic and authored by this project, not real users.',
         'Graph isomorphism ignores duration values and task names.','Lexical/template similarity can remain despite zero exact overlap.',
         'Dev and public evaluation share project authorship and are not statistically independent.',
         'No weights are trained or updated by this builder.','Existing neural training command still uses the earlier answer-text corpus.']}


if __name__=='__main__':
    rows,fixture,excluded=build();report=audit(rows,fixture,excluded)
    for split in ['train','dev']:
        path=ROOT/f'training/extraction_{split}.jsonl';data=''.join(json.dumps(c)+'\n' for c in rows if c['split']==split).encode();path.write_bytes(data)
        report[f'{split}_sha256']=hashlib.sha256(data).hexdigest()
    if (ROOT/'evaluation/semantic_fixture.jsonl').read_bytes()!=fixture:raise ValueError('evaluation fixture changed')
    (ROOT/'training/EXTRACTION_DATA_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
