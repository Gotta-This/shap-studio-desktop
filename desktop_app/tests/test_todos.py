"""Persistent task edits, default launch, and independent Word opt-in defaults."""
import os,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QTimer,QEvent,QCoreApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox,QPushButton
from clinical_studio.app import create_application
from clinical_studio.todos import TodoStore
from clinical_studio.todo_ui import TodoPage,TodoDialog,DateButton
APP=create_application([])

class StoreTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'todos.json';self.store=TodoStore(self.path)
    def tearDown(self):self.tmp.cleanup()
    def test_persistence_sorting_soft_delete_and_restore(self):
        low=self.store.add('甲的文档','low');high=self.store.add('乙的文档','high',date.today().isoformat())
        self.assertEqual(TodoStore(self.path).visible()[0]['id'],high['id'])
        self.store.update(high['id'],name='乙的新文档',completed=True)
        self.assertEqual(TodoStore(self.path).visible(True)[0]['name'],'乙的新文档')
        self.store.delete(low['id']);self.assertEqual(self.store.visible(),[])
        self.assertTrue(next(t for t in self.store.read() if t['id']==low['id'])['deleted'])
        self.store.restore(low['id']);self.assertEqual(len(self.store.visible()),1)
    def test_two_stores_never_overwrite_each_others_tasks(self):
        other=TodoStore(self.path);self.store.add('一');other.add('二');self.store.add('三')
        self.assertEqual({t['name'] for t in other.visible()},{'一','二','三'})
    def test_invalid_input_and_corrupt_file_never_overwrite(self):
        for args in [(' ',),('文档','unknown'),('文档','normal','bad-date')]:
            with self.assertRaises(ValueError):self.store.add(*args)
        self.path.write_text('broken',encoding='utf-8')
        with self.assertRaises(ValueError):self.store.add('新文档')
        self.assertEqual(self.path.read_text(),'broken')
    def test_failed_atomic_save_keeps_original(self):
        task=self.store.add('原始文档');before=self.path.read_bytes()
        with patch('clinical_studio.todos.os.replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):self.store.update(task['id'],name='修改')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(list(self.path.parent.glob('.todos-*.tmp')))

class TodoUiTests(unittest.TestCase):
    def pump(self):
        for _ in range(5):APP.processEvents()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'todos.json';self.store=TodoStore(self.path);self.page=TodoPage(store=self.store);self.page.resize(1100,850);self.page.show();self.pump()
    def tearDown(self):
        self.page.close();self.page.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.tmp.cleanup()
    def test_add_edit_filter_completion_delete_undo_and_reload(self):
        self.page.name.setText('张老师的文档');QTest.keyClick(self.page.name,Qt.Key_Return);self.pump()
        self.assertEqual(self.page.table.rowCount(),1)
        item=self.page.table.item(0,1);item.setText('张老师 · 修改稿');self.pump()
        combo=self.page.table.cellWidget(0,2).findChild(QComboBox);combo.setCurrentIndex(combo.findData('high'));self.pump()
        due=(date.today()+timedelta(days=2)).isoformat();self.page.table.cellWidget(0,3).set_date(due);self.pump()
        current=TodoStore(self.path).visible()[0];self.assertEqual((current['name'],current['priority'],current['due_date']),('张老师 · 修改稿','high',due))
        self.page.search.setText('找不到');self.pump();self.assertEqual(self.page.table.rowCount(),0)
        self.page.search.clear();self.pump();self.page.table.item(0,0).setCheckState(Qt.Checked);self.pump();self.assertEqual(self.page.table.rowCount(),0)
        self.page.done_button.click();self.pump();self.assertEqual(self.page.table.rowCount(),1)
        self.page.delete(current['id']);self.pump();self.assertEqual(self.page.table.rowCount(),0)
        self.page.undo.click();self.pump();self.assertEqual(self.page.table.rowCount(),1)
        self.assertTrue(TodoStore(self.path).visible(True)[0]['completed'])
    def test_calendar_selection_and_clear_are_saved(self):
        self.store.add('带日期文档');self.page.refresh();self.pump()
        field=self.page.table.cellWidget(0,3)
        def select_today():field.date_menu.actions()[0].trigger();field.date_menu.close()
        QTimer.singleShot(40,select_today);field.click();self.pump()
        self.assertEqual(self.store.visible()[0]['due_date'],date.today().isoformat())
        self.page.table.cellWidget(0,3).set_date(None);self.pump();self.assertIsNone(self.store.visible()[0]['due_date'])
    def test_inline_validation_and_compact_dialog(self):
        self.page.add_button.click();self.pump();self.assertEqual(self.store.visible(),[]);self.assertIn('填写',self.page.message.text())
        dialog=TodoDialog(self.page)
        try:
            self.assertEqual(set(dialog.result_task or {}),set());dialog.accept();self.assertTrue(dialog.isVisible()==False);self.assertIn('填写',dialog.error.text())
            dialog.name.setText('李老师的文档');dialog.accept();self.assertEqual(set(dialog.result_task),{'name','priority','due_date'})
        finally:dialog.deleteLater()
    def test_all_cell_controls_remain_inside_their_cells_after_refresh(self):
        self.store.add('控件位置');self.page.refresh();self.page.refresh();self.pump()
        for col in (2,3,4):
            widget=self.page.table.cellWidget(0,col)
            expected=self.page.table.visualRect(self.page.table.model().index(0,col))
            self.assertGreaterEqual(widget.x(),expected.left())
            self.assertLessEqual(widget.geometry().right(),expected.right())
        visible=[b for b in self.page.table.viewport().findChildren(QPushButton) if b.isVisible() and b.text() in ('修改','删除')]
        self.assertEqual(len(visible),2)
    def test_startup_navigation_and_word_defaults(self):
        from clinical_studio.strict_ui import DesktopWindow
        with patch('clinical_studio.todos.default_path',return_value=self.path):window=DesktopWindow()
        window.timer.stop();window.show();self.pump()
        try:
            self.assertEqual(window.board_index,9)
            for width in (1100,1800,1440):
                window.resize(width,1000);self.pump();board=window.boards[9]
                self.assertEqual(window.todo_page.width(),board.width()-296)
                self.assertEqual(window.views[9].transform().m11(),1)
            self.assertLess(window.boards[9].controls['nav-todo'].y(),window.home_button.y())
            window.home_button.click();self.pump();self.assertEqual(window.board_index,0)
            tool=window.open_module('word');self.pump()
            self.assertFalse(tool.use_word_prose.isChecked());self.assertFalse(tool.prose_table_editor.reviewed.isChecked())
            tool.prose_table_editor.reviewed.setChecked(True);tool.reset_prose_table();self.pump();self.assertFalse(tool.prose_table_editor.reviewed.isChecked())
            window.boards[3].controls['nav-todo'].click();self.pump();self.assertEqual(window.board_index,9)
        finally:window.close();window.deleteLater();self.pump()

if __name__=='__main__':unittest.main()
