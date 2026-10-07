import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque


_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32, "maxmem": 64 * 1024 * 1024}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt": return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected), maxmem=_SCRYPT["maxmem"])
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# A precomputed hash lets failed logins for unknown users cost the same time as real ones.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_class_code() -> str:
    # Unambiguous characters, easy to dictate in a classroom: e.g. "K7QH-M2XP".
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


class RateLimiter:
    """Sliding-window failure counter kept in memory (reset on restart by design)."""

    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures, self.window = max_failures, window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float]:
        events = self.events[key]
        while events and events[0] < now - self.window: events.popleft()
        return events

    def blocked(self, *keys: str, limit: int | None = None) -> bool:
        now = time.time()
        with self.lock:
            return any(len(self._trim(key, now)) >= (limit or self.max_failures) for key in keys)

    def fail(self, *keys: str) -> None:
        now = time.time()
        with self.lock:
            for key in keys: self._trim(key, now).append(now)

    def reset(self, key: str) -> None:
        with self.lock: self.events.pop(key, None)


# Magic-number checks: the declared browser MIME type is never trusted on its own.
# Returns every media family the container can hold (MP4/WebM carry audio-only files too).
def sniff_media(head: bytes) -> set[str]:
    if head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG\r\n\x1a\n") or head[:6] in (b"GIF87a", b"GIF89a"): return {"image"}
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP": return {"image"}
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE": return {"audio"}
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ": return {"video"}
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "): return {"audio"}
        if brand in (b"avif", b"avis", b"heic", b"heix", b"mif1"): return {"image"}
        return {"video", "audio"}
    if head.startswith(b"\x1a\x45\xdf\xa3"): return {"video", "audio"}  # Matroska / WebM
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0): return {"audio"}
    if head.startswith(b"fLaC") or head.startswith(b"OggS"): return {"audio"}
    return set()
