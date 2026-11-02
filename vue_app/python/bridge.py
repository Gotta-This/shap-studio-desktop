"""JSON stdin/stdout adapter. Both Vite development and Tauri call this allowlist.

The V3 profile is separate from Qt; choosing an existing workspace is explicit.
Filesystem transactions and manuscript validation are the released Python core.
"""
from pathlib import Path
import base64, contextlib, csv, io, json, os, sqlite3, sys, tempfile, uuid, threading
os.environ.setdefault("MPL_IGNORE_SYSTEM_FONTS", "1")
from dataclasses import asdict
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(ROOT / 'desktop_app'))
from clinical_studio.manuscripts import WorkspaceStore, CATEGORIES, STATUSES, component, due_date

from storage import data_root,initialize
AUTO_WORKSPACE = not bool(os.environ.get('RESEARCH_V3_PROFILE'))
DATA_ROOT = data_root() if AUTO_WORKSPACE else Path(os.environ['RESEARCH_V3_PROFILE']).expanduser().resolve()
PROFILE = DATA_ROOT/'profile' if AUTO_WORKSPACE else DATA_ROOT
_WORKSPACE_INIT_LOCK=threading.Lock()

def using_default_storage():return AUTO_WORKSPACE and PROFILE==DATA_ROOT/'profile'

def profile():
    if using_default_storage():initialize(DATA_ROOT,os.environ.get('RESEARCH_V3_LEGACY_PROFILE'))
    PROFILE.mkdir(parents=True, exist_ok=True)
    return PROFILE

def workspace(required=True):
    config = profile() / 'workspace.json'
    with _WORKSPACE_INIT_LOCK:
        if not config.exists() and using_default_storage():
            store=WorkspaceStore(DATA_ROOT/'workspace')
            fd,tmp=tempfile.mkstemp(dir=profile(),prefix='.workspace-')
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(dict(root=str(store.root)),stream);stream.flush();os.fsync(stream.fileno())
                os.replace(tmp,config)
            finally:Path(tmp).unlink(missing_ok=True)
    if config.exists():
        return WorkspaceStore(json.loads(config.read_text(encoding='utf-8'))['root'], create=False)
    if required: raise ValueError('请先选择本地工作空间。')

@contextlib.contextmanager
def personal_db():
    db = sqlite3.connect(profile() / 'personal.sqlite3', timeout=5)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS todos (id TEXT PRIMARY KEY, text TEXT, priority TEXT, due_date TEXT, completed INTEGER, deleted INTEGER)')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def todos(store):
    with personal_db() as db:
        rows = [dict(r, completed=bool(r['completed']), deleted=bool(r['deleted']), task_id=None, task_name='个人待办', client='', file_ids=[]) for r in db.execute('SELECT * FROM todos')]
    return [r for r in rows + (store.todos() if store else []) if not r['deleted']]

def state():
    s = workspace(False)
    result = dict(root=str(s.root) if s else None, tasks=s.tasks() if s else [], todos=todos(s), inbox=s.files() if s else [], categories=CATEGORIES, statuses=STATUSES)
    if s:
        for task in result['tasks']:
            task['next_todo'] = next((t for t in result['todos'] if t['task_id']==task['id'] and not t['completed']), None)
        for f in result['inbox']: f['available'] = s.inside(f['path']).is_file()
    return result

@contextlib.contextmanager
def sources(params):
    """Browser uploads are staged temporarily; native paths remain originals."""
    with tempfile.TemporaryDirectory(prefix='research-v3-upload-') as folder:
        paths = [Path(p).expanduser().resolve() for p in params.get('paths', [])]
        for i, f in enumerate(params.get('uploads', [])):
            data = base64.b64decode(f['content'], validate=True)
            if len(data)>32*1024*1024: raise ValueError('单个材料最多 32 MB，请使用桌面版导入更大文件。')
            name=f['name']
            if not isinstance(name,str) or not name or name in ('.','..') or any(c in name for c in ('/','\\','\0')) or len(name.encode('utf-8'))>255:raise ValueError('上传文件名无效，不能含路径且 UTF-8 最多 255 字节。')
            target=Path(folder)/str(i)/name;target.parent.mkdir();target.write_bytes(data);paths.append(target)
        yield paths

def csv_result(values, digits=None):
    from clinical_studio.data_tools_engine import format_values, statistics
    mean, sd=statistics(values)
    out=io.StringIO();writer=csv.writer(out);writer.writerow(['模拟数据']);writer.writerows([[x] for x in values])
    return dict(values=values, mean=mean, sd=sd, text=format_values(values,'line',digits), csv=out.getvalue())

def preview_file(s, fid):
    p=s.file_path(fid)
    if p.stat().st_size>10*1024*1024: raise ValueError('预览仅支持 10 MB 内文件，请使用系统程序打开。')
    ext=p.suffix.lower()
    if ext in ('.png','.jpg','.jpeg','.gif','.webp','.pdf'):
        import mimetypes
        return dict(kind='pdf' if ext=='.pdf' else 'image',name=p.name,url='data:'+mimetypes.guess_type(str(p))[0]+';base64,'+base64.b64encode(p.read_bytes()).decode())
    if ext=='.docx':
        with ZipFile(p) as z:
            node=ET.fromstring(z.read('word/document.xml'))
            text='\n'.join(''.join(t.text or '' for t in n.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')) for n in node.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
    elif ext in ('.txt','.csv','.md','.json','.tsv'):
        text=p.read_text(encoding='utf-8-sig',errors='replace')
    else: raise ValueError('此格式请使用系统程序打开。')
    return dict(kind='text',name=p.name,text=text[:100000])

def dispatch(method, p):
    if method=='weather.search':
        from weather import search
        return search(p['query'])
    if method=='weather.choose':
        from weather import choose
        return choose(profile(),p['location'])
    if method=='weather.current':
        from weather import current,DEFAULT_LOCATION
        return current(profile(),p.get('force',False),DEFAULT_LOCATION if using_default_storage() else None)
    if method=='updates.check':
        from releases import check
        return check()
    if method=='updates.download':
        from releases import download
        return download(profile())
    if method=='migration.inspect':
        from migration import inspect
        return inspect(p.get('directory'))
    if method=='migration.import':
        from migration import migrate
        return migrate(profile(),p.get('directory'))
    if method=='storage.info': return dict(directory=str(DATA_ROOT),profile=str(profile()),automatic=using_default_storage())
    if method=='state': return state()
    if method=='runtime.info':
        import importlib.metadata
        return dict(engine_pid=os.getpid(),application_version=__import__('releases').VERSION,bundled=bool(getattr(sys,'frozen',False)),versions={name:importlib.metadata.version(name) for name in ['numpy','pandas','scikit-learn','shap','matplotlib','Pillow','openpyxl']})
    if method=='workspace.enable':
        s=WorkspaceStore(p['root'])
        config=profile()/'workspace.json'
        fd,tmp=tempfile.mkstemp(dir=profile(),prefix='.workspace-')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(dict(root=str(s.root)),f);f.flush();os.fsync(f.fileno())
            os.replace(tmp,config)
        finally: Path(tmp).unlink(missing_ok=True)
        return state()
    if method=='task.create': return workspace().create_task(**p)
    if method=='task.update':
        fields=dict(p);tid=fields.pop('id');workspace().update_task(tid,**fields);return state()
    if method=='task.detail':
        s=workspace();files=s.files(p['id'])
        for f in files: f['available']=s.inside(f['path']).is_file()
        return dict(task=s.task(p['id']),files=files,todos=[t for t in s.todos(p['id']) if not t['deleted']],events=s.events(p['id']))
    if method=='events': return workspace().events(p.get('task_id'))
    if method=='files.import':
        with sources(p) as paths:
            return workspace().receive_files(paths,task_id=p.get('task_id'),categories=p.get('categories'),todo_text=p.get('todo_text',''),deadline=p.get('deadline'),priority=p.get('priority','normal'))
    if method=='files.archive':
        workspace().archive_files(p['ids'],p['task_id'],p['categories'],p.get('todo_text',''),p.get('deadline'),p.get('priority','normal'));return state()
    if method=='files.undo': workspace().undo_archive(p['id']);return state()
    if method=='files.relocate':
        with sources(p) as paths:
            if len(paths)!=1: raise ValueError('请选择一个原始文件。')
            workspace().relocate_file(p['id'],paths[0]);return True
    if method=='exports.save':
        target=Path(p['path']).expanduser()
        if not target.is_absolute() or not target.parent.is_dir() or target.is_dir():raise ValueError('请选择有效的导出文件位置。')
        content=base64.b64decode(p['content'],validate=True) if p.get('base64') else p['content'].encode('utf-8')
        fd,tmp=tempfile.mkstemp(dir=target.parent,prefix='.research-export-')
        try:
            with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:Path(tmp).unlink(missing_ok=True)
        return dict(path=str(target),size=len(content))
    if method=='files.preview': return preview_file(workspace(),p['id'])
    if method=='files.path': return str(workspace().file_path(p['id']))
    if method=='task.path':
        s=workspace();return str(s.inside(s.task(p['id'])['directory']))
    if method=='todo.save':
        fields=dict(p);tid=fields.pop('id',None);task_id=fields.pop('task_id',None)
        if tid and not tid.startswith('personal:'): return workspace().update_todo(tid,**fields)
        if not tid and task_id:
            return workspace().add_todo(task_id,fields['text'],fields.get('priority','normal'),fields.get('due_date'),fields.get('file_ids',[]))
        with personal_db() as db:
            current=dict(db.execute('SELECT * FROM todos WHERE id=?',(tid,)).fetchone() or {})
            value=dict(text='',priority='normal',due_date=None,completed=False,deleted=False);value.update(current);value.update(fields)
            if not str(value['text']).strip() or len(value['text'])>300: raise ValueError('请填写 1～300 字的下一步工作。')
            if value['priority'] not in ('high','normal','low'): raise ValueError('优先级无效。')
            for key in ('completed','deleted'):
                if key in fields and type(fields[key]) is not bool: raise ValueError('完成状态无效。')
            value['due_date']=due_date(value['due_date']);tid=tid or 'personal:'+str(uuid.uuid4())
            db.execute('INSERT OR REPLACE INTO todos VALUES(?,?,?,?,?,?)',(tid,value['text'].strip(),value['priority'],value['due_date'],int(value['completed']),int(value['deleted'])))
        return tid
    if method=='tool.category':
        from clinical_studio.data_tools_engine import category_numbers
        if any(type(r['count']) not in (int,float) or not float(r['count']).is_integer() for r in p['rows']): raise ValueError('类别数量必须是整数。')
        return csv_result(category_numbers([(float(r['value']),int(r['count'])) for r in p['rows']],str(p.get('seed',12))))
    if method=='tool.numeric':
        from clinical_studio.data_tools_engine import numeric_numbers
        return csv_result(numeric_numbers(**p),p.get('digits',0))
    if method=='tool.job.start':
        from jobs import start
        return start(profile(),p)
    if method=='tool.job.status':
        from jobs import status
        return status(profile(),p['id'])
    if method=='tool.job.cancel':
        from jobs import cancel
        return cancel(profile(),p['id'])
    if method=='tool.word.scan':
        from word_workflow import scan
        with sources(p) as paths:
            if len(paths)!=1:raise ValueError('请选择一个 Word 文档。')
            return scan(profile(),paths[0],p.get('decimal_mode','zero'))
    if method=='tool.word.match':
        from word_workflow import match
        return match(profile(),p)
    if method=='tool.word.apply':
        from word_workflow import apply
        return apply(profile(),p)
    if method=='tool.word.review':
        from word_workflow import review
        return review(p)
    if method=='tool.word.field.save':
        from clinical_studio.typed_field_rules import validate_edit,peer_schema
        value=validate_edit(p['field'])
        return dict(field=value,peers=[peer_schema(f,value) for f in p.get('peers',[])])
    if method=='tool.word.convert':
        from clinical_studio.typed_field_rules import convert
        return convert(p['field'],p['kind'])
    if method=='tool.word.prose.parse':
        from clinical_studio.prose_table_engine import parse_document
        from clinical_studio.word_precision import prose_precision
        return prose_precision(parse_document(p['text'],p.get('groups')),p.get('decimal_mode','zero'))
    if method=='tool.word.prose.confirm':
        from clinical_studio.prose_matching import metric_key
        cell=dict(p['cell'],reviewed=True,issues=[])
        old=next((f for f in p['fields'] if f['group']==p['group'] and metric_key(f['name'])==metric_key(p['variable'])),None)
        if old is not None:cell['table_conflict']=old
        return cell
    if method=='tool.word.prose.validate':
        from clinical_studio.prose_table_engine import validate_study
        return validate_study(p['study'])
    if method=='tool.shap.table':
        from analysis_workflow import table
        return table(profile(),p)
    if method=='tool.shap.export':
        from analysis_workflow import export
        return export(profile(),p)
    if method in ('tool.word.configuration','tool.shap.configuration','tool.word.prose.configuration'):
        from configuration import word,shap,prose_document
        return {'tool.word.configuration':word,'tool.shap.configuration':shap,'tool.word.prose.configuration':prose_document}[method](p['config'])
    if method=='tool.word.defaults':
        from clinical_studio.word_batch_engine import default_batch_config
        return default_batch_config()
    if method=='tool.word.read':
        from clinical_studio.word_batch_engine import read_word, default_batch_config
        with sources(p) as paths:
            if len(paths)!=1: raise ValueError('请选择一个 DOCX。')
            r=read_word(paths[0],groups=p.get('groups',['对照组','中药组']))
            config=default_batch_config(p.get('groups',['对照组','中药组']));config['indicators']=r.indicators;config['typed_fields']=r.typed_fields;config['include_basics']=not r.baseline_columns
            for group in config['groups']:
                if group['name'] in r.group_sizes: group['n']=r.group_sizes[group['name']]
            return dict(imported=asdict(r),config=config)
    if method=='tool.word.generate':
        from clinical_studio.word_batch_engine import generate_batch, export_batch
        result=generate_batch(p['config']);folder=profile()/'exports';folder.mkdir(exist_ok=True)
        path=folder/('word-'+uuid.uuid4().hex[:8]+'.xlsx');export_batch(result,path)
        return dict(columns=result['columns'],rows=result['rows'][:200],total=len(result['rows']),name=path.name,base64=base64.b64encode(path.read_bytes()).decode())
    if method=='tool.shap.defaults':
        from clinical_studio.config import default_config
        return default_config()
    if method=='tool.shap.run':
        os.environ.setdefault('MPLBACKEND','Agg');os.environ.setdefault('MPLCONFIGDIR',str(profile()/'mpl'))
        from clinical_studio.engine import run_analysis
        result=run_analysis(p['config'],p.get('output') or profile()/'exports',data_only=p.get('data_only',False))
        images=[dict(name=f.name,url='data:image/png;base64,'+base64.b64encode(f.read_bytes()).decode()) for f in (result.folder/'figures').glob('*.png')]
        return dict(folder=str(result.folder),metrics=result.metrics,columns=list(result.data.columns),rows=json.loads(result.data.head(200).to_json(orient='values')),images=images)
    raise ValueError('不支持的操作：'+method)

def serve():
    """Multiplex independent IPC requests in one warmed embedded interpreter."""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    directory=profile()  # Finish any legacy copy before concurrent requests.
    logs=directory/'logs';logs.mkdir(exist_ok=True)
    diagnostics=(logs/f'engine-{os.getpid()}.log').open('a',encoding='utf-8',buffering=1)
    # Keep the protocol on its own descriptor. Native and Python diagnostics
    # remain writable after the GUI exits, so accepted saves/jobs can finish.
    output=os.fdopen(os.dup(sys.stdout.fileno()),'w',encoding='utf-8',buffering=1)
    os.dup2(diagnostics.fileno(),1);os.dup2(diagnostics.fileno(),2)
    sys.stdout=sys.stderr=diagnostics
    os.environ['RESEARCH_V3_ENGINE_SERVICE']='1'
    connected=True
    lock=threading.Lock()
    def execute(envelope):
        nonlocal connected
        try:
            request=envelope['request']
            result=dispatch(request['method'],request.get('params') or {})
            response=dict(ok=True,result=result)
            encoded=json.dumps(dict(id=envelope['id'],response=response),ensure_ascii=False,allow_nan=False,default=str)
        except Exception as exc:
            encoded=json.dumps(dict(id=envelope.get('id'),response=dict(ok=False,error=str(exc))),ensure_ascii=False)
        with lock:
            if connected:
                try:output.write(encoded+'\n');output.flush()
                except (OSError,ValueError):connected=False
    with ThreadPoolExecutor(max_workers=6,thread_name_prefix='v3-ipc') as executor:
        for line in sys.stdin:
            try:envelope=json.loads(line)
            except ValueError:continue
            executor.submit(execute,envelope)
    try:output.close()
    except OSError:pass

def main():
    try:
        request=json.loads(sys.stdin.read())
        # Third party numerical engines may print; stdout is exclusively protocol.
        with contextlib.redirect_stdout(sys.stderr): result=dispatch(request['method'],request.get('params') or {})
        response=dict(ok=True,result=result)
        encoded=json.dumps(response,ensure_ascii=False,allow_nan=False,default=str)
    except Exception as exc:
        encoded=json.dumps(dict(ok=False,error=str(exc)),ensure_ascii=False)
    sys.stdout.write(encoded);sys.stdout.flush()

if __name__=='__main__':
    # Windows GUI processes may inherit a locale codec; the IPC protocol is UTF-8.
    for stream in (sys.stdin,sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    if len(sys.argv)==3 and sys.argv[1]=='--job-worker':
        from jobs import worker
        worker(profile(),sys.argv[2])
    elif len(sys.argv)==2 and sys.argv[1]=='--serve':serve()
    else: main()
