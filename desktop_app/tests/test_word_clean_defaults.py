"""Defaults stay enabled; every output rule is visible and previous Word results are cleared."""
import os,tempfile,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from unittest.mock import patch
from PySide6.QtWidgets import QFileDialog
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.word_batch_engine import W,generate_batch,export_batch
from tests.test_word_groups import document
APP=create_application([])
FIELDS=['性别','年龄','病程','病情程度','病变范围','总有效率','复发率']

class WordCleanDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'table.docx';document(self.path)
        self.w=DesktopWindow();self.w.timer.stop();self.w.show();self.t=self.w.open_module('word');APP.processEvents()
    def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents();self.tmp.cleanup()
    def select(self,path=None):
        t=self.t;t.import_word(path or self.path);t.group_inputs[0].setText('观察组');t.add_group_input('常规治疗组');t.confirm_groups();APP.processEvents();self.assertTrue(t.groups_confirmed,t.message.text())
    def check_defaults_generate(self,result):
        for field in ['性别','年龄','病程','病情程度','总有效率','复发率']:
            index=result['columns'].index(field);self.assertTrue(all(row[index]!='' for row in result['rows']),field)
        rules=result['config']['field_rules']
        for field in FIELDS:self.assertTrue(any(row['column']==field and row['source']=='程序默认参数' for row in rules),field)
        self.assertEqual({row['column'] for row in rules},set(result['columns']))
    def test_initial_defaults_are_editable_and_generate_without_hidden_patient_data(self):
        t=self.t;self.assertIsNone(t.result);self.assertEqual(t.metrics.rowCount(),0);self.assertEqual(t.preview.rowCount(),0)
        self.assertFalse(t.leave_unknown_blank.isChecked());self.assertTrue(t.group_editors[0].fields['effective'].isEnabled());self.assertTrue(t.group_editors[0].age.isEnabled())
        t.add_indicator();self.check_defaults_generate(generate_batch(t.get_config()))
    def test_customer_rows_reproduce_from_seed_without_importing_any_word(self):
        t=self.t;t.add_indicator();c=t.get_config();self.assertEqual(c['source'],'')
        result=generate_batch(c)
        actual=[[row[i] for i in (0,2,3,4,5)] for row in result['rows'][43:49]]
        expected=[[44,'男',28,23,'轻度'],[45,'男',31,5,'中度'],[46,'男',67,7,'中度'],[47,'女',54,39,'中度'],[48,'男',47,10,'轻度'],[49,'男',22,58,'轻度']]
        self.assertEqual(actual,expected)
        self.assertEqual(result['rows'],generate_batch(c)['rows'])
        t.seed.setText('99');changed=generate_batch(t.get_config())
        self.assertNotEqual(actual,[[row[i] for i in (0,2,3,4,5)] for row in changed['rows'][43:49]])
    def test_table_only_import_generates_defaults_and_exposes_every_output_field(self):
        self.select();t=self.t;t.common_n.setValue(8);config=t.get_config()
        self.assertEqual(config['detected_basics'],{'观察组':[],'常规治疗组':[]})
        t.pages.setCurrentIndex(2);APP.processEvents();self.assertEqual(t.rule_table.rowCount(),len(config['field_rules']))
        t.generate_button.click();deadline=time.monotonic()+30
        while t.is_running() and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
        APP.processEvents();self.assertIsNotNone(t.result,t.message.text());self.check_defaults_generate(t.result)
        output=Path(self.tmp.name)/'with-provenance.xlsx';export_batch(t.result,output)
        from openpyxl import load_workbook
        book=load_workbook(output,data_only=True);settings=list(book['生成配置'].values)
        self.assertTrue(any(str(row[0]).startswith('field_rules[') for row in settings));book.close()
    def test_new_word_discards_old_indicators_results_and_clinical_edits(self):
        self.select();t=self.t;t.common_n.setValue(8)
        t.group_editors[0].fields['effective'].setText('100');t.group_editors[0].fields['recurrence'].setText('100')
        t.group_editors[0].age.table.item(0,0).setText('44');t.group_editors[0].age.table.item(0,1).setText('44')
        t.add_indicator();old_name=t.metrics.item(t.metrics.rowCount()-1,1).text()
        t.show_result(generate_batch(t.get_config()));self.assertEqual(t.result['rows'][0][3],44)
        self.select();self.assertFalse(t.leave_unknown_blank.isChecked());self.assertIsNone(t.result);self.assertFalse(t.export_button.isEnabled())
        config=t.get_config();self.assertFalse(any(s['name']==old_name for s in config['indicators']))
        self.assertEqual(config['groups'][0]['effective'],80.);self.assertEqual(config['groups'][0]['recurrence'],10.)
        self.check_defaults_generate(generate_batch(config))
    def test_current_word_rates_have_word_source_and_next_word_restores_default_source(self):
        doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body');table=ET.SubElement(body,W+'tbl')
        for values in [('组别','例数','评分','总有效率','复发率'),('观察组','8','10±2','75%','25%'),('常规治疗组','8','11±2','50%','0%')]:
            tr=ET.SubElement(table,W+'tr')
            for value in values:
                tc=ET.SubElement(tr,W+'tc');p=ET.SubElement(tc,W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=value
        rates=Path(self.tmp.name)/'rates.docx'
        with ZipFile(rates,'w') as archive:archive.writestr('word/document.xml',ET.tostring(doc))
        self.t.use_word_sizes.setChecked(True);self.t.use_word_rates.setChecked(True);self.select(rates)
        c=self.t.get_config();self.assertEqual(c['detected_basics']['观察组'],['总有效率','复发率'])
        self.assertTrue(any(r['column']=='总有效率' and r['source']=='Word表格' for r in c['field_rules']))
        result=generate_batch(c);rows=[r for r in result['rows'] if r[1]=='观察组']
        self.assertEqual(sum(r[-2]=='有效' for r in rows),6);self.assertEqual(sum(r[-1]=='复发' for r in rows),2)
        self.select();self.check_defaults_generate(generate_batch(self.t.get_config()))
    def test_manual_edits_and_saved_configuration_preserve_rule_sources(self):
        self.select();t=self.t;t.group_editors[0].fields['effective'].setText('93');c=t.get_config()
        self.assertTrue(any(r['column']=='总有效率' and r['group']=='观察组' and r['source']=='手工配置' and '93%' in r['rule'] for r in c['field_rules']))
        config_path=Path(self.tmp.name)/'rules.json'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(config_path),'JSON')):t.save_config()
        t.leave_unknown_blank.setChecked(True)
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(config_path),'JSON')):t.load_config()
        self.assertEqual(t.get_config(),c);self.assertFalse(t.leave_unknown_blank.isChecked())

if __name__=='__main__':unittest.main()
