"""Drag actual grips on all four tools; outer content must scroll without data loss."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QScrollArea,QPlainTextEdit,QTableView,QDialog,QVBoxLayout,QDialogButtonBox
from PySide6.QtTest import QTest
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.resizable_fields import resize_field,install_resize_behavior
APP=create_application([])

class ResizeTests(unittest.TestCase):
    def setUp(self):self.w=DesktopWindow();self.w.timer.stop();self.w.resize(1200,800);self.w.show();APP.processEvents()
    def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents()
    def pump(self):
        for _ in range(3):APP.processEvents()
    def drag(self,field,dx=0,dy=250):
        self.pump();grip=field.resize_grip;point=grip.rect().center();global_point=grip.mapToGlobal(point)
        QTest.mousePress(grip,Qt.LeftButton,pos=point)
        event=QMouseEvent(QEvent.MouseMove,QPointF(point+QPoint(dx,dy)),QPointF(global_point+QPoint(dx,dy)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
        APP.sendEvent(grip,event);QTest.mouseRelease(grip,Qt.LeftButton,pos=grip.rect().center());self.pump()
    def outer(self,field):
        parent=field.parentWidget()
        while parent and not isinstance(parent,QScrollArea):parent=parent.parentWidget()
        return parent
    def test_category_table_resizes_and_keeps_external_scroll_and_add_controls(self):
        self.w.open_module('category');self.pump();table=self.w.category_table
        oldrows=[[table.item(i,j).text() for j in (0,1)] for i in range(table.rowCount())]
        self.drag(table,dy=650);area=self.w.category_scroll
        self.assertGreater(table.height(),500);self.assertGreater(area.verticalScrollBar().maximum(),0)
        self.assertGreater(self.w.category_region.controls['add-category'].y(),table.height())
        self.assertEqual(oldrows,[[table.item(i,j).text() for j in (0,1)] for i in range(table.rowCount())])
        height=table.height();self.w.add_category();self.pump();self.assertEqual(table.height(),height)
    def test_category_output_expands_outer_page_and_moves_following_link(self):
        self.w.open_module('category');self.pump();field=self.w.category_output;field.setPlainText('1\n2\n3')
        link=self.w.boards[1].controls['category-report'];before=link.y()
        self.drag(field,dy=650)
        self.assertGreater(link.y(),before);self.assertGreater(link.y(),field.geometry().bottom())
        self.assertGreater(self.w.views[1].verticalScrollBar().maximum(),0);self.assertEqual(field.toPlainText(),'1\n2\n3')
    def test_numeric_output_grows_both_axes_with_outer_scrollbars(self):
        self.w.open_module('numeric');self.pump();field=self.w.numeric_output;field.setPlainText('10\n20')
        self.drag(field,dx=650,dy=650)
        self.assertGreater(self.w.views[2].verticalScrollBar().maximum(),0)
        self.assertGreater(self.w.views[2].horizontalScrollBar().maximum(),0)
        self.assertEqual(field.toPlainText(),'10\n20')
    def test_word_text_and_table_grow_independently_in_scrollable_tab(self):
        tool=self.w.open_module('word');tool.pages.setCurrentIndex(tool.PROSE_PAGE);self.pump();e=tool.prose_table_editor
        e.source.setPlainText('原文仍在');e.evidence.setPlainText('来源仍在')
        evidence_height=e.evidence.height();status_height=e.status.height();table_height=e.table.height()
        self.drag(e.source,dy=420);self.assertEqual(e.table.height(),table_height)
        self.drag(e.table,dy=500);self.assertEqual(e.evidence.height(),evidence_height);self.assertEqual(e.status.height(),status_height)
        area=self.outer(e.table);self.assertIsNotNone(area);self.assertGreater(area.verticalScrollBar().maximum(),0)
        self.assertEqual(e.source.toPlainText(),'原文仍在');self.assertEqual(e.evidence.toPlainText(),'来源仍在')
        resize_field(e.table,e.table.width(),120,False,True);self.pump();self.assertEqual(e.table.height(),120)
    def test_multiple_word_tables_keep_neighbour_height_when_one_grows(self):
        self.w.resize(1440,1100);tool=self.w.open_module('word');tool.add_indicator()
        fields=[dict(table=1,name='额外指标',group=g.name,kind='mean_sd',mean=10.,sd=2.,digits=2,lower=None,upper=None,raw='10±2',confirmed=True) for g in tool.group_editors]
        tool.set_typed_fields(fields);tool.pages.setCurrentIndex(tool.TABLE_PAGE);self.pump()
        before=tool.source_tables.tables[0].height();self.drag(tool.source_tables.tables[1],dy=600)
        self.assertEqual(tool.source_tables.tables[0].height(),before)
        self.assertGreater(self.outer(tool.source_tables.tables[1]).verticalScrollBar().maximum(),0)

    def test_fourth_tool_data_table_expands_and_keeps_cells(self):
        self.w.open_module('shap');self.pump();table=self.w.data_table
        value=table.item(0,0).text();old=table.height();self.drag(table,dy=700)
        self.assertGreater(table.height(),old);self.assertGreater(self.w.views[4].verticalScrollBar().maximum(),0)
        self.assertEqual(table.item(0,0).text(),value)
    def test_new_dialog_text_gets_grip_and_outer_scroll(self):
        d=QDialog(self.w);d.resize(600,400);layout=QVBoxLayout(d);text=QPlainTextEdit();text.setPlainText('不丢失');layout.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);layout.addWidget(buttons);d.show();self.pump()
        self.assertTrue(hasattr(text,'resize_grip'));self.drag(text,dy=700)
        area=self.outer(text);self.assertIsNotNone(area);self.assertGreater(area.verticalScrollBar().maximum(),0);self.assertEqual(text.toPlainText(),'不丢失');d.close()
    def test_shrinking_prose_blocks_packs_following_fields_upwards(self):
        self.w.resize(1440,1250);tool=self.w.open_module('word');tool.pages.setCurrentIndex(tool.PROSE_PAGE);self.pump();editor=tool.prose_table_editor
        for field in (editor.source,editor.table,editor.evidence,editor.status):
            resize_field(field,600,600);self.pump()
        for field in (editor.source,editor.table,editor.evidence,editor.status):
            resize_field(field,500,80);self.pump()
        panels=editor.table.parentWidget().layout()
        self.assertLessEqual(editor.table.y(),panels.contentsMargins().top()+1)
        self.assertLessEqual(editor.evidence.y()-editor.table.geometry().bottom()-1,panels.spacing()+1)
        self.assertLessEqual(editor.status.y()-editor.evidence.geometry().bottom()-1,panels.spacing()+1)
        self.assertLessEqual(editor.source.y(),65)
        self.assertLessEqual(self.outer(editor.source).verticalScrollBar().maximum(),5)
    def test_shrinking_matching_tables_keeps_caption_at_top(self):
        self.w.resize(1440,1250);tool=self.w.open_module('word');tool.add_indicator();self.pump()
        for page,tables in ((tool.TABLE_PAGE,tuple(tool.source_tables.tables.values())),(tool.SOURCES_PAGE,(tool.rule_table,tool.log))):
            tool.pages.setCurrentIndex(page);self.pump()
            for field in tables:
                if field.isVisible():resize_field(field,500,80);self.pump()
            body=self.outer(tables[0]).widget();layout=body.layout();caption=layout.itemAt(0).widget()
            self.assertLessEqual(caption.y(),layout.contentsMargins().top()+1)
            self.assertLessEqual(caption.height(),caption.sizeHint().height()+1)
            visible=[body.layout().itemAt(i).widget() for i in range(layout.count())]
            visible=[item for item in visible if item is not None and item.isVisible()]
            for before,after in zip(visible,visible[1:]):
                self.assertLessEqual(after.y()-before.geometry().bottom()-1,layout.spacing()+2)
    def test_all_visible_multiline_and_tables_have_grips_after_switching_tabs(self):
        for key in ('category','numeric','word','shap'):
            tool=self.w.open_module(key);self.pump()
            for field in self.w.findChildren((QPlainTextEdit)):
                if field.isVisible():self.assertTrue(hasattr(field,'resize_grip'))
            for field in self.w.findChildren(QTableView):
                if field.isVisible():self.assertTrue(hasattr(field,'resize_grip'))

if __name__=='__main__':unittest.main()
