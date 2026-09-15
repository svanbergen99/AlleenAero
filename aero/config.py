from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RUNTIME_DIR = ROOT / "runtime"
ORIGIN_FILE = ROOT / "ORIGIN.md"
DB_FILE = DATA_DIR / "aero.db"

HOST = "127.0.0.1"
PORT = 8091
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "project-ai-engine:27b"
THINK = False
NUM_CTX = 8192
KEEP_ALIVE = "10m"
REQUEST_TIMEOUT_SECONDS = 600
RECENT_HISTORY_MESSAGES = 8
MAX_AGENT_STEPS = 8
MAX_TOOL_CALLS = 6

DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
