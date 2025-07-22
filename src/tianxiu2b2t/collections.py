from collections import deque
from typing import Callable, TypeVar

T = TypeVar('T')

class PoriorityDeque(deque[T]):
    def __init__(self, key: Callable[[T, T], bool], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._key = key

    def append(self, item):
        # calc index
        index = 0
        for i, v in enumerate(self):
            if self._key(item, v):
                index = i
                break
        super().insert(index, item)
