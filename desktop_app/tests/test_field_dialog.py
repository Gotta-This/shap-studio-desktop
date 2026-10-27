"""Field editing uses a native window and expands small category lists on open."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QDialogButtonBox
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.typed_field_ui import FieldDialog
APP=create_application([])

def field(n=2):
    return dict(name='性别' if n==2 else '分类指标',group='对照组',kind='category',labels=['男','女'] if n==2 else [f'类别{i+1}' for i in range(n)],weights=[100/n]*n,raw='18（90.00）/2（10.00）',source_n=20,confirmed=True,header_path=['一般资料','性别（男/女）'])

class FieldDialogTests(unittest.TestCase):
    def pump(self):
        for _ in range(4):APP.processEvents()
    def setUp(self):self.dialogs=[]
    def tearDown(self):
        for dialog in self.dialogs:dialog.close();dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def show_dialog(self,n=2):
        dialog=FieldDialog(field(n));self.dialogs.append(dialog);dialog.show();self.pump();return dialog
    def test_small_lists_show_all_rows_without_manual_drag(self):
        for n in (2,3,6):
            dialog=self.show_dialog(n);table=dialog.categories
            self.assertEqual(table.verticalScrollBar().maximum(),0)
            self.assertGreaterEqual(table.viewport().height(),sum(table.rowHeight(i) for i in range(n)))
            self.assertLessEqual(table.horizontalScrollBar().maximum(),0)
            self.assertEqual(dialog.buttons.button(QDialogButtonBox.Cancel).text(),'取消')
            dialog.close()
    def test_large_list_scrolls_and_actions_stay_in_dialog(self):
        dialog=self.show_dialog(25)
        self.assertGreater(dialog.categories.verticalScrollBar().maximum(),0)
        self.assertLessEqual(dialog.height(),max(380,dialog.screen().availableGeometry().height()-80))
        for button in dialog.buttons.buttons():
            self.assertTrue(dialog.rect().contains(button.mapTo(dialog,button.rect().bottomRight())))
    def test_add_and_remove_category_updates_visible_height(self):
        dialog=self.show_dialog();table=dialog.categories;height=table.height()
        table.item(0,1).setText('90');dialog.add_category('其他',0);self.pump()
        self.assertGreater(table.height(),height);self.assertEqual(table.item(0,1).text(),'90')
        table.setCurrentCell(2,0);dialog.remove_category();self.pump()
        self.assertEqual(table.height(),height);self.assertEqual(table.rowCount(),2)
    def test_proxy_page_parent_resolves_to_real_main_window(self):
        window=DesktopWindow();window.timer.stop();window.show();tool=window.open_module('word');self.pump()
        try:
            dialog=FieldDialog(field(),tool);dialog.show();self.pump()
            self.assertIs(dialog.parentWidget(),window);self.assertTrue(dialog.isWindow());self.assertIsNone(dialog.graphicsProxyWidget())
            dialog.close();dialog.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        finally:window.close();window.deleteLater();self.pump()
    def test_type_changes_and_invalid_parameters_keep_editor_usable(self):
        dialog=self.show_dialog()
        for kind in ('mean_sd','yesno','excluded','category'):
            dialog.kind.setCurrentIndex(dialog.kind.findData(kind));self.pump()
        dialog.categories.item(0,1).setText('99');dialog.apply();self.pump()
        self.assertIsNone(dialog.result_field);self.assertTrue(dialog.error.isVisible())
        dialog.categories.item(0,1).setText('50');dialog.apply()
        self.assertIsNotNone(dialog.result_field)

if __name__=='__main__':unittest.main()
