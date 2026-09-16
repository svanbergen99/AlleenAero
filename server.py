import base64
import json
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent import respond
from auth import cookie_header, is_operator
from config import HOST, KEEP_ALIVE, MEDIA_MAX_BYTES, MODEL, NUM_CTX, PORT, THINK, UPLOAD_DIR
from memory import initialize
from permissions import authorize_path
from state import is_active

UPLOAD_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml", ".html",
    ".css", ".py", ".js", ".ts", ".toml", ".ini", ".cfg", ".pdf", ".docx",
}

HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Aero</title>
<style>
body{background:#101217;color:#eee;font-family:Arial;max-width:900px;margin:auto;padding:28px}
#chat{white-space:pre-wrap}.msg{padding:12px;margin:10px 0;background:#181c24;border-radius:8px}
textarea{width:100%;height:100px;background:#181c24;color:white;border:1px solid #444;padding:10px}
button{margin-top:10px;padding:9px 18px}
</style></head><body>
<h1>Aero</h1><div id="chat"></div>
<textarea id="m" placeholder="Praat met Aero..."></textarea><br><button onclick="send()">Stuur</button>
<script>
async function send(){
 const box=document.getElementById('m'), text=box.value.trim(); if(!text)return; box.value='';
 chat.innerHTML += '<div class="msg"><b>Bas:</b> '+text+'</div>';
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
 const j=await r.json(); chat.innerHTML += '<div class="msg"><b>Aero:</b> '+(j.reply||j.error)+'</div>';
}
</script></body></html>"""


def _attachment_prompt(path, question):
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        tool = "analyze_image"
    elif suffix in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}:
        tool = "analyze_audio"
    else:
        tool = "analyze_document"
    return (
        f"Bas heeft een mediabijlage toegevoegd: {path}\n"
        f"Gebruik {tool} om de inhoud echt te analyseren voordat je antwoordt.\n"
        f"Vraag van Bas: {question or 'Analyseer deze bijlage.'}"
    )


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
            return self.send_json({
                "ok": True,
                "name": "Aero",
                "active": is_active(),
                "model": MODEL,
                "think": THINK,
                "num_ctx": NUM_CTX,
                "keep_alive": KEEP_ALIVE,
            })
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", cookie_header())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return self.send_json({"error": "not_found"}, 404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")

            if self.path == "/api/upload":
                name = Path(str(payload.get("name") or "upload")).name
                suffix = Path(name).suffix.lower()
                if suffix not in UPLOAD_EXTENSIONS:
                    return self.send_json({"error": "unsupported_file_type"}, 400)
                raw = base64.b64decode(str(payload.get("data") or ""), validate=True)
                if not raw or len(raw) > MEDIA_MAX_BYTES:
                    return self.send_json({"error": "empty_or_too_large"}, 400)
                stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)[:80] or "media"
                target = UPLOAD_DIR / f"{stem}-{uuid.uuid4().hex[:10]}{suffix}"
                target.write_bytes(raw)
                return self.send_json({"ok": True, "name": name, "path": str(target), "size": len(raw)})

            if self.path != "/api/chat":
                return self.send_json({"error": "not_found"}, 404)

            message = str(payload.get("message") or "").strip()
            attachment_path = str(payload.get("attachmentPath") or "").strip()
            if not message and not attachment_path:
                return self.send_json({"error": "empty_message"}, 400)

            if attachment_path:
                path = authorize_path(attachment_path)
                if not path.is_file():
                    return self.send_json({"error": "attachment_not_found"}, 400)
                message = _attachment_prompt(path, message)

            operator = is_operator(self)
            return self.send_json({"reply": respond(message, operator_authorized=operator), "operator": operator})
        except Exception as exc:
            return self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main():
    initialize()
    print(f"Aero: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

