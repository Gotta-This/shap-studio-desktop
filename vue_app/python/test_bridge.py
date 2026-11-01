from pathlib import Path
import base64,json,os,sqlite3,subprocess,sys,tempfile,unittest
from zipfile import ZipFile
import bridge
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=bridge.PROFILE;bridge.PROFILE=Path(self.tmp.name)/'profile';self.root=Path(self.tmp.name)/'workspace';self.call=bridge.dispatch
    def tearDown(self):bridge.PROFILE=self.old;self.tmp.cleanup()
    def enable(self):return self.call('workspace.enable',{'root':str(self.root)})
    def create(self,name='冠心病返修'):
        return self.call('task.create',dict(name=name,client='张老师',tags='预测模型，返修',deadline='2028-02-29',first_todo='核对审稿意见'))
    def upload(self,name='材料.txt',body=b'original',task=None):
        return self.call('files.import',dict(task_id=task,uploads=[dict(name=name,content=base64.b64encode(body).decode())],categories=['原稿'] if task else None))
    def test_empty_profile_does_not_enable_or_scan_workspace(self):
        self.assertIsNone(self.call('state',{})['root']);self.assertFalse(self.root.exists())
        self.root.mkdir();(self.root/'历史文件.txt').write_text('保留');self.enable();self.assertEqual(self.call('state',{})['tasks'],[])
    def test_task_directory_rename_preserves_completed_and_file_links(self):
        self.enable();tid=self.create();received=self.upload(task=tid);todo=self.call('task.detail',{'id':tid})['todos'][0]
        self.call('todo.save',{'id':todo['id'],'completed':True})
        self.call('task.update',dict(id=tid,name='第二轮返修',client='李老师',tags=['返修'],status='返修中',deadline='2028-03-01',notes='核对图表'))
        d=self.call('task.detail',{'id':tid});self.assertTrue(d['todos'][0]['completed']);self.assertEqual(d['task']['due_date'],'2028-03-01');self.assertTrue(bridge.workspace().file_path(received['file_ids'][0]).exists())
        self.assertTrue((self.root/d['task']['directory']/'原稿').is_dir())
    def test_duplicate_import_reuses_files_without_reopening_completed_work(self):
        self.enable();tid=self.create();a=self.upload(task=tid);todo=self.call('task.detail',{'id':tid})['todos'][0];self.call('todo.save',{'id':todo['id'],'completed':True});b=self.upload(task=tid)
        self.assertEqual(a['file_ids'],b['file_ids']);self.assertEqual(b['received'],0);self.assertEqual(b['duplicates'],['材料.txt']);self.assertTrue(self.call('task.detail',{'id':tid})['todos'][0]['completed'])
    def test_inbox_archive_preview_and_undo(self):
        self.enable();tid=self.create();fid=self.upload(body='新材料'.encode())['file_ids'][0]
        self.call('files.archive',dict(ids=[fid],task_id=tid,categories=['修改稿']))
        self.assertEqual(self.call('state',{})['inbox'],[]);self.assertEqual(self.call('files.preview',{'id':fid})['text'],'新材料')
        event=next(e for e in self.call('events',{}) if e['kind']=='归档材料');self.call('files.undo',{'id':event['id']});self.assertEqual(len(self.call('state',{})['inbox']),1)
    def test_personal_todo_date_completion_delete_restore(self):
        tid=self.call('todo.save',{'text':'个人待办','due_date':'2028-02-29'})
        self.call('todo.save',{'id':tid,'completed':True});self.assertTrue(self.call('state',{})['todos'][0]['completed'])
        self.call('todo.save',{'id':tid,'deleted':True});self.assertFalse(self.call('state',{})['todos']);self.call('todo.save',{'id':tid,'deleted':False,'due_date':None});self.assertIsNone(self.call('state',{})['todos'][0]['due_date'])
    def test_invalid_dates_do_not_change_saved_state(self):
        tid=self.call('todo.save',{'text':'保留日期','due_date':'2028-02-29'})
        with self.assertRaises(ValueError):self.call('todo.save',{'id':tid,'due_date':'2027-02-29'})
        self.assertEqual(self.call('state',{})['todos'][0]['due_date'],'2028-02-29')
    def test_relocate_rejects_wrong_content_and_recovers_original(self):
        self.enable();tid=self.create();fid=self.upload(task=tid)['file_ids'][0];bridge.workspace().file_path(fid).unlink()
        with self.assertRaises(ValueError):self.call('files.relocate',dict(id=fid,uploads=[dict(name='wrong.txt',content=base64.b64encode(b'wrong').decode())]))
        self.call('files.relocate',dict(id=fid,uploads=[dict(name='right.txt',content=base64.b64encode(b'original').decode())]));self.assertTrue(bridge.workspace().file_path(fid).is_file())
    def test_category_deterministic_and_numeric_actual_statistics(self):
        p={'rows':[{'value':1,'count':28},{'value':0,'count':93}],'seed':12};a=self.call('tool.category',p);self.assertEqual(a,self.call('tool.category',p));self.assertEqual(len(a['values']),121);self.assertEqual(sum(a['values']),28)
        r=self.call('tool.numeric',dict(n=20,mean=10,sd=2,digits=2,seed=12));self.assertEqual(len(r['values']),20);self.assertLess(abs(r['mean']-10),.1)
    def test_native_and_uploaded_material_categories_match_actual_folders(self):
        self.enable();tid=self.create()
        native=Path(self.tmp.name)/'原始数据.csv';native.write_text('x,y\n1,2')
        received=self.call('files.import',dict(task_id=tid,paths=[str(native)],uploads=[dict(name='原稿.txt',content=base64.b64encode(b'original').decode())],categories=['原始数据','原稿']))
        files=self.call('task.detail',{'id':tid})['files'];by_name={f['original_name']:f for f in files}
        self.assertEqual(by_name['原始数据.csv']['category'],'原始数据')
        self.assertEqual(by_name['原稿.txt']['category'],'原稿')
        self.assertEqual(bridge.workspace().file_path(by_name['原稿.txt']['id']).parent.name,'原稿')
        self.assertEqual(native.read_text(),'x,y\n1,2')
    def test_upload_name_cannot_escape_staging(self):
        self.enable()
        with self.assertRaises(ValueError):self.upload('../escape.txt')
    def test_stdin_protocol_errors_are_structured(self):
        result=subprocess.run([sys.executable,str(Path(bridge.__file__))],input=json.dumps({'method':'not.allowed'}),text=True,capture_output=True,env={**os.environ,'RESEARCH_V3_PROFILE':str(bridge.PROFILE)})
        response=json.loads(result.stdout);self.assertFalse(response['ok']);self.assertIn('不支持',response['error'])
if __name__=='__main__':unittest.main()
