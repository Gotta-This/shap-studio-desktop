"""Close the real hidden window during an active IPC call, without desktop input."""
from pathlib import Path
import json,os,sqlite3,subprocess,sys,time
host=Path(sys.argv[1]).resolve();folder=Path(sys.argv[2]).resolve();folder.mkdir(parents=True,exist_ok=True)
request=folder/'close-request.json';report=folder/'native-close-report.json'
request.unlink(missing_ok=True);report.unlink(missing_ok=True)
with (folder/'app.log').open('w') as log:
 result=subprocess.run([str(host),'--close-review',str(folder)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,env={**os.environ,'PYTHONUTF8':'1','RESEARCH_V3_DEBUG':'0'},timeout=60)
assert result.returncode==0,result.returncode
assert report.is_file(),'Native window never received its close event'
value=json.loads(report.read_text());started=json.loads(request.read_text())
assert value['native_close_event'] and value['active_requests']>0,value
elapsed=time.time()*1000-started['requested_at_ms']
assert elapsed<5000,elapsed
with sqlite3.connect(folder/'data/profile/personal.sqlite3') as db:
 assert db.execute('SELECT text FROM todos WHERE text=?',('关闭验收：已保存的待办',)).fetchone()
value.update(exit_after_request_ms=round(elapsed),saved_data_preserved=True,ok=True)
report.write_text(json.dumps(value,ensure_ascii=False,indent=2))
print(json.dumps(value,ensure_ascii=False,indent=2))
print('Actual native window close during active IPC passed; no system mouse or keyboard used')
