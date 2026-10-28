"""Synthetic paragraphs verify changing parameters, counts, constraints and DOCX export."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from collections import Counter
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from unittest.mock import patch
from PySide6.QtWidgets import QFileDialog
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.word_batch_engine import W,read_word,generate_batch,export_batch,statistics
APP=create_application([])


def prose_document(path,n=25,bmi=22.8,bad_age=False,bad_counts=False,table=False):
    root=ET.Element(W+'document');body=ET.SubElement(root,W+'body')
    def paragraph(text):
        p=ET.SubElement(body,W+'p')
        # Word commonly splits numbers and ± across styled runs.
        for part in (text[:25],text[25:70],text[70:]):
            r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=part
    paragraph('两组患者一般资料比较：')
    for group,male,mean in [('对照组',15,65.),('试验组',14,66.)]:
        male=round(n*male/25);female=n-male+(1 if bad_counts else 0)
        age='61～78 岁，平均（62.40±10.80）岁' if bad_age else f'60～79 岁，平均（{mean:.2f}±3.00）岁'
        a=round(n*13/25);b=n-a;vent=round(n*18/25)
        paragraph(f'{group} {n} 例，男 {male} 例、女 {female} 例；年龄 {age}；BMI（{bmi:.2f}±3.10）kg/m²；呼吸衰竭类型Ⅰ型 {a} 例、Ⅱ型 {b} 例；机械通气方式经口气管插管 {vent} 例、气管切开 {n-vent} 例；APACHEⅡ评分（18.60±4.20）分，SOFA 评分（7.20±2.10）分；入组前机械通气时间（52.60±15.40）h。')
    paragraph('两组上述一般资料比较，差异均无统计学意义（P>0.05）。')
    if table:
        tbl=ET.SubElement(body,W+'tbl')
        for values in [('组别','治疗前指标'),('对照组','10±2'),('试验组','11±2')]:
            tr=ET.SubElement(tbl,W+'tr')
            for v in values:
                tc=ET.SubElement(tr,W+'tc');p=ET.SubElement(tc,W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=v
    with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(root))


class WordProseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'prose.docx'
        self.w=DesktopWindow();self.w.timer.stop();self.w.show();self.t=self.w.open_module('word');self.t.decimal_mode.setCurrentIndex(self.t.decimal_mode.findData('source'));self.t.use_word_prose.setChecked(True);APP.processEvents()
    def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents();self.tmp.cleanup()
    def import_prose(self,**kwargs):
        prose_document(self.path,**kwargs);t=self.t;t.use_word_sizes.setChecked(True)
        t.import_word(self.path);t.show_group_selection(['对照组','试验组']);t.confirm_groups();APP.processEvents()
        self.assertTrue(t.groups_confirmed,t.message.text());t.leave_unknown_blank.setChecked(True)
    def test_prose_only_counts_categories_and_excel(self):
        self.import_prose();t=self.t;c=t.get_config()
        self.assertFalse(c['include_basics']);self.assertEqual([g['n'] for g in c['groups']],[25,25])
        self.assertTrue(t.inline_prose_active)
        self.assertEqual(len(c['typed_fields']),16)
        self.assertEqual([f['counts'][0] for f in c['typed_fields'] if f['name']=='性别'],[15,14])
        self.assertTrue(all(f['raw'] for f in c['typed_fields']))
        result=generate_batch(c)
        self.assertEqual(len(result['rows']),50)
        self.assertTrue(all(name not in result['columns'] for name in ('病程','病情程度','病变范围','总有效率','复发率')))
        self.assertFalse(any(check['field'] in ('病程','病情程度','总有效率','复发率') for check in result['checks']))
        fields=result['columns']
        for group,male in [('对照组',15),('试验组',14)]:
            rows=[r for r in result['rows'] if r[1]==group]
            self.assertEqual(Counter(r[2] for r in rows),{'男':male,'女':25-male})
            self.assertEqual(Counter(r[fields.index('呼吸衰竭类型')] for r in rows),{'I型':13,'II型':12})
            self.assertEqual(Counter(r[fields.index('机械通气方式')] for r in rows),{'经口气管插管':18,'气管切开':7})
            self.assertTrue(all(60<=r[3]<=79 for r in rows))
            mean,sd=statistics([r[3] for r in rows]);self.assertLess(abs(mean-(65 if group=='对照组' else 66)),.3);self.assertLess(abs(sd-3),.5)
        checks=[v for v in result['checks'] if 'actual_mean' in v and v['field']!='年龄']
        self.assertEqual(len(checks),8);self.assertTrue(all(abs(v['mean_error'])<.02 and abs(v['sd_error'])<.02 for v in checks))
        target=Path(self.tmp.name)/'out.xlsx';export_batch(result,target)
        from openpyxl import load_workbook
        b=load_workbook(target,data_only=True)
        self.assertEqual(list(next(b.worksheets[0].values)),fields)
        self.assertEqual(b.worksheets[0].max_row,51);b.close()
        config_path=Path(self.tmp.name)/'config.json'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(config_path),'JSON')):t.save_config()
        t.import_word(self.path)
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(config_path),'JSON')):t.load_config()
        self.assertEqual(t.get_config(),c)
    def test_changed_numbers_are_read_from_new_document(self):
        self.import_prose(n=30,bmi=27.4,table=True)
        c=self.t.get_config();self.assertEqual([g['n'] for g in c['groups']],[30,30])
        self.assertEqual([s['mean'] for s in c['typed_fields'] if s['name']=='BMI'],[27.4,27.4])
        self.assertEqual(len(c['indicators']),2)
        self.assertEqual(len(generate_batch(c)['rows']),60)
    def test_impossible_age_is_blocked_without_dropping_range(self):
        self.import_prose(bad_age=True)
        with self.assertRaisesRegex(ValueError,'无法同时满足'):self.t.get_config()
        age=next(v for v in self.t.prose_table_editor.study()['variables'] if v['name']=='年龄')['cells']['对照组']
        self.assertEqual([age['lower'],age['upper']],[61.,78.]);self.assertEqual(age['sd'],10.8)
    def test_inconsistent_sex_counts_are_blocked(self):
        self.import_prose(bad_counts=True)
        with self.assertRaisesRegex(ValueError,'男女例数之和'):self.t.get_config()
    def test_missing_field_is_not_filled_with_example_numbers(self):
        prose_document(self.path)
        with ZipFile(self.path) as z:data=z.read('word/document.xml')
        root=ET.fromstring(data)
        for text in root.iter(W+'t'):
            if text.text:text.text=text.text.replace('7.20±2.10','未报告')
        with ZipFile(self.path,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
        result=read_word(self.path,['对照组','试验组'])
        self.assertTrue(all(any('SOFA' in issue for issue in g['issues']) for g in result.general_groups.values()))
        self.assertFalse(any(s['name']=='SOFA评分' for g in result.general_groups.values() for s in g['indicators']))

if __name__=='__main__':unittest.main()
