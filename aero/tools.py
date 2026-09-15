import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

from .config import ROOT
from .media import analyze_audio, analyze_document, analyze_image
from .permissions import (
    authorize_path,
    grant_external_scope,
    list_grants,
    request_action,
    revoke_external_scope,
)

TEXT_EXTS = {
    ".md", ".txt", ".py", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg",
    ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".csv", ".xml", ".ps1",
}


def _text(path, max_chars=120_000):
    data = path.read_text(encoding="utf-8", errors="replace")
    return data[:max_chars]


def list_dir(path="."):
    root = authorize_path(path)
    if not root.is_dir():
        raise ValueError("not_a_directory")
    return [
        {
            "name": p.name,
            "path": str(p),
            "type": "dir" if p.is_dir() else "file",
            "size": p.stat().st_size if p.is_file() else None,
        }
        for p in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    ]


def read_file(path):
    target = authorize_path(path)
    if not target.is_file():
        raise ValueError("file_not_found")
    if target.suffix.lower() not in TEXT_EXTS:
        raise ValueError("unsupported_text_file")
    return {"path": str(target), "content": _text(target)}


def file_info(path):
    target = authorize_path(path)
    stat = target.stat()
    return {
        "path": str(target),
        "exists": target.exists(),
        "is_file": target.is_file(),
        "is_dir": target.is_dir(),
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }


def search_text(path, query, max_results=50):
    root = authorize_path(path)
    needle = str(query).lower()
    results = []
    files = [root] if root.is_file() else root.rglob("*")
    for item in files:
        if len(results) >= int(max_results):
            break
        if not item.is_file() or item.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = _text(item, 250_000)
        except Exception:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if needle in line.lower():
                results.append({"path": str(item), "line": number, "text": line[:500]})
                if len(results) >= int(max_results):
                    break
    return results


def read_tree(path, max_files=20, max_chars=16000):
    root = authorize_path(path)
    if not root.is_dir():
        raise ValueError("not_a_directory")
    out = []
    used = 0
    for item in root.rglob("*"):
        if len(out) >= min(max(int(max_files), 1), 50):
            break
        if not item.is_file() or item.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = _text(item, min(max(int(max_chars) - used, 0), 50_000))
        except Exception:
            continue
        if not text:
            continue
        out.append({"path": str(item), "content": text})
        used += len(text)
        if used >= int(max_chars):
            break
    return {"root": str(root), "files": out, "chars": used}


def write_text(path, content):
    target = authorize_path(path, write=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
    target.write_text(str(content), encoding="utf-8")
    return {"path": str(target), "backup": str(backup) if backup else None}


def make_dir(path):
    target = authorize_path(path, write=True)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target)}


def system_info():
    return {
        "hostname": socket.gethostname(),
        "platform": os.name,
        "cwd": str(Path.cwd()),
        "repo": str(ROOT),
    }


def list_processes():
    if os.name == "nt":
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process | Select-Object Id,ProcessName,CPU,WorkingSet64 | ConvertTo-Json -Compress"],
            text=True, capture_output=True, timeout=15, check=False,
        )
        return json.loads(proc.stdout or "[]")
    proc = subprocess.run(["ps", "-eo", "pid,comm,%cpu,rss"], text=True, capture_output=True, timeout=10)
    return proc.stdout


def list_listeners():
    if os.name == "nt":
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetTCPConnection -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Compress"],
            text=True, capture_output=True, timeout=15, check=False,
        )
        return json.loads(proc.stdout or "[]")
    proc = subprocess.run(["ss", "-ltnp"], text=True, capture_output=True, timeout=10)
    return proc.stdout


def gpu_info():
    proc = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu",
         "--format=csv,noheader,nounits"],
        text=True, capture_output=True, timeout=10, check=False,
    )
    return {"returncode": proc.returncode, "output": proc.stdout.strip(), "error": proc.stderr.strip()}


def list_external_scopes():
    return list_grants()


OBSERVE_TOOLS = {
    "list_dir": list_dir,
    "read_file": read_file,
    "file_info": file_info,
    "search_text": search_text,
    "read_tree": read_tree,
    "system_info": system_info,
    "list_processes": list_processes,
    "list_listeners": list_listeners,
    "gpu_info": gpu_info,
    "list_external_scopes": list_external_scopes,
    "analyze_document": analyze_document,
    "analyze_image": analyze_image,
    "analyze_audio": analyze_audio,
}

MAINTAIN_TOOLS = {
    "write_text": write_text,
    "make_dir": make_dir,
}


def execute(name, args):
    name = str(name)
    args = dict(args or {})
    if name in OBSERVE_TOOLS:
        return OBSERVE_TOOLS[name](**args)
    if name in MAINTAIN_TOOLS:
        return MAINTAIN_TOOLS[name](**args)

    if name == "grant_external_scope":
        return request_action(
            "grant_external_scope",
            args,
            f"Geef Aero {args.get('access', 'read')} toegang tot {args.get('path')}",
        )
    if name == "revoke_external_scope":
        return request_action(
            "revoke_external_scope",
            args,
            f"Trek Aero-toegang in voor {args.get('path')}",
        )
    if name == "delete_path":
        target = authorize_path(args.get("path"), write=True)
        return request_action("delete_path", {"path": str(target)}, f"Verwijder {target}")
    if name == "move_path":
        src = authorize_path(args.get("src"), write=True)
        dst = authorize_path(args.get("dst"), write=True)
        return request_action("move_path", {"src": str(src), "dst": str(dst)}, f"Verplaats {src} naar {dst}")
    if name == "kill_process":
        return request_action("kill_process", {"pid": int(args["pid"])}, f"Stop proces PID {int(args['pid'])}")
    if name == "start_program":
        target = authorize_path(args.get("path"))
        return request_action(
            "start_program",
            {"path": str(target), "args": list(args.get("args") or [])},
            f"Start programma {target}",
        )
    raise ValueError(f"unknown_tool:{name}")


def execute_approved(kind, args):
    if kind == "grant_external_scope":
        return grant_external_scope(args["path"], args["access"])
    if kind == "revoke_external_scope":
        return revoke_external_scope(args["path"])
    if kind == "delete_path":
        target = authorize_path(args["path"], write=True)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"deleted": str(target)}
    if kind == "move_path":
        src = authorize_path(args["src"], write=True)
        dst = authorize_path(args["dst"], write=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"src": str(src), "dst": str(dst)}
    if kind == "kill_process":
        pid = int(args["pid"])
        if pid in {0, 4, os.getpid()}:
            raise PermissionError("critical_process_blocked")
        command = ["taskkill", "/PID", str(pid), "/F"] if os.name == "nt" else ["kill", "-TERM", str(pid)]
        proc = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    if kind == "start_program":
        target = authorize_path(args["path"])
        proc = subprocess.Popen([str(target), *list(args.get("args") or [])], cwd=str(target.parent))
        return {"pid": proc.pid, "path": str(target)}
    raise ValueError(f"unknown_approved_action:{kind}")


TOOL_SCHEMAS = {
    "list_dir": {"description": "List files and folders in an authorized path.", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "read_file": {"description": "Read an authorized text/code file.", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "file_info": {"description": "Get metadata for an authorized path.", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "search_text": {"description": "Search text recursively.", "properties": {"path": {"type": "string"}, "query": {"type": "string"}}, "required": ["path", "query"]},
    "read_tree": {"description": "Read a bounded set of text/code files from a folder.", "properties": {"path": {"type": "string"}, "max_files": {"type": "integer"}, "max_chars": {"type": "integer"}}, "required": ["path"]},
    "write_text": {"description": "Write an authorized text file; existing file is backed up.", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    "make_dir": {"description": "Create a directory in an authorized write scope.", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "system_info": {"description": "Read basic local system information.", "properties": {}, "required": []},
    "list_processes": {"description": "List running processes.", "properties": {}, "required": []},
    "list_listeners": {"description": "List listening TCP ports.", "properties": {}, "required": []},
    "gpu_info": {"description": "Read NVIDIA GPU status using nvidia-smi.", "properties": {}, "required": []},
    "list_external_scopes": {"description": "List owner-approved external folders.", "properties": {}, "required": []},
    "grant_external_scope": {"description": "Request owner approval for one exact external folder.", "properties": {"path": {"type": "string"}, "access": {"type": "string", "enum": ["read", "read_write"]}}, "required": ["path", "access"]},
    "revoke_external_scope": {"description": "Request revocation of an external folder grant.", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "delete_path": {"description": "Request deletion of an authorized path.", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    "move_path": {"description": "Request move/rename inside authorized write scopes.", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]},
    "kill_process": {"description": "Request termination of a process by PID.", "properties": {"pid": {"type": "integer"}}, "required": ["pid"]},
    "start_program": {"description": "Request starting a program from an authorized path.", "properties": {"path": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}}, "required": ["path"]},
    "analyze_document": {"description": "Read and extract an authorized TXT/PDF/DOCX document.", "properties": {"path_value": {"type": "string"}, "question": {"type": "string"}}, "required": ["path_value"]},
    "analyze_image": {"description": "Analyze an authorized image with the configured local vision service.", "properties": {"path_value": {"type": "string"}, "question": {"type": "string"}}, "required": ["path_value"]},
    "analyze_audio": {"description": "Transcribe authorized audio locally with faster-whisper.", "properties": {"path_value": {"type": "string"}, "question": {"type": "string"}}, "required": ["path_value"]},
}


def schemas(names):
    result = []
    for name in names:
        spec = TOOL_SCHEMAS[name]
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": {
                    "type": "object",
                    "properties": spec["properties"],
                    "required": spec["required"],
                },
            },
        })
    return result


def select_tool_names(message):
    low = str(message or "").lower()
    names = set()

    if any(x in low for x in ("bestand", "file", "map", "folder", "repo", "project", "code", "script", "lees", "bekijk", "inspect", "analyse", "zoek", "search", "toon")):
        names.update(("list_dir", "read_file", "file_info", "search_text", "read_tree"))
    if any(x in low for x in ("schrijf", "write", "maak", "create", "wijzig", "change", "fix", "repareer")):
        names.update(("write_text", "make_dir"))
    if any(x in low for x in ("proces", "process", "pid")):
        names.update(("list_processes", "kill_process"))
    if any(x in low for x in ("poort", "port", "listener")):
        names.add("list_listeners")
    if any(x in low for x in ("gpu", "vram", "nvidia")):
        names.add("gpu_info")
    if any(x in low for x in ("systeem", "system", "computer", "pc")):
        names.add("system_info")
    if any(x in low for x in ("scope", "toegang", "external", "externe map")):
        names.update(("list_external_scopes", "grant_external_scope", "revoke_external_scope"))
    if any(x in low for x in ("delete", "verwijder", "move", "verplaats", "rename", "hernoem")):
        names.update(("delete_path", "move_path"))
    if any(x in low for x in ("start programma", "start program", "open programma", "open program")):
        names.add("start_program")
    if any(x in low for x in ("document", "pdf", "docx", "tekstbijlage")):
        names.add("analyze_document")
    if any(x in low for x in ("afbeelding", "image", "foto", "screenshot", "plaatje")):
        names.add("analyze_image")
    if any(x in low for x in ("audio", "voice", "stem", "geluid", "wav", "mp3")):
        names.add("analyze_audio")
    if "mediabijlage" in low or "bijlage" in low:
        names.update(("analyze_document", "analyze_image", "analyze_audio"))

    return sorted(names)
