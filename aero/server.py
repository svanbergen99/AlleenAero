import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .agent import respond
from .config import HOST, KEEP_ALIVE, MODEL, NUM_CTX, PORT, THINK
from .memory import initialize


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(
                {
                    "ok": True,
                    "name": "Aero",
                    "model": MODEL,
                    "think": THINK,
                    "num_ctx": NUM_CTX,
                    "keep_alive": KEEP_ALIVE,
                }
            )
        return self.send_json({"error": "not_found"}, 404)

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_json({"error": "not_found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            message = str(payload.get("message") or "").strip()
            if not message:
                return self.send_json({"error": "empty_message"}, 400)
            return self.send_json({"reply": respond(message)})
        except Exception as exc:
            return self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main():
    initialize()
    print(f"Aero: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
