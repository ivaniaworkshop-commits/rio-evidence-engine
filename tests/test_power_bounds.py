"""H12 statistical robustness tests, not independent field observations."""
import unittest
from rio_evidence.power_bounds import probability_at_least,minimum_n_for_power,design_effect
from rio_evidence.paired_runner import evaluate_paired

class PowerBoundsTests(unittest.TestCase):
    def test_exact_threshold_five_wins(self):
        self.assertEqual(probability_at_least(5,.5,5),.03125)
    def test_n80_for_ten_percent_gain_without_losses(self):
        self.assertEqual(minimum_n_for_power(.10),66)
        self.assertAlmostEqual(probability_at_least(30,.10,5),.17549487903389513,places=12)
    def test_design_effect_is_explicitly_heuristic(self):
        a=design_effect(40,5,.5)
        self.assertAlmostEqual(a["effective_n_heuristic"],40/3)
        self.assertEqual(a["design_effect"],3)
    def test_invalid_probability_rejected(self):
        with self.assertRaises(ValueError):
            probability_at_least(30,float("nan"))
    def test_single_cluster_five_wins_are_not_independent_five_clusters(self):
        gold={"tasks":[{"id":"A","depends_on":[]}],"durations":{"A":3}}
        cases=[]
        for i in range(40):
            source=("C0" if i<5 else "C1" if i<30 else f"C{2+i%4}")
            cases.append({"case_id":f"SC{i}","cluster":source,
                          "text":f"Synthetic invented observation number {i}.",
                          "expected":gold if i<30 else None})
        mapping={c["text"]:c for c in cases}
        def candidate(text):
            row=mapping[text]
            if row["expected"] is not None and row["cluster"]=="C0":
                return {"status":"EXPLICIT_GRAPH_RECOVERED","graph":gold}
            return {"status":"ABSTAIN","graph":None}
        report=evaluate_paired(cases,candidate,repetitions=1)
        self.assertEqual(report["candidate_wins"],5)
        self.assertEqual(report["cluster_wins"],1)
        self.assertEqual(report["conditional_one_sided_p_descriptive"],.03125)
        self.assertEqual(report["cluster_one_sided_p_descriptive"],.5)
        self.assertFalse(report["preliminary_engineering_screen"])
        self.assertFalse(report["candidate_promoted"])
    def test_perfect_memorizer_has_multiple_positive_clusters_but_no_provenance(self):
        gold={"tasks":[{"id":"A","depends_on":[]}],"durations":{"A":3}}
        cases=[{"case_id":f"P{i}","cluster":f"C{i%8}","text":f"Artificial case {i}.",
                "expected":gold if i<30 else None} for i in range(40)]
        memory={c["text"]:c["expected"] for c in cases}
        def candidate(t):
            return {"status":"EXPLICIT_GRAPH_RECOVERED","graph":memory[t]} if memory[t] is not None else {"status":"ABSTAIN","graph":None}
        r=evaluate_paired(cases,candidate,repetitions=1)
        self.assertGreaterEqual(r["cluster_wins"],5)
        self.assertTrue(r["preliminary_engineering_screen"])
        self.assertFalse(r["candidate_promoted"])
