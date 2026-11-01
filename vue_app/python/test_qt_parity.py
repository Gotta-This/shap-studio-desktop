"""Exercise the live Qt engines through the new V3 workflow, without desktop input."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
import base64, io, json, os, subprocess, sys, tempfile, time, unittest
import bridge
from word_workflow import compose, review
from clinical_studio.word_batch_engine import default_batch_config

class ParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=bridge.PROFILE;bridge.PROFILE=self.root
    def tearDown(self):bridge.PROFILE=self.old;self.tmp.cleanup()
    def doc(self):
        w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}';root=E.Element(w+'document');body=E.SubElement(root,w+'body')
        E.SubElement(E.SubElement(E.SubElement(body,w+'p'),w+'r'),w+'t').text='表1 一般资料'
        t=E.SubElement(body,w+'tbl')
        for row in [['项目','对照组(n=10)','中药组(n=12)'],['年龄','58.2±4.1','57.9±3.5']]:
            r=E.SubElement(t,w+'tr')
            for text in row:E.SubElement(E.SubElement(E.SubElement(E.SubElement(r,w+'tc'),w+'p'),w+'r'),w+'t').text=text
        path=self.root/'统计.docx'
        with ZipFile(path,'w') as z:z.writestr('word/document.xml',E.tostring(root))
        return path
    def import_word(self,**options):
        scanned=bridge.dispatch('tool.word.scan',{'paths':[str(self.doc())]})
        p=dict(session=scanned['session'],draft=scanned['draft'],groups=scanned['scan']['candidates'],options=options)
        return scanned,p,bridge.dispatch('tool.word.apply',p)
    def wait(self,jid):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            r=bridge.dispatch('tool.job.status',{'id':jid})
            if r['status']!='running':return r
            time.sleep(.1)
        self.fail('worker did not finish')
    def test_scan_is_headless_and_n_requires_explicit_opt_in(self):
        s,p,r=self.import_word()
        self.assertEqual([g['n'] for g in r['config']['groups']],[70,70]);self.assertTrue(s['scan']['tables'])
        p['options']['sizes']=True;r=bridge.dispatch('tool.word.apply',p)
        self.assertEqual([g['n'] for g in r['config']['groups']],[10,12])
        script="import sys;sys.path[:0]=['desktop_app','vue_app/python'];import word_workflow;assert not any(x.startswith('PySide6') for x in sys.modules)"
        subprocess.run([sys.executable,'-c',script],check=True,cwd=Path(__file__).resolve().parents[2])
    def test_draft_edits_and_table_titles_survive_confirm_and_background_export(self):
        s,p,r=self.import_word(sizes=True)
        p['draft']['fields'][0]['mean']=61;p['draft']['fields'][0]['digits']=1;p['draft']['tables'][0]['title']='修订原表名'
        r=bridge.dispatch('tool.word.apply',p)
        self.assertEqual(r['config']['table_titles']['1'],'修订原表名')
        self.assertEqual((r['config']['indicators']+r['config']['typed_fields'])[0]['mean'],61)
        old=os.environ.get('RESEARCH_V3_PROFILE');os.environ['RESEARCH_V3_PROFILE']=str(self.root)
        try:state=self.wait(bridge.dispatch('tool.job.start',{'kind':'word','params':{'config':r['config']}})['id'])
        finally:
            if old is None:os.environ.pop('RESEARCH_V3_PROFILE',None)
            else:os.environ['RESEARCH_V3_PROFILE']=old
        self.assertEqual(state['status'],'done',state)
        result=state['result'];self.assertEqual(result['total'],22);self.assertEqual(len(result['text'].splitlines()),23)
        with ZipFile(io.BytesIO(base64.b64decode(result['base64']))) as z:self.assertIn('xl/workbook.xml',z.namelist())
    def test_shared_basics_preserves_per_group_outcomes_and_invalid_prose_keeps_sources(self):
        _,_,r=self.import_word();c=r['config'];c['shared_basics']=True;c['groups'][1].update(male=2,effective=23,recurrence=8)
        built=compose({'config':c});self.assertEqual(built['groups'][1]['male'],50);self.assertEqual(built['groups'][1]['effective'],23)
        p=dict(config=c,prose_document={'studies':[]},prose_stale=True)
        with self.assertRaisesRegex(ValueError,'重新识别'):compose(p)
        self.assertTrue(review(p)['rows']);self.assertIn('重新识别',review(p)['error'])
    def test_prose_conflicts_need_current_table_snapshot_and_unparsed_review(self):
        from clinical_studio.prose_table_engine import parse_document
        _,_,r=self.import_word(sizes=True);c=r['config']
        doc=parse_document('对照组10例，年龄（60±4）岁。中药组12例，年龄（59±3）岁。',['对照组','中药组'])
        p=dict(config=c,prose_document=doc)
        with self.assertRaisesRegex(ValueError,'冲突'):compose(p)
        for variable in doc['studies'][0]['variables']:
            for group,cell in variable['cells'].items():
                cell.update(reviewed=True,table_conflict=next(f for f in c['typed_fields']+c['indicators'] if f['group']==group))
        confirmed=bridge.dispatch('tool.word.prose.confirm',dict(variable='年龄（岁）',group='对照组',cell=doc['studies'][0]['variables'][0]['cells']['对照组'],fields=c['typed_fields']+c['indicators']))
        self.assertIn('table_conflict',confirmed)
        self.assertFalse(compose(p)['include_basics'])
        doc['studies'][0]['unparsed']=[{'raw':'额外说明','reason':'核对'}]
        with self.assertRaisesRegex(ValueError,'未识别'):compose(p)
        self.assertTrue(review(p)['rows'])
    def test_ungrouped_source_counts_and_cooperative_cancel(self):
        from clinical_studio.merged_table_verify import save_fixture
        from clinical_studio.word_batch_engine import generate_batch
        path=save_fixture(self.root/'ungrouped.docx',[[['项目','数值'],['性别（男/女）','18/2'],['年龄','60±5']]])
        scanned=bridge.dispatch('tool.word.scan',{'paths':[str(path)]})
        r=bridge.dispatch('tool.word.apply',dict(session=scanned['session'],draft=scanned['draft'],ungrouped=True,n=20))
        result=generate_batch(compose({'config':r['config']}))
        self.assertNotIn('分组',result['columns']);self.assertEqual(len(result['rows']),20)
        jid=bridge.dispatch('tool.job.start',{'kind':'word','params':{'config':r['config']}})['id']
        bridge.dispatch('tool.job.cancel',{'id':jid});state=self.wait(jid)
        self.assertEqual(state['status'],'cancelled',state)
    def test_legacy_doc_session_survives_bridge_exit(self):
        source=self.doc();legacy=source.with_suffix('.doc');legacy.write_bytes(source.read_bytes())
        env={**os.environ,'RESEARCH_V3_PROFILE':str(self.root)}
        def request(method,params):
            r=subprocess.run([sys.executable,str(Path(bridge.__file__))],input=json.dumps(dict(method=method,params=params)),text=True,capture_output=True,env=env,check=True)
            response=json.loads(r.stdout);self.assertTrue(response['ok'],response);return response['result']
        scanned=request('tool.word.scan',{'paths':[str(legacy)]})
        reference=json.loads((self.root/'word-sessions'/scanned['session']/'source.json').read_text())
        self.assertTrue(Path(reference['path']).is_file());self.assertTrue(Path(reference['path']).resolve().is_relative_to(self.root.resolve()))
        applied=request('tool.word.apply',dict(session=scanned['session'],groups=scanned['scan']['candidates']))
        self.assertEqual(applied['config']['source'],legacy.name)
    def test_field_editor_keeps_peer_values_confirmation_and_requires_valid_rules(self):
        current=dict(table=1,name='评分',group='对照组',kind='mean_sd',mean=50,sd=5,digits=0,confirmed=True)
        peer=dict(current,group='试验组',mean=60,classification='原分类')
        edited=dict(current,mean=51,classification='新分类')
        result=bridge.dispatch('tool.word.field.save',dict(field=edited,peers=[peer]))
        self.assertEqual(result['peers'][0]['mean'],60);self.assertTrue(result['peers'][0]['confirmed']);self.assertEqual(result['peers'][0]['classification'],'新分类')
        for field in [dict(current,sd=None),dict(current,sd=-1),dict(current,digits=1,parity='odd'),dict(current,aggregate_pending=True),dict(current,kind='category',labels=['甲','乙'],weights=[-10,110])]:
            with self.subTest(field=field),self.assertRaises(ValueError):bridge.dispatch('tool.word.field.save',{'field':field})
        derived=bridge.dispatch('tool.word.field.save',{'field':dict(current,kind='derived',from_field='疗效',positive_labels=['显效'])})['field']
        self.assertEqual(derived['labels'],['有效','无效'])
    def test_review_shows_pending_prose_and_disabled_prose_does_not_change_group_sizes(self):
        from clinical_studio.prose_table_engine import parse_document
        _,_,r=self.import_word();c=r['config'];c['same_group_size']=True;c['groups'][1]['n']=35
        doc=parse_document('对照组10例，年龄（60±4）岁。中药组12例，年龄（59±3）岁。',['对照组','中药组'])
        reviewed=review(dict(config=c,prose_document=doc,prose_stale=True))
        self.assertTrue(any(x['source']=='Word正文（待核对）' for x in reviewed['rows']));self.assertIn('重新识别',reviewed['error'])
        built=compose(dict(config=c,prose_document=doc,prose_active=False))
        self.assertEqual([g['n'] for g in built['groups']],[70,70])
    def test_numeric_background_snapshot_cancel_and_category_fractional_counts(self):
        params=dict(n=20,mean=50,sd=5,digits=1,seed=42)
        done=self.wait(bridge.dispatch('tool.job.start',dict(kind='numeric',params=params))['id'])
        self.assertEqual(done['status'],'done',done);self.assertEqual(done['result']['params'],params)
        self.assertEqual(len(done['result']['values']),20)
        jid=bridge.dispatch('tool.job.start',dict(kind='numeric',params=dict(params,n=5000)))['id']
        bridge.dispatch('tool.job.cancel',{'id':jid});self.assertEqual(self.wait(jid)['status'],'cancelled')
        bad=self.wait(bridge.dispatch('tool.job.start',dict(kind='category',params=dict(rows=[dict(value=1,count=2.5)])))['id'])
        self.assertEqual(bad['status'],'error');self.assertIn('整数',bad['message'])
    def test_configuration_loading_rejects_broken_structure_without_hiding_drafts(self):
        for method,config in [('tool.word.configuration',{'version':1,'groups':[{}]}),('tool.shap.configuration',{'schema_version':1,'data':{'features':[]},'plots':{'common':{}}}),('tool.word.prose.configuration',{'studies':[{'groups':[]}]})]:
            with self.subTest(method=method),self.assertRaises(ValueError):bridge.dispatch(method,{'config':config})
        c=bridge.dispatch('tool.word.configuration',{'config':dict(version=1,groups=[dict(name='对照组')],typed_fields=[dict(name='待补指标',group='对照组',kind='unknown')])})
        self.assertEqual(c['groups'][0]['severity'],[50,50,0]);self.assertEqual(c['typed_fields'][0]['kind'],'unknown')
    def test_first_todo_and_archive_keep_independent_deadlines_and_priorities(self):
        bridge.dispatch('workspace.enable',{'root':str(self.root/'workspace')})
        tid=bridge.dispatch('task.create',dict(name='测试稿件',deadline='2028-03-10',first_todo='第一项',todo_deadline='2028-02-29',priority='high'))
        first=next(t for t in bridge.dispatch('state',{})['todos'] if t['text']=='第一项')
        self.assertEqual((first['due_date'],first['priority']),('2028-02-29','high'))
        f=self.root/'原件.txt';f.write_text('内容')
        bridge.dispatch('files.import',{'paths':[str(f)]})
        fid=bridge.dispatch('state',{})['inbox'][0]['id']
        state=bridge.dispatch('files.archive',dict(ids=[fid],task_id=tid,categories=['原稿'],todo_text='归档后核对',deadline='2028-03-01',priority='low'))
        todo=next(t for t in state['todos'] if t['text']=='归档后核对')
        self.assertEqual((todo['due_date'],todo['priority']),('2028-03-01','low'));self.assertIn(fid,todo['file_ids'])
    def test_long_real_word_names_are_not_subject_to_task_name_limits(self):
        name='原稿'+('稿'*78)+'.docx'
        source=self.doc();uploaded=base64.b64encode(source.read_bytes()).decode()
        result=bridge.dispatch('tool.word.scan',{'uploads':[{'name':name,'content':uploaded}]})
        self.assertEqual(result['scan']['source_name'],name)
        self.assertTrue(result['scan']['fields'])
    def test_native_save_preserves_unicode_and_binary_content(self):
        target=self.root/'导出参数.json'
        bridge.dispatch('exports.save',dict(path=str(target),content='中文😀参数'))
        self.assertEqual(target.read_text(),'中文😀参数')
        content=b'PK\x03\x04binary-test\x00'
        bridge.dispatch('exports.save',dict(path=str(target),content=base64.b64encode(content).decode(),base64=True))
        self.assertEqual(target.read_bytes(),content)
        with self.assertRaises(ValueError):bridge.dispatch('exports.save',dict(path='relative.json',content='x'))
    def test_real_shap_data_pagination_and_selective_export(self):
        from analysis_workflow import run,table,export
        c=bridge.dispatch('tool.shap.defaults',{});c['data']['n_samples']=205
        r=run(self.root,dict(config=c,data_only=True),lambda _:None)
        self.assertEqual(r['total'],205);self.assertEqual(len(table(self.root,dict(id=r['id'],page=1))['rows']),5)
        z=export(self.root,dict(id=r['id'],kinds=['config']))
        with ZipFile(io.BytesIO(base64.b64decode(z['base64']))) as archive:self.assertEqual([Path(x).name for x in archive.namelist()],['parameters.json'])
        with self.assertRaisesRegex(ValueError,'无效'):table(self.root,{'id':'../../file'})
    def test_real_shap_model_redraw_and_changed_data_guard(self):
        from analysis_workflow import run
        c=bridge.dispatch('tool.shap.defaults',{});c['data']['n_samples']=80;c['explanation']['background_max_samples']=10
        for p in c['plots']['plots'].values():p['enabled']=False
        r=run(self.root,dict(config=c),lambda _:None);self.assertTrue(r['has_model'])
        c['plots']['common']['font_size']=12
        redraw=run(self.root,dict(config=c,previous=r['id']),lambda _:None);self.assertEqual(redraw['metrics']['auc'],r['metrics']['auc'])
        c['data']['n_samples']=81
        with self.assertRaises(ValueError):run(self.root,dict(config=c,previous=r['id']),lambda _:None)
if __name__=='__main__':unittest.main()
