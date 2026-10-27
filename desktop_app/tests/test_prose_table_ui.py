import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QFileDialog
from clinical_studio.prose_table_ui import ProseTableEditor
from clinical_studio.prose_table_engine import read_docx_text,to_simulation_config,validate_study
from test_prose_table import FIRST,SECOND
APP=QApplication.instance() or QApplication([])

class EditorTests(unittest.TestCase):
    def setUp(self):self.e=ProseTableEditor();self.e.source.setPlainText(SECOND);self.e.convert();self.e.show();APP.processEvents()
    def tearDown(self):self.e.close();self.e.deleteLater();APP.processEvents()
    def find(self,name,part='summary',label=None):
        return next(i for i,(vi,p,l) in enumerate(self.e.rows) if vi is not None and self.e.study()['variables'][vi]['name']==name and p==part and l==label)
    def test_edits_change_export_and_keep_source(self):
        e=self.e;row=self.find('年龄');e.table.item(row,4).setText('59.1±10.1');APP.processEvents()
        cell=e.study()['variables'][1]['cells']['对照组'];self.assertEqual(cell['mean'],59.1)
        self.assertIn('58.6',cell['evidence'][0]['raw']);self.assertEqual(cell['edits'][-1]['value'],'59.1±10.1')
        e.table.setCurrentCell(row,4);e.show_evidence(row,4);self.assertIn('58.6',e.evidence.toPlainText())
        self.assertEqual(to_simulation_config(e.study())['typed_fields'][2]['mean'],59.1)
        # Invalid edit is visibly rejected, and leaves model unchanged.
        e.table.item(row,4).setText('garbage');self.assertEqual(e.study()['variables'][1]['cells']['对照组']['mean'],59.1)
        self.assertIn('未应用',e.status.toPlainText())
    def test_missing_fill_and_save_roundtrip(self):
        e=self.e;e.source.setPlainText(FIRST);e.convert();row=self.find('入ICU时氧合指数');vi=e.rows[row][0]
        e.change_kind(vi,'mean_sd');row=self.find('入ICU时氧合指数')
        e.table.item(row,4).setText('150±30');e.table.item(row,5).setText('151±31')
        self.assertFalse(validate_study(e.study())['errors'])
        with tempfile.TemporaryDirectory() as tmp:
            table=Path(tmp)/'table.json';config=Path(tmp)/'config.json'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(table),'')):e.save_json()
            self.assertTrue(table.exists())
            with patch.object(QFileDialog,'getOpenFileName',return_value=(str(table),'')):e.open_json()
            self.assertEqual(e.study()['source_text'],FIRST)
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(config),'')):e.export_config()
            self.assertEqual(len(json.loads(config.read_text())['typed_fields']),10)
    def test_category_edit_and_multiple_studies(self):
        e=self.e;row=self.find('性别','category','男');e.table.item(row,4).setText('13')
        with self.assertRaises(ValueError):to_simulation_config(e.study())
        row=self.find('性别','category','女');e.table.item(row,4).setText('12')
        self.assertFalse(validate_study(e.study())['errors'])
        e.source.setPlainText(FIRST+'\n\n'+SECOND);e.convert();self.assertEqual(e.selector.count(),2)
        e.selector.setCurrentIndex(1);self.assertEqual(e.study()['groups'][0]['n'],25)
    def test_stale_text_prevents_mismatched_export(self):
        self.e.source.appendPlainText('资料变更')
        with self.assertRaises(ValueError):self.e.check_export()
    def test_word_reader_excludes_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.docx'
            with ZipFile(p,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>正文</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
            self.assertEqual(read_docx_text(p),'正文')
    def test_existing_workflow_loads_adapter(self):
        from clinical_studio.word_batch import WordBatchTool
        e=self.e
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'simulation.json';p.write_text(json.dumps(to_simulation_config(e.study()),ensure_ascii=False))
            tool=WordBatchTool()
            with patch.object(QFileDialog,'getOpenFileName',return_value=(str(p),'')):tool.load_config()
            self.assertNotIn('失败',tool.message.text())
            config=tool.get_config();self.assertEqual(len(config['typed_fields']),10);self.assertFalse(config['include_basics'])
            self.assertEqual([g['n'] for g in config['groups']],[25,25])
            tool.show();tool.open_prose_table();APP.processEvents();self.assertTrue(tool.prose_table_editor.isVisible());tool.prose_table_editor.close();tool.close()

if __name__=='__main__':unittest.main()
