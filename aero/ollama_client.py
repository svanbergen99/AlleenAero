import json
import time
import urllib.error
import urllib.request

from .config import (
    KEEP_ALIVE,
    MODEL,
    NUM_CTX,
    OLLAMA_URL,
    REQUEST_TIMEOUT_SECONDS,
    THINK,
)


def chat(messages, tools=None):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": THINK,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_ctx": NUM_CTX},
    }
    if tools:
        payload["tools"] = tools

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = None

    for attempt in range(3):
        request = urllib.request.Request(
            OLLAMA_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["message"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"Ollama HTTP {exc.code}: {detail[:500]}")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc

        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

    raise last_error or RuntimeError("Ollama request failed")
