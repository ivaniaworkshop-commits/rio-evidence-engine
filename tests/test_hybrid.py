import unittest
from rio_evidence.hybrid import solve

class HybridTests(unittest.TestCase):
    def data(self):return {'tasks':[{'id':'a'},{'id':'b','depends_on':['a']}],'durations':{'a':5,'b':20}}
    def test_deterministic_answer_is_complete(self):
        r=solve(self.data());self.assertEqual(r['schedule']['minutes'],25)
        self.assertIn('25 minutes',r['explanation']);self.assertIn('enough workers',r['explanation'])
    def test_ranker_cannot_change_numbers(self):
        r=solve(self.data(),lambda texts:[0.,3.,1.]);self.assertEqual(r['selection']['candidate_index'],1)
        self.assertEqual(r['schedule']['single_worker_minutes'],25)
    def test_bad_scores_use_fallback(self):
        for scores in [[float('nan')]*3,[],[True]*3]:
            with self.subTest(scores=scores):
                r=solve(self.data(),lambda texts:scores)
                self.assertEqual(r['selection']['status'],'RANKER_FAILED_DETERMINISTIC_FALLBACK')
    def test_ranker_failure_does_not_hide_bad_graph(self):
        d=self.data();d['tasks'][0]['depends_on']=['b']
        with self.assertRaises(ValueError):solve(d,lambda texts:[1,2,3])
