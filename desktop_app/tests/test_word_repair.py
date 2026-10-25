import os,unittest,tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from copy import deepcopy
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.word_batch_engine import W,read_word,generate_batch,validate_batch
from tests.test_word_batch import fixture_docx,small_config
APP=create_application([])

class WordRepairTests(unittest.TestCase):
    def setUp(self):self.w=DesktopWindow();self.w.timer.stop();self.w.show();self.tool=self.w.open_module('word');APP.processEvents()
    def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents()
    def test_user_counts_preserved_and_word_counts_are_opt_in(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source.docx';fixture_docx(p);self.tool.common_n.setValue(77);self.tool.group_editors[0].fields['effective'].setText('63')
            self.tool.import_word(p);c=self.tool.get_config();self.assertEqual([g['n'] for g in c['groups']],[77,77]);self.assertEqual(c['groups'][0]['effective'],63)
            self.tool.use_word_sizes.setChecked(True);self.tool.import_word(p);self.assertEqual([g['n'] for g in self.tool.get_config()['groups']],[10,12])
    def test_shared_basics_and_independent_outcome_settings(self):
        t=self.tool;t.add_indicator();t.group_editors[0].fields['male'].setText('70');t.group_editors[1].fields['male'].setText('20');t.group_editors[1].fields['effective'].setText('91')
        c=t.get_config();self.assertEqual(c['groups'][1]['male'],70);self.assertEqual(c['groups'][1]['effective'],91)
        t.shared_basics.setChecked(False);self.assertEqual(t.get_config()['groups'][1]['male'],20)
    def test_metric_rename_updates_both_groups(self):
        self.tool.add_indicator();self.tool.metrics.item(0,1).setText('前-主要症状')
        self.assertEqual([s['name'] for s in self.tool.get_config()['indicators']],['前-主要症状']*2)
    def test_unrecognized_numeric_cells_are_marked_and_block_generation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'incomplete.docx';fixture_docx(p,missing=True);self.tool.import_word(p)
            field=self.tool.metrics.item(1,3)
            self.assertEqual(field.background().color().name(),'#fadeda')
            with self.assertRaises(ValueError):self.tool.get_config()
            field.setText('16.36');self.assertEqual(field.toolTip(),'')
            with self.assertRaises(ValueError):self.tool.get_config()
            self.tool.metrics.item(1,4).setText('2.57');self.tool.get_config()
    def test_adjacent_range_boundaries_do_not_double_count(self):
        c=small_config()
        for g in c['groups']:g.update(n=20,age=[dict(lower=10,upper=20,percent=40),dict(lower=20,upper=30,percent=60)])
        r=generate_batch(c)
        for group in ('对照组','中药组'):
            ages=[row[3] for row in r['rows'] if row[1]==group];self.assertEqual(sum(10<=v<20 for v in ages),8);self.assertEqual(sum(20<=v<=30 for v in ages),12)
    def test_effective_denominator_and_outcome_labels(self):
        c=small_config()
        for g in c['groups']:g.update(effective=50,recurrence=100,recurrence_scope='effective')
        r=generate_batch(c)
        self.assertTrue(all(row[-1]==('复发' if row[-2]=='有效' else '未复发') for row in r['rows']))
        self.assertEqual(set(row[-2] for row in r['rows']),{'有效','无效'})
    def test_extent_blank_category_and_range(self):
        c=small_config();r=generate_batch(c);self.assertTrue(all(row[6]=='' for row in r['rows']))
        for g in c['groups']:g.update(extent_mode='category',extent=[dict(label='局限',percent=100)])
        self.assertTrue(all(row[6]=='局限' for row in generate_batch(c)['rows']))
        for g in c['groups']:g.update(extent_mode='range',extent_ranges=[dict(lower=1,upper=2,percent=100)],extent_digits=1)
        self.assertTrue(all(1<=row[6]<=2 for row in generate_batch(c)['rows']))
    def test_word_without_count_column_preserves_first_metric(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'no-count.docx';root=ET.Element(W+'document');body=ET.SubElement(root,W+'body');tbl=ET.SubElement(body,W+'tbl')
            for values in [('组别','治疗前','治疗后'),('对照组','10±2','8±1'),('中药组','11±2','7±1')]:
                row=ET.SubElement(tbl,W+'tr')
                for value in values:
                    cell=ET.SubElement(row,W+'tc');par=ET.SubElement(cell,W+'p');run=ET.SubElement(par,W+'r');ET.SubElement(run,W+'t').text=value
            with ZipFile(p,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
            r=read_word(p);self.assertEqual(len(r.indicators),4);self.assertEqual(r.group_sizes,{})
            self.assertEqual(r.indicators[0]['mean'],10)
    def test_workflow_is_main_page_and_return_from_parameter_menu_keeps_it(self):
        t=self.tool;self.assertTrue(t.isVisible());self.assertIs(t.parentWidget(),self.w.boards[3]);self.w.advanced('word',3);self.assertEqual(t.pages.currentIndex(),3);self.assertTrue(t.isVisible())
        self.w.open_module('shap');self.w.open_module('word');self.assertIs(self.w.modules['word'],t);self.assertTrue(t.isVisible())
if __name__=='__main__':unittest.main()
