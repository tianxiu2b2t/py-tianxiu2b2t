import json
from typing import Any


class ConfigParser:
    def __init__(
        self,
        value: Any
    ):
        self._required = False
        self._value = value

    def required(self):
        self._required = True
        return self
    
    def not_required(self):
        self._required = False
        return self

    def as_int(self):
        self._check_required()
        return int(self._value)
    
    def as_float(self):
        self._check_required()
        return float(self._value)
    
    def as_bool(self):
        self._check_required()
        return bool(self._value)
    
    def as_str(self):
        self._check_required()
        return str(self._value)
    
    def as_json(self):
        self._check_required()
        return json.loads(self._value)
    
    def _check_required(self):
        if self._value is None and self._required:
            raise ValueError("Value is required")