"""Independent routing and state ownership across all four tools."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from clinical_studio.app import create_application
from clinical_studio.hub import DesktopWindow

APP=create_application([])


class HubTests(unittest.TestCase):
    def setUp(self):
        self.window=DesktopWindow();self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def enter(self,key):
        if self.window.current_module:QTest.mouseClick(self.window.home_button,Qt.LeftButton)
        QTest.mouseClick(self.window.launch_buttons[key],Qt.LeftButton);APP.processEvents()
        self.assertEqual(self.window.current_module,key)
        return self.window.modules[key]

    def test_four_peer_entries_and_lazy_creation(self):
        self.assertEqual(set(self.window.launch_buttons),{'category','numeric','word','shap'})
        self.assertEqual(self.window.modules,{})
        for key in ('category','numeric','word','shap'):
            tool=self.enter(key)
            self.assertTrue(self.window.module_pages[key].isAncestorOf(tool))
        self.assertEqual(len({id(t) for t in self.window.modules.values()}),4)
        shap=self.window.modules['shap']
        self.assertEqual(shap.nav.count(),6)
        self.assertFalse(hasattr(shap,'data_tools_page'))
        for key,tool in self.window.modules.items():
            for other_key,other in self.window.modules.items():
                if key!=other_key:self.assertFalse(tool.isAncestorOf(other))

    def test_shap_reload_preserves_other_modules(self):
        category=self.enter('category');category.seed.setText('first');category.generate();category_values=category.result.values[:]
        numeric=self.enter('numeric');numeric.mean.setText('123');numeric.seed.setText('second')
        word=self.enter('word');word.seed.setText('99');word.unit.setText('周')
        shap=self.enter('shap');shap.build_pages();APP.processEvents()
        self.assertEqual(category.seed.text(),'first');self.assertEqual(category.result.values,category_values)
        self.assertEqual(numeric.mean.text(),'123');self.assertEqual(numeric.seed.text(),'second')
        self.assertEqual(word.seed.text(),'99');self.assertEqual(word.unit.text(),'周')
        self.assertIs(self.enter('category'),category)
        self.assertIs(self.enter('numeric'),numeric)
        self.assertIs(self.enter('word'),word)
