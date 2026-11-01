"""Background scientific operations with atomic status and cooperative cancellation."""
from pathlib import Path
import json,os,re,subprocess,sys,uuid,tempfile,threading

def write(path,value):
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.status-')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,allow_nan=False,default=str)
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)

def location(profile,jid):
    if not re.fullmatch('[a-f0-9]{32}',jid or ''):raise ValueError('计算任务无效。')
    path=profile/'jobs'/jid
    if not path.is_dir():raise ValueError('计算任务已不可用。')
    return path

def start(profile,p):
    if p['kind'] not in ('word','shap','numeric','category'):raise ValueError('计算任务类型无效。')
    jid=uuid.uuid4().hex;path=profile/'jobs'/jid;path.mkdir(parents=True)
    write(path/'request.json',p);write(path/'status.json',dict(id=jid,status='running',message='正在准备本机计算…'))
    args=[sys.executable]+([] if getattr(sys,'frozen',False) else [str(Path(__file__).with_name('bridge.py'))])+['--job-worker',jid]
    env={**os.environ,'RESEARCH_V3_PROFILE':str(profile),'MPLBACKEND':'Agg'}
    # The worker outlives the bridge. A one-file child needs its own extraction
    # directory; sharing the parent's _MEIPASS races with bridge cleanup.
    if getattr(sys,'frozen',False):env['PYINSTALLER_RESET_ENVIRONMENT']='1'
    with (path/'worker.log').open('w') as log:
        process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,start_new_session=os.name!='nt',creationflags=0x08000000 if os.name=='nt' else 0)
    threading.Thread(target=process.wait,daemon=True).start()
    return dict(id=jid)

def status(profile,jid):return json.loads((location(profile,jid)/'status.json').read_text())
def cancel(profile,jid):
    path=location(profile,jid);(path/'cancel').touch();return dict(id=jid,message='正在取消；当前计算步骤结束后停止。')

def worker(profile,jid):
    path=location(profile,jid);p=json.loads((path/'request.json').read_text())
    def progress(message):
        if (path/'cancel').exists():raise InterruptedError('已取消本次计算。')
        write(path/'status.json',dict(id=jid,status='running',message=message))
    try:
        progress('正在核对当前参数…')
        if p['kind']=='word':
            from word_workflow import compose
            from clinical_studio.word_batch_engine import generate_batch,export_batch
            import base64
            config=compose(p['params']);r=generate_batch(config,progress,lambda:(path/'cancel').exists());progress('正在保存完整 Excel…')
            target=profile/'exports'/('word-'+jid[:8]+'.xlsx');target.parent.mkdir(exist_ok=True);export_batch(r,target)
            result=dict(text='\n'.join('\t'.join(map(str,row)) for row in [r['columns']]+r['rows']),columns=r['columns'],rows=r['rows'][:200],total=len(r['rows']),checks=r['checks'],name=target.name,base64=base64.b64encode(target.read_bytes()).decode(),config=config)
        elif p['kind'] in ('numeric','category'):
            from clinical_studio.data_tools_engine import numeric_numbers,category_numbers
            from bridge import csv_result,dispatch
            params=p['params'];progress('正在生成模拟数值…')
            values=numeric_numbers(**params,cancelled=lambda:(path/'cancel').exists()) if p['kind']=='numeric' else None
            result=csv_result(values,params.get('digits')) if p['kind']=='numeric' else dispatch('tool.category',params);result['params']=params
        else:
            from analysis_workflow import run
            result=run(profile,p['params'],progress)
        if (path/'cancel').exists():raise InterruptedError('已取消本次计算。')
        write(path/'status.json',dict(id=jid,status='done',message='计算完成，结果已保存。',result=result))
    except Exception as e:
        cancelled=(path/'cancel').exists() or isinstance(e,InterruptedError)
        write(path/'status.json',dict(id=jid,status='cancelled' if cancelled else 'error',message='已取消本次计算。' if cancelled else str(e)))
