import json
import threading

from .config import STATE_FILE

_LOCK = threading.Lock()


def _read():
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {"active": bool(data.get("active", True))}
    except Exception:
        return {"active": True}


def is_active():
    return _read()["active"]


def set_active(value):
    state = {"active": bool(value)}
    with _LOCK:
        temp = STATE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp.replace(STATE_FILE)
    return state["active"]
