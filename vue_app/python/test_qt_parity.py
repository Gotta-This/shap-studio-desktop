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
