"""H11 locally synthetic adversarial tests; not independent model evidence."""
import unittest
from rio_evidence.paired_runner import evaluate_paired,_one_sided_exact_p
from rio_evidence.extended_graph import extract_extended_graph
from rio_evidence.graph_copy import extract_graph

class PairedRunnerTests(unittest.TestCase):
    def cases(self):
        return [
            {"case_id":"P1","cluster":"C1","text":"Tasks: 1\nStep A takes 3 minutes after none.",
             "expected":{"tasks":[{"id":"A","depends_on":[]}],"durations":{"A":3}}},
            {"case_id":"N1","cluster":"C2","text":"No complete task graph specified.","expected":None}
        ]

    def test_identity_control_has_no_gain(self):
        r=evaluate_paired(self.cases(),extract_extended_graph)
        self.assertEqual((r["baseline_supported_exact"],r["candidate_supported_exact"]),(1,1))
        self.assertEqual(r["candidate_wins"],0)
        self.assertFalse(r["candidate_promoted"])

    def test_legacy_regression_control(self):
        r=evaluate_paired(self.cases(),extract_graph)
        self.assertEqual(r["candidate_supported_exact"],0)
        self.assertEqual(r["candidate_losses"],1)

    def test_runtime_exception_not_correct_abstention(self):
        def crash(t):raise RuntimeError("test")
        r=evaluate_paired(self.cases(),crash)
        self.assertEqual(r["candidate_correct_abstentions"],0)
        self.assertEqual(r["candidate_invalid_or_error"],2)

    def test_false_abstention_status_rejected(self):
        r=evaluate_paired(self.cases(),lambda t:{"graph":None})
        self.assertEqual(r["candidate_correct_abstentions"],0)

    def test_forged_candidate_outputs_rejected(self):
        data=self.cases();data[0]["candidate_output"]="ABSTAIN"
        with self.assertRaisesRegex(ValueError,"REJECT_SUBMITTED"):
            evaluate_paired(data,extract_extended_graph)

    def test_forged_latency_rejected(self):
        data=self.cases();data[0]["candidate_latency_ms"]=0
        with self.assertRaisesRegex(ValueError,"REJECT_SUBMITTED"):
            evaluate_paired(data,extract_extended_graph)

    def test_unstable_candidate_fails_closed(self):
        n=[0]
        def flip(t):
            n[0]+=1
            return extract_extended_graph(t) if n[0]%2 else {"status":"ABSTAIN","graph":None}
        with self.assertRaisesRegex(ValueError,"NONDETERMINISTIC"):
            evaluate_paired(self.cases(),flip)

    def test_duplicate_id_rejected(self):
        data=self.cases();data[1]["case_id"]=data[0]["case_id"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            evaluate_paired(data,extract_extended_graph)

    def test_observed_latency_and_data_minimization(self):
        r=evaluate_paired(self.cases(),extract_extended_graph)
        self.assertGreaterEqual(r["baseline_observed_median_ms"],0)
        self.assertTrue(all("text" not in x and "expected" not in x for x in r["observations"]))

    def test_conditional_exact_p(self):
        self.assertEqual(_one_sided_exact_p(5,0),0.03125)
        self.assertEqual(_one_sided_exact_p(0,0),1.0)

    def test_source_claim_not_authentication(self):
        r=evaluate_paired(self.cases(),extract_extended_graph,source_class="OFFICIAL_ORGANIZER")
        self.assertFalse(r["source_class_verified"])
        self.assertFalse(r["candidate_promoted"])

    def test_perfect_memorizer_cannot_promote(self):
        graph={"tasks":[{"id":"A","depends_on":[]}],"durations":{"A":3}}
        data=[{"case_id":f"X{i}","cluster":f"C{i%8}","text":f"Internal synthetic invented {i}.",
               "expected":graph if i<30 else None} for i in range(40)]
        memory={r["text"]:r["expected"] for r in data}
        def memorizer(text):
            gold=memory[text]
            return {"status":"EXPLICIT_GRAPH_RECOVERED","graph":gold} if gold is not None else {"status":"ABSTAIN","graph":None}
        r=evaluate_paired(data,memorizer,repetitions=1,source_class="EXTERNAL_EVALUATOR")
        self.assertTrue(r["preliminary_engineering_screen"])
        self.assertFalse(r["candidate_promoted"])
        self.assertFalse(r["source_class_verified"])
