"""待确认状态管理（ok/改/cancel），按 bot_name+user_id 隔离。"""
import time, threading


class PendingStore:
    TIMEOUT = 1800
    def __init__(self, namespace: str):
        self._ns = namespace
        self._store: dict = {}
        self._lock = threading.Lock()

    def set(self, user_id: str, data: dict):
        with self._lock:
            data['_ts'] = time.time()
            self._store[user_id] = data

    def get(self, user_id: str) -> dict | None:
        self._clean()
        with self._lock:
            return self._store.get(user_id)

    def pop(self, user_id: str) -> dict | None:
        with self._lock:
            return self._store.pop(user_id, None)

    def _clean(self):
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._store.items() if now - v.get('_ts', 0) > self.TIMEOUT]
            for k in expired:
                del self._store[k]
