"""The three supplied table layouts, textual categories and editable summary types."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from zipfile import ZipFile
from collections import Counter
from xml.etree import ElementTree as ET
from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.word_batch_engine import W,read_word,generate_batch,export_batch
from clinical_studio.typed_field_ui import convert,FieldDialog
APP=create_application([])

def save(path,tables):
    doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body')
    for rows in tables:
        table=ET.SubElement(body,W+'tbl')
        for row in rows:
            tr=ET.SubElement(table,W+'tr')
            for cell in row:
                text,span=cell if isinstance(cell,tuple) else (cell,1)
                tc=ET.SubElement(tr,W+'tc')
                if span>1:ET.SubElement(ET.SubElement(tc,W+'tcPr'),W+'gridSpan',{W+'val':str(span)})
                ET.SubElement(ET.SubElement(ET.SubElement(tc,W+'p'),W+'r'),W+'t').text=text
    with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(doc))

PHASED=[ [('项目',1),('试验组（n=59）',2),('对照组（n=59）',2)],['项目','治疗前','治疗后','治疗前','治疗后'],['头晕目眩','4.09±0.64','1.49±0.35*△','4.15±0.60','2.39±0.25*'],['DHI','56.37±6.32','29.45±5.93','55.47±6.52','36.94±5.18'] ]
EFFICACY=[['组别','例数（n）','基本痊愈','显效','有效','无效','总有效率'],['试验组','59','22（37.29）','15（25.42）','18（30.51）','4（6.78）','55（93.22）'],['对照组','59','15（25.42）','9（15.25）','22（37.29）','13（22.03）','46（77.97）']]
BASELINE=[['项目','训练集(n=237)','验证集(n=101)','统计值','P'],['年龄（月）','85.09±16.44','84.70±17.03','t=0.197','0.844'],['性别','134(56.54)','54(53.47)','χ²=0.161','0.688'],['基础疾病','20(8.44)','11(10.89)','χ²=0.019','0.89'],['近1年发作次数','1.00(0.00,2.00)','1.00(0.00,2.00)','Z=0.0','1.0'],['白细胞计数（×10⁹/L）','13.50(10.80,15.50)','13.00(11.10,14.90)','Z=0.606','0.545'],['基线CRP','56.68±15.19','56.49±13.86','t=0.105','0.916']]

class WordTableTypesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'tables.docx';self.w=DesktopWindow();self.w.timer.stop();self.w.show();self.t=self.w.open_module('word');APP.processEvents()
    def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents();self.tmp.cleanup()
    def load(self,tables,names):
        save(self.path,tables);t=self.t;t.use_word_sizes.setChecked(True);t.import_word(self.path);t.show_group_selection(names)
        self.assertTrue(t.match_groups() is not None);t.confirm_groups();APP.processEvents();self.assertTrue(t.groups_confirmed,t.message.text())
    def test_phased_columns_do_not_become_group_named_headers(self):
        self.load([PHASED],['试验组','对照组']);t=self.t
        fields=t.get_config()['typed_fields'];self.assertEqual(len(fields),8)
        self.assertEqual({f['name'] for f in fields},{'前-头晕目眩','后-头晕目眩','前-DHI','后-DHI'})
        self.assertEqual([g['n'] for g in t.get_config()['groups']],[59,59])
        result=generate_batch(t.get_config());self.assertEqual(len(result['rows']),118)
        self.assertEqual(len([c for c in result['checks'] if 'actual_mean' in c]),8)
    def test_efficacy_counts_and_total_are_consistent_per_case(self):
        self.load([EFFICACY],['试验组','对照组']);t=self.t;r=generate_batch(t.get_config());fields=r['columns']
        for group,expected,total in [('试验组',[22,15,18,4],55),('对照组',[15,9,22,13],46)]:
            rows=[row for row in r['rows'] if row[1]==group]
            counts=Counter(row[fields.index('疗效分级')] for row in rows)
            self.assertEqual([counts[key] for key in ['基本痊愈','显效','有效','无效']],expected)
            self.assertEqual(sum(row[fields.index('总有效率')]=='有效' for row in rows),total)
            self.assertTrue(all((row[fields.index('总有效率')]=='有效')==(row[fields.index('疗效分级')]!='无效') for row in rows))
    def test_recurrence_uses_generated_efficacy_grades(self):
        self.load([EFFICACY],['试验组','对照组']);c=self.t.get_config()
        for group in c['groups']:group['recurrence_scope']='effective';group['recurrence']=100
        r=generate_batch(c);effective=r['columns'].index('总有效率');recurrence=r['columns'].index('复发率')
        self.assertTrue(all((row[effective]=='有效')==(row[recurrence]=='复发') for row in r['rows']))
        self.assertEqual([check['n'] for check in r['checks'] if check['field']=='复发率'],[55,46])

    def confirm_fields(self):
        fields=[]
        for field in self.t.typed_specs:
            if field['name']=='性别':field=convert(field,'gender')
            elif field['kind'] in ('binary','binary01'):field=convert(field,'yesno')
            if field['kind']=='quantile':field['confirmed']=True
            fields.append(field)
        self.t.set_typed_fields(fields)
    def test_baseline_projects_types_gender_counts_quantiles_and_excel(self):
        self.load([BASELINE],['训练集','验证集']);t=self.t
        with self.assertRaisesRegex(ValueError,'确认'):t.get_config()
        self.confirm_fields();c=t.get_config();self.assertFalse(c['include_basics'])
        self.assertEqual({f['kind'] for f in c['typed_fields']},{'mean_sd','gender','yesno','quantile'})
        r=generate_batch(c);names=r['columns'];self.assertEqual(names[:2],['编号','分组']);self.assertEqual(names[2:],[row[0] for row in BASELINE[1:]])
        self.assertEqual(len(r['rows']),338);self.assertNotIn('P',names);self.assertNotIn('病程',names)
        for group,n,male in [('训练集',237,134),('验证集',101,54)]:
            rows=[row for row in r['rows'] if row[1]==group];self.assertEqual(len(rows),n)
            self.assertEqual(Counter(row[names.index('性别')] for row in rows),{'男':male,'女':n-male})
        for check in r['checks']:
            if 'actual_q1' in check:
                self.assertLess(abs(check['actual_q1']-check['target_q1']),.006);self.assertLess(abs(check['actual_median']-check['target_median']),.006);self.assertLess(abs(check['actual_q3']-check['target_q3']),.006)
        out=Path(self.tmp.name)/'baseline.xlsx';export_batch(r,out)
        from openpyxl import load_workbook
        book=load_workbook(out,data_only=True);data=list(book.worksheets[0].values);self.assertEqual(list(data[0]),names);self.assertEqual(len(data),339);self.assertIsInstance(data[1][names.index('性别')],str);book.close()
    def test_real_type_combo_dialog_and_column_name_edit(self):
        self.load([BASELINE],['训练集','验证集']);t=self.t
        i=next(i for i,f in enumerate(t.typed_specs) if f['name']=='性别' and f['group']=='训练集')
        combo=t.typed_table.cellWidget(i,3);combo.setCurrentIndex(combo.findData('gender'));APP.processEvents()
        self.assertTrue(all(f['labels']==['男','女'] and f['confirmed'] for f in t.typed_specs if f['name']=='性别'))
        dlg=FieldDialog(t.typed_specs[i],t);dlg.show();APP.processEvents();self.assertEqual(dlg.categories.item(0,0).text(),'男');dlg.categories.item(0,0).setText('女');dlg.categories.item(1,0).setText('男');dlg.apply();self.assertEqual(dlg.result_field['labels'],['女','男']);dlg.deleteLater()
        item=t.typed_table.item(i,1);t.typed_table.editItem(item);APP.processEvents();editor=t.typed_table.findChild(QLineEdit);self.assertIsNotNone(editor);editor.setText('患者性别');QTest.keyClick(editor,Qt.Key_Return);APP.processEvents()
        self.assertEqual(sum(f['name']=='患者性别' for f in t.typed_specs),2)
        t.typed_table.selectRow(i);t.remove_indicator();self.assertFalse(any(f['name']=='患者性别' for f in t.typed_specs))
    def test_legacy_numeric_type_can_be_converted_to_text(self):
        t=self.t;t.add_indicator();combo=t.metrics.cellWidget(0,8);combo.setCurrentIndex(combo.findData('type:yesno'));APP.processEvents()
        self.assertEqual(t.metrics.rowCount(),0);self.assertEqual(len(t.typed_specs),2)
        with self.assertRaises(ValueError):t.get_config()
        for field in t.typed_specs:field['weights']=[30.,70.];field['confirmed']=True
        t.set_typed_fields(t.typed_specs);r=generate_batch(t.get_config());idx=r['columns'].index('自定义指标1');self.assertEqual(set(row[idx] for row in r['rows']),{'有','无'})
    def test_numeric_binary_encoding_and_changed_input_are_not_fixed(self):
        changed=[list(row) for row in BASELINE];changed[2]=['性别','120(50.63)','60(59.41)','χ²=0','1']
        self.load([changed],['训练集','验证集']);self.confirm_fields()
        for i,f in enumerate(self.t.typed_specs):
            if f['name']=='性别':self.t.typed_specs[i]=convert(f,'binary01')
        self.t.set_typed_fields(self.t.typed_specs);r=generate_batch(self.t.get_config());idx=r['columns'].index('性别')
        self.assertEqual(sum(row[idx]==1 for row in r['rows'] if row[1]=='训练集'),120);self.assertTrue(all(type(row[idx]) is int for row in r['rows']))

if __name__=='__main__':unittest.main()
