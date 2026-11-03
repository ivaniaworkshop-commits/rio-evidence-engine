"""Bounded strict JSON decoding for local CLI inputs."""
import json
import math
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
    def strict_int(token):
        if token == '-0':
            raise ValueError('negative zero integer token is not cross-runtime portable')
        return int(token)
    def binary64_float(token):
        number=float(token)
        if not math.isfinite(number):
            raise ValueError('JSON number outside finite binary64 range')
        mantissa=token.lower().split('e',1)[0]
        if number == 0 and any(c in '123456789' for c in mantissa):
            raise ValueError('nonzero JSON number underflows binary64')
        return number
    try:
        return json.loads(text,object_pairs_hook=pairs,parse_constant=constant,
                          parse_float=binary64_float,parse_int=strict_int)
    except RecursionError as error:
        raise ValueError('JSON nesting exceeds decoder capacity') from error


def load(path):
    with Path(path).open('rb') as stream:
        data=stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('JSON input exceeds 1 MiB limit')
    return loads(data.decode('utf-8'))
