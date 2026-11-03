"""Read/write settings in an isolated profile; never move CI desktop icons."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
binary=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as tmp:
    env={**os.environ,'RESEARCH_V3_PROFILE':tmp,'PYTHONUTF8':'1'}
    def call(method,params=None):
        p=subprocess.run([str(binary)],input=json.dumps(dict(method=method,params=params or {})),encoding='utf8',capture_output=True,env=env,timeout=60)
        value=json.loads(p.stdout)
        assert value['ok'],value
        return value['result']
    initial=call('desktop.layout.info')
    assert initial['supported'] and initial['backups']==[],initial
    assert initial['settings']['interval_minutes']==10
    assert initial['settings']['keep_recent']==144
    call('desktop.layout.settings',dict(enabled=False,interval_minutes=1,keep_recent=3))
    # Separate frozen processes prove settings survive application restarts.
    saved=call('desktop.layout.info')['settings']
    assert not saved['enabled'] and saved['interval_minutes']==1 and saved['keep_recent']==3,saved
    assert not call('desktop.layout.tick')['created']
    exported=call('desktop.layout.diagnostics')
    report=json.loads(exported['content'])
    assert report['schema']==1 and isinstance(report['events'],list)
    assert report['environment']['windows'].get('CurrentBuildNumber'),report['environment']
    assert 'beta' in report['environment']['application_version'],report['environment']
    print('Frozen diagnostic export: Windows edition/build and JSON report passed')
    print('Frozen sixth tool: platform detection, persisted settings and disabled timer passed')
