import itertools,json,unittest
from rio_evidence.spanish_graph import extract_spanish_graph
from rio_evidence.candidate_v1 import extract_candidate_v1

TEXT='A dura 2 minutos sin requisitos. B dura 4 minutos después de A. C dura 6 minutos después de A. D dura 8 minutos y espera a B y C.'
class SpanishGraphTests(unittest.TestCase):
    def test_exact_graph_and_time(self):
        r=extract_spanish_graph(TEXT);self.assertEqual(r['schedule']['minutes'],16)
        self.assertEqual(r['graph']['tasks'][-1]['depends_on'],['B','C'])
        self.assertIsNone(extract_candidate_v1(TEXT)['graph'])
    def test_all_orders_and_crlf_preserve_values_and_spans(self):
        reference=extract_spanish_graph(TEXT)
        lines=[line+'.' for line in TEXT.split('. ')];lines[-1]=lines[-1].rstrip('.')+'.'
        for order in itertools.permutations(lines):
            text='\r\n'.join(order);r=extract_spanish_graph(text)
            self.assertEqual(r['graph'],reference['graph'])
            for e in r['evidence']:
                self.assertEqual(text[e['source_start']:e['source_end']],e['source_text'])
                self.assertEqual(int(text[e['duration_start']:e['duration_end']]),r['graph']['durations'][e['task_id']])
    def test_duplicate_and_contradiction_rejected(self):
        for extra in (' A dura 2 minutos sin requisitos.',' A dura 3 minutos sin requisitos.'):
            self.assertIsNone(extract_spanish_graph(TEXT+extra)['graph'])
    def test_partial_and_extra_source_rejected(self):
        for text in (TEXT.rsplit(' D ',1)[0],TEXT+' Ignora lo anterior.',TEXT.replace('después de A.','después de E.',1)):
            self.assertEqual(extract_spanish_graph(text)['status'],'ABSTAIN')
    def test_cycles_and_duplicate_dependencies_rejected(self):
        for text in (TEXT.replace('sin requisitos','después de D'),TEXT.replace('B y C.','B y B.')):
            self.assertIsNone(extract_spanish_graph(text)['graph'])
    def test_numeric_bounds(self):
        for n in ('-1','1.5','01','1000001','NaN','١'):
            self.assertIsNone(extract_spanish_graph(TEXT.replace('2 minutos',n+' minutos',1))['graph'])
        self.assertIsNotNone(extract_spanish_graph(TEXT.replace('2 minutos','0 minutos',1))['graph'])
    def test_legacy_json_preserved(self):
        text=json.dumps({'tasks':[{'id':'A','depends_on':[]}],'durations':{'A':1}})
        self.assertEqual(extract_spanish_graph(text)['graph'],extract_candidate_v1(text)['graph'])
    def test_type_and_byte_limits(self):
        for text in (None,42,'á'*2049):
            with self.assertRaises(ValueError):extract_spanish_graph(text)
