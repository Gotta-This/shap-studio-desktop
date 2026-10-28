"""Content widths stay compact, and leading actions preserve model edit indices."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QLineEdit,QPushButton
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.table_layout import fit_table_columns
APP=create_application([])

class ContentColumnTests(unittest.TestCase):
    def pump(self):
        for _ in range(8):APP.processEvents()
    def test_text_inputs_and_buttons_fit_without_stretching(self):
        table=QTableWidget(1,4);table.setHorizontalHeaderLabels(['值','输入','说明','操作'])
        item=QTableWidgetItem('12');item.setFlags(Qt.ItemIsEnabled);table.setItem(0,0,item)
        entry=QLineEdit('123.45');table.setCellWidget(0,1,entry)
        text=QTableWidgetItem('这是较长的文字内容');text.setFlags(Qt.ItemIsEnabled);table.setItem(0,2,text)
        button=QPushButton('删除类别');table.setCellWidget(0,3,button);table.resize(1100,260);table.show();fit_table_columns(table);self.pump()
        try:
            self.assertEqual(table.horizontalHeader().visualIndex(3),0)
            self.assertLess(table.columnWidth(0),80);self.assertGreaterEqual(table.columnWidth(1),96)
            self.assertGreaterEqual(table.columnWidth(2),table.fontMetrics().horizontalAdvance(text.text())+24)
            before=[table.columnWidth(c) for c in range(4)];table.resize(1500,260);self.pump()
            self.assertEqual(before,[table.columnWidth(c) for c in range(4)])
            text.setText('新的文字内容比之前更长一点');self.pump();self.assertGreater(table.columnWidth(2),before[2])
        finally:table.close();table.deleteLater();self.pump()
    def test_category_remove_visible_first_and_edits_keep_original_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('clinical_studio.todos.default_path',return_value=Path(folder)/'todos.json'):window=DesktopWindow()
            window.timer.stop();window.show();tool=window.open_module('category');self.pump()
            try:
                table=window.category_table;self.assertEqual(table.horizontalHeader().visualIndex(2),0)
                self.assertLess(table.columnWidth(1),130)
                table.item(0,1).setText('7');self.pump();self.assertEqual(tool.table.item(0,1).text(),'7')
                window.add_category();self.pump();before=table.rowCount()
                table.cellWidget(before-1,2).click();self.pump();self.assertEqual(table.rowCount(),before-1)
                table.resize(180,table.height());self.pump();self.assertLess(table.cellWidget(0,2).geometry().right(),table.viewport().width())
            finally:window.close();window.deleteLater();self.pump()

if __name__=='__main__':unittest.main()
