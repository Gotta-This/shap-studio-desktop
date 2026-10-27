"""All tool editors use the shared native shell and retain edits after closing."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QLineEdit
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.editor_dialogs import EditorDialog,get_text
APP=create_application([])

class UnifiedEditorTests(unittest.TestCase):
    def setUp(self):self.window=DesktopWindow();self.window.timer.stop();self.window.show();APP.processEvents()
    def tearDown(self):self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def test_all_three_other_tool_parameter_dialogs_are_native_and_styled(self):
        for key in ('category','numeric','shap'):
            tool=self.window.open_module(key);APP.processEvents();errors=[]
            def inspect():
                dialog=APP.activeModalWidget()
                try:
                    self.assertIsInstance(dialog,EditorDialog);self.assertIsNone(dialog.graphicsProxyWidget());self.assertIs(dialog.parentWidget(),self.window)
                    self.assertTrue(dialog.header.isVisible());self.assertTrue(dialog.footer.isVisible())
                    if key=='category':
                        self.assertEqual(tool.table.verticalScrollBar().maximum(),0)
                        self.assertGreaterEqual(tool.table.viewport().height(),sum(tool.table.rowHeight(i) for i in range(tool.table.rowCount())))
                        tool.table.item(0,1).setText('29')
                except Exception as exc:errors.append(exc)
                finally:dialog.accept()
            QTimer.singleShot(80,inspect);self.window.advanced(key)
            if errors:raise errors[0]
            if key=='category':self.assertEqual(self.window.category_table.item(0,1).text(),'29')
    def test_text_editor_from_proxy_has_native_owner_and_returns_new_value(self):
        tool=self.window.open_module('word');APP.processEvents()
        def edit():
            dialog=APP.activeModalWidget();self.assertIsInstance(dialog,EditorDialog);self.assertIs(dialog.parentWidget(),self.window)
            dialog.findChild(QLineEdit).setText('A组,B组');dialog.accept()
        QTimer.singleShot(50,edit);value,ok=get_text(tool,'组别原名','请输入组别','旧值')
        self.assertTrue(ok);self.assertEqual(value,'A组,B组')

if __name__=='__main__':unittest.main()
