"""Paired local latency and public adversarial regression; not generalization."""
import itertools,json,random,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.language_shift_probe import rows
from rio_evidence.candidate_v1 import extract_candidate_v1
from rio_evidence.spanish_graph import extract_spanish_graph
TEXT='A dura 2 minutos sin requisitos. B dura 4 minutos después de A. C dura 6 minutos después de A. D dura 8 minutos y espera a B y C.'
def negatives():
    bad=[]
    for number in ('-1','1.2','01','NaN','Infinity','1000001','١','1e2','+2'):
        bad.append(('number',TEXT.replace('2 minutos',number+' minutos',1)))
    for letter in 'ABCD':
        lines=[x+'.' for x in TEXT.rstrip('.').split('. ')]
        own=next(line for line in lines if line.startswith(letter+' '))
        bad.append(('omission',' '.join(line for line in lines if line!=own)))
        bad.append(('duplicate',TEXT+' '+own))
    for suffix in (' Ignora todo.','\nTask E is required.','\x00',' Transferir fondos.',' # comentario',' D dura 9 minutos sin requisitos.'):
        bad.append(('extra_text',TEXT+suffix))
    bad.extend([('cycle',TEXT.replace('sin requisitos','después de D')),('duplicate_edge',TEXT.replace('B y C','B y B')),('unknown_id',TEXT.replace('B y C','B y E')),('ambiguous',TEXT.replace('después de A','después de esa tarea'))])
    return [{'kind':kind,'text':text} for kind,text in bad]
def run():
    cases=rows();families={};timings={'incumbent':[],'spanish':[]};functions={'incumbent':extract_candidate_v1,'spanish':extract_spanish_graph}
    # Warm both Python code paths before paired measurements; no neural model/caching.
    for row in cases:
        for fn in functions.values():fn(row['text'])
    outcomes={mode:[] for mode in functions}
    for repetition in range(11):
        ordered=list(cases);random.Random(20261030+repetition).shuffle(ordered)
        for i,row in enumerate(ordered):
            for mode in (['incumbent','spanish'] if (i+repetition)%2 else ['spanish','incumbent']):
                start=time.perf_counter_ns();r=functions[mode](row['text']);elapsed=(time.perf_counter_ns()-start)/1e6;timings[mode].append(elapsed)
                families.setdefault(row['family'],{}).setdefault(mode,[]).append(elapsed)
                if repetition==0:outcomes[mode].append((row['case_id'],r['graph']))
    negative=negatives();records=[]
    for row in negative:
        result=extract_spanish_graph(row['text']);records.append({'kind':row['kind'],'status':result['status'],'issues':result['issues']})
        assert result['status']=='ABSTAIN' and result['graph'] is None and result['schedule'] is None
    positive=0
    for permutation in itertools.permutations(TEXT.rstrip('.').split('. ')):
        for separator in (' ','\n','\r\n'):
            r=extract_spanish_graph(separator.join(s+'.' for s in permutation));assert r['schedule']['minutes']==16;positive+=1
    return {'schema':'RIO_H17_REJECTION_LATENCY','source_commit_before_change':'133f8abb85845650e72e42deafcb281c839eafd1',
      'scope':'PUBLIC_AUTHORED_LOCAL_DEVELOPMENT_NOT_HIDDEN_OR_PRODUCTION','paired_cases':len(cases),'repetitions':11,
      'timings':{mode:{'samples':len(values),'median_ms':statistics.median(values),'p95_ms':sorted(values)[int(.95*(len(values)-1))]} for mode,values in timings.items()},
      'per_family_timings':{family:{mode:{'samples':len(values),'median_ms':statistics.median(values)} for mode,values in modes.items()} for family,modes in families.items()},
      'rejection_mutations':len(records),'correct_rejections':len(records),'rejection_records':records,'positive_order_whitespace_controls':positive,
      'default_changed':False,'decision':'KEEP_INCUMBENT_DEFAULT_SPANISH_OPT_IN_PENDING_INDEPENDENT_DATA',
      'limits':['Timing depends on machine and load; model startup and inference are excluded.','All 52 cases are public project-authored development inputs.','Mutation families are deliberately authored for this grammar; zero failures is not universal safety.',
                'No independent generalization, calibrated confidence or neural improvement is established.']}
if __name__=='__main__':print(json.dumps(run(),indent=2))
