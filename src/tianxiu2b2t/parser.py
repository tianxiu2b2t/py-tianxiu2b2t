import json
from typing import Any, TypeVar, Generic

T = TypeVar('T')

class ConfigParser(Generic[T]):
    def __init__(
        self,
        value: Any
    ):
        self._required = False
        self._value = value
        self._default: Any = None

    def required(self):
        self._required = True
        return self
    
    def not_required(self):
        self._required = False
        return self
    
    def default(self, value: Any):
        self._default = value
        return self

    def as_int(self):
        self._check_required()
        return int(self._get_value())
    
    def as_float(self):
        self._check_required()
        return float(self._get_value())
    
    def as_bool(self):
        return self.as_str().lower() in ("true", "t", "y", "yes", "1", "on", "enabled", "enable", "active", "activated")
    
    def as_str(self):
        self._check_required()
        return str(self._get_value())
    
    def as_json(self):
        self._check_required()
        return json.loads(self._get_value())
    
    def as_list(self) -> list[Any]:
        return self.as_json()
    
    def as_dict(self) -> dict[str, Any]:
        return self.as_json()
    
    def _check_required(self):
        if self._get_value() is None and self._required:
            raise ValueError("Value is required")
        
    def _get_value(self):
        return self._value if self._value is not None else self._default