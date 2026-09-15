import secrets

OPERATOR_TOKEN = secrets.token_urlsafe(32)
COOKIE_NAME = "aero_operator"


def cookie_header():
    return f"{COOKIE_NAME}={OPERATOR_TOKEN}; HttpOnly; SameSite=Strict; Path=/"


def is_operator(handler):
    origin = (handler.headers.get("Origin") or "").strip().lower()
    if origin:
        return origin in {
            "http://127.0.0.1:8091",
            "http://localhost:8091",
        }

    target = f"{COOKIE_NAME}={OPERATOR_TOKEN}"
    cookie = handler.headers.get("Cookie") or ""
    return any(part.strip() == target for part in cookie.split(";"))
