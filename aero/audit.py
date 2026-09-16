import json
import threading
from datetime import datetime, timezone

from .config import DATA_DIR

AUDIT_FILE = DATA_DIR / "audit.jsonl"
_LOCK = threading.Lock()
_REDACT_KEYS = {"content", "base64", "value", "body", "text", "stdout", "stderr", "rows", "answer"}


def _sanitize(value, key=""):
    if str(key).lower() in _REDACT_KEYS:
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _sanitize(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value[:100]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "...<truncated>"
    return value


def write(event, **fields):
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event),
        **_sanitize(fields),
    }
    line = json.dumps(record, ensure_ascii=False)
    with _LOCK:
        with AUDIT_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
