"""Independent routing and state ownership across all four tools."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QListView, QLineEdit, QFileDialog
from clinical_studio.app import create_application
from clinical_studio.hub import DesktopWindow

APP=create_application([])


class HubTests(unittest.TestCase):
    def setUp(self):
        self.window=DesktopWindow();self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def enter(self,key):
        if self.window.board_index!=0:QTest.mouseClick(self.window.home_button,Qt.LeftButton)
        QTest.mouseClick(self.window.launch_buttons[key],Qt.LeftButton);APP.processEvents()
        self.assertEqual(self.window.current_module,key)
        return self.window.modules[key]

    def test_four_peer_entries_and_lazy_creation(self):
        self.assertEqual(set(self.window.launch_buttons),{'category','numeric','word','shap'})
        self.assertEqual(self.window.modules,{})
        for key in ('category','numeric','word','shap'):
            tool=self.enter(key)
            self.assertTrue(self.window.isAncestorOf(tool) or (key=='word' and tool.parentWidget() is self.window.module_pages[key]))
            self.assertIs(self.window.stack.currentWidget().board,self.window.module_pages[key])
        self.assertEqual(len({id(t) for t in self.window.modules.values()}),4)
        shap=self.window.modules['shap']
        self.assertEqual(shap.nav.count(),6)
        self.assertFalse(hasattr(shap,'data_tools_page'))
        for key,tool in self.window.modules.items():
            for other_key,other in self.window.modules.items():
                if key!=other_key:self.assertFalse(tool.isAncestorOf(other))

    def test_shap_reload_preserves_other_modules(self):
        category=self.enter('category');category.seed.setText('123');category.generate();category_values=category.result.values[:]
        numeric=self.enter('numeric');numeric.mean.setText('123');numeric.seed.setText('second')
        word=self.enter('word');word.seed.setText('99');word.unit.setText('周')
        shap=self.enter('shap');shap.build_pages();APP.processEvents()
        self.assertEqual(category.seed.text(),'123');self.assertEqual(category.result.values,category_values)
        self.assertEqual(numeric.mean.text(),'123');self.assertEqual(numeric.seed.text(),'second')
        self.assertEqual(word.seed.text(),'99');self.assertEqual(word.unit.text(),'周')
        self.assertIs(self.enter('category'),category)
        self.assertIs(self.enter('numeric'),numeric)
        self.assertIs(self.enter('word'),word)

    def test_persistent_sidebar_keeps_module_state(self):
        category=self.enter('category');category.seed.setText('456');category.generate()
        values=category.result.values[:]
        QTest.mouseClick(self.window.nav_buttons['word'],Qt.LeftButton);APP.processEvents()
        word=self.window.modules['word'];word.seed.setText('77')
        QTest.mouseClick(self.window.nav_buttons['category'],Qt.LeftButton);APP.processEvents()
        self.assertIs(self.window.modules['category'],category)
        self.assertEqual(category.result.values,values)
        self.assertEqual(category.seed.text(),'456')
        self.assertEqual(word.seed.text(),'77')
        self.assertTrue(self.window.nav_buttons['category'].isChecked())

    def test_embedded_workflow_and_full_configuration(self):
        from clinical_studio.config import default_config
        shap=self.enter('shap')
        self.assertTrue(shap.embedded)
        self.assertEqual(shap.nav.flow(),QListView.LeftToRight)
        expected=default_config();expected["plots"]["output_dir"]=shap.output_edit.text()
        self.assertEqual(shap.collect_config(),expected)
        self.window.show_board(6);APP.processEvents()
        editor=shap.style_editor
        self.assertEqual(editor.plot_list.count(),7)
        QTest.mouseClick(self.window.boards[6].controls['plot-summary'],Qt.LeftButton)
        APP.processEvents()
        self.assertEqual(editor.selector.currentData(),'summary')
        expected=default_config();expected["plots"]["output_dir"]=shap.output_edit.text()
        self.assertEqual(shap.collect_config(),expected)

    def test_advanced_enter_commits_without_opening_import_dialog(self):
        shap=self.enter('shap');observed=[]
        def operate():
            dialog=APP.activeModalWidget()
            try:
                editor=shap.data_editor.general.fields['n_samples'].editor
                editor.setFocus();QTest.keyClick(editor,Qt.Key_Return);APP.processEvents()
                observed.append(APP.activeModalWidget() is dialog)
            finally:dialog.accept()
        QTimer.singleShot(50,operate)
        self.window.advanced('shap',1)
        self.assertEqual(observed,[True])
