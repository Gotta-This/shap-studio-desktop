"""Regression for menus/dialogs/scrollbars inheriting macOS dark surfaces."""
import os,json,unittest,tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtCore import QPoint,QTimer,Qt
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QApplication,QMenu,QDialog,QFileDialog,QColorDialog,QMessageBox,QComboBox
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.theme import COLORS,apply_light_palette
APP=create_application([])

class LightThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(__file__).resolve().parents[2]/'evidence/light-theme';cls.out.mkdir(parents=True,exist_ok=True)
    def setUp(self):
        # Emulate the dark palette inherited from macOS before application startup.
        dark=QPalette()
        for role in (QPalette.Window,QPalette.Base,QPalette.Button):dark.setColor(role,QColor('#202020'))
        APP.setPalette(dark);create_application([])
        self.w=DesktopWindow(output=os.path.join(tempfile.gettempdir(), 'light-theme-runs'));self.w.timer.stop();self.w.show();APP.processEvents()
    def tearDown(self):self.w.close();self.w.deleteLater();APP.processEvents()
    def light(self,pix):
        img=pix.toImage()
        # Look inside the surface, avoiding native window shadows and borders.
        longest=0
        for y in range(5,img.height()-5,3):
            run=0
            for x in range(5,img.width()-5,3):
                c=img.pixelColor(x,y)
                run=run+1 if c.alpha()>240 and max(c.red(),c.green(),c.blue())<45 else 0
                longest=max(longest,run)
        self.assertLessEqual(longest,10,'unexpected near-black background strip wider than 30px')
    def test_palette_and_scheme_override_dark_system(self):
        for role in (QPalette.Window,QPalette.Base,QPalette.Button):
            c=APP.palette().color(role);self.assertGreater(min(c.red(),c.green(),c.blue()),230)
        # The offscreen plugin does not expose a native system appearance.
        allowed=(Qt.ColorScheme.Light,Qt.ColorScheme.Unknown) if APP.platformName()=='offscreen' else (Qt.ColorScheme.Light,)
        self.assertIn(APP.styleHints().colorScheme(),allowed)
    def test_actual_parameter_menus_of_all_four_modules(self):
        for key in ('category','numeric','word','shap'):
            self.w.open_module(key);errors=[]
            def capture(key=key):
                menu=APP.activePopupWidget()
                try:
                    self.assertIsInstance(menu,QMenu);pix=menu.grab();pix.save(str(self.out/(key+'-menu.png')));self.light(pix)
                except Exception as exc:errors.append(exc)
                finally:menu.close()
            QTimer.singleShot(80,capture);self.w.parameter_menu()
            if errors:raise errors[0]
    def test_horizontal_and_vertical_scrollbars(self):
        self.w.open_module('shap');table=self.w.data_table
        # Content-sized columns can fit a wide viewport on Windows. Make the
        # scrollbar fixture deliberately narrow, independent of platform fonts.
        table.setFixedWidth(180);APP.processEvents();APP.processEvents()
        self.assertGreater(table.horizontalScrollBar().maximum(),0)
        for name,bar in [('horizontal',table.horizontalScrollBar()),('vertical',table.verticalScrollBar())]:
            pix=bar.grab();pix.save(str(self.out/(name+'-scrollbar.png')));self.light(pix)
        self.w.grab().save(str(self.out/'data-light-theme.png'))
    def test_dialog_surfaces_and_dropdown(self):
        dialogs=[QDialog(self.w),QMessageBox(self.w),QFileDialog(self.w),QColorDialog(self.w)]
        for i,d in enumerate(dialogs):
            if isinstance(d,QFileDialog):d.setOption(QFileDialog.DontUseNativeDialog)
            if isinstance(d,QColorDialog):d.setOption(QColorDialog.DontUseNativeDialog)
            d.show();APP.processEvents();pix=d.grab();pix.save(str(self.out/f'dialog-{i}.png'))
            if isinstance(d,QColorDialog):
                self.assertEqual(pix.toImage().pixelColor(5,5).name(),COLORS['background'].lower())
            else:self.light(pix)
            d.close();d.deleteLater()
        combo=QComboBox(self.w);combo.addItems(['完整参数','浅绿色菜单']);combo.show();combo.showPopup();APP.processEvents()
        popup=combo.view().window();pix=popup.grab();pix.save(str(self.out/'dropdown.png'));self.light(pix);combo.hidePopup()

if __name__=='__main__':unittest.main()
