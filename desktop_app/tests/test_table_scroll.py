"""Table gestures move by pixels rather than jumping a row or wide column."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QPointF,QCoreApplication,QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QTableWidget,QAbstractItemView,QTableView,QApplication
from clinical_studio.app import create_application
APP=create_application([])

class TableScrollTests(unittest.TestCase):
    def setUp(self):
        self.table=QTableWidget(100,20);self.table.resize(500,300)
        for col in range(20):self.table.setColumnWidth(col,300)
        self.table.show();APP.processEvents()
    def tearDown(self):
        self.table.close();self.table.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def wheel(self,pixels,angles=QPoint(),phase=Qt.ScrollUpdate):
        view=self.table.viewport();p=view.rect().center()
        event=QWheelEvent(QPointF(p),QPointF(view.mapToGlobal(p)),pixels,angles,Qt.NoButton,Qt.NoModifier,phase,False)
        APP.sendEvent(view,event);APP.processEvents()
    def test_modes_and_arrow_steps(self):
        self.assertEqual(self.table.horizontalScrollMode(),QAbstractItemView.ScrollPerPixel)
        self.assertEqual(self.table.verticalScrollMode(),QAbstractItemView.ScrollPerPixel)
        self.assertEqual(self.table.horizontalScrollBar().singleStep(),16)
        self.assertEqual(self.table.verticalScrollBar().singleStep(),16)
    def test_small_native_trackpad_deltas_and_momentum(self):
        for pixels,bar in [(QPoint(-3,0),self.table.horizontalScrollBar()),(QPoint(0,-3),self.table.verticalScrollBar())]:
            bar.setValue(100)
            self.wheel(pixels)
            self.assertEqual(bar.value(),103)
            self.wheel(pixels,phase=Qt.ScrollMomentum)
            self.assertEqual(bar.value(),106)
            self.wheel(-pixels)
            self.assertEqual(bar.value(),103)
    def test_mouse_wheel_has_small_steps_with_wide_columns(self):
        for angles,bar in [(QPoint(-120,0),self.table.horizontalScrollBar()),(QPoint(0,-120),self.table.verticalScrollBar())]:
            bar.setValue(100);self.wheel(QPoint(),angles)
            self.assertGreater(bar.value(),100)
            self.assertLessEqual(bar.value()-100,48)
    def test_model_changes_and_reshow_keep_pixel_scrolling(self):
        self.table.setRowCount(200);self.table.setColumnCount(30)
        self.table.hide();self.table.show();APP.processEvents()
        self.test_modes_and_arrow_steps()
    def test_installation_is_idempotent(self):
        controller=APP.table_scroll_behavior
        create_application([])
        self.assertIs(APP.table_scroll_behavior,controller)
    def test_all_four_tools_use_pixel_scrolling(self):
        from clinical_studio.strict_ui import DesktopWindow
        window=DesktopWindow();window.timer.stop();window.show()
        try:
            for key in ('category','numeric','word','shap'):
                window.open_module(key);APP.processEvents()
                tables=[table for table in QApplication.allWidgets() if isinstance(table,QTableView) and table.isVisible()]
                self.assertTrue(tables,key)
                for table in tables:
                    self.assertEqual(table.horizontalScrollMode(),QAbstractItemView.ScrollPerPixel,key)
                    self.assertEqual(table.verticalScrollMode(),QAbstractItemView.ScrollPerPixel,key)
        finally:
            window.close();window.deleteLater();APP.processEvents()

if __name__=='__main__':unittest.main()
