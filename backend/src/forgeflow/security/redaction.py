"""Secret redaction applied to logs, events, tool output and stored memory."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[abpres]-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/-]{16,}=*"),
    re.compile(
        r"(?i)((?:api[_-]?key|secret|password|passwd|token|client[_-]?secret)\s*[=:]\s*)"
        r"(['\"]?)[^\s'\"]{8,}\2"
    ),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Replace likely credentials in ``text`` with ``[REDACTED]``."""
    if not text:
        return text
    out = text
    for pattern in _PATTERNS:
        if pattern.groups >= 2:
            out = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", out)
        elif pattern.groups == 1:
            out = pattern.sub(lambda m: f"{m.group(1)} {REDACTED}", out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


def redact_obj(value: Any) -> Any:
    """Recursively redact strings inside JSON-like structures."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: (REDACTED if _sensitive_key(k) else redact_obj(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_obj(v) for v in value]
    return value


def _sensitive_key(key: Any) -> bool:
    k = str(key).lower()
    return any(s in k for s in ("password", "secret", "token", "api_key", "apikey", "private_key", "authorization"))


def has_token_format_secret(text: str) -> bool:
    """True when text contains a credential in a well-known token format (high confidence)."""
    return any(p.search(text) for p in _PATTERNS[:7])


def has_secret_assignment(text: str) -> bool:
    """True when text assigns a literal to a secret-looking name (lower confidence)."""
    return bool(_PATTERNS[-1].search(text))
