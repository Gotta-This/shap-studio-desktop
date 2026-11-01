from pathlib import Path
import json,os,sqlite3,subprocess,sys,tempfile,unittest
from unittest.mock import patch
import storage
from clinical_studio.manuscripts import WorkspaceStore

class StorageTests(unittest.TestCase):
    def test_platform_user_directories(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(storage.data_root('darwin',home=Path('/users/example')),Path('/users/example/.research-data-tools'))
            self.assertEqual(storage.data_root('win32',documents=Path('/redirected/Documents')),Path('/redirected/Documents/.research-data-tools'))
    def test_old_v3_profile_is_copied_once_without_changing_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old';old.mkdir();data=root/'data'
            workspace=WorkspaceStore(root/'chosen-workspace')
            (old/'source.json').write_text(json.dumps(dict(path=str(old/'word-sessions/source.docx'))))
            (old/'workspace.json').write_text(json.dumps(dict(root=str(workspace.root))))
            with sqlite3.connect(old/'personal.sqlite3') as db:db.execute('CREATE TABLE todos(text TEXT)');db.execute("INSERT INTO todos VALUES('旧记录')")
            profile=storage.initialize(data,old)
            with sqlite3.connect(profile/'personal.sqlite3') as db:self.assertEqual(db.execute('SELECT text FROM todos').fetchone()[0],'旧记录');db.execute("UPDATE todos SET text='新版本修改'")
            storage.initialize(data,old)
            with sqlite3.connect(profile/'personal.sqlite3') as db:self.assertEqual(db.execute('SELECT text FROM todos').fetchone()[0],'新版本修改')
            with sqlite3.connect(old/'personal.sqlite3') as db:self.assertEqual(db.execute('SELECT text FROM todos').fetchone()[0],'旧记录')
            self.assertEqual(json.loads((profile/'workspace.json').read_text())['root'],str(workspace.root))
            self.assertEqual(json.loads((profile/'source.json').read_text())['path'],str(profile/'word-sessions/source.docx'))
    def test_default_workspace_and_todos_survive_new_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=(Path(tmp)/'.research-data-tools').resolve()
            env={**os.environ,'RESEARCH_V3_DATA_ROOT':str(root),'PYTHONUTF8':'1'};env.pop('RESEARCH_V3_PROFILE',None);env.pop('RESEARCH_V3_LEGACY_PROFILE',None)
            def call(method,params=None):
                p=subprocess.run([sys.executable,str(Path(__file__).with_name('bridge.py'))],input=json.dumps(dict(method=method,params=params or {})),text=True,encoding='utf-8',capture_output=True,env=env,timeout=20)
                value=json.loads(p.stdout);self.assertTrue(value['ok'],value);return value['result']
            state=call('state');self.assertEqual(state['root'],str(root/'workspace'))
            call('todo.save',dict(text='重装后保留的待办'))
            self.assertEqual(call('state')['todos'][0]['text'],'重装后保留的待办')
            self.assertTrue((root/'profile/personal.sqlite3').is_file())
            self.assertEqual(call('storage.info')['directory'],str(root))
            self.assertTrue((root/'workspace/.manuscripts.sqlite3').is_file())

if __name__=='__main__':unittest.main()
