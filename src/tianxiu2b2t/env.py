import os
from typing import Optional, TypeVar
import dotenv

T = TypeVar('T')

class Env:
    def __init__(
        self,
    ):
        self.config = {}
        # load .env and .env.*

        self.load()

    def load(self):
        config: dict[str, dict[str, str | None]] = {}
        for file in search_env():
            name = os.path.basename(file)
            config[name] = dotenv.dotenv_values(file)
        if not config:
            return
        result = {}
        if '.env' in config:
            result = config['.env']
            type = get_value(result, 'type', 'prod')
            cfg = get_value(config, f".env.{type}", {})
            result = {**result, **cfg}
        elif config:
            result = config[list(config.keys())[0]]
        self.config = result

    def get(self, key: str, def_ = None):
        for k, v in self.config.items():
            if k.lower() == key.lower():
                return v
        return def_
    
    def get_bool(self, key: str, def_ = None) -> bool:
        return (self.get(key, def_) or '').lower() in ['true', '1', 'yes']
    
    def get_int(self, key: str, def_ = None) -> int:
        return int(self.get(key, def_) or def_ or 0)
    
    def get_float(self, key: str, def_ = None) -> float:
        return float(self.get(key, def_) or def_ or 0)
    
    def get_str(self, key: str, def_ = None) -> str:
        return str(self.get(key, def_) or def_ or '')
            

def get_value(dict: dict[str, T], key: str, def_: T = None) -> T:
    for k, v in dict.items():
        if k.lower() == key.lower():
            return v
    return def_

def search_env(path: Optional[str] = None):
    root = os.path.join(os.getcwd(), path) if path else os.getcwd()
    for file in os.listdir(root):
        filepath = os.path.join(root, file)
        if not os.path.isfile(filepath) or not file.startswith(".env"):
            continue
        yield filepath