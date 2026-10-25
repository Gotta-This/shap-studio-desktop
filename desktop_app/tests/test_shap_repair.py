import os
import tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import patch
from pathlib import Path
from copy import deepcopy
from clinical_studio.app import create_application,MainWindow
from clinical_studio.strict_ui import DesktopWindow,set_field
from clinical_studio.config import default_config,validate
from clinical_studio.widgets import ValueField
APP=create_application([])

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.w=DesktopWindow(output=os.path.join(tempfile.gettempdir(), 'shap-repair-tests'));self.w.show();self.w.open_module('shap');APP.processEvents()
    def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents()
    def test_separate_cell_errors_cannot_be_cleared_by_valid_edit(self):
        t=self.w.data_table
        t.item(0,1).setText('bad');t.item(1,2).setText('nan');t.item(2,1).setText('66')
        self.assertEqual(len(t.property('input-errors')),2)
        t.item(0,1).setText('70');self.assertEqual(len(t.property('input-errors')),1)
        with patch('clinical_studio.strict_ui.QMessageBox.warning') as warn:
            self.assertFalse(self.w.commit());warn.assert_called_once()
        t.item(1,2).setText('.8');self.assertTrue(self.w.commit())
    def test_both_group_limits_and_processing_are_independent(self):
        t=self.w.data_table;f=self.w.modules['shap'].data_editor.data['features'][2]
        for col,v in [(5,'18'),(6,'80'),(7,'23'),(8,'75'),(9,'none'),(10,'5')]:t.item(2,col).setText(v)
        c=self.w.modules['shap'].collect_config()['data']['features'][2]
        self.assertEqual(c['positive']['min'],18);self.assertEqual(c['negative']['min'],23)
        self.assertEqual(c['positive']['max'],80);self.assertEqual(c['negative']['max'],75)
        self.assertEqual(c['transform'],'none');self.assertEqual(c['digits'],5)
    def test_restore_preserves_specific_notebook_layout(self):
        self.w.show_board(6)
        for key in ('force','waterfall'):
            self.w.select_style(key);self.w.set_style('figsize',[3.,3.]);self.w.set_style('font_size',17.5);self.w.restore_style()
            expected=default_config()['plots']['plots'][key]
            self.assertEqual(self.w.style_field('figsize').value(),expected['figsize'])
            if key=='force':self.assertEqual(self.w.style_field('font_size').value(),10)
            if key=='waterfall':self.assertEqual(self.w.style_field('xlabel_pad').value(),40)
        self.w.select_style('common');self.w.set_style('axis_width',3.);self.w.restore_style()
        self.assertEqual(self.w.style_field('axis_width').value(),1.)
    def test_fractional_styles_and_small_tolerance(self):
        for key,v in [('font_size',11.25),('title_pad',13.5),('point_size',18.75),('text_rotation',12.5),('tol',1e-8)]:
            f=ValueField(key,default_config()['plots']['common'].get(key,15 if key=='text_rotation' else .0001));set_field(f,v)
            self.assertEqual(f.value(),v)
            if key=='font_size':self.assertEqual(f.editor.text(),'11.25')
        f=ValueField('ylim',[-.4,.52]);set_field(f,[-.123456789,.567891234])
        self.assertEqual(f.value(),[-.123456789,.567891234])
    def test_explicit_invalid_protective_feature_rejected(self):
        c=default_config();c['explanation']['protective_feature']='does-not-exist'
        with self.assertRaisesRegex(ValueError,'保护'):validate(c)
        c['explanation']['protective_feature']=None;validate(c)
    def test_configuration_output_folder_is_bound(self):
        c=default_config();c['plots']['output_dir']=os.path.join(tempfile.gettempdir(), 'restored-shap-location')
        w=MainWindow(c);self.assertEqual(w.output_edit.text(),c['plots']['output_dir'])
        w.output_edit.setText(os.path.join(tempfile.gettempdir(), 'changed-shap-location'));self.assertEqual(w.collect_config()['plots']['output_dir'],w.output_edit.text());w.close()
    def test_style_frontend_reconnects_after_configuration_rebuild(self):
        self.w.show_board(6);self.w.select_style('force');tool=self.w.modules['shap']
        tool.collect_config();tool.build_pages();self.w.refresh(force=True)
        self.assertEqual(tool.style_editor.selector.currentData(),'force')
        self.assertEqual(self.w.style_field('figsize').value(),[14.,4.])
    def test_rename_updates_dependence_and_protective_references(self):
        tool=self.w.modules['shap'];tool.style_editor.config['plots']['dependence_risk']['interaction_feature']='Alb'
        self.w.data_table.item(4,0).setText('白蛋白')
        cfg=tool.collect_config();self.assertEqual(cfg['explanation']['protective_feature'],'白蛋白')
        self.assertEqual(cfg['plots']['plots']['dependence_risk']['interaction_feature'],'白蛋白');validate(cfg)

if __name__=='__main__':unittest.main()
