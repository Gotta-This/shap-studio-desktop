"""Closed dropdowns must never change values as a side effect of scrolling."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QCoreApplication
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QWidget,QVBoxLayout,QComboBox,QFontComboBox,QApplication,QScrollArea,QTableWidget,QLabel
from PySide6.QtTest import QTest,QSignalSpy
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
APP=create_application([])


def wheel(widget,dy=-120,pixel=False,dx=0):
    local=widget.rect().center();glob=widget.mapToGlobal(local)
    event=QWheelEvent(QPointF(local),QPointF(glob),QPoint(dx,dy) if pixel else QPoint(),QPoint() if pixel else QPoint(dx,dy),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    APP.sendEvent(widget,event);APP.processEvents()


class SelectWheelTests(unittest.TestCase):
    def setUp(self):
        self.host=QWidget();self.layout=QVBoxLayout(self.host);self.host.resize(400,300);self.host.show()
    def tearDown(self):
        self.host.close();self.host.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def combo(self,editable=False,font=False):
        c=QFontComboBox() if font else QComboBox();c.setEditable(editable or font)
        if not font:c.addItems(['第一项','第二项','第三项'])
        c.setCurrentIndex(1);self.layout.addWidget(c);APP.processEvents();return c
    def test_closed_values_unchanged_with_and_without_focus(self):
        c=self.combo();spy=QSignalSpy(c.currentIndexChanged)
        for focused in (False,True):
            c.setFocus() if focused else c.clearFocus()
            for pixel,dy in [(False,-120),(False,120),(True,-25),(True,25)]:wheel(c,dy,pixel)
            self.assertEqual(c.currentIndex(),1)
        self.assertEqual(spy.count(),0)
    def test_editable_and_font_combos_include_line_edit_children(self):
        for font in (False,True):
            c=self.combo(editable=True,font=font);before=(c.currentIndex(),c.currentText());spy=QSignalSpy(c.currentIndexChanged)
            for target in (c,c.lineEdit()):
                target.setFocus();wheel(target);wheel(target,120,True)
            self.assertEqual((c.currentIndex(),c.currentText()),before);self.assertEqual(spy.count(),0)
    def test_open_popup_still_scrolls_and_mouse_selection_works(self):
        c=self.combo();c.clear();c.addItems([str(i) for i in range(80)]);c.setMaxVisibleItems(6);c.showPopup();APP.processEvents()
        view=c.view();bar=view.verticalScrollBar();old=bar.value();index=c.currentIndex();wheel(view.viewport(),-120)
        self.assertEqual(c.currentIndex(),index)
        self.assertGreater(bar.value(),old)
        target=view.indexAt(QPoint(10,view.viewport().height()//2));self.assertTrue(target.isValid())
        QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=view.visualRect(target).center());APP.processEvents()
        self.assertEqual(c.currentIndex(),target.row())
    def test_keyboard_selection_still_works(self):
        c=self.combo();c.setFocus();QTest.keyClick(c,Qt.Key_Down);self.assertEqual(c.currentIndex(),2)
        QTest.keyClick(c,Qt.Key_Up);self.assertEqual(c.currentIndex(),1)
    def test_wheel_scrolls_page_instead_of_closed_combo(self):
        area=QScrollArea();area.setWidgetResizable(True);body=QWidget();body.setMinimumHeight(1800);layout=QVBoxLayout(body)
        c=QComboBox();c.addItems(['A','B','C']);c.setCurrentIndex(1);layout.addWidget(c);layout.addStretch();area.setWidget(body);self.layout.addWidget(area);APP.processEvents()
        bar=area.verticalScrollBar();self.assertGreater(bar.maximum(),0);wheel(c)
        self.assertGreater(bar.value(),0);self.assertEqual(c.currentIndex(),1)
        wheel(c,120,True);self.assertEqual(c.currentIndex(),1)
    def test_wheel_over_table_cell_combo_scrolls_table(self):
        table=QTableWidget(50,1);self.layout.addWidget(table);c=QComboBox();c.addItems(['A','B','C']);c.setCurrentIndex(1);table.setCellWidget(0,0,c);APP.processEvents()
        wheel(c);self.assertEqual(c.currentIndex(),1);self.assertGreater(table.verticalScrollBar().value(),0)
    def test_all_four_tools_dynamic_dropdowns_are_guarded(self):
        w=DesktopWindow();w.timer.stop();w.show();APP.processEvents();tested=0
        try:
            for key in ('category','numeric','word','shap'):
                tool=w.open_module(key);APP.processEvents()
                combos=list(dict.fromkeys(tool.findChildren(QComboBox)+[c for b in w.boards.values() for c in b.findChildren(QComboBox)]))
                for c in combos:
                    if c.count()<2:continue
                    before=(c.currentIndex(),c.currentText());spy=QSignalSpy(c.currentIndexChanged)
                    wheel(c);wheel(c,120,True)
                    self.assertEqual((c.currentIndex(),c.currentText()),before,(key,c.objectName()));self.assertEqual(spy.count(),0);tested+=1
            self.assertGreater(tested,20)
        finally:w.close();w.deleteLater();APP.processEvents()
    def test_installation_is_idempotent_for_later_windows(self):
        guard=APP.combo_wheel_guard;create_application([]);self.assertIs(APP.combo_wheel_guard,guard)
        c=self.combo();wheel(c);self.assertEqual(c.currentIndex(),1)

if __name__=='__main__':unittest.main()
