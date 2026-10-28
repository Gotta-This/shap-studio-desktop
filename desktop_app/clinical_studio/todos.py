"""Small, versioned local todo store. Every edit is locked and atomically saved."""
from copy import deepcopy
from datetime import date,datetime,timezone
from pathlib import Path
import json,os,tempfile,uuid
from PySide6.QtCore import QLockFile,QStandardPaths

PRIORITIES={'high':'高','normal':'普通','low':'低'}


def default_path():
    override=os.environ.get('CLINICAL_STUDIO_TODO_PATH')
    return Path(override) if override else Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))/'todos.json'


class TodoStore:
    def __init__(self,path=None):self.path=Path(path) if path is not None else default_path()
    def read(self):
        if not self.path.exists():return []
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version')!=1 or not isinstance(data.get('tasks'),list):raise ValueError()
            seen=set()
            for task in data['tasks']:
                if not isinstance(task,dict) or not isinstance(task.get('id'),str) or not task['id'] or task['id'] in seen:raise ValueError()
                seen.add(task['id']);self.validate(task)
                if type(task.get('completed')) is not bool or type(task.get('deleted',False)) is not bool:raise ValueError()
            return data['tasks']
        except (ValueError,TypeError,KeyError,AttributeError) as exc:raise ValueError('待办文件无法读取，原文件已保留。请检查本地待办文件后重试。') from exc
    @staticmethod
    def validate(task):
        if not isinstance(task.get('name'),str) or not task['name'].strip():raise ValueError('请填写谁的文档。')
        if len(task['name'].strip())>300:raise ValueError('文档名称最多300个字符。')
        if task.get('priority') not in PRIORITIES:raise ValueError('请选择有效优先级。')
        if task.get('due_date') is not None:
            if not isinstance(task['due_date'],str):raise ValueError('截止日期无效。')
            try:date.fromisoformat(task['due_date'])
            except ValueError as exc:raise ValueError('截止日期无效。') from exc
    def mutate(self,action):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        lock=QLockFile(str(self.path)+'.lock');lock.setStaleLockTime(30000)
        if not lock.tryLock(1500):raise ValueError('另一个窗口正在保存待办，请稍后重试。')
        temporary=None
        try:
            tasks=self.read();result=action(tasks)
            for task in tasks:self.validate(task)
            fd,temporary=tempfile.mkstemp(prefix='.todos-',suffix='.tmp',dir=self.path.parent)
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(dict(version=1,tasks=tasks),stream,ensure_ascii=False,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path);temporary=None
            return deepcopy(result)
        finally:
            if temporary is not None:Path(temporary).unlink(missing_ok=True)
            lock.unlock()
    def add(self,name,priority='normal',due_date=None):
        task=dict(id=str(uuid.uuid4()),name=name.strip(),priority=priority,due_date=due_date,completed=False,deleted=False,created_at=datetime.now(timezone.utc).isoformat())
        self.validate(task)
        def action(tasks):tasks.append(task);return task
        return self.mutate(action)
    def update(self,task_id,**changes):
        if set(changes)-{'name','priority','due_date','completed','deleted'}:raise ValueError('不支持的待办字段。')
        def action(tasks):
            task=next((t for t in tasks if t['id']==task_id),None)
            if task is None:raise ValueError('这条待办已不存在，请刷新后重试。')
            if 'name' in changes:changes['name']=changes['name'].strip()
            if any(k in changes and type(changes[k]) is not bool for k in ('completed','deleted')):raise ValueError('待办状态无效。')
            task.update(changes);self.validate(task);return task
        return self.mutate(action)
    def delete(self,task_id):return self.update(task_id,deleted=True)
    def restore(self,task_id):return self.update(task_id,deleted=False)
    def visible(self,completed=False,query=''):
        tasks=[t for t in self.read() if not t.get('deleted') and t['completed']==completed and query.casefold() in t['name'].casefold()]
        return sorted(tasks,key=lambda t:(t['due_date'] or '9999-12-31',{'high':0,'normal':1,'low':2}[t['priority']],t.get('created_at',''),t['id']))
