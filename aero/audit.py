import json
import threading
from datetime import datetime, timezone

from .config import DATA_DIR

AUDIT_FILE = DATA_DIR / "audit.jsonl"
_LOCK = threading.Lock()


def write(event, **fields):
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event),
        **fields,
    }
    line = json.dumps(record, ensure_ascii=False)
    with _LOCK:
        with AUDIT_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
