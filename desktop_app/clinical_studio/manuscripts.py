"""Portable manuscript index and compensating filesystem transactions.

Only explicitly created tasks and received files are indexed; existing folders
are never scanned. Paths in the database are relative to the selected root.
"""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import uuid

CATEGORIES = ('原稿', '原始数据', '图表', '修改稿', '交付')
STATUSES = ('进行中', '待补资料', '返修中', '待交付', '已完成')
PRIORITIES = ('high', 'normal', 'low')
INBOX = '待归档材料'


def now():
    return datetime.now(timezone.utc).isoformat()


def component(value, fallback=None):
    value = unicodedata.normalize('NFC', str(value).strip())
    if not value and fallback:
        value = fallback
    if not value or len(value) > 100 or len(value.encode('utf-8')) > 240 or value in ('.', '..'):
        raise ValueError('名称不能为空，且最多 100 个字符（UTF-8 不超过 240 字节）。')
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value.endswith(('.', ' ')):
        raise ValueError('名称不能包含路径分隔符或 Windows 不支持的字符。')
    if re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', value.split('.')[0]):
        raise ValueError('这个名称是系统保留名称，请换一个名称。')
    return value


def due_date(value):
    if value in (None, ''):
        return None
    return date.fromisoformat(value).isoformat()


def config_path():
    override = os.environ.get('CLINICAL_STUDIO_WORKSPACE_CONFIG')
    if override:
        return Path(override)
    # Verification processes must never open the user's real workspace.
    if os.environ.get('CLINICAL_STUDIO_TODO_PATH'):
        return Path(os.environ['CLINICAL_STUDIO_TODO_PATH']).parent / 'workspace-config.json'
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / 'manuscript-workspace.json'


def configured_workspace():
    path = config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('root'), str):
            raise ValueError()
        return WorkspaceStore(data['root'], create=False)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('工作空间配置无法读取，原文件已保留。') from exc


def enable_workspace(root):
    store = WorkspaceStore(root)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.workspace-config-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(dict(version=1, root=str(store.root)), stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return store


class WorkspaceStore:
    def __init__(self, root, create=True):
        self.root = Path(root).expanduser().resolve()
        self.path = self.root / '.manuscripts.sqlite3'
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        elif not self.root.is_dir() or not self.path.is_file():
            raise ValueError('工作空间目录或索引已不可用，请重新选择原工作空间。')
        if self.path.is_symlink():
            raise ValueError('工作空间索引不能是符号链接。')
        with self.connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('工作空间由较新的版本创建，请升级应用。')
            if version == 0:
                db.executescript('''
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY, client TEXT NOT NULL, name TEXT NOT NULL,
                        created_date TEXT NOT NULL, due_date TEXT, status TEXT NOT NULL,
                        tags TEXT NOT NULL, notes TEXT NOT NULL, directory TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL, UNIQUE(client,created_date,name));
                    CREATE TABLE files (
                        id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id),
                        category TEXT, path TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
                        sha256 TEXT NOT NULL, size INTEGER NOT NULL, received_at TEXT NOT NULL,
                        batch TEXT NOT NULL);
                    CREATE INDEX files_digest ON files(sha256,size);
                    CREATE TABLE todos (
                        id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
                        text TEXT NOT NULL, priority TEXT NOT NULL, due_date TEXT,
                        completed INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL);
                    CREATE TABLE todo_files (
                        todo_id TEXT REFERENCES todos(id), file_id TEXT REFERENCES files(id),
                        PRIMARY KEY(todo_id,file_id));
                    CREATE TABLE events (
                        id INTEGER PRIMARY KEY, task_id TEXT REFERENCES tasks(id),
                        kind TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
                    PRAGMA user_version=1;
                ''')

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def inside(self, relative):
        rel = PurePosixPath(relative)
        if '\\' in str(relative) or ':' in str(relative) or rel.is_absolute() or '..' in rel.parts or not rel.parts:
            raise ValueError('工作空间内的路径无效。')
        current = self.root
        for part in rel.parts:
            current /= part
            if current.is_symlink():
                raise ValueError('工作空间内部不允许通过符号链接访问其他位置。')
        if not current.resolve().is_relative_to(self.root):
            raise ValueError('文件位置超出工作空间。')
        return current

    @staticmethod
    def event(db, task_id, kind, details):
        db.execute('INSERT INTO events(task_id,kind,details,created_at) VALUES(?,?,?,?)',
                   (task_id, kind, json.dumps(details, ensure_ascii=False), now()))

    @staticmethod
    def _task(db, task_id):
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise ValueError('这项稿件任务已不存在，请刷新。')
        return dict(row)

    @staticmethod
    def _tags(values):
        if isinstance(values, str):
            values = re.split(r'[,，;；]', values)
        result = list(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))
        if len(result) > 30 or any(len(v) > 60 for v in result):
            raise ValueError('最多 30 个标签，每个标签最多 60 个字符。')
        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def _todo(db, task_id, text, priority='normal', deadline=None, file_ids=()):
        text = str(text).strip()
        if not text or len(text) > 300 or priority not in PRIORITIES:
            raise ValueError('请填写 1–300 字的下一步工作，并选择有效优先级。')
        deadline = due_date(deadline)
        # Repeatedly receiving the same material must not duplicate the same work.
        existing = db.execute('SELECT id FROM todos WHERE task_id=? AND text=? AND deleted=0',
                              (task_id, text)).fetchone()
        todo_id = existing['id'] if existing else str(uuid.uuid4())
        if not existing:
            db.execute('INSERT INTO todos VALUES(?,?,?,?,?,0,0,?)',
                       (todo_id, task_id, text, priority, deadline, now()))
        for fid in file_ids:
            row = db.execute('SELECT task_id FROM files WHERE id=?', (fid,)).fetchone()
            if row is None or row['task_id'] != task_id:
                raise ValueError('只能关联当前稿件任务的文件。')
            db.execute('INSERT OR IGNORE INTO todo_files VALUES(?,?)', (todo_id, fid))
        return todo_id

    def create_task(self, name, client='', tags=(), status='进行中', deadline=None,
                    first_todo='整理稿件材料', todo_deadline=None, priority='normal', notes=''):
        name, client = component(name), component(client, '未分类')
        if client == '未分类' and name == INBOX:
            raise ValueError('这个任务名称保留给收件箱使用，请换一个名称。')
        if status not in STATUSES:
            raise ValueError('任务状态无效。')
        created = date.today().strftime('%Y%m%d')
        relative = PurePosixPath(client, created, name).as_posix()
        directory = self.inside(relative)
        made = False
        try:
            with self.connection(True) as db:
                if directory.exists() or db.execute('SELECT id FROM tasks WHERE directory=?', (relative,)).fetchone():
                    raise ValueError('同一客户、建立日期下已存在这个名称，请修改任务名称。')
                directory.parent.mkdir(parents=True, exist_ok=True)
                directory.mkdir()  # Never reuse or overwrite a pre-existing user directory.
                made = True
                for category in CATEGORIES:
                    (directory / category).mkdir()
                task_id = str(uuid.uuid4())
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (task_id, client, name, created, due_date(deadline), status,
                            self._tags(tags), str(notes), relative, now()))
                self._todo(db, task_id, first_todo, priority, todo_deadline or deadline)
                self.event(db, task_id, '新建任务', dict(client=client, name=name, directory=relative))
            return task_id
        except Exception:
            if made:
                for child in directory.iterdir():
                    if child.is_dir():
                        child.rmdir()
                directory.rmdir()
            raise

    def update_task(self, task_id, *, name, client, tags=(), status='进行中', deadline=None, notes=''):
        name, client = component(name), component(client, '未分类')
        if status not in STATUSES or (client == '未分类' and name == INBOX):
            raise ValueError('任务名称或状态无效。')
        moved = None
        try:
            with self.connection(True) as db:
                task = self._task(db, task_id)
                relative = PurePosixPath(client, task['created_date'], name).as_posix()
                old, new = self.inside(task['directory']), self.inside(relative)
                if relative != task['directory']:
                    if new.exists() or db.execute('SELECT id FROM tasks WHERE directory=? AND id<>?', (relative, task_id)).fetchone():
                        raise ValueError('目标目录已存在，任务和文件均未更名。')
                    if not old.is_dir():
                        raise ValueError('原任务目录已被外部移动，请先恢复原目录再修改名称。')
                    new.parent.mkdir(parents=True, exist_ok=True)
                    old.rename(new)
                    moved = (new, old)
                    for f in db.execute('SELECT id,path FROM files WHERE task_id=?', (task_id,)).fetchall():
                        suffix = PurePosixPath(f['path']).relative_to(task['directory'])
                        db.execute('UPDATE files SET path=? WHERE id=?', ((PurePosixPath(relative) / suffix).as_posix(), f['id']))
                db.execute('UPDATE tasks SET client=?,name=?,due_date=?,status=?,tags=?,notes=?,directory=? WHERE id=?',
                           (client, name, due_date(deadline), status, self._tags(tags), str(notes), relative, task_id))
                self.event(db, task_id, '修改任务', dict(old_directory=task['directory'], directory=relative))
        except Exception:
            if moved:
                moved[0].rename(moved[1])
            raise

    def tasks(self, query='', client='', tag='', status='', due_before=None, due_after=None, pending_only=False):
        with self.connection() as db:
            rows = db.execute('''SELECT t.*, (SELECT count(*) FROM files f WHERE f.task_id=t.id) file_count,
                (SELECT count(*) FROM todos d WHERE d.task_id=t.id AND d.completed=0 AND d.deleted=0) pending_count,
                (SELECT group_concat(text,' ') FROM todos d WHERE d.task_id=t.id AND d.deleted=0) todo_text,
                (SELECT group_concat(original_name,' ') FROM files f WHERE f.task_id=t.id) file_names
                FROM tasks t ORDER BY t.due_date IS NULL,t.due_date,t.created_at DESC''').fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r['tags'] = json.loads(r['tags'])
            if client and r['client'] != client or tag and tag not in r['tags'] or status and r['status'] != status:
                continue
            if pending_only and not r['pending_count']:
                continue
            if due_before and (not r['due_date'] or r['due_date'] > due_before):
                continue
            if due_after and (not r['due_date'] or r['due_date'] < due_after):
                continue
            haystack = ' '.join([r['name'], r['client'], *r['tags'], r['notes'], r['todo_text'] or '', r['file_names'] or ''])
            if query.casefold() not in haystack.casefold():
                continue
            result.append(r)
        return result

    def task(self, task_id):
        with self.connection() as db:
            r = self._task(db, task_id)
            r['tags'] = json.loads(r['tags'])
            return r

    def files(self, task_id=None, category=None):
        with self.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM files WHERE task_id IS ? ORDER BY received_at DESC,rowid DESC', (task_id,))]
        return [r for r in rows if category is None or r['category'] == category]

    def todos(self, task_id=None):
        with self.connection() as db:
            rows = db.execute('''SELECT d.*,t.name task_name,t.client FROM todos d JOIN tasks t ON t.id=d.task_id
                WHERE (? IS NULL OR d.task_id=?) ORDER BY d.completed,d.due_date IS NULL,d.due_date,d.created_at''',
                              (task_id, task_id)).fetchall()
            result = []
            for r in rows:
                r = dict(r)
                r['file_ids'] = [f[0] for f in db.execute('SELECT file_id FROM todo_files WHERE todo_id=?', (r['id'],))]
                r['completed'], r['deleted'] = bool(r['completed']), bool(r['deleted'])
                result.append(r)
            return result

    def add_todo(self, task_id, text, priority='normal', deadline=None, file_ids=()):
        with self.connection(True) as db:
            self._task(db, task_id)
            tid = self._todo(db, task_id, text, priority, deadline, file_ids)
            self.event(db, task_id, '新增待办', dict(todo_id=tid, text=text))
            return tid

    def update_todo(self, todo_id, **changes):
        allowed = {'text', 'priority', 'due_date', 'completed', 'deleted', 'file_ids'}
        if set(changes) - allowed:
            raise ValueError('不支持的待办字段。')
        with self.connection(True) as db:
            row = db.execute('SELECT * FROM todos WHERE id=?', (todo_id,)).fetchone()
            if row is None:
                raise ValueError('待办已不存在。')
            r = dict(row)
            r.update({k: v for k, v in changes.items() if k != 'file_ids'})
            if not isinstance(r['text'], str) or not r['text'].strip() or len(r['text']) > 300 or r['priority'] not in PRIORITIES:
                raise ValueError('待办名称或优先级无效。')
            for key in ('completed', 'deleted'):
                if key in changes and type(changes[key]) is not bool:
                    raise ValueError('待办完成状态无效。')
            db.execute('UPDATE todos SET text=?,priority=?,due_date=?,completed=?,deleted=? WHERE id=?',
                       (r['text'].strip(), r['priority'], due_date(r['due_date']), int(r['completed']), int(r['deleted']), todo_id))
            if 'file_ids' in changes:
                for fid in changes['file_ids']:
                    f = db.execute('SELECT task_id FROM files WHERE id=?', (fid,)).fetchone()
                    if f is None or f[0] != r['task_id']:
                        raise ValueError('关联文件不属于当前任务。')
                db.execute('DELETE FROM todo_files WHERE todo_id=?', (todo_id,))
                db.executemany('INSERT OR IGNORE INTO todo_files VALUES(?,?)', [(todo_id, fid) for fid in changes['file_ids']])
            self.event(db, r['task_id'], '修改待办', dict(todo_id=todo_id, changes=changes))
        return next(t for t in self.todos() if t['id'] == todo_id)

    def linked_todos(self):
        return [dict(id='workspace:' + t['id'], name=t['text'], priority=t['priority'], due_date=t['due_date'],
                     completed=t['completed'], deleted=t['deleted'], created_at=t['created_at'],
                     workspace_task_id=t['task_id'], manuscript_title=t['task_name'], client=t['client'], file_ids=t['file_ids'])
                for t in self.todos()]

    @staticmethod
    def _unique(directory, name):
        name = component(name)
        stem, suffix = Path(name).stem, Path(name).suffix
        for n in range(10000):
            candidate = directory / (name if n == 0 else f'{stem}_{n + 1}{suffix}')
            if not candidate.exists():
                return candidate
        raise ValueError('同名文件过多，请修改文件名后重试。')

    def receive_files(self, sources, task_id=None, categories=None, todo_text='', deadline=None, priority='normal'):
        sources = [Path(p).expanduser().resolve() for p in sources]
        if not sources:
            raise ValueError('请先选择材料文件。')
        categories = list(categories or ['原稿'] * len(sources))
        if len(categories) != len(sources) or any(c not in CATEGORIES for c in categories):
            raise ValueError('请选择有效文件分类。')
        created_paths, ids, duplicates = [], [], []
        batch_id = str(uuid.uuid4())
        try:
            with tempfile.TemporaryDirectory(prefix='.manuscript-import-', dir=self.root) as stage:
                staged = []
                for n, source in enumerate(sources):
                    if not source.is_file():
                        raise ValueError('材料文件不存在或不是普通文件：' + source.name)
                    component(source.name)
                    before = source.stat()
                    target = Path(stage) / str(n)
                    hasher = hashlib.sha256()
                    with source.open('rb') as src, target.open('xb') as dst:
                        for chunk in iter(lambda: src.read(1024 * 1024), b''):
                            hasher.update(chunk)
                            dst.write(chunk)
                    after = source.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError('文件在接收时发生变化，请保存源文件后重试：' + source.name)
                    staged.append((source, target, hasher.hexdigest(), after.st_size))
                with self.connection(True) as db:
                    task = self._task(db, task_id) if task_id else None
                    for (source, staged_file, digest, size), category in zip(staged, categories):
                        duplicate = db.execute('SELECT id FROM files WHERE task_id IS ? AND sha256=? AND size=?',
                                               (task_id, digest, size)).fetchone()
                        if duplicate:
                            ids.append(duplicate[0])
                            duplicates.append(source.name)
                            continue
                        relative = (PurePosixPath(task['directory']) / category if task else
                                    PurePosixPath('未分类', date.today().strftime('%Y%m%d'), INBOX))
                        directory = self.inside(relative.as_posix())
                        directory.mkdir(parents=True, exist_ok=True)
                        destination = self._unique(directory, source.name)
                        with destination.open('xb') as dst:
                            created_paths.append(destination)
                            with staged_file.open('rb') as src:
                                shutil.copyfileobj(src, dst)
                            dst.flush()
                            os.fsync(dst.fileno())
                        fid = str(uuid.uuid4())
                        db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?)',
                                   (fid, task_id, category if task else None, destination.relative_to(self.root).as_posix(),
                                    source.name, digest, size, now(), batch_id))
                        ids.append(fid)
                    if todo_text:
                        if not task_id:
                            raise ValueError('未归属材料请先归档到稿件任务，再建立待办。')
                        self._todo(db, task_id, todo_text, priority, deadline, ids)
                    self.event(db, task_id, '接收材料', dict(batch=batch_id, file_ids=ids, reused=duplicates))
            return dict(file_ids=list(dict.fromkeys(ids)), duplicates=duplicates, received=len(created_paths))
        except Exception:
            for path in reversed(created_paths):
                path.unlink(missing_ok=True)
            raise

    def archive_files(self, file_ids, task_id, categories, todo_text='', deadline=None, priority='normal'):
        file_ids, categories = list(file_ids), list(categories)
        if not file_ids or len(file_ids) != len(categories) or len(set(file_ids)) != len(file_ids):
            raise ValueError('请选中需要归档的文件。')
        moved = []
        try:
            with self.connection(True) as db:
                task = self._task(db, task_id)
                previous = []
                for fid, category in zip(file_ids, categories):
                    if category not in CATEGORIES:
                        raise ValueError('文件分类无效。')
                    f = db.execute('SELECT * FROM files WHERE id=?', (fid,)).fetchone()
                    if f is None:
                        raise ValueError('文件记录已不存在。')
                    if f['task_id'] not in (None, task_id):
                        raise ValueError('请勿将其他稿件的文件直接移入当前任务。')
                    old = self.inside(f['path'])
                    if not old.is_file():
                        raise ValueError('文件已被外部移动，请先重新关联：' + f['original_name'])
                    directory = self.inside((PurePosixPath(task['directory']) / category).as_posix())
                    directory.mkdir(parents=True, exist_ok=True)
                    if old.parent == directory:
                        continue
                    new = self._unique(directory, old.name)
                    # Both locations are managed copies, on the same workspace volume.
                    old.rename(new)
                    moved.append((new, old))
                    new_relative = new.relative_to(self.root).as_posix()
                    previous.append(dict(file_id=fid, old_path=f['path'], old_category=f['category'],
                                         old_task_id=f['task_id'], new_path=new_relative))
                    db.execute('UPDATE files SET task_id=?,category=?,path=? WHERE id=?', (task_id, category, new_relative, fid))
                if todo_text:
                    self._todo(db, task_id, todo_text, priority, deadline, file_ids)
                self.event(db, task_id, '归档材料', dict(files=previous))
        except Exception:
            for new, old in reversed(moved):
                new.rename(old)
            raise

    def undo_archive(self, event_id):
        moved = []
        try:
            with self.connection(True) as db:
                row = db.execute("SELECT * FROM events WHERE id=? AND kind='归档材料'", (event_id,)).fetchone()
                if row is None or db.execute("SELECT id FROM events WHERE kind='撤销归档' AND json_extract(details,'$.event_id')=?", (event_id,)).fetchone():
                    raise ValueError('这次归档不存在或已经撤销。')
                entries = json.loads(row['details'])['files']
                if not entries:
                    raise ValueError('此次操作没有需要撤销的文件移动。')
                for f in entries:
                    current = db.execute('SELECT path FROM files WHERE id=?', (f['file_id'],)).fetchone()
                    old, new = self.inside(f['old_path']), self.inside(f['new_path'])
                    if current is None or current[0] != f['new_path'] or not new.is_file() or old.exists():
                        raise ValueError('文件位置已变化或原位置已被占用，未执行撤销。')
                    # Keep links consistent: work completed or edited after import is not silently removed.
                    if f['old_task_id'] is None and db.execute('SELECT 1 FROM todo_files WHERE file_id=?', (f['file_id'],)).fetchone():
                        raise ValueError('文件已关联待办；请先在待办编辑中解除关联，再撤销归档。')
                    old.parent.mkdir(parents=True, exist_ok=True)
                    new.rename(old)
                    moved.append((old, new))
                    db.execute('UPDATE files SET path=?,category=?,task_id=? WHERE id=?',
                               (f['old_path'], f['old_category'], f['old_task_id'], f['file_id']))
                self.event(db, row['task_id'], '撤销归档', dict(event_id=event_id))
        except Exception:
            for old, new in reversed(moved):
                old.rename(new)
            raise

    def relocate_file(self, file_id, source):
        with self.connection() as db:
            row = db.execute('SELECT * FROM files WHERE id=?', (file_id,)).fetchone()
        if row is None:
            raise ValueError('文件记录不存在。')
        old = self.inside(row['path'])
        if old.exists():
            raise ValueError('原关联文件仍存在，不需要重新关联。')
        source = Path(source).expanduser().resolve()
        if not source.is_file():
            raise ValueError('请选择实际存在的文件。')
        digest = hashlib.sha256()
        old.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with self.connection(True) as db:
                with source.open('rb') as src, old.open('xb') as dst:
                    created = True
                    for chunk in iter(lambda: src.read(1024 * 1024), b''):
                        digest.update(chunk)
                        dst.write(chunk)
                if digest.hexdigest() != row['sha256'] or old.stat().st_size != row['size']:
                    raise ValueError('所选文件内容与原材料不一致，原关联记录已保留。')
                self.event(db, row['task_id'], '重新关联文件', dict(file_id=file_id))
        except Exception:
            if created:
                old.unlink(missing_ok=True)
            raise

    def file_path(self, file_id):
        with self.connection() as db:
            row = db.execute('SELECT path FROM files WHERE id=?', (file_id,)).fetchone()
        if row is None:
            raise ValueError('文件记录不存在。')
        path = self.inside(row['path'])
        if not path.is_file():
            raise FileNotFoundError('文件已被移动或删除，请重新关联。')
        return path

    def events(self, task_id=None):
        with self.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM events WHERE (? IS NULL OR task_id=?) ORDER BY id DESC', (task_id, task_id))]
        for r in rows:
            r['details'] = json.loads(r['details'])
        return rows

    def signature(self):
        stat = self.path.stat()
        return (stat.st_mtime_ns, stat.st_size)
