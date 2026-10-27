"""A single DOCX owns independent editable table and prose sources across edits/reload."""
import os,tempfile,json,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QFileDialog
from clinical_studio.word_batch import WordBatchTool
from clinical_studio.word_batch_engine import generate_batch
from test_prose_table_workflow import make_docx,SECOND,W
APP=QApplication.instance() or QApplication([])

class MixedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.t=WordBatchTool();self.t.show()
        self.path=self.root/'mixed.docx';make_docx(self.path,SECOND,table=True);self.load()
    def tearDown(self):self.t.close();self.t.deleteLater();APP.processEvents();self.tmp.cleanup()
    def load(self):
        t=self.t;t.import_word(self.path);t.show_group_selection(['对照组','试验组']);t.confirm_groups();APP.processEvents()
        self.assertTrue(t.groups_confirmed,t.message.text())
    def table_fields(self):return deepcopy(self.t.typed_specs)
    def roundtrip(self):
        config=self.t.get_config();p=self.root/'saved.json';p.write_text(json.dumps(config,ensure_ascii=False))
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(p),'')):self.t.load_config()
        self.assertNotIn('失败',self.t.message.text());return config
    def test_raw_text_edit_and_reparse_never_clears_table_or_source_review(self):
        t=self.t;e=t.prose_table_editor;before=self.table_fields()
        e.source.setPlainText(SECOND.replace('22.8','24.1'))
        t.pages.setCurrentIndex(t.SOURCES_PAGE);APP.processEvents()
        self.assertTrue(any(t.rule_table.item(i,0).text()=='CRP' for i in range(t.rule_table.rowCount())))
        self.assertIn('表格匹配保持不变',t.rule_note.text());self.assertEqual(t.typed_specs,before)
        with self.assertRaisesRegex(ValueError,'重新识别'):t.get_config()
        e.convert();self.assertEqual(t.typed_specs,before)
        c=t.get_config();self.assertEqual(next(f['mean'] for f in c['typed_fields'] if f['name']=='BMI' and f['group']=='对照组'),24.1)
        r=generate_batch(c);self.assertEqual(len(r['rows']),50);self.assertIn('CRP',r['columns']);self.assertIn('BMI',r['columns'])
    def test_both_source_edits_survive_save_reload_and_more_text_edits(self):
        t=self.t;e=t.prose_table_editor
        field=next(f for f in t.typed_specs if f['name']=='CRP' and f['group']=='对照组');field['mean']=57.2
        t.set_typed_fields(t.typed_specs);e.source.setPlainText(SECOND.replace('22.8','24.2'));e.convert()
        table=self.table_fields();config=self.roundtrip()
        self.assertEqual(self.table_fields(),table);self.assertEqual({f['name'] for f in t.typed_specs},{'CRP'})
        self.assertEqual(t.get_config(),config)
        e.source.setPlainText(SECOND.replace('22.8','25.1'));e.convert()
        self.assertEqual(self.table_fields(),table)
        r=generate_batch(t.get_config());self.assertIn('CRP',r['columns']);self.assertIn('BMI',r['columns'])
    def test_identical_overlap_is_saved_separately_and_conflict_does_not_remove_table(self):
        with ZipFile(self.path) as z:root=ET.fromstring(z.read('word/document.xml'))
        row=list(root.iter(W+'tbl'))[0].findall(W+'tr')[1]
        for cell,value in zip(row.findall(W+'tc'),['BMI','22.8±3.1','22.5±2.9']):next(cell.iter(W+'t')).text=value
        with ZipFile(self.path,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
        self.load();t=self.t;e=t.prose_table_editor;before=self.table_fields();self.roundtrip()
        self.assertEqual(t.typed_specs,before)
        e.source.setPlainText(SECOND.replace('22.8','26.2'));e.convert()
        with self.assertRaisesRegex(ValueError,'冲突'):t.get_config()
        t.refresh_rule_review();self.assertTrue(any(t.rule_table.item(i,2).text().startswith('Word表') for i in range(t.rule_table.rowCount())))
        self.assertEqual(t.typed_specs,before)
        # Explicitly confirming the prose value affects the generation view only.
        i=next(i for i,(vi,part,_) in enumerate(e.rows) if vi is not None and e.study()['variables'][vi]['name']=='BMI' and part=='summary')
        e.table.setCurrentCell(i,4);e.resolve_cell();config=self.roundtrip()
        self.assertEqual(t.typed_specs,before)
        self.assertEqual(next(f['mean'] for f in config['typed_fields'] if f['name']=='BMI' and f['group']=='对照组'),26.2)
        self.assertEqual(next(f['mean'] for f in config['table_match']['typed_fields'] if f['name']=='BMI' and f['group']=='对照组'),22.8)
    def test_manual_prose_added_to_table_only_document_is_included(self):
        make_docx(self.path,'本页仅有汇总表',table=True);self.load();self.assertFalse(self.t.inline_prose_active)
        e=self.t.prose_table_editor;e.source.setPlainText(SECOND);e.convert()
        result=generate_batch(self.t.get_config());self.assertIn('CRP',result['columns']);self.assertIn('BMI',result['columns'])
    def test_deleting_a_prose_variable_never_deletes_table_fields(self):
        e=self.t.prose_table_editor;before=self.table_fields()
        row=next(i for i,(vi,part,_) in enumerate(e.rows) if vi is not None and e.study()['variables'][vi]['name']=='BMI' and part=='summary')
        e.table.setCurrentCell(row,4);e.remove_variable()
        self.assertEqual(self.t.typed_specs,before);result=generate_batch(self.t.get_config())
        self.assertIn('CRP',result['columns']);self.assertNotIn('BMI',result['columns'])

if __name__=='__main__':unittest.main()
