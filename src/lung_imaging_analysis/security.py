"""Access control, limits and safety helpers for the web GUI (configured through environment variables)."""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from pathlib import Path

MB = 1024 * 1024
COOKIE_NAME = "lung_gui_session"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def access_token() -> str:
    """Shared access token; when empty the GUI is open (fine for localhost only)."""
    return os.environ.get("LUNG_GUI_TOKEN", "")


def demo_mode() -> bool:
    """Demo mode never saves uploads, whatever the consent box says."""
    return os.environ.get("LUNG_GUI_DEMO", "") == "1"


def max_upload_bytes() -> int:
    return int(float(os.environ.get("LUNG_GUI_MAX_MB", "50")) * MB)


def max_store_bytes() -> int:
    return int(float(os.environ.get("LUNG_GUI_MAX_STORE_MB", "500")) * MB)


def rate_limit_per_minute() -> int:
    return int(os.environ.get("LUNG_GUI_RATE", "10"))


def trust_proxy() -> bool:
    return os.environ.get("LUNG_GUI_TRUST_PROXY", "") == "1"


def session_value(token: str) -> str:
    return hmac.new(token.encode(), b"lung-gui-session", hashlib.sha256).hexdigest()


def token_matches(supplied: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(supplied.encode(), token.encode())


def cookie_is_valid(cookie_header: str | None, token: str) -> bool:
    if not token:
        return True
    if not cookie_header:
        return False
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return False
    morsel = jar.get(COOKIE_NAME)
    return bool(morsel) and hmac.compare_digest(morsel.value.encode(), session_value(token).encode())


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.iterdir() if p.is_file())


class RateLimiter:
    """Sliding-window limiter keyed by client address."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


def refuse_open_exposure(host: str) -> str | None:
    """Return an error message if the server would be exposed without a token."""
    if host in LOOPBACK_HOSTS or access_token() or os.environ.get("LUNG_GUI_ALLOW_OPEN") == "1":
        return None
    return ("Refusing to listen on a non-local address without an access token. "
            "Set LUNG_GUI_TOKEN to a long random value (or LUNG_GUI_ALLOW_OPEN=1 to override).")
