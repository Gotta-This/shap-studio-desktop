"""Exercise date choices, cancellation, leap years and actual popup geometry."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QDate,QPoint,QRect,QSize,QTimer,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget,QVBoxLayout,QAbstractScrollArea,QTableView,QCalendarWidget,QDialog
from clinical_studio.app import create_application
from clinical_studio.date_picker import DateButton,DatePopup,popup_position,anchor_rect
APP=create_application([])

class DatePickerTests(unittest.TestCase):
    def pump(self):
        for _ in range(5):APP.processEvents()
    def setUp(self):
        self.host=QWidget();layout=QVBoxLayout(self.host);self.field=DateButton('2024-02-10');layout.addWidget(self.field)
        self.host.resize(440,180);self.host.show();self.pump()
    def tearDown(self):
        self.host.close();self.host.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.pump()
    def popup(self,value='2024-02-10'):
        p=DatePopup(value,self.host);p.show();self.pump();return p
    def test_real_last_column_and_leap_day_click_commit_only_once(self):
        changes=[];errors=[];self.field.changed.connect(changes.append)
        def select():
            try:
                p=self.field.date_popup
                self.assertEqual(len(p.days),42)
                self.assertFalse(p.findChildren(QAbstractScrollArea))
                for b in p.days:
                    self.assertTrue(p.rect().contains(b.mapTo(p,QPoint()),False))
                    self.assertTrue(p.rect().contains(b.mapTo(p,b.rect().bottomRight()),False))
                    self.assertGreaterEqual(b.width(),32)
                sunday=next(b for b in p.days if b.date_value==QDate(2024,2,11))
                self.assertEqual(p.days.index(sunday)%7,6)
                QTest.mouseClick(sunday,Qt.LeftButton)
            except Exception as exc:errors.append(exc);self.field.date_popup.reject()
        QTimer.singleShot(80,select);QTest.mouseClick(self.field,Qt.LeftButton)
        if errors:raise errors[0]
        self.assertEqual(changes,['2024-02-11'])
        p=self.popup('2024-02-10');QTest.mouseClick(next(b for b in p.days if b.date_value==QDate(2024,2,29)),Qt.LeftButton)
        self.assertEqual(p.result_value,'2024-02-29')
    def test_year_month_views_and_rollover_never_commit_navigation(self):
        p=self.popup('2024-12-31');QTest.mouseClick(p.next_month,Qt.LeftButton)
        self.assertEqual(p.page,QDate(2025,1,1));self.assertEqual(p.result_value,'2024-12-31')
        QTest.mouseClick(p.year_button,Qt.LeftButton);self.assertEqual(p.mode,'years')
        target=next(b for b in p.years.buttons if b.text()=='2028');QTest.mouseClick(target,Qt.LeftButton)
        self.assertEqual(p.mode,'months');QTest.mouseClick(p.months.buttons[1],Qt.LeftButton)
        self.assertEqual(p.page,QDate(2028,2,1));self.assertEqual(p.mode,'days')
        self.assertEqual(p.result_value,'2024-12-31')
    def test_invalid_input_leaves_dialog_open_then_valid_input_or_clear_commits(self):
        p=self.popup();p.input.setText('2025-02-29');QTest.keyClick(p.input,Qt.Key_Return);self.pump()
        self.assertTrue(p.isVisible());self.assertTrue(p.error.text());self.assertEqual(p.result_value,'2024-02-10')
        p.input.setText('2024-02-29');QTest.keyClick(p.input,Qt.Key_Return);self.pump()
        self.assertEqual(p.result(),QDialog.Accepted);self.assertEqual(p.result_value,'2024-02-29')
        p=self.popup();QTest.mouseClick(p.clear_button,Qt.LeftButton);self.assertEqual(p.result(),QDialog.Accepted);self.assertIsNone(p.result_value)
    def test_escape_cancel_preserves_saved_value_and_emits_nothing(self):
        changes=[];self.field.changed.connect(changes.append)
        QTimer.singleShot(60,lambda:QTest.keyClick(self.field.date_popup,Qt.Key_Escape))
        QTest.mouseClick(self.field,Qt.LeftButton)
        self.assertEqual(self.field.value,'2024-02-10');self.assertEqual(changes,[])
    def test_keyboard_navigation_and_selection_across_months(self):
        p=self.popup('2024-02-29');b=next(b for b in p.days if b.date_value==QDate(2024,2,29));b.setFocus()
        QTest.keyClick(b,Qt.Key_Right);self.pump();self.assertEqual(p.page,QDate(2024,3,1))
        b=next(b for b in p.days if b.hasFocus());self.assertEqual(b.date_value,QDate(2024,3,1))
        QTest.keyClick(b,Qt.Key_Return);self.assertEqual(p.result_value,'2024-03-01')
    def test_popup_flips_up_and_clamps_to_each_screen_edge(self):
        screen=QRect(100,80,1000,700);size=QSize(344,450)
        for anchor in [QRect(110,90,80,34),QRect(1050,700,80,34),QRect(80,780,80,34)]:
            pos=popup_position(anchor,size,screen);self.assertTrue(screen.contains(QRect(pos,size)))
        pos=popup_position(QRect(1050,700,80,34),size,screen)
        self.assertLess(pos.y()+size.height(),700)
        self.assertEqual(anchor_rect(self.field).topLeft(),self.field.mapToGlobal(QPoint()))
    def test_generic_resize_behavior_leaves_native_calendar_internals_alone(self):
        calendar=QCalendarWidget(self.host);calendar.show();self.pump()
        for view in calendar.findChildren(QTableView):
            self.assertFalse(hasattr(view,'content_columns'));self.assertFalse(hasattr(view,'resize_grip'))
        calendar.close();calendar.deleteLater()
