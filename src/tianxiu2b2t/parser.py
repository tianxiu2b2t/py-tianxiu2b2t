class ConfigParser:
    def __init__(
        self,
        value: str
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
        return int(self._value)
    
    def as_float(self):
        return float(self._value)
    
    def as_bool(self):
        return bool(self._value)
    
    def as_str(self):
        return str(self._value)