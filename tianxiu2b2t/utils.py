# process start
import time


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