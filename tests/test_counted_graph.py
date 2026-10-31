import json
import unittest
from rio_evidence.candidate_v1 import extract_candidate_v1
from rio_evidence.counted_graph import extract_counted_graph

class DeclaredCountTests(unittest.TestCase):
    def csv(self, n):
        return 'task,duration,predecessors\n'+'\n'.join(f'{k},1,none' for k in 'ABCDEFGH'[:n])
    def test_complete_inventory_all_supported_sizes(self):
        for n in range(1,9):
            text=self.csv(n)
            self.assertEqual(extract_counted_graph(text,n)['graph'],extract_candidate_v1(text)['graph'])
    def test_terminal_omission_rejected_when_count_is_declared(self):
        for n in range(2,9):
            text=self.csv(n-1)
            self.assertIsNotNone(extract_candidate_v1(text)['graph'])
            result=extract_counted_graph(text,n)
            self.assertEqual(result['issues'],['DECLARED_TASK_COUNT_MISMATCH'])
            self.assertIsNone(result['schedule'])
    def test_invalid_count_does_not_invoke_parser(self):
        from unittest.mock import patch
        with patch('rio_evidence.counted_graph.extract_candidate_v1') as parser:
            for count in (True,False,None,'4',4.0,0,-1,9):
                with self.assertRaises(ValueError):extract_counted_graph('bad',count)
            parser.assert_not_called()
    def test_underdeclared_count_also_rejected(self):
        self.assertIsNone(extract_counted_graph(self.csv(4),3)['graph'])
    def test_matching_count_does_not_accept_bad_graph(self):
        self.assertEqual(extract_counted_graph('task,duration,predecessors\nA,1,A',1)['status'],'ABSTAIN')
    def test_json_count_and_authority_limit(self):
        text=json.dumps({'tasks':[{'id':'A','depends_on':[]}],'durations':{'A':1}})
        result=extract_counted_graph(text,1)
        self.assertIsNotNone(result['graph'])
        self.assertEqual(result['inventory_evidence']['authority'],'CALLER_DECLARATION_NOT_AUTHENTICATED_INTENT')
        self.assertIsNone(extract_counted_graph(text,2)['graph'])
