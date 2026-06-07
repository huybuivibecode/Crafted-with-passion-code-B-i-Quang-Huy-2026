from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any, Dict


class SessionObjectStore:
    """Temporary per-session store for the latest returned objects."""

    def __init__(self, ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._store: Dict[str, Dict[str, Any]] = {}

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, snapshot in self._store.items()
            if now - float(snapshot.get("timestamp", 0)) > self.ttl_seconds
        ]
        for session_id in expired:
            self._store.pop(session_id, None)

    def save_snapshot(self, session_id: str, snapshot: Dict[str, Any]) -> None:
        if not session_id:
            return
        payload = deepcopy(snapshot or {})
        payload["timestamp"] = time.time()
        with self._lock:
            self._prune_locked()
            self._store[session_id] = payload

    def get_snapshot(self, session_id: str) -> Dict[str, Any]:
        if not session_id:
            return {}
        with self._lock:
            self._prune_locked()
            snapshot = self._store.get(session_id)
            return deepcopy(snapshot) if snapshot else {}

    def clear_session(self, session_id: str) -> None:
        if not session_id:
            return
        with self._lock:
            self._store.pop(session_id, None)
