import json
import secrets
import threading
import time
from pathlib import Path

from .config import APPROVAL_TTL_SECONDS, GRANTS_FILE, ROOT

_PENDING = {}
_LOCK = threading.Lock()

SENSITIVE_NAMES = {".env", "approval.key", "chat.key", "lifeline.json"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}
SENSITIVE_PARTS = {".ssh", "credentials", "secrets", "tokens", "private_keys"}


def _normalize(value):
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve(strict=False)


def _within(path, root):
    return path == root or root in path.parents


def _assert_not_sensitive(path):
    parts = {part.lower() for part in path.parts}
    if parts & SENSITIVE_PARTS:
        raise PermissionError("sensitive_path_blocked")
    if path.name.lower() in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
        raise PermissionError("sensitive_file_blocked")


def _load_grants():
    try:
        data = json.loads(GRANTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for item in data.get("grants", []):
        try:
            path = Path(str(item["path"])).resolve(strict=False)
            access = str(item.get("access", "read"))
            if path.is_absolute() and access in {"read", "read_write"}:
                out.append({"path": str(path), "access": access})
        except Exception:
            continue
    return out


def _save_grants(grants):
    temp = GRANTS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps({"grants": grants}, indent=2), encoding="utf-8")
    temp.replace(GRANTS_FILE)


def list_grants():
    return _load_grants()


def authorize_path(value, write=False):
    path = _normalize(value)
    _assert_not_sensitive(path)

    if _within(path, ROOT):
        return path

    needed = "read_write" if write else "read"
    for grant in _load_grants():
        root = Path(grant["path"]).resolve(strict=False)
        if _within(path, root):
            if write and grant["access"] != "read_write":
                continue
            return path

    raise PermissionError(f"path_not_authorized:{needed}")


def request_action(kind, args, summary):
    approval_id = secrets.token_hex(5)
    expires_at = time.time() + APPROVAL_TTL_SECONDS
    with _LOCK:
        _PENDING[approval_id] = {
            "kind": str(kind),
            "args": dict(args or {}),
            "summary": str(summary),
            "expires_at": expires_at,
        }
    return {
        "approval_required": True,
        "approval_id": approval_id,
        "summary": summary,
        "expires_seconds": APPROVAL_TTL_SECONDS,
    }


def consume_approval(approval_id):
    with _LOCK:
        item = _PENDING.pop(str(approval_id), None)
    if not item:
        raise ValueError("approval_not_found")
    if time.time() > float(item["expires_at"]):
        raise ValueError("approval_expired")
    return item


def cancel_approval(approval_id):
    with _LOCK:
        return _PENDING.pop(str(approval_id), None) is not None


def grant_external_scope(path_value, access):
    path = _normalize(path_value)
    if not path.is_absolute() or path == Path(path.anchor):
        raise ValueError("invalid_external_scope")
    if access not in {"read", "read_write"}:
        raise ValueError("invalid_access")
    grants = [g for g in _load_grants() if Path(g["path"]).resolve(strict=False) != path]
    grants.append({"path": str(path), "access": access})
    _save_grants(grants)
    return {"path": str(path), "access": access}


def revoke_external_scope(path_value):
    path = _normalize(path_value)
    grants = _load_grants()
    updated = [g for g in grants if Path(g["path"]).resolve(strict=False) != path]
    _save_grants(updated)
    return {"revoked": len(updated) != len(grants), "path": str(path)}
