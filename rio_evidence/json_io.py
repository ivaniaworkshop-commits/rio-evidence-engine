"""Bounded strict JSON decoding for local CLI inputs."""
import json
from pathlib import Path
MAX_BYTES = 1024 * 1024


def loads(text):
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('JSON input exceeds 1 MiB limit')
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj:raise ValueError('duplicate JSON key: '+key)
            obj[key]=value
        return obj
    def constant(value):
        raise ValueError('nonstandard JSON number: '+value)
    try:
        return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
    except RecursionError as error:
        raise ValueError('JSON nesting exceeds decoder capacity') from error


def load(path):
    with Path(path).open('rb') as stream:
        data=stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('JSON input exceeds 1 MiB limit')
    return loads(data.decode('utf-8'))
