"""Real DOCX -> auto inline table -> edit -> existing generate button, no config import."""
import os,time,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from collections import Counter
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from clinical_studio.word_batch import WordBatchTool
from clinical_studio.word_batch_engine import generate_batch
from test_prose_table import FIRST,SECOND,PEDIATRIC,RESPIRATORY
APP=QApplication.instance() or QApplication([])
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def make_docx(path,text,table=False):
    root=ET.Element(W+'document');body=ET.SubElement(root,W+'body')
    ET.SubElement(ET.SubElement(ET.SubElement(body,W+'p'),W+'r'),W+'t').text=text
    if table:
        tbl=ET.SubElement(body,W+'tbl')
        for row in [['项目','对照组(n=25)','试验组(n=25)'],['CRP','56.68±15.19','56.49±13.86']]:
            tr=ET.SubElement(tbl,W+'tr')
            for value in row:ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(tr,W+'tc'),W+'p'),W+'r'),W+'t').text=value
    with ZipFile(path,'w') as archive:archive.writestr('word/document.xml',ET.tostring(root))

class WorkflowTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.t=WordBatchTool();self.t.use_word_prose.setChecked(True);self.t.resize(1400,1000);self.t.show()
    def tearDown(self):
        if self.t.worker and self.t.worker.isRunning():self.t.worker.requestInterruption();self.t.worker.wait(10000)
        self.t.close();self.t.deleteLater();APP.processEvents();self.tmp.cleanup()
    def load(self,text,table=False):
        p=Path(self.tmp.name)/'study.docx';make_docx(p,text,table)
        self.t.import_word(p);self.t.show_group_selection(['对照组','试验组']);self.t.confirm_groups();APP.processEvents()
        self.assertTrue(self.t.groups_confirmed,self.t.message.text());self.assertTrue(self.t.inline_prose_active,self.t.message.text())
        self.assertEqual(self.t.pages.currentIndex(),self.t.prose_table_tab)
    def row(self,name):
        e=self.t.prose_table_editor
        return next(i for i,(vi,part,label) in enumerate(e.rows) if vi is not None and e.study()['variables'][vi]['name']==name and part=='summary')
    def test_pediatric_word_import_preview_and_generation(self):
        path=Path(self.tmp.name)/'pediatric.docx';make_docx(path,PEDIATRIC)
        self.t.import_word(path);self.t.show_group_selection(['对照组','观察组']);self.t.confirm_groups();APP.processEvents()
        self.assertTrue(self.t.inline_prose_active)
        editor=self.t.prose_table_editor;study=editor.study()
        self.assertEqual([g['n_origin'] for g in study['groups']],['reported','reported'])
        self.assertEqual({v['name'] for v in study['variables']},{'性别','年龄','病程'})
        row=self.row('病程');vi=editor.rows[row][0]
        self.assertEqual(editor.study()['variables'][vi]['unit'],'年')
        config=self.t.get_config()
        self.assertEqual(len(config['typed_fields']),6)
        result=generate_batch(config)
        self.assertEqual(len(result['rows']),108)
        self.assertIn('病程',result['columns'])

    def test_general_comparison_intro_imports_all_fields(self):
        self.load(RESPIRATORY)
        config=self.t.get_config();self.assertEqual(len(config['typed_fields']),14)
        result=generate_batch(config);self.assertEqual(len(result['rows']),50)
        self.assertIn('呼吸衰竭类型',result['columns']);self.assertIn('机械通气方式',result['columns'])

    def test_text_without_group_n_auto_displays_and_blocks_missing(self):
        self.load(FIRST)
        self.assertEqual([g['n'] for g in self.t.prose_table_editor.study()['groups']],[30,30])
        self.t.generate();self.assertIsNone(self.t.result);self.assertIn('未报告',self.t.message.text())
        e=self.t.prose_table_editor;row=self.row('入ICU时氧合指数');vi=e.rows[row][0];e.change_kind(vi,'mean_sd')
        row=self.row('入ICU时氧合指数');e.table.item(row,4).setText('150±30');e.table.item(row,5).setText('151±31')
        result=generate_batch(self.t.get_config());self.assertEqual(len(result['rows']),60)
        self.assertIn('入ICU时氧合指数',result['columns']);self.assertEqual(len(result['columns']),7)
    def test_existing_word_table_and_edited_prose_both_generated(self):
        self.load(SECOND,table=True);e=self.t.prose_table_editor
        row=self.row('BMI');e.table.item(row,4).setText('23.1±3.2')
        config=self.t.get_config();self.assertEqual(next(f['mean'] for f in config['typed_fields'] if f['name']=='BMI' and f['group']=='对照组'),23.1)
        self.t.generate()
        deadline=time.monotonic()+15
        while self.t.result is None and time.monotonic()<deadline:
            APP.processEvents();QTest.qWait(10)
            if self.t.worker is None:break
        self.assertIsNotNone(self.t.result,self.t.message.text());r=self.t.result
        self.assertEqual(len(r['rows']),50);self.assertIn('CRP',r['columns']);self.assertIn('BMI',r['columns']);self.assertEqual(len(r['columns']),8)
        gender=r['columns'].index('性别');rows=[row for row in r['rows'] if row[1]=='对照组']
        self.assertEqual(Counter(row[gender] for row in rows),{'男':14,'女':11})
    def test_new_word_resets_old_prose(self):
        self.load(SECOND);p=Path(self.tmp.name)/'empty.docx';make_docx(p,'另一份无一般资料的文档')
        self.t.import_word(p);self.assertFalse(self.t.inline_prose_active);self.assertIsNone(self.t.prose_table_editor.document)
    def test_overlapping_table_fields_do_not_duplicate(self):
        self.load(SECOND,table=True)
        config=self.t.get_config()
        config['typed_fields'].append(dict(config['typed_fields'][0],name='年龄',mean=58.6,sd=10.2))
        merged=self.t.merge_prose_table(config)
        names=[(f['name'],f['group']) for f in merged['typed_fields']]
        self.assertEqual(len(names),len(set(names)))

if __name__=='__main__':unittest.main()
