"""Visible copy feedback and whole-panel scrolling in the real desktop UI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtCore import Qt,QTimer,QCoreApplication,QEvent,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow

APP=create_application([])


class FeedbackScrollTests(unittest.TestCase):
    def setUp(self):
        self.window=DesktopWindow();self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_rows_expand_before_whole_parameter_region_scrolls(self):
        w=self.window;w.open_module('category');APP.processEvents()
        table=w.category_table;area=w.category_scroll;button=w.boards[1].controls['add-category'];seed=w.boards[1].controls['category-seed']
        generate=w.boards[1].controls['generate-category'].geometry()
        self.assertEqual(table.height(),128);self.assertEqual(area.verticalScrollBar().maximum(),0)
        QTest.mouseClick(button,Qt.LeftButton);APP.processEvents()
        self.assertEqual(table.height(),172);self.assertEqual(button.y(),190);self.assertEqual(seed.y(),317)
        self.assertEqual(area.verticalScrollBar().maximum(),0)
        for _ in range(7):
            area.ensureWidgetVisible(button);QTest.mouseClick(button,Qt.LeftButton);APP.processEvents()
        self.assertEqual(table.rowCount(),10);self.assertEqual(table.height(),480)
        self.assertGreater(area.verticalScrollBar().maximum(),0)
        self.assertEqual(table.verticalScrollBar().maximum(),0)
        self.assertEqual(w.boards[1].controls['generate-category'].geometry(),generate)
        area.verticalScrollBar().setValue(0)
        wheel=QWheelEvent(QPointF(30,60),QPointF(table.viewport().mapToGlobal(QPoint(30,60))),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        APP.sendEvent(table.viewport(),wheel);APP.processEvents()
        self.assertGreater(area.verticalScrollBar().value(),0)
        for _ in range(8):
            delete=table.cellWidget(table.rowCount()-1,2);area.ensureWidgetVisible(delete)
            QTest.mouseClick(delete,Qt.LeftButton);APP.processEvents()
        self.assertEqual(table.rowCount(),2);self.assertEqual(table.height(),128)
        self.assertEqual(button.y(),146);self.assertEqual(seed.y(),273)
        self.assertEqual(area.verticalScrollBar().maximum(),0)

    def test_category_copy_is_visible_repeatable_and_dismisses_itself(self):
        w=self.window;tool=w.open_module('category');APP.processEvents()
        button=w.boards[1].controls['copy-category']
        for _ in range(2):
            QTest.mouseClick(button,Qt.LeftButton);APP.processEvents()
            self.assertTrue(w.copy_feedback.isVisible());self.assertIn('复制成功',w.copy_feedback.text())
            self.assertEqual(APP.clipboard().text().splitlines(),tool.result.output.toPlainText().splitlines())
            self.assertIsNone(APP.activeModalWidget())
        QTest.qWait(2800);self.assertFalse(w.copy_feedback.isVisible())

    def test_numeric_and_word_copy_feedback_appears_inside_current_dialog(self):
        w=self.window
        for key in ('numeric',):
            tool=w.open_module(key);APP.processEvents()
            if key=='numeric':tool.result.set_values([1.25,2.5]);button=tool.result.copy_button
            else:
                tool.result={'columns':['组别','数值'],'rows':[['A',1],['B',2]]}
                tool.copy_button.setEnabled(True);button=tool.copy_button
            observations=[]
            def operate():
                dialog=APP.activeModalWidget()
                try:
                    QTest.mouseClick(button,Qt.LeftButton);APP.processEvents()
                    observations.append(hasattr(dialog,'copy_feedback') and dialog.copy_feedback.isVisible() and '复制成功' in dialog.copy_feedback.text())
                finally:dialog.accept()
            QTimer.singleShot(100,operate);w.advanced(key,3 if key=='word' else None)
            self.assertEqual(observations,[True])
        tool=w.open_module('word');APP.processEvents()
        tool.result={'columns':['组别','数值'],'rows':[['A',1],['B',2]]}
        tool.pages.setCurrentIndex(3);tool.copy_button.setEnabled(True);APP.processEvents();tool.copy_button.click();APP.processEvents()
        self.assertTrue(tool.window().copy_feedback.isVisible());self.assertIn('复制成功',tool.window().copy_feedback.text())
        self.assertEqual(APP.clipboard().text().splitlines(),['组别\t数值','A\t1','B\t2'])


if __name__=='__main__':unittest.main()
