import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
from rio_evidence.streaming import validate_request,generate_streaming
from rio_evidence.neural_lm import ContextBudgetError
ROOT=Path(__file__).resolve().parents[1]

class StreamBudgetTests(unittest.TestCase):
    def test_utf8_boundary_and_rejection(self):
        self.assertEqual(len(validate_request('é'*2048,1)),4096)
        with self.assertRaises(ContextBudgetError):validate_request('é'*2049,1)
    def test_rejected_input_never_loads_runtime(self):
        with patch('rio_evidence.streaming.runtime') as runtime:
            with self.assertRaises(ContextBudgetError):generate_streaming(ROOT,'x'*4097)
            runtime.assert_not_called()

@unittest.skipUnless(importlib.util.find_spec('torch'),'optional torch required')
class StreamRuntimeTests(unittest.TestCase):
    def test_all_long_prompt_bytes_accounted_for(self):
        prompt='abcé'*55;r=generate_streaming(ROOT,prompt,4)
        self.assertEqual(r['processed_prompt_bytes'],len(prompt.encode()))
        self.assertEqual(sum(b['bytes'] for b in r['prefill_blocks']),len(prompt.encode()))
    def test_streamed_greedy_matches_full_prefix_reference(self):
        from rio_evidence.neural_lm import runtime,make_model
        torch=runtime();model=make_model(torch)
        model.load_state_dict(torch.load(ROOT/'model/byte_gru.pt',weights_only=True)['state_dict']);model.eval()
        prompt='Case: parallel '+('A takes 3 minutes. '*8)
        values=list(prompt.encode());expected=[]
        with torch.no_grad():
            for _ in range(8):
                token=int(model(torch.tensor([values],dtype=torch.long))[0,-1].argmax());values.append(token);expected.append(token)
        observed=generate_streaming(ROOT,prompt,8,chunk_bytes=31)
        self.assertEqual(bytes.fromhex(observed['generated_bytes_hex']),bytes(expected))
