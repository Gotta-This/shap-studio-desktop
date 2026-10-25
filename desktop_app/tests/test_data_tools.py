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
            # 近似优化使用固定随机样本，让同一精度检查可在各平台复现。
            a=numeric_numbers(lower=lo,upper=hi,seed=42)
            self.assertEqual(len(a),70)
            self.assertTrue(all(x==int(x) and (lo is None or x>=lo) and (hi is None or x<=hi) for x in a))
            m,s=statistics(a);self.assertLess(abs(m-27.92),.15);self.assertLess(abs(s-14.87),.2)
        self.assertEqual(numeric_numbers(n=10,mean=5,sd=0),[5]*10)
        a=numeric_numbers(n=100,lower=1.23,upper=1.25,digits=2,mode='range',seed=42)
        self.assertTrue(all(x in (1.23,1.24,1.25) for x in a))
        for options in [dict(mode='range'),dict(lower=7,upper=50,sd=100),dict(lower=50,upper=7),dict(sd=-1)]:
            with self.assertRaises(ValueError):numeric_numbers(**options)

    def test_app_entry_generation_copy_and_persistence(self):
        from clinical_studio.hub import DesktopWindow
        from PySide6.QtWidgets import QFileDialog
        from unittest.mock import patch
        from pathlib import Path
        import csv
        import tempfile
        window=DesktopWindow();window.show();APP.processEvents()
        numeric=None
        try:
            self.assertEqual(len(window.launch_buttons),4)
            category=window.open_module('category')
            category.add_row('2','5');category.generate_button.click()
            self.assertEqual(Counter(category.result.values),{1:28,0:93,2:5})
            category.result.copy();self.assertEqual(APP.clipboard().text(),category.result.output.toPlainText())
            numeric=window.open_module('numeric');numeric.lower.clear();numeric.upper.clear();numeric.seed.setText('42')
            numeric.generate_button.click()
            deadline=time.monotonic()+15
            while numeric.is_running() and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
            APP.processEvents();self.assertFalse(numeric.is_running());self.assertEqual(len(numeric.result.values),70)
            numeric.result.copy();self.assertEqual(APP.clipboard().text(),numeric.result.output.toPlainText())
            previous=numeric.result.values[:]
            window.show_home();window.open_module('category');window.show_home();window.open_module('numeric')
            self.assertEqual(numeric.result.values,previous)
            self.assertEqual(Counter(category.result.values),{1:28,0:93,2:5})
            with tempfile.TemporaryDirectory() as directory:
                csv_path=Path(directory)/'类别.csv';xlsx_path=Path(directory)/'数值.xlsx'
                with patch.object(QFileDialog,'getSaveFileName',return_value=(str(csv_path),'CSV')):category.result.save_button.click()
                with csv_path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
                self.assertEqual([float(row[0]) for row in rows[1:]],category.result.values)
                with patch.object(QFileDialog,'getSaveFileName',return_value=(str(xlsx_path),'Excel')):numeric.result.save_button.click()
                from openpyxl import load_workbook
                workbook=load_workbook(xlsx_path,data_only=True);self.assertEqual([row[0] for row in list(workbook.active.values)[1:]],previous);workbook.close()
                self.assertNotEqual(category.result.last_save_path,numeric.result.last_save_path)
            numeric.range_mode.setChecked(True);numeric.generate_button.click()
            deadline=time.monotonic()+5
            while numeric.is_running() and time.monotonic()<deadline:APP.processEvents();time.sleep(.01)
            APP.processEvents();self.assertIn('两个边界',numeric.error.text())
        finally:
            if numeric and numeric.worker:numeric.worker.wait(15000)
            window.close();window.deleteLater();APP.processEvents()

if __name__=='__main__':unittest.main()
