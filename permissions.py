import secrets
import threading
import time
from pathlib import Path

from audit import write as audit
from config import APPROVAL_TTL_SECONDS, PROJECT_ROOT

ROOT = PROJECT_ROOT
_PENDING = {}
_LOCK = threading.Lock()


def normalize_path(value):
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve(strict=False)


def _within(path, root):
    return path == root or root in path.parents


def is_inside_project(value):
    return _within(normalize_path(value), ROOT)


def authorize_path(value, write=False):
    """Authorize direct runtime access only inside the project root."""
    path = normalize_path(value)
    if not _within(path, ROOT):
        raise PermissionError("outside_project_requires_owner_approval")
    return path


def prepare_path_for_approval(value):
    """Normalize any path so an exact one-shot action can be approved."""
    return normalize_path(value)


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
    audit("approval_requested", approval_id=approval_id, kind=str(kind), summary=str(summary))
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
        audit("approval_expired", approval_id=str(approval_id), kind=item.get("kind"))
        raise ValueError("approval_expired")
    audit("approval_consumed", approval_id=str(approval_id), kind=item.get("kind"))
    return item


def cancel_approval(approval_id):
    with _LOCK:
        removed = _PENDING.pop(str(approval_id), None) is not None
    audit("approval_cancelled", approval_id=str(approval_id), found=removed)
    return removed

