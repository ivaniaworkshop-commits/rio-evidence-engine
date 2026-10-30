"""Experimental bounded GRU prefill with recurrent state, not semantic memory assurance."""
import argparse,hashlib,json
from pathlib import Path
from .neural_lm import runtime,make_model,ContextBudgetError
MAX_PROMPT_BYTES=4096
MAX_OUTPUT_BYTES=512


def validate_request(prompt,max_bytes):
    if not isinstance(prompt,str) or not prompt:raise ValueError('prompt must be nonempty text')
    if type(max_bytes) is not int or not 1<=max_bytes<=MAX_OUTPUT_BYTES:
        raise ValueError('output bytes must be an integer in 1..512')
    encoded=prompt.encode('utf-8')
    if len(encoded)>MAX_PROMPT_BYTES:
        raise ContextBudgetError('STREAM_PROMPT_BUDGET_EXCEEDED: prompt exceeds 4096 UTF-8 bytes; no inference performed')
    return encoded


def generate_streaming(root,prompt,max_bytes=64,chunk_bytes=128):
    encoded=validate_request(prompt,max_bytes)
    if type(chunk_bytes) is not int or not 1<=chunk_bytes<=128:
        raise ValueError('chunk_bytes must be 1..128')
    torch=runtime();model=make_model(torch)
    model.load_state_dict(torch.load(Path(root)/'model/byte_gru.pt',weights_only=True)['state_dict']);model.eval()
    hidden=None;processed=0;blocks=[];result=[]
    with torch.no_grad():
        for offset in range(0,len(encoded),chunk_bytes):
            block=encoded[offset:offset+chunk_bytes]
            x=torch.tensor([list(block)],dtype=torch.long)
            outputs,hidden=model.gru(model.embedding(x),hidden)
            logits=model.output(outputs[:,-1]);processed+=len(block)
            blocks.append({'offset':offset,'bytes':len(block)})
        for index in range(max_bytes):
            token=int(logits[0].argmax());result.append(token)
            if index+1<max_bytes:
                x=torch.tensor([[token]],dtype=torch.long)
                outputs,hidden=model.gru(model.embedding(x),hidden)
                logits=model.output(outputs[:,-1])
    if processed!=len(encoded):raise ValueError('prefill byte accounting failed')
    return {'generated_untrusted_text':bytes(result).decode('utf-8',errors='replace'),
            'generated_bytes_hex':bytes(result).hex(),'prompt_bytes':len(encoded),
            'processed_prompt_bytes':processed,'prompt_sha256':hashlib.sha256(encoded).hexdigest(),
            'prefill_blocks':blocks,'requested_output_bytes':max_bytes,
            'policy':'EXPERIMENTAL_FULL_PREFILL_WITH_CACHED_RECURRENT_STATE',
            'limits':'All bytes are processed; fixed-size hidden state does not guarantee semantic retention or correct answers.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prompt',required=True);p.add_argument('--max-bytes',type=int,default=64);a=p.parse_args(argv)
    try:
        print(json.dumps(generate_streaming(Path(__file__).resolve().parents[1],a.prompt,a.max_bytes)));return 0
    except (ValueError,OSError,RuntimeError,ImportError) as error:
        print(json.dumps({'error':str(error),'status':'CONTEXT_REJECTED' if isinstance(error,ContextBudgetError) else 'EXECUTION_FAILED'}));return 2

if __name__=='__main__':raise SystemExit(main())
