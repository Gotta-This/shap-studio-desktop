"""Scene proxies must follow their content through window and field resizing."""
import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QCoreApplication,QEvent,QPoint,Qt
from PySide6.QtWidgets import QPushButton
from PySide6.QtTest import QTest
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.resizable_fields import resize_field
APP=create_application([])

class WindowResizeTests(unittest.TestCase):
    def pump(self):
        for _ in range(5):APP.processEvents()
    def setUp(self):
        self.window=DesktopWindow();self.window.timer.stop();self.window.show();self.pump()
    def tearDown(self):
        self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def assert_bounds(self,index):
        board=self.window.boards[index];view=self.window.views[index];proxy=board.graphicsProxyWidget()
        self.assertEqual(proxy.size().toSize(),board.size())
        self.assertEqual(view.sceneRect().size().toSize(),board.size())
        return board,view,proxy
    def test_repeated_word_window_resize_after_enlarging_text(self):
        tool=self.window.open_module('word');tool.pages.setCurrentIndex(tool.PROSE_PAGE);self.pump()
        source=tool.prose_table_editor.source;source.setPlainText('原文保持')
        resize_field(source,source.width(),500,False,True)
        for width,height in [(1440,1250),(1100,800),(1600,1100),(1010,1000),(1440,960)]:
            self.window.resize(width,height);self.pump();board,view,proxy=self.assert_bounds(3)
            self.assertEqual(tool.geometry().bottom(),board.height()-25)
            self.assertEqual(source.height(),500);self.assertEqual(source.toPlainText(),'原文保持')
    def test_window_expands_content_without_zooming(self):
        tool=self.window.open_module('word');self.pump()
        measurements=[]
        for width in (1100,1440,1800,1100):
            self.window.resize(width,1050);self.pump();board,view,proxy=self.assert_bounds(3)
            self.assertEqual(view.transform().m11(),1)
            self.assertEqual(view.transform().m22(),1)
            self.assertEqual(tool.width(),board.width()-296)
            self.assertEqual(board.controls['brand-icon'].width(),40)
            self.assertEqual(board.controls['nav-word'].width(),192)
            self.assertEqual(view.footer.width(),184)
            measurements.append(tool.width())
        self.assertLess(measurements[0],measurements[1])
        self.assertLess(measurements[1],measurements[2])
        self.assertEqual(measurements[0],measurements[3])
    def test_other_pages_stretch_fields_without_zooming(self):
        for key,field in [('category','category-values'),('numeric','numeric-values'),('shap','continuous-variables')]:
            self.window.open_module(key);self.pump();board=self.window.boards[self.window.board_index]
            self.window.resize(1440,1050);self.pump();before=board.controls[field].width()
            self.window.resize(1800,1050);self.pump()
            self.assertGreater(board.controls[field].width(),before)
            self.assertEqual(self.window.views[board.index].transform().m11(),1)
            self.assertEqual(board.controls['brand-icon'].width(),40)

    def test_all_pages_resize_and_bottom_content_accepts_clicks(self):
        for index,key in enumerate(('category','numeric','word','shap'),1):
            self.window.open_module(key);self.pump()
            for width,height in [(1440,1250),(1050,820),(1440,960)]:
                self.window.resize(width,height);self.pump();board,view,proxy=self.assert_bounds(index)
            self.window.resize(1440,1250);self.pump();board,view,proxy=self.assert_bounds(index)
            button=QPushButton('底部测试',board);button.setGeometry(600,board.height()-65,160,35);button.show();clicked=[];button.clicked.connect(lambda:clicked.append(True));self.pump()
            pos=view.mapFromScene(proxy.mapToScene(button.geometry().center()))
            QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=pos);self.pump()
            self.assertEqual(clicked,[True],key)
            button.deleteLater();self.pump()

if __name__=='__main__':unittest.main()
