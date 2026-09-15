import ipaddress
import secrets

OPERATOR_TOKEN = secrets.token_urlsafe(32)
COOKIE_NAME = "aero_operator"


def cookie_header():
    return f"{COOKIE_NAME}={OPERATOR_TOKEN}; HttpOnly; SameSite=Strict; Path=/"


def _client_is_loopback(handler):
    try:
        host = handler.client_address[0]
        return ipaddress.ip_address(host).is_loopback
    except Exception:
        return False


def is_operator(handler):
    # Aero binds to loopback by default. A direct request or a local ChatBox proxy
    # therefore remains authorized without depending on a browser cookie.
    if _client_is_loopback(handler):
        return True

    origin = (handler.headers.get("Origin") or "").strip().lower()
    if origin in {"http://127.0.0.1:8091", "http://localhost:8091"}:
        return True

    target = f"{COOKIE_NAME}={OPERATOR_TOKEN}"
    cookie = handler.headers.get("Cookie") or ""
    return any(part.strip() == target for part in cookie.split(";"))
