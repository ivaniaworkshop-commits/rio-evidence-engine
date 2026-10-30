"""Bounded warm runtime and atomic dependency planning. No model or external actions."""
from collections import OrderedDict
import hashlib,json,threading
from pathlib import Path
from .graph_copy import extract_graph
from .core import critical_path
ATOMS=['duration_parser','dependency_parser','graph_parser','numeric_engine','evidence_guard','public_precompute','graph_cache','schedule_cache','delta_planner']
EDGES=[('duration_parser','graph_parser'),('dependency_parser','graph_parser'),('numeric_engine','graph_parser'),
       ('graph_parser','public_precompute'),('evidence_guard','public_precompute'),('public_precompute','graph_cache'),
       ('graph_parser','graph_cache'),('numeric_engine','schedule_cache')]
GRAPH_DEPS={'duration_parser','dependency_parser','graph_parser','numeric_engine','evidence_guard','public_precompute','graph_cache'}
SCHEDULE_DEPS={'numeric_engine','schedule_cache'}


def canonical_bytes(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def matrix_product(a,b):
    n=len(a)
    if len(b)!=n or any(len(row)!=n for row in a+b):raise ValueError('equal square matrices required')
    return [[sum(a[i][k]*b[k][j] for k in range(n)) for j in range(n)] for i in range(n)]


def atomic_matrices():
    index={name:i for i,name in enumerate(ATOMS)};a=[[0]*len(ATOMS) for _ in ATOMS]
    for source,target in EDGES:a[index[source]][index[target]]=1
    a2=matrix_product(a,a);a3=matrix_product(a2,a)
    return {'atoms':list(ATOMS),'edges':[list(edge) for edge in EDGES],'A':a,'A2':a2,'A3':a3,
            'scope':'DIRECTED_DEPENDENCY_PATH_COUNTS_NOT_CAUSAL_PROOF_OR_PHYSICAL_GEOMETRY'}


def affected(changed):
    if set(changed)-set(ATOMS):raise ValueError('unknown changed atoms')
    result=set(changed)
    while True:
        expanded=result|{b for a,b in EDGES if a in result}
        if expanded==result:return result
        result=expanded


def source_fingerprint(root):
    names=['rio_evidence/core.py','rio_evidence/duration_copy.py','rio_evidence/graph_copy.py','rio_evidence/semantic_gate.py']
    return hashlib.sha256(canonical_bytes({n:hashlib.sha256((Path(root)/n).read_bytes()).hexdigest() for n in names})).hexdigest()


class WarmRuntime:
    """Single-process cache; caller content is never persisted by this class."""
    def __init__(self,revision,capacity=128):
        if type(capacity) is not int or not 1<=capacity<=1024:raise ValueError('capacity must be 1..1024')
        self.revision=revision;self.capacity=capacity;self.cache=OrderedDict();self.lock=threading.RLock()
        self.hits=0;self.misses=0;self.evictions=0;self.warm=False
    def _cached(self,kind,payload,compute,deps):
        key=(kind,hashlib.sha256(canonical_bytes(payload)).hexdigest())
        with self.lock:
            if key in self.cache:
                self.hits+=1;encoded,_=self.cache.pop(key);self.cache[key]=(encoded,set(deps))
            else:
                self.misses+=1;encoded=canonical_bytes(compute());self.cache[key]=(encoded,set(deps))
                if len(self.cache)>self.capacity:self.cache.popitem(last=False);self.evictions+=1
            return json.loads(encoded) # Never return shared mutable cached state.
    def graph(self,text):
        if not isinstance(text,str) or len(text.encode('utf-8'))>4096:raise ValueError('text must fit 4096 UTF-8 bytes')
        return self._cached('graph',text,lambda:extract_graph(text),GRAPH_DEPS)
    def schedule(self,payload):
        return self._cached('schedule',payload,lambda:critical_path(payload['tasks'],payload['durations']),SCHEDULE_DEPS)
    def prewarm(self,texts):
        if not isinstance(texts,list) or len(texts)>128:raise ValueError('at most 128 warm cases')
        for text in texts:self.graph(text)
        self.warm=True;return self.stats()
    def invalidate(self,changed):
        impacted=affected(changed)
        with self.lock:
            removed=[key for key,(value,deps) in self.cache.items() if deps&impacted]
            for key in removed:del self.cache[key]
            if 'graph_cache' in impacted:self.warm=False
        return {'changed':sorted(changed),'affected':sorted(impacted),'entries_invalidated':len(removed)}
    def stats(self):
        return {'revision':self.revision,'entries':len(self.cache),'capacity':self.capacity,'hits':self.hits,'misses':self.misses,
                'evictions':self.evictions,'warm':self.warm,'scope':'PROCESS_LOCAL_NOT_CONTINUOUS_BACKGROUND_RUNTIME'}
    def load_public_precompute(self,package):
        if package.get('source_revision')!=self.revision:raise ValueError('stale precompute source revision')
        if hashlib.sha256(canonical_bytes(package['records'])).hexdigest()!=package.get('records_sha256'):raise ValueError('precompute bytes mismatch')
        if len(package['records'])>128:raise ValueError('public precompute exceeds bound')
        prepared=[]
        for row in package['records']:
            if row['status']!='OBSERVED_PUBLIC_AUTHORED_CASE':raise ValueError('unapproved precompute provenance')
            key=('graph',row['text_sha256']);prepared.append((key,canonical_bytes(row['result'])))
        with self.lock:
            for key,encoded in prepared:
                self.cache[key]=(encoded,set(GRAPH_DEPS))
                if len(self.cache)>self.capacity:self.cache.popitem(last=False);self.evictions+=1
            self.warm=True
        return self.stats()


def precompute_public(root):
    root=Path(root);rows=[json.loads(s) for s in (root/'training/extraction_dev.jsonl').read_text().splitlines()]
    if len(rows)>128:raise ValueError('public precompute case limit')
    records=[{'case_id':r['case_id'],'text_sha256':hashlib.sha256(canonical_bytes(r['text'])).hexdigest(),
              'result':extract_graph(r['text']),'status':'OBSERVED_PUBLIC_AUTHORED_CASE'} for r in rows]
    return {'source_revision':source_fingerprint(root),'source_data_sha256':hashlib.sha256((root/'training/extraction_dev.jsonl').read_bytes()).hexdigest(),
            'records_sha256':hashlib.sha256(canonical_bytes(records)).hexdigest(),'records':records,
            'limits':'Public derived data only. Hash consistency is not truth or authenticity. No user-input persistence.'}
