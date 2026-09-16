import ast
import base64
import fnmatch
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .audit import write as audit
from .config import PROJECT_ROOT
from .media import analyze_audio, analyze_document, analyze_image
from .permissions import is_inside_project, prepare_path_for_approval, request_action

TEXT_EXTS = {
    ".md", ".txt", ".py", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".css", ".csv", ".xml",
    ".ps1", ".cmd", ".bat", ".log", ".env",
}


def _path(value):
    return prepare_path_for_approval(value)


def _scope_label(path):
    return "BINNEN PROJECT" if is_inside_project(path) else "BUITEN PROJECT"


def _request(kind, args, summary, paths=()):
    normalized = dict(args or {})
    labels = []
    for key, value in paths:
        target = _path(value if value not in {None, ""} else PROJECT_ROOT)
        normalized[key] = str(target)
        labels.append(f"{_scope_label(target)}: {target}")
    detail = str(summary)
    if labels:
        detail += "\n" + "\n".join(labels)
    if any("BUITEN PROJECT" in item for item in labels):
        detail += "\nLET OP: deze exacte actie gaat buiten de primaire projectscope en vereist jouw approval."
    if kind == "run_command":
        detail += "\nLET OP: dit is een exact shell-commando. Approval geldt voor het volledige gedrag van dat commando."
    return request_action(kind, normalized, detail)


def _run(command, cwd=None, timeout=120, input_text=None, env=None):
    proc = subprocess.run(
        [str(x) for x in command],
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=min(max(int(timeout), 1), 900),
        check=False,
        env=env,
    )
    return {"returncode": proc.returncode, "stdout": proc.stdout[-100000:], "stderr": proc.stderr[-100000:]}


def _powershell(script, timeout=60, input_text=None):
    if os.name != "nt":
        raise RuntimeError("windows_only")
    return _run(["powershell", "-NoProfile", "-Command", script], timeout=timeout, input_text=input_text)


def _backup(target):
    if not target.exists() or not target.is_file():
        return None
    backup = target.with_suffix(target.suffix + ".aero.bak")
    shutil.copy2(target, backup)
    return str(backup)


def _read_text(target, max_chars=250000):
    if not target.is_file():
        raise ValueError("file_not_found")
    return target.read_text(encoding="utf-8", errors="replace")[: min(max(int(max_chars), 1), 10_000_000)]


def _validate_text(path, content):
    suffix = path.suffix.lower()
    text = str(content)
    if suffix == ".py":
        compile(text, str(path), "exec")
        return {"ok": True, "checker": "python_compile"}
    if suffix == ".json":
        json.loads(text)
        return {"ok": True, "checker": "json_parser"}
    if suffix in {".js", ".mjs", ".cjs"} and shutil.which("node"):
        with tempfile.NamedTemporaryFile("w", suffix=suffix, encoding="utf-8", delete=False) as handle:
            handle.write(text)
            temp_name = handle.name
        try:
            result = _run(["node", "--check", temp_name], timeout=30)
            if result["returncode"] != 0:
                raise SyntaxError(result["stderr"] or result["stdout"])
            return {"ok": True, "checker": "node_check"}
        finally:
            Path(temp_name).unlink(missing_ok=True)
    return {"ok": True, "checker": "not_required"}


def _dotenv_load(path):
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _dotenv_save(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + ("\n" if values else ""), encoding="utf-8")


def _mask(value):
    value = str(value or "")
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * max(len(value) - 6, 4) + value[-3:]


def execute(name, args):
    name = str(name)
    args = dict(args or {})
    path_fields = {
        "list_dir": (("path", args.get("path")),), "file_info": (("path", args.get("path")),),
        "read_text": (("path", args.get("path")),), "read_bytes": (("path", args.get("path")),),
        "find_files": (("path", args.get("path")),), "search_text": (("path", args.get("path")),),
        "tail_log": (("path", args.get("path")),), "write_text": (("path", args.get("path")),),
        "append_text": (("path", args.get("path")),), "replace_text": (("path", args.get("path")),),
        "write_bytes": (("path", args.get("path")),), "make_dir": (("path", args.get("path")),),
        "copy_path": (("src", args.get("src")), ("dst", args.get("dst"))),
        "move_path": (("src", args.get("src")), ("dst", args.get("dst"))),
        "rename_path": (("src", args.get("src")), ("dst", args.get("dst"))),
        "delete_path": (("path", args.get("path")),), "execute_file": (("path", args.get("path")),),
        "syntax_check": (("path", args.get("path")),), "sqlite_query": (("path", args.get("path")),),
        "json_query": (("path", args.get("path")),), "zip_create": (("src", args.get("src")), ("dst", args.get("dst"))),
        "zip_extract": (("src", args.get("src")), ("dst", args.get("dst"))),
        "npm_check": (("cwd", args.get("cwd") or PROJECT_ROOT),), "npm_install": (("cwd", args.get("cwd") or PROJECT_ROOT),), "run_command": (("cwd", args.get("cwd") or PROJECT_ROOT),),
        "analyze_document": (("path_value", args.get("path_value")),), "analyze_image": (("path_value", args.get("path_value")),),
        "analyze_audio": (("path_value", args.get("path_value")),),
    }
    summaries = {
        "list_dir": "Lees mapinhoud", "file_info": "Lees bestandsmetadata", "read_text": "Lees tekstbestand",
        "read_bytes": "Lees binair bestand", "find_files": "Zoek bestanden op naam/extensie", "search_text": "Zoek tekst in bestanden",
        "tail_log": "Lees laatste regels van logbestand", "write_text": "Schrijf/vervang tekstbestand", "append_text": "Voeg tekst toe",
        "replace_text": "Vervang tekst gericht", "write_bytes": "Schrijf binair bestand", "make_dir": "Maak map",
        "copy_path": "Kopieer bestand/map", "move_path": "Verplaats bestand/map", "rename_path": "Hernoem bestand/map",
        "delete_path": "Verwijder bestand/map", "execute_file": "Voer bestand/programma uit", "env_get": "Lees omgevingsvariabele",
        "env_set": "Stel omgevingsvariabele in", "env_delete": "Verwijder omgevingsvariabele", "pip_check": "Controleer Python-package",
        "pip_install": "Installeer Python-package(s)", "npm_check": "Controleer npm dependencies", "npm_install": "Installeer npm dependencies",
        "syntax_check": "Controleer code-syntaxis", "sqlite_query": "Voer SQLite-query uit", "json_query": "Lees JSON-datapad",
        "resource_monitor": "Lees CPU/RAM-belasting", "gpu_info": "Lees GPU-status", "list_processes": "Lees processenlijst",
        "process_status": "Lees processtatus", "start_process": "Start achtergrondproces", "kill_process": "Stop proces",
        "zip_create": "Maak ZIP-archief", "zip_extract": "Pak ZIP-archief uit", "port_check": "Controleer netwerkpoort",
        "ping_host": "Ping host", "http_request": "Voer HTTP/API-request uit", "clipboard_read": "Lees klembord",
        "clipboard_write": "Schrijf klembord", "run_command": f"Voer shell-commando uit: {args.get('command', '')}",
        "service_status": "Lees Windows-service", "service_start": "Start Windows-service", "service_stop": "Stop Windows-service",
        "service_restart": "Herstart Windows-service",
        "analyze_document": "Analyseer document", "analyze_image": "Analyseer afbeelding", "analyze_audio": "Analyseer audio",
    }
    if name in {"env_get", "env_set", "env_delete"} and str(args.get("scope") or "dotenv") == "dotenv":
        path = args.get("path") or str(PROJECT_ROOT / ".env")
        path_fields[name] = (("path", path),)
    if name == "start_process":
        path_fields[name] = (("path", args.get("path")), ("cwd", args.get("cwd") or Path(args.get("path") or PROJECT_ROOT).parent))
    if name not in summaries:
        raise ValueError(f"unknown_tool:{name}")
    return _request(name, args, summaries[name], path_fields.get(name, ()))


def execute_approved(kind, args):
    args = dict(args or {})
    result = _execute_approved(kind, args)
    safe_args = {k: v for k, v in args.items() if k not in {"content", "base64", "value", "body"}}
    audit("approved_action", kind=kind, args=safe_args, result=result if isinstance(result, dict) else {"items": len(result) if hasattr(result, "__len__") else 1})
    return result


def _execute_approved(kind, args):
    if kind == "list_dir":
        target = _path(args["path"])
        if not target.is_dir(): raise ValueError("not_a_directory")
        return [{"name": p.name, "path": str(p), "type": "dir" if p.is_dir() else "file", "size": p.stat().st_size if p.is_file() else None} for p in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))]
    if kind == "file_info":
        target = _path(args["path"]); exists = target.exists()
        return {"path": str(target), "exists": exists, "is_file": target.is_file(), "is_dir": target.is_dir(), "size": target.stat().st_size if exists and target.is_file() else None, "modified": target.stat().st_mtime if exists else None}
    if kind == "read_text":
        target = _path(args["path"]); return {"path": str(target), "content": _read_text(target, args.get("max_chars", 250000))}
    if kind == "read_bytes":
        target = _path(args["path"]); max_bytes = min(max(int(args.get("max_bytes", 2_000_000)), 1), 10_000_000)
        if not target.is_file(): raise ValueError("file_not_found")
        return {"path": str(target), "base64": base64.b64encode(target.read_bytes()[:max_bytes]).decode("ascii")}
    if kind == "find_files":
        root = _path(args["path"]); pattern = str(args.get("pattern") or "*"); limit = min(max(int(args.get("max_results", 200)), 1), 2000)
        files = [root] if root.is_file() else root.rglob("*")
        found = []
        for item in files:
            if len(found) >= limit: break
            if fnmatch.fnmatch(item.name.lower(), pattern.lower()):
                found.append({"path": str(item), "type": "dir" if item.is_dir() else "file"})
        return found
    if kind == "search_text":
        root = _path(args["path"]); query = str(args.get("query") or "").lower(); limit = min(max(int(args.get("max_results", 50)), 1), 500)
        found = []; files = [root] if root.is_file() else root.rglob("*")
        for item in files:
            if len(found) >= limit: break
            if not item.is_file() or item.suffix.lower() not in TEXT_EXTS: continue
            try: text = item.read_text(encoding="utf-8", errors="replace")
            except Exception: continue
            for number, line in enumerate(text.splitlines(), 1):
                if query in line.lower():
                    found.append({"path": str(item), "line": number, "text": line[:1000]})
                    if len(found) >= limit: break
        return found
    if kind == "tail_log":
        target = _path(args["path"]); lines = min(max(int(args.get("lines", 100)), 1), 5000)
        content = target.read_text(encoding="utf-8", errors="replace").splitlines()
        return {"path": str(target), "lines": content[-lines:]}
    if kind in {"write_text", "append_text", "replace_text"}:
        target = _path(args["path"]); target.parent.mkdir(parents=True, exist_ok=True); backup = _backup(target)
        if kind == "write_text":
            content = str(args.get("content") or ""); check = _validate_text(target, content); target.write_text(content, encoding="utf-8")
            return {"path": str(target), "backup": backup, "syntax": check}
        if kind == "append_text":
            old = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""; content = old + str(args.get("content") or ""); check = _validate_text(target, content); target.write_text(content, encoding="utf-8")
            return {"path": str(target), "backup": backup, "syntax": check}
        old_value = str(args.get("old") or ""); new_value = str(args.get("new") or "")
        if not old_value: raise ValueError("old_text_required")
        text = _read_text(target, 10_000_000); count = text.count(old_value)
        if count == 0: raise ValueError("text_not_found")
        updated = text.replace(old_value, new_value, int(args.get("count", -1))); check = _validate_text(target, updated); target.write_text(updated, encoding="utf-8")
        return {"path": str(target), "replacements_found": count, "backup": backup, "syntax": check}
    if kind == "write_bytes":
        target = _path(args["path"]); target.parent.mkdir(parents=True, exist_ok=True); backup = _backup(target); target.write_bytes(base64.b64decode(str(args.get("base64") or ""), validate=True)); return {"path": str(target), "backup": backup}
    if kind == "make_dir":
        target = _path(args["path"]); target.mkdir(parents=True, exist_ok=True); return {"path": str(target)}
    if kind == "copy_path":
        src, dst = _path(args["src"]), _path(args["dst"]); dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=bool(args.get("merge", False))) if src.is_dir() else shutil.copy2(src, dst)
        return {"src": str(src), "dst": str(dst)}
    if kind in {"move_path", "rename_path"}:
        src, dst = _path(args["src"]), _path(args["dst"]); dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst)); return {"src": str(src), "dst": str(dst)}
    if kind == "delete_path":
        target = _path(args["path"])
        if target == PROJECT_ROOT: raise PermissionError("project_root_delete_blocked")
        if target.is_dir(): shutil.rmtree(target)
        elif target.exists(): target.unlink()
        return {"deleted": str(target)}
    if kind == "execute_file":
        target = _path(args["path"])
        if not target.is_file(): raise ValueError("executable_not_found")
        if target.suffix.lower() == ".py": compile(target.read_text(encoding="utf-8"), str(target), "exec")
        argv = [str(x) for x in (args.get("args") or [])]; suffix = target.suffix.lower()
        if suffix == ".py": command = [sys.executable, str(target), *argv]
        elif suffix == ".ps1": command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target), *argv]
        elif suffix in {".cmd", ".bat"}: command = ["cmd", "/d", "/c", str(target), *argv]
        else: command = [str(target), *argv]
        result = _run(command, cwd=target.parent, timeout=args.get("timeout", 120)); result["path"] = str(target); return result
    if kind in {"env_get", "env_set", "env_delete"}:
        scope = str(args.get("scope") or "dotenv").lower(); name = str(args.get("name") or "").strip()
        if not name: raise ValueError("env_name_required")
        reveal = bool(args.get("reveal", False))
        if scope == "dotenv":
            path = _path(args.get("path") or PROJECT_ROOT / ".env"); values = _dotenv_load(path)
            if kind == "env_get":
                value = values.get(name); return {"scope": scope, "name": name, "exists": name in values, "value": value if reveal else _mask(value)}
            backup = _backup(path)
            if kind == "env_set": values[name] = str(args.get("value") or "")
            else: values.pop(name, None)
            _dotenv_save(path, values); return {"scope": scope, "name": name, "path": str(path), "backup": backup}
        if scope == "process":
            if kind == "env_get":
                value = os.environ.get(name); return {"scope": scope, "name": name, "exists": value is not None, "value": value if reveal else _mask(value)}
            if kind == "env_set": os.environ[name] = str(args.get("value") or "")
            else: os.environ.pop(name, None)
            return {"scope": scope, "name": name, "updated": True}
        if scope == "user" and os.name == "nt":
            escaped = name.replace("'", "''")
            if kind == "env_get":
                value = _powershell(f"[Environment]::GetEnvironmentVariable('{escaped}','User')")["stdout"].strip(); return {"scope": scope, "name": name, "exists": bool(value), "value": value if reveal else _mask(value)}
            value = None if kind == "env_delete" else str(args.get("value") or "")
            ps_value = "$null" if value is None else "'" + value.replace("'", "''") + "'"
            return _powershell(f"[Environment]::SetEnvironmentVariable('{escaped}',{ps_value},'User')")
        raise ValueError("invalid_env_scope")
    if kind == "pip_check":
        package = str(args.get("package") or "").strip(); return _run([sys.executable, "-m", "pip", "show", package], timeout=60)
    if kind == "pip_install":
        packages = [str(x) for x in (args.get("packages") or [])]
        if not packages: raise ValueError("packages_required")
        return _run([sys.executable, "-m", "pip", "install", *packages], timeout=args.get("timeout", 600))
    if kind == "npm_check":
        cwd = _path(args.get("cwd") or PROJECT_ROOT); package = str(args.get("package") or "").strip(); command = ["npm", "ls", "--depth=0"] + ([package] if package else []); return _run(command, cwd=cwd, timeout=120)
    if kind == "npm_install":
        cwd = _path(args.get("cwd") or PROJECT_ROOT); packages = [str(x) for x in (args.get("packages") or [])]; command = ["npm", "install", *packages]; return _run(command, cwd=cwd, timeout=args.get("timeout", 600))
    if kind == "syntax_check":
        target = _path(args["path"]); content = target.read_text(encoding="utf-8", errors="replace"); return {"path": str(target), **_validate_text(target, content)}
    if kind == "sqlite_query":
        target = _path(args["path"]); target.parent.mkdir(parents=True, exist_ok=True); query = str(args.get("query") or ""); params = list(args.get("params") or [])
        with sqlite3.connect(target, timeout=30) as db:
            db.row_factory = sqlite3.Row; cur = db.execute(query, params); rows = [dict(row) for row in cur.fetchmany(min(max(int(args.get("max_rows", 200)), 1), 2000))] if cur.description else []; db.commit()
            return {"path": str(target), "rows": rows, "rowcount": cur.rowcount}
    if kind == "json_query":
        target = _path(args["path"]); data = json.loads(target.read_text(encoding="utf-8")); dotted = str(args.get("key") or "").strip()
        value = data
        if dotted:
            for part in dotted.split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
        return {"path": str(target), "key": dotted, "value": value}
    if kind == "resource_monitor":
        if os.name == "nt":
            script = "$cpu=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; $os=Get-CimInstance Win32_OperatingSystem; [pscustomobject]@{cpu_percent=$cpu;memory_total_bytes=[int64]$os.TotalVisibleMemorySize*1024;memory_free_bytes=[int64]$os.FreePhysicalMemory*1024} | ConvertTo-Json -Compress"
            raw = _powershell(script)["stdout"].strip(); return json.loads(raw or "{}")
        load = os.getloadavg(); return {"load_1m": load[0], "load_5m": load[1], "load_15m": load[2]}
    if kind == "gpu_info":
        return _run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"], timeout=30)
    if kind == "list_processes":
        if os.name == "nt":
            raw = _powershell("Get-Process | Select-Object Id,ProcessName,CPU,WorkingSet64,Path | ConvertTo-Json -Compress")["stdout"].strip(); return json.loads(raw or "[]")
        return _run(["ps", "-eo", "pid,comm,%cpu,rss"])
    if kind == "process_status":
        pid = int(args["pid"])
        if os.name == "nt":
            raw = _powershell(f"Get-Process -Id {pid} -ErrorAction Stop | Select-Object Id,ProcessName,CPU,WorkingSet64,Path | ConvertTo-Json -Compress")["stdout"].strip(); return json.loads(raw or "{}")
        return _run(["ps", "-p", str(pid), "-o", "pid,comm,%cpu,rss"])
    if kind == "start_process":
        target = _path(args["path"]); cwd = _path(args.get("cwd") or target.parent); argv = [str(x) for x in (args.get("args") or [])]
        suffix = target.suffix.lower(); command = [sys.executable, str(target), *argv] if suffix == ".py" else (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target), *argv] if suffix == ".ps1" else [str(target), *argv])
        flags = 0
        if os.name == "nt": flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        proc = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        return {"pid": proc.pid, "path": str(target), "cwd": str(cwd)}
    if kind == "kill_process":
        pid = int(args["pid"])
        if pid in {0, 4, os.getpid()}: raise PermissionError("critical_process_blocked")
        return _run(["taskkill", "/PID", str(pid), "/F"] if os.name == "nt" else ["kill", "-TERM", str(pid)], timeout=30)
    if kind == "zip_create":
        src, dst = _path(args["src"]), _path(args["dst"]); dst.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if src.is_dir():
                for item in src.rglob("*"):
                    if item.is_file(): archive.write(item, item.relative_to(src.parent))
            else: archive.write(src, src.name)
        return {"src": str(src), "dst": str(dst), "size": dst.stat().st_size}
    if kind == "zip_extract":
        src, dst = _path(args["src"]), _path(args["dst"]); dst.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "r") as archive:
            for member in archive.infolist():
                out = (dst / member.filename).resolve(strict=False)
                if not (out == dst or dst in out.parents): raise PermissionError("zip_path_escape_blocked")
            archive.extractall(dst)
        return {"src": str(src), "dst": str(dst)}
    if kind == "port_check":
        host = str(args.get("host") or "127.0.0.1"); port = int(args["port"]); timeout = float(args.get("timeout", 3))
        try:
            with socket.create_connection((host, port), timeout=timeout): return {"host": host, "port": port, "open": True}
        except OSError as exc: return {"host": host, "port": port, "open": False, "error": str(exc)}
    if kind == "ping_host":
        host = str(args["host"]); return _run(["ping", "-n" if os.name == "nt" else "-c", "1", host], timeout=args.get("timeout", 15))
    if kind == "http_request":
        url = str(args["url"]); method = str(args.get("method") or "GET").upper(); headers = {str(k): str(v) for k, v in dict(args.get("headers") or {}).items()}; body = args.get("body"); data = None if body is None else str(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=min(max(int(args.get("timeout", 30)), 1), 120)) as response:
                content = response.read(min(max(int(args.get("max_bytes", 200000)), 1), 2_000_000)).decode("utf-8", errors="replace")
                return {"url": response.geturl(), "status": response.status, "headers": dict(response.headers.items()), "body": content}
        except urllib.error.HTTPError as exc:
            return {"url": url, "status": exc.code, "body": exc.read(200000).decode("utf-8", errors="replace")}
    if kind == "clipboard_read":
        if os.name != "nt": raise RuntimeError("windows_only")
        return {"text": _powershell("Get-Clipboard -Raw")["stdout"]}
    if kind == "clipboard_write":
        if os.name != "nt": raise RuntimeError("windows_only")
        return _powershell("$input | Set-Clipboard", input_text=str(args.get("text") or ""))
    if kind == "run_command":
        cwd = _path(args.get("cwd") or PROJECT_ROOT); command = str(args.get("command") or "").strip()
        if not command: raise ValueError("command_required")
        if os.name == "nt": return _run(["powershell", "-NoProfile", "-Command", command], cwd=cwd, timeout=args.get("timeout", 120))
        return _run(["/bin/sh", "-lc", command], cwd=cwd, timeout=args.get("timeout", 120))
    if kind.startswith("service_"):
        if os.name != "nt": raise RuntimeError("windows_only")
        name = str(args.get("name") or "").replace("'", "''")
        if kind == "service_status": script = f"Get-Service -Name '{name}' | Select-Object Name,DisplayName,Status,StartType | ConvertTo-Json -Compress"
        elif kind == "service_start": script = f"Start-Service -Name '{name}' -ErrorAction Stop; Get-Service -Name '{name}' | ConvertTo-Json -Compress"
        elif kind == "service_stop": script = f"Stop-Service -Name '{name}' -Force -ErrorAction Stop; Get-Service -Name '{name}' | ConvertTo-Json -Compress"
        else: script = f"Restart-Service -Name '{name}' -Force -ErrorAction Stop; Get-Service -Name '{name}' | ConvertTo-Json -Compress"
        return _powershell(script, timeout=60)
    if kind == "analyze_document": return analyze_document(args["path_value"], args.get("question", ""))
    if kind == "analyze_image": return analyze_image(args["path_value"], args.get("question", "Beschrijf wat je ziet."))
    if kind == "analyze_audio": return analyze_audio(args["path_value"], args.get("question", "Transcribeer deze audio."))
    raise ValueError(f"unknown_approved_action:{kind}")


def _s(description, properties=None, required=None):
    return (description, properties or {}, required or [])


TOOL_SCHEMAS = {
    "list_dir": _s("Mapinhoud opvragen.", {"path": {"type": "string"}}, ["path"]),
    "file_info": _s("Bestandsmetadata opvragen.", {"path": {"type": "string"}}, ["path"]),
    "read_text": _s("Tekst/code lezen.", {"path": {"type": "string"}, "max_chars": {"type": "integer"}}, ["path"]),
    "read_bytes": _s("Binair bestand lezen als base64.", {"path": {"type": "string"}, "max_bytes": {"type": "integer"}}, ["path"]),
    "find_files": _s("Recursief bestanden/mappen zoeken op glob-patroon.", {"path": {"type": "string"}, "pattern": {"type": "string"}, "max_results": {"type": "integer"}}, ["path", "pattern"]),
    "search_text": _s("Recursief tekst zoeken in bestanden.", {"path": {"type": "string"}, "query": {"type": "string"}, "max_results": {"type": "integer"}}, ["path", "query"]),
    "tail_log": _s("Laatste regels van log/tekstbestand lezen.", {"path": {"type": "string"}, "lines": {"type": "integer"}}, ["path"]),
    "write_text": _s("Tekstbestand maken/vervangen met syntax-precheck voor Python/JSON/JS.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "append_text": _s("Tekst toevoegen met syntax-precheck waar mogelijk.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "replace_text": _s("Gericht tekst vervangen met syntax-precheck.", {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}, "count": {"type": "integer"}}, ["path", "old", "new"]),
    "write_bytes": _s("Binaire inhoud schrijven vanuit base64.", {"path": {"type": "string"}, "base64": {"type": "string"}}, ["path", "base64"]),
    "make_dir": _s("Map maken.", {"path": {"type": "string"}}, ["path"]),
    "copy_path": _s("Bestand/map kopiëren.", {"src": {"type": "string"}, "dst": {"type": "string"}, "merge": {"type": "boolean"}}, ["src", "dst"]),
    "move_path": _s("Bestand/map verplaatsen.", {"src": {"type": "string"}, "dst": {"type": "string"}}, ["src", "dst"]),
    "rename_path": _s("Bestand/map hernoemen.", {"src": {"type": "string"}, "dst": {"type": "string"}}, ["src", "dst"]),
    "delete_path": _s("Bestand/map verwijderen.", {"path": {"type": "string"}}, ["path"]),
    "execute_file": _s("Script/programmaatje synchroon uitvoeren.", {"path": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}, "timeout": {"type": "integer"}}, ["path"]),
    "env_get": _s("Omgevingsvariabele of .env-waarde lezen; standaard gemaskeerd.", {"name": {"type": "string"}, "scope": {"type": "string", "enum": ["dotenv", "process", "user"]}, "path": {"type": "string"}, "reveal": {"type": "boolean"}}, ["name"]),
    "env_set": _s("Omgevingsvariabele of .env-waarde instellen.", {"name": {"type": "string"}, "value": {"type": "string"}, "scope": {"type": "string", "enum": ["dotenv", "process", "user"]}, "path": {"type": "string"}}, ["name", "value"]),
    "env_delete": _s("Omgevingsvariabele verwijderen.", {"name": {"type": "string"}, "scope": {"type": "string", "enum": ["dotenv", "process", "user"]}, "path": {"type": "string"}}, ["name"]),
    "pip_check": _s("Python-package controleren.", {"package": {"type": "string"}}, ["package"]),
    "pip_install": _s("Python-package(s) installeren met pip.", {"packages": {"type": "array", "items": {"type": "string"}}, "timeout": {"type": "integer"}}, ["packages"]),
    "npm_check": _s("npm-dependencies controleren.", {"cwd": {"type": "string"}, "package": {"type": "string"}}, []),
    "npm_install": _s("npm-dependencies installeren.", {"cwd": {"type": "string"}, "packages": {"type": "array", "items": {"type": "string"}}, "timeout": {"type": "integer"}}, []),
    "syntax_check": _s("Python/JSON/JS-syntaxis controleren.", {"path": {"type": "string"}}, ["path"]),
    "sqlite_query": _s("SQLite-query uitvoeren, inclusief writes.", {"path": {"type": "string"}, "query": {"type": "string"}, "params": {"type": "array"}, "max_rows": {"type": "integer"}}, ["path", "query"]),
    "json_query": _s("JSON-bestand uitlezen via dotted key.", {"path": {"type": "string"}, "key": {"type": "string"}}, ["path"]),
    "resource_monitor": _s("CPU- en RAM-belasting lezen."),
    "gpu_info": _s("NVIDIA GPU/VRAM/status lezen."),
    "list_processes": _s("Actieve processen tonen."),
    "process_status": _s("Processtatus op PID lezen.", {"pid": {"type": "integer"}}, ["pid"]),
    "start_process": _s("Achtergrondproces starten.", {"path": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}, "cwd": {"type": "string"}}, ["path"]),
    "kill_process": _s("Proces geforceerd stoppen.", {"pid": {"type": "integer"}}, ["pid"]),
    "zip_create": _s("ZIP-archief maken.", {"src": {"type": "string"}, "dst": {"type": "string"}}, ["src", "dst"]),
    "zip_extract": _s("ZIP-archief uitpakken.", {"src": {"type": "string"}, "dst": {"type": "string"}}, ["src", "dst"]),
    "port_check": _s("TCP-poort controleren.", {"host": {"type": "string"}, "port": {"type": "integer"}, "timeout": {"type": "number"}}, ["port"]),
    "ping_host": _s("Host pingen.", {"host": {"type": "string"}, "timeout": {"type": "integer"}}, ["host"]),
    "http_request": _s("HTTP/API-request uitvoeren.", {"url": {"type": "string"}, "method": {"type": "string"}, "headers": {"type": "object"}, "body": {"type": "string"}, "timeout": {"type": "integer"}, "max_bytes": {"type": "integer"}}, ["url"]),
    "clipboard_read": _s("Windows-klembord lezen."),
    "clipboard_write": _s("Windows-klembord schrijven.", {"text": {"type": "string"}}, ["text"]),
    "run_command": _s("Exact PowerShell/cmd-equivalent shellcommando uitvoeren na approval.", {"command": {"type": "string"}, "cwd": {"type": "string"}, "timeout": {"type": "integer"}}, ["command"]),
    "service_status": _s("Windows-service status lezen.", {"name": {"type": "string"}}, ["name"]),
    "service_start": _s("Windows-service starten.", {"name": {"type": "string"}}, ["name"]),
    "service_stop": _s("Windows-service stoppen.", {"name": {"type": "string"}}, ["name"]),
    "service_restart": _s("Windows-service herstarten.", {"name": {"type": "string"}}, ["name"]),
    "analyze_document": _s("Document lokaal analyseren.", {"path_value": {"type": "string"}, "question": {"type": "string"}}, ["path_value"]),
    "analyze_image": _s("Afbeelding lokaal analyseren.", {"path_value": {"type": "string"}, "question": {"type": "string"}}, ["path_value"]),
    "analyze_audio": _s("Audio lokaal analyseren/transcriberen.", {"path_value": {"type": "string"}, "question": {"type": "string"}}, ["path_value"]),
}


def schemas(names):
    return [{"type": "function", "function": {"name": name, "description": TOOL_SCHEMAS[name][0], "parameters": {"type": "object", "properties": TOOL_SCHEMAS[name][1], "required": TOOL_SCHEMAS[name][2]}}} for name in names]


def select_tool_names(message):
    low = str(message or "").lower(); names = set()
    groups = [
        (("bestand", "file", "map", "folder", "lees", "read", "inspect", "project", "repo"), {"list_dir", "file_info", "read_text", "read_bytes", "find_files"}),
        (("zoek", "search", "find", "grep", "trefwoord"), {"find_files", "search_text"}),
        (("log", "tail", "foutmelding"), {"tail_log", "search_text", "read_text"}),
        (("schrijf", "write", "wijzig", "replace", "vervang", "append", "fix", "repareer"), {"write_text", "append_text", "replace_text", "syntax_check"}),
        (("env", ".env", "omgeving", "api-key", "api key", "poortnummer"), {"env_get", "env_set", "env_delete"}),
        (("pip", "python package", "dependency", "dependencies", "importerror", "module not found"), {"pip_check", "pip_install"}),
        (("npm", "node package", "package.json"), {"npm_check", "npm_install"}),
        (("syntax", "compile", "linter", "py_compile"), {"syntax_check"}),
        (("sqlite", "database", "db", "json-db", "json db"), {"sqlite_query", "json_query"}),
        (("cpu", "ram", "memory", "geheugen", "belasting", "resource"), {"resource_monitor"}),
        (("gpu", "vram", "nvidia"), {"gpu_info"}),
        (("proces", "process", "pid", "server starten", "server stoppen"), {"list_processes", "process_status", "start_process", "kill_process"}),
        (("zip", "archive", "archief", "backup", "uitpakken"), {"zip_create", "zip_extract"}),
        (("poort", "port", "ping", "verbinding", "listener"), {"port_check", "ping_host"}),
        (("http", "https", "api", "url", "website", "health"), {"http_request", "port_check"}),
        (("clipboard", "klembord"), {"clipboard_read", "clipboard_write"}),
        (("shell", "terminal", "powershell", "cmd", "command", "commando"), {"run_command"}),
        (("service", "dienst", "windows service"), {"service_status", "service_start", "service_stop", "service_restart"}),
        (("document", "pdf", "docx"), {"analyze_document"}),
        (("afbeelding", "image", "foto", "screenshot"), {"analyze_image"}),
        (("audio", "voice", "stem", "wav", "mp3"), {"analyze_audio"}),
        (("execute", "voer uit", "run script", "start programma"), {"execute_file", "start_process"}),
        (("copy", "kopieer", "move", "verplaats", "rename", "hernoem", "delete", "verwijder", "mkdir"), {"copy_path", "move_path", "rename_path", "delete_path", "make_dir"}),
    ]
    for words, tools in groups:
        if any(word in low for word in words): names.update(tools)
    if any(word in low for word in ("diagnose", "onderzoek", "probleem", "werkt niet", "alles controleren")):
        names.update({"resource_monitor", "gpu_info", "list_processes", "port_check", "tail_log", "find_files", "search_text", "syntax_check"})
    return sorted(names)
