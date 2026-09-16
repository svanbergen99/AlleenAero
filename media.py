import base64
import json
import urllib.request
from pathlib import Path

from config import MEDIA_MAX_BYTES, VISION_BASE_URL, VISION_MODEL
from permissions import prepare_path_for_approval

TEXT_DOC_EXTS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml", ".html", ".css", ".py", ".js", ".ts", ".toml", ".ini", ".cfg"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}


def _checked(path_value):
    path = prepare_path_for_approval(path_value)
    if not path.is_file():
        raise ValueError("media_not_found")
    if path.stat().st_size > MEDIA_MAX_BYTES:
        raise ValueError("media_too_large")
    return path


def analyze_document(path_value, question=""):
    path = _checked(path_value)
    suffix = path.suffix.lower()
    if suffix in TEXT_DOC_EXTS:
        text = path.read_text(encoding="utf-8", errors="replace")[:120_000]
        return {"ok": True, "path": str(path), "text": text, "question": question}
    if suffix in PDF_EXTS:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("missing_dependency:pypdf") from exc
        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)[:120_000]
        return {"ok": True, "path": str(path), "text": text, "pages": len(reader.pages), "question": question}
    if suffix in DOCX_EXTS:
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("missing_dependency:python-docx") from exc
        doc = Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs)[:120_000]
        return {"ok": True, "path": str(path), "text": text, "question": question}
    raise ValueError("unsupported_document_type")


def analyze_image(path_value, question="Beschrijf wat je ziet."):
    path = _checked(path_value)
    if path.suffix.lower() not in IMAGE_EXTS:
        raise ValueError("unsupported_image_type")
    image = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": str(question)},
                {"type": "image_url", "image_url": {"url": f"data:image/{path.suffix.lower().lstrip('.')};base64,{image}"}},
            ],
        }],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    request = urllib.request.Request(
        VISION_BASE_URL.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    return {"ok": True, "path": str(path), "model": VISION_MODEL, "answer": content}


def analyze_audio(path_value, question="Transcribeer deze audio."):
    path = _checked(path_value)
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("missing_dependency:faster-whisper") from exc
    model = WhisperModel("small", device="auto", compute_type="int8")
    segments, info = model.transcribe(str(path), vad_filter=True)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return {
        "ok": True,
        "path": str(path),
        "language": getattr(info, "language", None),
        "text": text,
        "question": question,
    }

