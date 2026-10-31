"""Logging setup with a redaction filter, so no key can reach a log line (CLAUDE.md §3)."""
from __future__ import annotations

import logging
import os
import re

_SECRET = re.compile(r"(sk-ant-[A-Za-z0-9_\-]+|cd_[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9_\-\.]{12,})")


def redact(text: str) -> str:
    out = _SECRET.sub("[REDACTED]", text)
    for name in ("CRUSTDATA_API_KEY", "ANTHROPIC_API_KEY"):
        val = os.environ.get(name)
        if val and len(val) >= 8:
            out = out.replace(val, "[REDACTED]")
    return out


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        clean = redact(msg)
        if clean != msg:
            record.msg, record.args = clean, None
        return True


def setup(level: str | int | None = None) -> None:
    """Configure the `proofroom` logger once; level from PROOFROOM_LOG (default WARNING)."""
    logger = logging.getLogger("proofroom")
    if getattr(logger, "_proofroom_ready", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                           "%H:%M:%S"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(level or os.environ.get("PROOFROOM_LOG", "WARNING").upper())
    logger.propagate = False
    logger._proofroom_ready = True  # type: ignore[attr-defined]
