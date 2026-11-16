"""Validate and serialize pey bank-account requests without performing I/O."""
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class BankAccountRegistration:
    alias: str
    name: str
    clabe: str
    entity: str

    def __post_init__(self):
        for value in (self.alias, self.name):
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                raise ValueError('Alias and account holder name must be 1 to 255 characters')
            try:
                value.encode('utf-8')
            except UnicodeEncodeError:
                raise ValueError('Alias and account holder name must be valid UTF-8') from None
        if self.entity not in ('BUSINESS', 'PERSON'):
            raise ValueError('Entity must be BUSINESS or PERSON')
        if not isinstance(self.clabe, str) or not re.fullmatch(r'[0-9]{18}', self.clabe):
            raise ValueError('CLABE must contain exactly 18 ASCII digits')
        weights = (3, 7, 1)
        total = sum((int(digit) * weights[index % 3]) % 10 for index, digit in enumerate(self.clabe[:17]))
        if (10 - total % 10) % 10 != int(self.clabe[-1]):
            raise ValueError('CLABE check digit is invalid')

    def __repr__(self):
        return 'BankAccountRegistration(<redacted>)'

    def to_json_bytes(self):
        """Return sensitive bytes for a separately authorized provider operation."""
        return json.dumps({
            'alias': self.alias,
            'name': self.name,
            'clabe': self.clabe,
            'entity': self.entity,
        }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
