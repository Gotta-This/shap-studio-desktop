"""Test the shipped Rust host and its real engine path without creating windows."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,time,signal
from zipfile import ZipFile
from xml.etree import ElementTree as ET

host=Path(sys.argv[1]).resolve()
assert host.is_file(),host
with tempfile.TemporaryDirectory(prefix='v3-desktop-bridge-') as tmp:
    env={**os.environ,'PYTHONUTF8':'1','RESEARCH_V3_PYTHON':str(Path(tmp)/'no-system-python'),'MPLBACKEND':'Agg','MPLCONFIGDIR':tmp+'/mpl','RESEARCH_V3_DATA_ROOT':tmp+'/data'}
    def call(method,params=None):
        result=subprocess.run([str(host),'--bridge-request','-'],input=json.dumps(dict(method=method,params=params or {})),encoding='utf-8',capture_output=True,env=env,timeout=45)
        assert result.stdout.strip(),(result.returncode,result.stderr)
        response=json.loads(result.stdout)
        assert response['ok'],response
        return response['result']
    def job(kind,params):
        jid=call('tool.job.start',dict(kind=kind,params=params))['id']
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            value=call('tool.job.status',dict(id=jid))
            if value['status']!='running':break
            time.sleep(.2)
        assert value['status']=='done',value
        return value['result']
    runtime=call('runtime.info')
    assert runtime['bundled'], 'Production host used the development Python instead of the sidecar'
    expected=json.loads((Path(__file__).resolve().parents[1]/'package.json').read_text(encoding='utf-8'))['version']
    assert runtime['application_version']==expected,runtime
    assert call('state')['root']==str((Path(tmp)/'data/workspace').resolve())
    assert call('storage.info')['directory']==str((Path(tmp)/'data').resolve())
    tid=call('todo.save',dict(text='桌面桥接测试😀'))
    assert call('state')['todos'][0]['text']=='桌面桥接测试😀'
    value=job('numeric',dict(n=70,mean=27.92,sd=14.87,digits=0,lower=None,upper=None,mode='target',seed=12))
    assert len(value['values'])==70 and abs(value['mean']-27.92)<.02 and abs(value['sd']-14.87)<.1,value
    print('Actual desktop host: bundled engine, Unicode persistence and screenshot numeric parameters passed',flush=True)
    value=job('category',dict(rows=[dict(value=1,count=28),dict(value=0,count=93)],seed=12))
    assert len(value['values'])==121 and value['values'].count(1)==28
    w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    document=ET.Element(w+'document');body=ET.SubElement(document,w+'body');table=ET.SubElement(body,w+'tbl')
    for values in [['项目','对照组(n=10)','中药组(n=12)'],['评分','50±5','60±5']]:
        row=ET.SubElement(table,w+'tr')
        for text in values:ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(row,w+'tc'),w+'p'),w+'r'),w+'t').text=text
    source=Path(tmp)/'真实Word导入.docx'
    with ZipFile(source,'w') as z:z.writestr('word/document.xml',ET.tostring(document))
    scanned=call('tool.word.scan',dict(paths=[str(source)]))
    applied=call('tool.word.apply',dict(session=scanned['session'],groups=scanned['scan']['candidates']))
    assert applied['config']['source']==source.name and (applied['config']['typed_fields'] or applied['config']['indicators'])
    print('Actual desktop host: real Word file scan and confirmed import passed',flush=True)
    config=call('tool.word.defaults');config['indicators']=[dict(name='评分',group=g['name'],mean=50,sd=5,digits=0,parity='any',lower=None,upper=None) for g in config['groups']]
    assert job('word',dict(config=config))['total']==140
    config=call('tool.shap.defaults');assert config['data']['features'] and len(config['plots']['plots'])==6
    config['data']['n_samples']=40
    assert job('shap',dict(config=config,data_only=True))['total']==40
    print('Actual desktop host: category, Word and SHAP background round trips passed',flush=True)
    # Exercise the same persistent engine used by the GUI, not just one-shot CLI.
    service=subprocess.Popen([str(host),'--bridge-service-host'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,encoding='utf-8',env=env)
    def warm_call(method,params=None):
        service.stdin.write(json.dumps(dict(method=method,params=params or {}))+'\n');service.stdin.flush()
        response=json.loads(service.stdout.readline());assert response['ok'],response
        return response['result']
    try:
        before=time.monotonic();pid=warm_call('runtime.info')['engine_pid'];cold=time.monotonic()-before
        before=time.monotonic();assert warm_call('runtime.info')['engine_pid']==pid;warm=time.monotonic()-before
        started=warm_call('tool.job.start',dict(kind='numeric',params=dict(n=70,mean=27.92,sd=14.87,digits=0,mode='target',seed=12)))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            completed=warm_call('tool.job.status',dict(id=started['id']))
            if completed['status']!='running':break
            time.sleep(.02)
        assert completed['status']=='done' and len(completed['result']['values'])==70,completed
        assert warm_call('runtime.info')['engine_pid']==pid
        print(f'Persistent desktop engine: same process, warm IPC {warm:.3f}s (cold {cold:.3f}s), background numeric passed',flush=True)
        os.kill(pid,signal.SIGTERM)
        recovered=None
        for _ in range(3):
            time.sleep(.1)
            try:recovered=warm_call('runtime.info')['engine_pid'];break
            except AssertionError:pass
        assert recovered and recovered!=pid,'Engine did not recover after termination'
        assert warm_call('runtime.info')['engine_pid']==recovered
        print('Persistent desktop engine: crash recovery passed',flush=True)
    finally:
        service.stdin.close();service.wait(timeout=60);service.stdout.close()
