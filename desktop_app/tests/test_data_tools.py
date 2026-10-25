import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import math
import time
import unittest
from collections import Counter
from clinical_studio.app import MainWindow, create_application
from clinical_studio.data_tools_engine import category_numbers, numeric_numbers, statistics

APP=create_application([])

class DataToolTests(unittest.TestCase):
    def test_categories_and_repeatability(self):
        categories=[(1,28),(0,93),(2,10),(3,15)]
        result=category_numbers(categories,'12')
        self.assertEqual(Counter(result),{1:28,0:93,2:10,3:15})
        self.assertEqual(result,category_numbers(categories,'12'))
        self.assertNotEqual(result,category_numbers(categories,'13'))
        for categories in [[],[(0,-1)],[(math.nan,3)],[(1,100001)]]:
            with self.assertRaises(ValueError):category_numbers(categories)

    def test_numeric_constraints_and_statistics(self):
        for lo,hi in [(7,50),(None,None),(7,None),(None,50)]:
            a=numeric_numbers(lower=lo,upper=hi)
            self.assertEqual(len(a),70)
            self.assertTrue(all(x==int(x) and (lo is None or x>=lo) and (hi is None or x<=hi) for x in a))
            m,s=statistics(a);self.assertLess(abs(m-27.92),.15);self.assertLess(abs(s-14.87),.2)
        self.assertEqual(numeric_numbers(n=10,mean=5,sd=0),[5]*10)
        a=numeric_numbers(n=100,lower=1.23,upper=1.25,digits=2,mode='range')
        self.assertTrue(all(x in (1.23,1.24,1.25) for x in a))
        for options in [dict(mode='range'),dict(lower=7,upper=50,sd=100),dict(lower=50,upper=7),dict(sd=-1)]:
            with self.assertRaises(ValueError):numeric_numbers(**options)

    def test_app_entry_generation_copy_and_persistence(self):
        window=MainWindow();window.show();APP.processEvents()
        try:
            self.assertEqual(window.nav.count(),7)
            window.nav.setCurrentRow(6);APP.processEvents()
            tools=window.data_tools_page
            self.assertIs(window.stack.currentWidget(),tools)
            self.assertFalse(window.run_button.isVisible())
            tools.category.add_row('2','5');tools.category.generate_button.click()
            self.assertEqual(Counter(tools.category.result.values),{1:28,0:93,2:5})
            tools.category.result.copy()
            self.assertEqual(APP.clipboard().text(),tools.category.result.output.toPlainText())
            tools.tabs.setCurrentIndex(1);tools.numeric.lower.clear();tools.numeric.upper.clear()
            tools.numeric.generate_button.click()
            deadline=time.monotonic()+15
            while tools.numeric.is_running() and time.monotonic()<deadline:
                APP.processEvents();time.sleep(.01)
            APP.processEvents();self.assertFalse(tools.numeric.is_running())
            self.assertEqual(len(tools.numeric.result.values),70)
            tools.numeric.result.copy();self.assertEqual(APP.clipboard().text(),tools.numeric.result.output.toPlainText())
            previous=tools.numeric.result.values[:]
            window.nav.setCurrentRow(0);window.nav.setCurrentRow(6)
            window.build_pages();window.stack.setCurrentIndex(6);APP.processEvents()
            self.assertIs(window.data_tools_page,tools);self.assertEqual(tools.numeric.result.values,previous)
            tools.numeric.range_mode.setChecked(True);tools.numeric.generate_button.click()
            deadline=time.monotonic()+5
            while tools.numeric.is_running() and time.monotonic()<deadline:
                APP.processEvents();time.sleep(.01)
            APP.processEvents();self.assertIn('两个边界',tools.numeric.error.text())
        finally:
            if window.data_tools_page.numeric.worker:window.data_tools_page.numeric.worker.wait(15000)
            window.close();window.deleteLater();APP.processEvents()

if __name__=='__main__':unittest.main()
