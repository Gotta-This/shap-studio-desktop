"""Read/write settings in an isolated profile; never move CI desktop icons."""
import json,os,subprocess,sys,tempfile,hashlib,zipfile
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
    # Restore synthetic vendor files through the frozen bridge. APPDATA is
    # redirected: CI never reads or replaces the real user's 360 directory.
    vendor_appdata=Path(tmp)/'synthetic-appdata';vendor=vendor_appdata/'360DesktopLite'
    vendor.mkdir(parents=True);(vendor/'layout.ini').write_bytes(b'current synthetic config')
    env['APPDATA']=str(vendor_appdata)
    call('desktop.layout.settings',dict(feature_enabled=True,enabled=False,interval_minutes=10,keep_recent=144))
    content=b'backed up synthetic config'
    digest=hashlib.sha256(json.dumps([('layout.ini',hashlib.sha256(content).hexdigest())],ensure_ascii=False).encode()).hexdigest()
    folder=Path(tmp)/'desktop-layouts';archives=folder/'360-data';archives.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archives/(digest+'.zip'),'w') as archive:archive.writestr('layout.ini',content)
    identifier='a'*32
    snapshot=dict(version=1,id=identifier,label='Synthetic vendor restore',created_at='2026-11-04T00:00:00+08:00',protected=True,reason='manual',computer='synthetic',display={},icons=[],assistant=dict(status='saved',archive=digest+'.zip',file_count=1,bytes=len(content),message='Synthetic only'))
    (folder/(identifier+'.json')).write_text(json.dumps(snapshot),encoding='utf8')
    preview=call('desktop.layout.assistant_preview',dict(id=identifier))
    restored=call('desktop.layout.assistant_restore',dict(id=identifier,fingerprint=preview['fingerprint']))
    assert (vendor/'layout.ini').read_bytes()==content
    assert (Path(restored['rollback_directory'])/'layout.ini').read_bytes()==b'current synthetic config'
    assert call('desktop.layout.diagnostics')['event_count']>=4
    call('desktop.layout.settings',dict(feature_enabled=False,enabled=True,interval_minutes=10,keep_recent=144))
    assert not call('desktop.layout.info')['settings']['feature_enabled']
    assert not call('desktop.layout.tick')['created']
    print('Frozen sixth tool: persisted switches, synthetic 360 restore/rollback and diagnostics passed')
