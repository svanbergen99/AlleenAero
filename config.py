import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RUNTIME_DIR = ROOT / "runtime"
ORIGIN_FILE = ROOT / "ORIGIN.md"
DB_FILE = DATA_DIR / "aero.db"
STATE_FILE = DATA_DIR / "state.json"
UPLOAD_DIR = DATA_DIR / "uploads"


def _project_root():
    configured = os.environ.get("AERO_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    if os.name == "nt":
        return Path("D:\\").resolve(strict=False)
    return ROOT.resolve(strict=False)


PROJECT_ROOT = _project_root()

HOST = os.environ.get("AERO_HOST", "127.0.0.1")
PORT = int(os.environ.get("AERO_PORT", "8091"))

OLLAMA_URL = os.environ.get("AERO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.environ.get("AERO_MODEL", "project-ai-engine:27b")
THINK = os.environ.get("AERO_THINK", "false").lower() in {"1", "true", "yes"}
NUM_CTX = int(os.environ.get("AERO_NUM_CTX", "8192"))
KEEP_ALIVE = os.environ.get("AERO_KEEP_ALIVE", "10m")
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("AERO_REQUEST_TIMEOUT", "600"))

RECENT_HISTORY_MESSAGES = int(os.environ.get("AERO_RECENT_HISTORY", "8"))
MAX_AGENT_STEPS = int(os.environ.get("AERO_MAX_AGENT_STEPS", "8"))
MAX_TOOL_CALLS = int(os.environ.get("AERO_MAX_TOOL_CALLS", "6"))
APPROVAL_TTL_SECONDS = int(os.environ.get("AERO_APPROVAL_TTL", "300"))

VISION_BASE_URL = os.environ.get("AERO_VISION_BASE_URL", "http://127.0.0.1:8110")
VISION_MODEL = os.environ.get("AERO_VISION_MODEL", "aero-vision")
MEDIA_MAX_BYTES = int(os.environ.get("AERO_MEDIA_MAX_BYTES", str(80 * 1024 * 1024)))

DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
