import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from .config import RUNTIME_DIR


def _pid_running(pid):
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
            output = (proc.stdout or "").lower()
            return str(int(pid)) in output and "no tasks are running" not in output
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


@contextmanager
def runtime_lock(name="gpu", timeout=120, stale_after=300):
    lock_dir = Path(RUNTIME_DIR) / f"{name}.lock"
    owner_file = lock_dir / "owner.json"
    deadline = time.time() + timeout

    while True:
        try:
            lock_dir.mkdir()
            owner_file.write_text(
                json.dumps({"pid": os.getpid(), "time": time.time()}),
                encoding="utf-8",
            )
            break
        except FileExistsError:
            owner = {}
            try:
                if owner_file.is_file():
                    owner = json.loads(owner_file.read_text(encoding="utf-8"))
                owner_pid = int(owner.get("pid") or 0)
                age = time.time() - lock_dir.stat().st_mtime
                if (owner_pid and not _pid_running(owner_pid)) or age > stale_after:
                    shutil.rmtree(lock_dir, ignore_errors=True)
                    continue
            except FileNotFoundError:
                continue
            if time.time() >= deadline:
                raise TimeoutError(f"runtime_lock_timeout:{name}")
            time.sleep(0.25)

    try:
        yield
    finally:
        shutil.rmtree(lock_dir, ignore_errors=True)
