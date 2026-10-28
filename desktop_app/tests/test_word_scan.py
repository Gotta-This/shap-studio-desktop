"""Recognize before group confirmation without committing drafts or allowing generation."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from zipfile import ZipFile
from copy import deepcopy
from xml.etree import ElementTree as ET
from clinical_studio.app import create_application
from clinical_studio.word_batch import WordBatchTool
from clinical_studio.word_batch_engine import W,generate_batch
from clinical_studio.word_scan import scan_word,apply_preview_fields
from clinical_studio.word_scan_ui import WordScanDialog
from clinical_studio.merged_table_verify import save_fixture
from clinical_studio.typed_field_ui import convert
APP=create_application([])
PROSE='对照组25例，男14例、女11例，年龄（58.6±10.2）岁，BMI（22.8±3.1）kg/m²；试验组25例，男15例、女10例，年龄（57.9±9.8）岁，BMI（22.5±2.9）kg/m²。'

class WordScanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=save_fixture(Path(self.temp.name)/'mixed.docx')
        with ZipFile(self.path) as z:root=ET.fromstring(z.read('word/document.xml'))
        body=root.find(W+'body')
        for i,table in enumerate(list(body),1):
            p=ET.Element(W+'p');ET.SubElement(ET.SubElement(p,W+'r'),W+'t').text=f'表{i} 测试表名{i}';body.insert(list(body).index(table),p)
        with ZipFile(self.path,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
        self.tool=WordBatchTool();self.tool.show();APP.processEvents()
    def tearDown(self):self.tool.close();self.tool.deleteLater();APP.processEvents();self.temp.cleanup()
    def test_import_scans_titles_orientations_and_fields_before_confirmation(self):
        t=self.tool;self.assertTrue(t.import_word(self.path))
        self.assertFalse(t.groups_confirmed);self.assertEqual([e.text() for e in t.group_inputs],['对照组','试验组']);self.assertFalse(t.generate_button.isEnabled())
        self.assertEqual(t.metrics.rowCount(),0);self.assertEqual(t.typed_specs,[])
        self.assertIn('表1 测试表名1',t.match_report.toPlainText());self.assertIn('竖表',t.match_report.toPlainText())
        self.assertEqual(len(t.word_scan['fields']),44);self.assertEqual(t.word_scan['candidates'],['对照组','试验组'])
        with self.assertRaisesRegex(ValueError,'确认'):t.get_config()
    def test_fill_candidates_still_requires_explicit_confirmation(self):
        t=self.tool;t.import_word(self.path);t.use_candidate_groups()
        self.assertEqual([e.text() for e in t.group_inputs],['对照组','试验组']);self.assertFalse(t.groups_confirmed)
        t.confirm_groups();self.assertTrue(t.groups_confirmed);self.assertEqual(len(t.typed_specs),32)
    def test_rematching_preserves_manual_names_and_deleted_groups(self):
        from PySide6.QtWidgets import QPushButton
        t=self.tool;t.import_word(self.path)
        t.group_inputs[0].setText('自定义组');t.match_groups()
        self.assertEqual([e.text() for e in t.group_inputs],['自定义组','试验组'])
        t.group_inputs[1].parentWidget().findChild(QPushButton).click()
        t.match_groups();APP.processEvents()
        self.assertEqual([e.text() for e in t.group_inputs],['自定义组'])
        self.assertFalse(t.groups_confirmed);self.assertFalse(t.generate_button.isEnabled())
        t.import_word(self.path)
        self.assertEqual([e.text() for e in t.group_inputs],['对照组','试验组'])
    def test_custom_group_column_names_are_prefilled(self):
        other=save_fixture(Path(self.temp.name)/'custom.docx',[[['组别','年龄'],['常规护理组','60±4'],['综合护理组','61±5']]])
        t=self.tool;t.import_word(other)
        self.assertEqual([e.text() for e in t.group_inputs],['常规护理组','综合护理组'])
        self.assertFalse(t.groups_confirmed)
    def test_preview_field_edits_are_applied_only_after_confirmation(self):
        t=self.tool;t.import_word(self.path)
        f=next(f for f in t.preview_draft['fields'] if f['table']==1 and f['name']=='年龄（岁）' and f['group']=='对照组');f['mean']=61.23;f['classification']='一般资料'
        self.assertFalse(t.typed_specs)
        t.use_candidate_groups();t.confirm_groups()
        field=next(f for f in t.typed_specs if f['table']==1 and f['name']=='年龄（岁）' and f['group']=='对照组')
        self.assertEqual(field['mean'],61.23);self.assertEqual(field['classification'],'一般资料')
    def test_preview_type_change_on_flat_numeric_field_survives_confirmation(self):
        t=self.tool;t.import_word(self.path)
        for i,f in enumerate(t.preview_draft['fields']):
            if f['table']==2 and f['name']=='术后6h':
                value=convert(f,'yesno');value.update(weights=[20.,80.],confirmed=True);t.preview_draft['fields'][i]=value
        t.use_candidate_groups();t.confirm_groups()
        self.assertFalse(any(t.metrics.item(i,1).text()=='术后6h' for i in range(t.metrics.rowCount())))
        self.assertEqual(sum(f['name']=='术后6h' and f['kind']=='yesno' for f in t.typed_specs),2)
    def test_preview_dialog_cancel_keeps_draft(self):
        t=self.tool;t.import_word(self.path);before=deepcopy(t.preview_draft)
        dialog=WordScanDialog(t,t.word_scan,t.preview_draft);dialog.fields.typed_specs[0]['name']='临时修改';dialog.reject();dialog.deleteLater();APP.processEvents()
        self.assertEqual(t.preview_draft,before)
    def test_text_only_word_is_recognized_before_confirmation_and_edits_carry(self):
        root=ET.Element(W+'document');body=ET.SubElement(root,W+'body');ET.SubElement(ET.SubElement(ET.SubElement(body,W+'p'),W+'r'),W+'t').text=PROSE
        with ZipFile(self.path,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
        t=self.tool;t.use_word_prose.setChecked(True);t.import_word(self.path);draft=t.preview_draft['prose_document'];self.assertTrue(draft['studies'][0]['variables'])
        v=next(v for v in draft['studies'][0]['variables'] if v['name']=='BMI');v['cells']['对照组']['mean']=24.5
        t.use_candidate_groups();t.confirm_groups();self.assertTrue(t.groups_confirmed,t.message.text())
        v=next(v for v in t.prose_table_editor.study()['variables'] if v['name']=='BMI');self.assertEqual(v['cells']['对照组']['mean'],24.5)
    def test_stale_preview_prose_blocks_confirmation_without_discarding_draft(self):
        t=self.tool;t.use_word_prose.setChecked(True);t.import_word(self.path);t.preview_draft['prose_document']['source_text']='尚未重新识别的文字';t.preview_draft['prose_stale']=True
        t.use_candidate_groups();t.confirm_groups();self.assertFalse(t.groups_confirmed);self.assertIn('重新识别',t.message.text())
    def test_new_document_clears_old_draft_and_unknown_groups_still_show_raw_table(self):
        t=self.tool;t.import_word(self.path);t.preview_draft['fields'][0]['name']='旧草稿'
        other=save_fixture(Path(self.temp.name)/'unknown.docx',[[['项目','甲队','乙队'],['年龄','60±4','61±5']]])
        t.import_word(other);self.assertEqual(t.preview_draft['fields'],[]);self.assertEqual(len(t.word_scan['tables']),1)
        self.assertEqual(t.word_scan['tables'][0]['rows'][1][0],'年龄')
        t.show_group_selection(['甲队','乙队']);t.match_groups();self.assertEqual(len(t.preview_draft['fields']),2)

if __name__=='__main__':unittest.main()
