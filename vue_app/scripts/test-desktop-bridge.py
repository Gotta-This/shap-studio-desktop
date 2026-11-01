"""Test the shipped Rust host and its real engine path without creating windows."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,time

host=Path(sys.argv[1]).resolve()
assert host.is_file(),host
with tempfile.TemporaryDirectory(prefix='v3-desktop-bridge-') as tmp:
    env={**os.environ,'PYTHONUTF8':'1','RESEARCH_V3_PYTHON':str(Path(tmp)/'no-system-python'),'MPLBACKEND':'Agg','MPLCONFIGDIR':tmp+'/mpl'}
    def call(method,params=None):
        result=subprocess.run([str(host),'--bridge-request',tmp],input=json.dumps(dict(method=method,params=params or {})),encoding='utf-8',capture_output=True,env=env,timeout=45)
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
    tid=call('todo.save',dict(text='桌面桥接测试😀'))
    assert call('state')['todos'][0]['text']=='桌面桥接测试😀'
    value=job('numeric',dict(n=70,mean=27.92,sd=14.87,digits=0,lower=None,upper=None,mode='target',seed=12))
    assert len(value['values'])==70 and abs(value['mean']-27.92)<.02 and abs(value['sd']-14.87)<.1,value
    print('Actual desktop host: bundled engine, Unicode persistence and screenshot numeric parameters passed',flush=True)
    value=job('category',dict(rows=[dict(value=1,count=28),dict(value=0,count=93)],seed=12))
    assert len(value['values'])==121 and value['values'].count(1)==28
    config=call('tool.word.defaults');config['indicators']=[dict(name='评分',group=g['name'],mean=50,sd=5,digits=0,parity='any',lower=None,upper=None) for g in config['groups']]
    assert job('word',dict(config=config))['total']==140
    config=call('tool.shap.defaults');config['data']['n_samples']=40
    assert job('shap',dict(config=config,data_only=True))['total']==40
    print('Actual desktop host: category, Word and SHAP background round trips passed',flush=True)
