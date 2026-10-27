"""The second tool generates editable-parameter data, with an auxiliary chart."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest,time
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow,MiniHistogram,RemoveCategoryButton

APP=create_application([])


class NumericWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.window=DesktopWindow();self.window.show();self.tool=self.window.open_module('numeric');APP.processEvents()

    def tearDown(self):
        if self.tool.is_running():self.tool.stop_generation();self.tool.worker.wait(10000)
        APP.processEvents();self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def type(self,key,text):
        editor=self.window.boards[2].controls[key];editor.setFocus();editor.selectAll();QTest.keyClicks(editor,text)

    def finish(self):
        deadline=time.monotonic()+8
        while self.tool.is_running() and time.monotonic()<deadline:APP.processEvents();QTest.qWait(10)
        APP.processEvents();self.window.refresh(force=True);self.assertFalse(self.tool.is_running())

    def test_primary_numeric_list_copy_modes_and_generation_snapshot(self):
        w=self.window;b=w.boards[2]
        self.type('numeric-seed','42');QTest.mouseClick(b.controls['generate-numeric'],Qt.LeftButton);self.finish()
        self.assertEqual(len(w.numeric_output.toPlainText().splitlines()),70)
        self.assertEqual([float(x) for x in w.numeric_output.toPlainText().splitlines()],self.tool.result.values)
        self.assertEqual(w.histogram.values,self.tool.result.values)
        QTest.mouseClick(b.controls['copy-numeric'],Qt.LeftButton)
        self.assertEqual(APP.clipboard().text(),w.numeric_output.toPlainText());self.assertTrue(w.copy_feedback.isVisible())
        old=list(self.tool.result.values);self.type('numeric-mean','30');w.commit();w.refresh(force=True)
        self.assertEqual(self.tool.result.values,old)
        self.assertEqual(w.numeric_stats.item(0,1).text(),'27.92')
        QTest.mouseClick(b.controls['numeric-range-mode'],Qt.LeftButton);w.refresh(force=True)
        self.assertTrue(self.tool.range_mode.isChecked());self.assertFalse(b.controls['numeric-mean'].isEnabled())
        for key,text in [('numeric-n','24'),('numeric-min','7'),('numeric-max','9'),('numeric-digits','2')]:self.type(key,text)
        QTest.mouseClick(b.controls['generate-numeric'],Qt.LeftButton);self.finish()
        self.assertEqual(len(self.tool.result.values),24);self.assertTrue(all(7<=v<=9 for v in self.tool.result.values))
        self.assertEqual(self.tool.result_options['mode'],'range');self.assertEqual(w.numeric_stats.item(0,1).text(),'—')
        QTest.mouseClick(b.controls['numeric-target-mode'],Qt.LeftButton);w.refresh(force=True)
        self.assertTrue(self.tool.target.isChecked());self.assertTrue(b.controls['numeric-mean'].isEnabled())

    def test_histogram_frequencies_match_data_including_constant_values(self):
        import numpy as np
        chart=MiniHistogram()
        for values in [[7,7,9,10,20,35,50],[-3,-2,-2,0,4],[10]*70,[]]:
            chart.values=values;spec=chart.distribution()
            expected=np.histogram(values,bins=8,range=(spec['low'],spec['high']))[0]
            self.assertEqual(spec['counts'],expected.tolist());self.assertEqual(sum(spec['counts']),len(values))
            self.assertGreaterEqual(spec['top'],max(expected));self.assertLess(spec['low'],spec['high'])

    def test_stop_preserves_previous_data(self):
        self.tool.result.set_values([7.,8.,9.],0)
        self.type('numeric-n','5000');QTest.mouseClick(self.window.boards[2].controls['generate-numeric'],Qt.LeftButton)
        self.window.refresh(force=True);self.assertTrue(self.window.boards[2].controls['stop-numeric'].isEnabled())
        QTest.mouseClick(self.window.boards[2].controls['stop-numeric'],Qt.LeftButton);self.finish()
        self.assertEqual(self.tool.result.values,[7.,8.,9.]);self.assertIn('已停止',self.tool.result.message.text())
        self.assertFalse(self.window.boards[2].controls['stop-numeric'].isEnabled())

    def test_delete_icon_is_clear_and_last_category_is_disabled(self):
        w=self.window;w.open_module('category');APP.processEvents()
        button=w.category_table.cellWidget(1,2);self.assertIsInstance(button,RemoveCategoryButton)
        self.assertTrue(button.isEnabled());QTest.mouseClick(button,Qt.LeftButton);APP.processEvents()
        last=w.category_table.cellWidget(0,2);self.assertFalse(last.isEnabled());self.assertIn('至少保留',last.toolTip())


if __name__=='__main__':unittest.main()
