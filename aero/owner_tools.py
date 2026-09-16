import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .audit import write as audit
from .config import PROJECT_ROOT
from .permissions import is_inside_project, prepare_path_for_approval, request_action

TEXT_EXTS = {".md", ".txt", ".py", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".csv", ".xml", ".ps1", ".cmd", ".bat"}


def _scope_label(path):
    return "BINNEN PROJECT" if is_inside_project(path) else "BUITEN PROJECT"


def _path(value):
    return prepare_path_for_approval(value)


def _request(kind, args, summary, paths=()):
    normalized = dict(args or {})
    labels = []
    for key, value in paths:
        target = _path(value)
        normalized[key] = str(target)
        labels.append(f"{_scope_label(target)}: {target}")
    detail = summary
    if labels:
        detail += "\n" + "\n".join(labels)
    if any("BUITEN PROJECT" in item for item in labels):
        detail += "\nLET OP: deze actie gaat buiten D:\\ProjectAI / D:\\Project AI."
    return request_action(kind, normalized, detail)


def execute(name, args):
    name = str(name)
    args = dict(args or {})
    if name == "list_dir":
        return _request(name, args, "Lees mapinhoud", (("path", args.get("path")),))
    if name == "file_info":
        return _request(name, args, "Lees bestandsmetadata", (("path", args.get("path")),))
    if name == "read_text":
        return _request(name, args, "Lees tekstbestand", (("path", args.get("path")),))
    if name == "read_bytes":
        return _request(name, args, "Lees binair bestand", (("path", args.get("path")),))
    if name == "search_text":
        return _request(name, args, f"Zoek tekst: {args.get('query', '')}", (("path", args.get("path")),))
    if name == "write_text":
        return _request(name, args, "Schrijf/vervang tekstbestand", (("path", args.get("path")),))
    if name == "append_text":
        return _request(name, args, "Voeg tekst toe aan bestand", (("path", args.get("path")),))
    if name == "replace_text":
        return _request(name, args, "Vervang tekst in bestand", (("path", args.get("path")),))
    if name == "write_bytes":
        return _request(name, args, "Schrijf/vervang binair bestand", (("path", args.get("path")),))
    if name == "make_dir":
        return _request(name, args, "Maak map", (("path", args.get("path")),))
    if name == "copy_path":
        return _request(name, args, "Kopieer bestand/map", (("src", args.get("src")), ("dst", args.get("dst"))))
    if name in {"move_path", "rename_path"}:
        return _request("move_path", args, "Verplaats/hernoem bestand/map", (("src", args.get("src")), ("dst", args.get("dst"))))
    if name == "delete_path":
        return _request(name, args, "Verwijder bestand/map", (("path", args.get("path")),))
    if name == "execute_file":
        return _request(name, args, "Voer lokaal bestand/programma uit", (("path", args.get("path")),))
    raise ValueError(f"unknown_tool:{name}")


def _backup(target):
    if not target.exists() or not target.is_file():
        return None
    backup = target.with_suffix(target.suffix + ".aero.bak")
    shutil.copy2(target, backup)
    return str(backup)


def _read_text(target, max_chars=250_000):
    if not target.is_file():
        raise ValueError("file_not_found")
    return target.read_text(encoding="utf-8", errors="replace")[: int(max_chars)]


def execute_approved(kind, args):
    args = dict(args or {})
    if kind == "list_dir":
        target = _path(args["path"])
        if not target.is_dir():
            raise ValueError("not_a_directory")
        result = [{"name": p.name, "path": str(p), "type": "dir" if p.is_dir() else "file", "size": p.stat().st_size if p.is_file() else None} for p in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))]
    elif kind == "file_info":
        target = _path(args["path"])
        result = {"path": str(target), "exists": target.exists(), "is_file": target.is_file(), "is_dir": target.is_dir(), "size": target.stat().st_size if target.exists() and target.is_file() else None, "modified": target.stat().st_mtime if target.exists() else None}
    elif kind == "read_text":
        target = _path(args["path"])
        result = {"path": str(target), "content": _read_text(target, args.get("max_chars", 250000))}
    elif kind == "read_bytes":
        target = _path(args["path"])
        if not target.is_file():
            raise ValueError("file_not_found")
        max_bytes = min(max(int(args.get("max_bytes", 2_000_000)), 1), 10_000_000)
        result = {"path": str(target), "base64": base64.b64encode(target.read_bytes()[:max_bytes]).decode("ascii")}
    elif kind == "search_text":
        root = _path(args["path"])
        query = str(args.get("query") or "").lower()
        limit = min(max(int(args.get("max_results", 50)), 1), 200)
        found = []
        files = [root] if root.is_file() else root.rglob("*")
        for item in files:
            if len(found) >= limit:
                break
            if not item.is_file() or item.suffix.lower() not in TEXT_EXTS:
                continue
            try:
                text = item.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if query in line.lower():
                    found.append({"path": str(item), "line": number, "text": line[:1000]})
                    if len(found) >= limit:
                        break
        result = found
    elif kind == "write_text":
        target = _path(args["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = _backup(target)
        target.write_text(str(args.get("content") or ""), encoding="utf-8")
        result = {"path": str(target), "backup": backup}
    elif kind == "append_text":
        target = _path(args["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = _backup(target)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(str(args.get("content") or ""))
        result = {"path": str(target), "backup": backup}
    elif kind == "replace_text":
        target = _path(args["path"])
        old = str(args.get("old") or "")
        new = str(args.get("new") or "")
        if not old:
            raise ValueError("old_text_required")
        text = _read_text(target, 10_000_000)
        count = text.count(old)
        if count == 0:
            raise ValueError("text_not_found")
        backup = _backup(target)
        target.write_text(text.replace(old, new, int(args.get("count", -1))), encoding="utf-8")
        result = {"path": str(target), "replacements_found": count, "backup": backup}
    elif kind == "write_bytes":
        target = _path(args["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = _backup(target)
        target.write_bytes(base64.b64decode(str(args.get("base64") or ""), validate=True))
        result = {"path": str(target), "backup": backup}
    elif kind == "make_dir":
        target = _path(args["path"])
        target.mkdir(parents=True, exist_ok=True)
        result = {"path": str(target)}
    elif kind == "copy_path":
        src, dst = _path(args["src"]), _path(args["dst"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=bool(args.get("merge", False)))
        else:
            shutil.copy2(src, dst)
        result = {"src": str(src), "dst": str(dst)}
    elif kind == "move_path":
        src, dst = _path(args["src"]), _path(args["dst"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        result = {"src": str(src), "dst": str(dst)}
    elif kind == "delete_path":
        target = _path(args["path"])
        if target == PROJECT_ROOT:
            raise PermissionError("project_root_delete_blocked")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        result = {"deleted": str(target)}
    elif kind == "execute_file":
        target = _path(args["path"])
        if not target.is_file():
            raise ValueError("executable_not_found")
        argv = [str(x) for x in (args.get("args") or [])]
        suffix = target.suffix.lower()
        if suffix == ".py":
            command = [sys.executable, str(target), *argv]
        elif suffix == ".ps1":
            command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target), *argv]
        elif suffix in {".cmd", ".bat"}:
            command = ["cmd", "/d", "/c", str(target), *argv]
        else:
            command = [str(target), *argv]
        proc = subprocess.run(command, cwd=str(target.parent), text=True, capture_output=True, timeout=min(max(int(args.get("timeout", 120)), 1), 900), check=False)
        result = {"returncode": proc.returncode, "stdout": proc.stdout[-100000:], "stderr": proc.stderr[-100000:], "path": str(target)}
    else:
        raise ValueError(f"unknown_approved_action:{kind}")

    audit("approved_action", kind=kind, args={k: v for k, v in args.items() if k not in {"content", "base64"}}, result=result if isinstance(result, dict) else {"items": len(result)})
    return result


TOOL_SCHEMAS = {
    "list_dir": ("Vraag toestemming om een map te lezen.", {"path": {"type": "string"}}, ["path"]),
    "file_info": ("Vraag toestemming om metadata van een pad te lezen.", {"path": {"type": "string"}}, ["path"]),
    "read_text": ("Vraag toestemming om een tekst/codebestand te lezen.", {"path": {"type": "string"}, "max_chars": {"type": "integer"}}, ["path"]),
    "read_bytes": ("Vraag toestemming om een binair bestand als base64 te lezen.", {"path": {"type": "string"}, "max_bytes": {"type": "integer"}}, ["path"]),
    "search_text": ("Vraag toestemming om tekst te zoeken in een bestand of map.", {"path": {"type": "string"}, "query": {"type": "string"}, "max_results": {"type": "integer"}}, ["path", "query"]),
    "write_text": ("Vraag toestemming om een tekstbestand te maken of volledig te vervangen.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "append_text": ("Vraag toestemming om tekst aan een bestand toe te voegen.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "replace_text": ("Vraag toestemming om tekst gericht te vervangen.", {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}, "count": {"type": "integer"}}, ["path", "old", "new"]),
    "write_bytes": ("Vraag toestemming om binaire inhoud te schrijven vanuit base64.", {"path": {"type": "string"}, "base64": {"type": "string"}}, ["path", "base64"]),
    "make_dir": ("Vraag toestemming om een map te maken.", {"path": {"type": "string"}}, ["path"]),
    "copy_path": ("Vraag toestemming om bestand/map te kopiëren.", {"src": {"type": "string"}, "dst": {"type": "string"}, "merge": {"type": "boolean"}}, ["src", "dst"]),
    "move_path": ("Vraag toestemming om bestand/map te verplaatsen of hernoemen.", {"src": {"type": "string"}, "dst": {"type": "string"}}, ["src", "dst"]),
    "rename_path": ("Vraag toestemming om bestand/map te hernoemen.", {"src": {"type": "string"}, "dst": {"type": "string"}}, ["src", "dst"]),
    "delete_path": ("Vraag toestemming om bestand/map te verwijderen.", {"path": {"type": "string"}}, ["path"]),
    "execute_file": ("Vraag toestemming om een .py/.ps1/.cmd/.bat of executable uit te voeren. Goedkeuring geldt ook voor het gedrag van dat programma.", {"path": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}, "timeout": {"type": "integer"}}, ["path"]),
}


def schemas(names):
    out = []
    for name in names:
        description, properties, required = TOOL_SCHEMAS[name]
        out.append({"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required}}})
    return out


def select_tool_names(message):
    low = str(message or "").lower()
    names = set()
    if any(x in low for x in ("lees", "read", "bekijk", "inspect", "bestand", "file", "map", "folder")):
        names.update(("list_dir", "file_info", "read_text", "read_bytes"))
    if any(x in low for x in ("zoek", "search", "vind", "find")):
        names.add("search_text")
    if any(x in low for x in ("schrijf", "write", "maak bestand", "create file", "overschrijf")):
        names.update(("write_text", "write_bytes"))
    if any(x in low for x in ("append", "toevoeg", "voeg toe")):
        names.add("append_text")
    if any(x in low for x in ("replace", "vervang", "wijzig", "change", "fix", "repareer")):
        names.update(("read_text", "replace_text", "write_text"))
    if any(x in low for x in ("maak map", "create folder", "mkdir")):
        names.add("make_dir")
    if any(x in low for x in ("copy", "kopieer")):
        names.add("copy_path")
    if any(x in low for x in ("move", "verplaats", "rename", "hernoem")):
        names.update(("move_path", "rename_path"))
    if any(x in low for x in ("delete", "verwijder", "wis")):
        names.add("delete_path")
    if any(x in low for x in ("execute", "voer uit", "run", "start script", "start programma")):
        names.add("execute_file")
    if not names and any(x in low for x in ("project", "code", "script", "repo")):
        names.update(("list_dir", "read_text", "search_text"))
    return sorted(names)
