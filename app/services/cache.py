"""TTL in-memory cache keyed by canonical request JSON hash."""

import hashlib
import json
import time
from threading import Lock

from app.core.config import settings


class TTLCache:
    def __init__(self, ttl_seconds: int | None = None, max_entries: int | None = None):
        self.ttl = (
            ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
        )
        self.max = (
            max_entries if max_entries is not None else settings.cache_max_entries
        )
        self._store: dict[str, tuple[float, dict]] = {}
        self._lock = Lock()

    @staticmethod
    def key(payload: dict) -> str:
        canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()

    def get(self, k: str) -> dict | None:
        now = time.time()
        with self._lock:
            entry = self._store.get(k)
            if not entry:
                return None
            ts, val = entry
            if now - ts > self.ttl:
                self._store.pop(k, None)
                return None
            return val

    def put(self, k: str, v: dict) -> None:
        with self._lock:
            if len(self._store) >= self.max:
                # Drop oldest by insertion order (dicts preserve insertion order in Python 3.7+)
                oldest = next(iter(self._store))
                self._store.pop(oldest, None)
            self._store[k] = (time.time(), v)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


cache = TTLCache()
