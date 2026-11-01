"""Explicit, repeatable Qt profile import. Original Qt files are never modified."""
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from clinical_studio.manuscripts import WorkspaceStore, due_date

def legacy_dir():
    if sys.platform == "darwin": return Path.home() / "Library/Application Support/ClinicalStudio/科研数据工具集"
    if sys.platform == "win32": return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "ClinicalStudio/科研数据工具集"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ClinicalStudio/科研数据工具集"

def inspect(directory=None):
    folder = Path(directory).expanduser() if directory else legacy_dir()
    return dict(directory=str(folder), available=any((folder / n).is_file() for n in ("todos.json", "manuscript-workspace.json")))

def migrate(profile, directory=None):
    folder = Path(directory).expanduser() if directory else legacy_dir()
    source = folder / "todos.json"
    config = folder / "manuscript-workspace.json"
    tasks = []
    workspace = None
    if source.exists():
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or not isinstance(payload.get("tasks"), list): raise ValueError("旧版待办格式无效")
        seen = set()
        for t in payload["tasks"]:
            if not isinstance(t.get("id"), str) or not t["id"] or t["id"] in seen: raise ValueError("旧版待办编号无效")
            seen.add(t["id"])
            if not isinstance(t.get("name"), str) or not t["name"].strip() or len(t["name"]) > 300: raise ValueError("旧版待办文字无效")
            if t.get("priority") not in ("high", "normal", "low"): raise ValueError("旧版待办优先级无效")
            if type(t.get("completed")) is not bool or type(t.get("deleted", False)) is not bool: raise ValueError("旧版待办状态无效")
            tasks.append(("personal:qt:" + t["id"], t["name"].strip(), t["priority"], due_date(t.get("due_date")), int(t["completed"]), int(t.get("deleted", False))))
    if config.exists() and not (profile / "workspace.json").exists():
        payload = json.loads(config.read_text(encoding="utf-8"))
        if payload.get("version") != 1: raise ValueError("旧版工作空间配置无效")
        workspace = str(WorkspaceStore(payload["root"], create=False).root)
    if not source.exists() and not config.exists(): raise ValueError("所选目录没有 Qt 待办或工作空间配置")
    backup = profile / "migration-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True)
    for file in (source, config):
        if file.exists(): shutil.copy2(file, backup / file.name)
    with sqlite3.connect(profile / "personal.sqlite3") as db:
        db.execute("CREATE TABLE IF NOT EXISTS todos (id TEXT PRIMARY KEY, text TEXT, priority TEXT, due_date TEXT, completed INTEGER, deleted INTEGER)")
        before = db.total_changes
        db.executemany("INSERT OR IGNORE INTO todos VALUES(?,?,?,?,?,?)", tasks)
        imported = db.total_changes - before
    if workspace:
        # Exclusive creation leaves an existing V3 selection untouched.
        with (profile / "workspace.json").open("x", encoding="utf-8") as stream: json.dump(dict(root=workspace), stream, ensure_ascii=False)
    return dict(imported=imported, workspace=workspace, backup=str(backup))
