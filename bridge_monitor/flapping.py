from collections import deque
import time


class FlappingDetector:
    def __init__(self, threshold: int = 4, window_seconds: int = 300):
        self.threshold = threshold
        self.window_seconds = window_seconds
        # history maps target_name -> deque of (timestamp, success_bool)
        self._history: dict[str, deque[tuple[float, bool]]] = {}
        self._is_flapping: dict[str, bool] = {}

    def register_result(self, target_name: str, success: bool) -> bool:
        now = time.time()
        if target_name not in self._history:
            self._history[target_name] = deque()

        q = self._history[target_name]
        q.append((now, success))

        # evict anything older than the window
        cutoff = now - self.window_seconds
        while q and q[0][0] < cutoff:
            q.popleft()

        flips = 0
        if len(q) >= 2:
            for i in range(1, len(q)):
                if q[i][1] != q[i - 1][1]:
                    flips += 1

        was_flapping = self._is_flapping.get(target_name, False)
        is_now_flapping = flips >= self.threshold
        self._is_flapping[target_name] = is_now_flapping

        # True if flapping status flipped on this check
        return is_now_flapping and not was_flapping

    def is_target_flapping(self, target_name: str) -> bool:
        return self._is_flapping.get(target_name, False)

    def reset(self, target_name: str):
        self._history.pop(target_name, None)
        self._is_flapping.pop(target_name, None)
