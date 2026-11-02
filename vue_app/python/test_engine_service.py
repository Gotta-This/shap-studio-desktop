"""The desktop's long-lived engine keeps IPC responsive while jobs run."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,time,unittest

class EngineServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.error=tempfile.TemporaryFile(mode='w+')
        self.launch()
    def launch(self,default=False):
        env={**os.environ,'RESEARCH_V3_PROFILE':self.temp.name,'MPLCONFIGDIR':self.temp.name+'/mpl'}
        if default:env.pop('RESEARCH_V3_PROFILE',None);env['RESEARCH_V3_DATA_ROOT']=self.temp.name
        self.process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('bridge.py')),'--serve'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.error,text=True,encoding='utf-8',env=env)
        self.sequence=0
    def call(self,method,params=None):
        self.sequence+=1
        self.process.stdin.write(json.dumps(dict(id=self.sequence,request=dict(method=method,params=params or {})))+'\n');self.process.stdin.flush()
        reply=json.loads(self.process.stdout.readline());self.assertEqual(reply['id'],self.sequence)
        return reply['response']
    def tearDown(self):
        if not self.process.stdin.closed:self.process.stdin.close()
        try:self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait();raise
        finally:self.process.stdout.close();self.error.close();self.temp.cleanup()
    def test_reuses_runtime_recovers_from_request_errors_and_multiplexes_ids(self):
        pid=self.call('runtime.info')['result']['engine_pid']
        self.assertEqual(pid,self.process.pid)
        self.assertFalse(self.call('not-a-method')['ok'])
        for i in range(20):
            self.process.stdin.write(json.dumps(dict(id=100+i,request=dict(method='runtime.info')))+'\n')
        self.process.stdin.flush()
        replies=[json.loads(self.process.stdout.readline()) for _ in range(20)]
        self.assertEqual({r['id'] for r in replies},set(range(100,120)))
        self.assertTrue(all(r['response']['result']['engine_pid']==pid for r in replies))
    def test_background_generation_and_persistence_use_warm_service(self):
        started=self.call('tool.job.start',dict(kind='numeric',params=dict(n=70,mean=27.92,sd=14.87,digits=0,mode='target',seed=12)))
        self.assertTrue(started['ok'],started)
        jid=started['result']['id']
        self.assertTrue(self.call('todo.save',dict(text='生成时也能保存待办'))['ok'])
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            state=self.call('tool.job.status',dict(id=jid))['result']
            if state['status']!='running':break
            time.sleep(.01)
        self.assertEqual(state['status'],'done',state)
        self.assertEqual(len(state['result']['values']),70)
        self.assertEqual(self.call('state')['result']['todos'][0]['text'],'生成时也能保存待办')

    def test_accepted_job_finishes_after_client_disconnects(self):
        started=self.call('tool.job.start',dict(kind='numeric',params=dict(n=70,mean=27.92,sd=14.87,digits=0,mode='target',seed=12)))
        jid=started['result']['id']
        self.process.stdin.close()
        self.process.wait(timeout=20)
        status=json.loads((Path(self.temp.name)/'jobs'/jid/'status.json').read_text())
        self.assertEqual(status['status'],'done',status)

    def test_default_workspace_initialization_is_safe_under_parallel_requests(self):
        self.process.stdin.close();self.process.wait(timeout=20);self.process.stdout.close()
        self.launch(default=True)
        for i in range(10):
            self.process.stdin.write(json.dumps(dict(id=100+i,request=dict(method='state')))+'\n')
        self.process.stdin.flush()
        for _ in range(10):
            reply=json.loads(self.process.stdout.readline())['response']
            self.assertTrue(reply['ok'],reply)
            self.assertEqual(reply['result']['root'],str((Path(self.temp.name)/'workspace').resolve()))
