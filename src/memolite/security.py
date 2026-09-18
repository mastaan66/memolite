"""Security helpers: PII redact, file perms, hash-chain, optional AES-GCM.

Stdlib-only except encryption which needs `cryptography` (pip install memolite[security]).
Fail-closed: if encryption requested but backend missing, raise.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from pathlib import Path

ENC_PREFIX = "ENC1:"
_SALT_LEN = 16
_NONCE_LEN = 12

PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)")),
    ("AWS_KEY", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("API_KEY", re.compile(r"(?i)(?:sk-|api[_-]?key\s*[:=]\s*)[A-Za-z0-9\-_]{8,}")),
    ("BEARER", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+")),
]


def redact_pii(text: str) -> str:
    """Replace emails, phones, IDs, keys with [REDACTED_*]. Offline regex."""
    out = text
    for name, pat in PII_PATTERNS:
        out = pat.sub(f"[REDACTED_{name}]", out)
    return out


def harden_file(path: str | Path) -> int | None:
    """chmod 0600 for db + wal files. Returns mode or None for :memory:."""
    p = str(path)
    if p == ":memory:":
        return None
    try:
        os.chmod(p, 0o600)
        wal = Path(p + "-wal")
        if wal.exists():
            os.chmod(wal, 0o600)
        return 0o600
    except OSError:
        return None


def file_perms_ok(path: str | Path) -> bool | None:
    """True if mode <= 0600. None for :memory: or missing."""
    p = str(path)
    if p == ":memory:" or not Path(p).exists():
        return None
    try:
        mode = Path(p).stat().st_mode & 0o777
        return mode <= 0o600
    except OSError:
        return None


def chain_hash(prev: str, session: str, role: str, content: str, ts: int) -> str:
    """SHA256(prev|session|role|content|ts) hex. WORM link."""
    h = hashlib.sha256()
    h.update(prev.encode("utf-8"))
    h.update(b"|")
    h.update(session.encode("utf-8"))
    h.update(b"|")
    h.update(role.encode("utf-8"))
    h.update(b"|")
    h.update(content.encode("utf-8"))
    h.update(b"|")
    h.update(str(ts).encode("utf-8"))
    return h.hexdigest()


def _raw_key_from_env(env_var: str) -> bytes:
    val = os.environ.get(env_var, "")
    if not val:
        raise ValueError(f"{env_var} not set")
    # accept base64, hex, or raw passphrase (derived via sha256)
    try:
        if len(val) >= 44 and val.endswith("="):
            return base64.b64decode(val)
    except Exception:
        pass
    try:
        if len(val) == 64 and all(c in "0123456789abcdefABCDEF" for c in val):
            return bytes.fromhex(val)
    except Exception:
        pass
    return hashlib.sha256(val.encode("utf-8")).digest()


def encrypt_str(plaintext: str, env_var: str = "MEMOLITE_KEY") -> str:
    """AES256-GCM encrypt. Output ENC1:base64(salt|nonce|ct). Needs cryptography."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise ImportError("pip install memolite[security] for encryption") from e
    salt = os.urandom(_SALT_LEN)
    # derive per-message key via PBKDF2 to avoid raw passphrase reuse
    raw = _raw_key_from_env(env_var)
    key = hashlib.pbkdf2_hmac("sha256", raw, salt, 200_000, dklen=32)
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    blob = salt + nonce + ct
    return ENC_PREFIX + base64.b64encode(blob).decode("ascii")


def decrypt_str(token: str, env_var: str = "MEMOLITE_KEY") -> str:
    """Inverse of encrypt_str. Pass through if not encrypted."""
    if not token.startswith(ENC_PREFIX):
        return token
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise ImportError("pip install memolite[security] for decryption") from e
    blob = base64.b64decode(token[len(ENC_PREFIX) :])
    salt = blob[:_SALT_LEN]
    nonce = blob[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
    ct = blob[_SALT_LEN + _NONCE_LEN :]
    raw = _raw_key_from_env(env_var)
    key = hashlib.pbkdf2_hmac("sha256", raw, salt, 200_000, dklen=32)
    pt = AESGCM(key).decrypt(nonce, ct, None)
    return pt.decode("utf-8")


def is_encrypted(token: str) -> bool:
    return token.startswith(ENC_PREFIX)
