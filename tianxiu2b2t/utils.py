import time
from typing import TypeVar

T = TypeVar('T')

class Runtime:
    # 单一实例，如果有则不要再创建
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self._perf_counter_ns = time.perf_counter_ns()
        self._monotonic_ns = time.monotonic_ns()

    def perf_counter(self):
        return self.perf_counter_ns() / 1e9
    
    def monotonic(self):
        return self.monotonic_ns() / 1e9
    
    def perf_counter_ns(self):
        return time.perf_counter_ns() - self._perf_counter_ns
    
    def monotonic_ns(self):
        return time.monotonic_ns() - self._monotonic_ns
    

    @staticmethod
    def instance():
        if Runtime._instance is None:
            Runtime._instance = Runtime()
        return Runtime._instance

runtime = Runtime()


def single_collection(*array: list[T]) -> list[T]:
    res = []
    for i in array:
        res.extend(i)
    return res

def varint_bytes(
    datum: int,
):
    # avro int
    datum = (datum << 1) ^ (datum >> 63)
    res = b''
    while (datum & ~0x7F) != 0:
        res += ((datum & 0x7F) | 0x80).to_bytes(1, 'big')
        datum >>= 7
    res += datum.to_bytes(1, 'big')
    return res

def varint_from_bytes(data: bytes) -> int:
    i = 0
    b = data[0]
    n = b & 0x7F
    shift = 7
    while (b & 0x80) != 0:
        b = data[i := i + 1]
        n |= (b & 0x7F) << shift
        shift += 7
    datum = (n >> 1) ^ -(n & 1)
    return datum