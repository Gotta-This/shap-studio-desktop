"""Mint desktop palette. These values style the UI, never exported figures."""
COLORS = {
    "background": "#F5F8F5", "surface": "#FFFFFF", "selected": "#DDF1E4",
    "subtle": "#ECF6EF", "primary": "#277453", "heading": "#193C2C",
    "body": "#314C3E", "muted": "#637668", "border": "#DEE8DF",
}

STYLE = """
QWidget { font-family: 'Noto Sans CJK SC', 'PingFang SC', sans-serif; font-size: 13px; color: @body; }
QMainWindow, #workspace, #homePage { background: @background; }
QDialog, QMessageBox, QFileDialog, QColorDialog { background: @background; }
QMenu, QMenuBar { background: @surface; color: @body; border: 1px solid @border; }
QMenu { padding: 6px; }
QMenu::item { background: transparent; color: @body; padding: 9px 22px; border-radius: 6px; }
QMenu::item:selected { background: @selected; color: @heading; }
QMenu::item:disabled { color: #89968B; }
QMenu::separator { background: @border; height: 1px; margin: 5px 10px; }
QMenuBar::item:selected { background: @selected; }
#appSidebar { background: @surface; border-right: 1px solid @border; }
#appHeader { background: @surface; border-bottom: 1px solid @border; }
#brandMark { background: @primary; color: white; border-radius: 12px; font-size: 22px; font-weight: 700; }
#brand { color: @heading; font-size: 16px; font-weight: 700; }
#brandSub, #muted { color: @muted; }
#pageTitle { color: @heading; font-size: 27px; font-weight: 600; }
#sectionTitle { color: @heading; font-size: 18px; font-weight: 600; }
#hero { background: @selected; border-radius: 18px; }
#heroTitle { font-size: 29px; font-weight: 600; color: @heading; }
#heroText { color: @primary; font-size: 14px; }
#card, QGroupBox { background: @surface; border: 1px solid @border; border-radius: 14px; }
QGroupBox { margin-top: 15px; padding: 23px 15px 15px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 18px; padding: 0 6px; color: @heading; }
#localBadge, #moduleBadge { background: @subtle; color: @primary; border-radius: 12px; padding: 9px 14px; }
QLabel { background: transparent; }
QPushButton { background: @surface; border: 1px solid @border; border-radius: 8px; padding: 9px 14px; color: @body; }
QPushButton:hover { background: @subtle; border-color: #A8CBB3; }
QPushButton:pressed { background: @selected; }
QPushButton:disabled { background: #F0F4F0; color: #8B9A8E; border-color: @border; }
QPushButton#primary { background: @primary; color: white; border-color: @primary; font-weight: 600; }
QPushButton#primary:hover { background: #1F6044; }
QPushButton#primary:disabled { background: #97B6A4; border-color: #97B6A4; }
QPushButton#moduleNav { border: none; background: transparent; text-align: left; padding: 14px 12px; border-radius: 10px; }
QPushButton#moduleNav:hover { background: @subtle; }
QPushButton#moduleNav:checked { background: @selected; color: @heading; font-weight: 600; }
#sidebar { background: @surface; }
#nav, #workflowNav, #plotList { border: none; background: transparent; outline: none; }
#nav::item, #workflowNav::item, #plotList::item { padding: 12px 14px; margin: 3px; border-radius: 8px; color: @body; }
#nav::item:selected, #workflowNav::item:selected, #plotList::item:selected { background: @selected; color: @heading; font-weight: 600; }
#nav::item:hover, #workflowNav::item:hover, #plotList::item:hover { background: @subtle; }
QListWidget { background: @surface; border: 1px solid @border; outline: none; }
QListWidget::item { padding: 6px 9px; }
QListWidget::item:selected { background: @selected; color: @heading; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: @surface; border: 1px solid @border; border-radius: 7px; padding: 7px; min-height: 22px; selection-background-color: @selected; selection-color: @heading; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid @primary; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { color: #89968B; background: #F3F6F3; }
QComboBox QAbstractItemView { background: @surface; selection-background-color: @selected; selection-color: @heading; }
QCheckBox, QRadioButton { spacing: 7px; }
QTabWidget::pane { border: 1px solid @border; background: @surface; border-radius: 10px; }
QTabBar::tab { background: @subtle; color: @muted; padding: 10px 14px; margin-right: 3px; }
QTabBar::tab:selected { background: @selected; color: @heading; border-bottom: 2px solid @primary; }
QScrollArea { border: none; background: transparent; }
QTabWidget > QStackedWidget > QWidget { background: @surface; }
QWidget[surface="true"] { background: @surface; }
QScrollBar:vertical { background: #F0F4F0; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #BDCEC1; border-radius: 5px; min-height: 26px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #F0F4F0; }
QScrollBar:horizontal { background: #F0F4F0; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: #BDCEC1; border-radius: 5px; min-width: 26px; }
QScrollBar::handle:horizontal:hover, QScrollBar::handle:vertical:hover { background: #9EBBA6; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: #F0F4F0; }
QAbstractScrollArea::corner, QTableCornerButton::section { background: @surface; border: none; }
QTableView { background: @surface; alternate-background-color: #F8FBF8; border: 1px solid @border; border-radius: 7px; gridline-color: @border; selection-background-color: @selected; selection-color: @heading; }
QTableView::item { padding: 5px; }
QHeaderView::section { background: @subtle; color: @muted; border: none; border-bottom: 1px solid @border; padding: 10px 8px; font-weight: 500; }
QPlainTextEdit { background: #F8FBF8; color: @heading; border: 1px solid @border; border-radius: 9px; padding: 12px; font-family: 'DejaVu Sans Mono', monospace; }
QProgressBar { background: @selected; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: @primary; }
QSplitter::handle { background: transparent; width: 12px; height: 12px; }
QToolTip { color: @heading; background: @surface; border: 1px solid @border; padding: 5px; }
"""
for _key, _value in COLORS.items():
    STYLE = STYLE.replace("@" + _key, _value)

# Scoped to the fourth tool's parameter dialog, including macOS dark appearance.
SHAP_DIALOG_STYLE = """
QDialog#shapParameters { background: #F5F8F5; }
QWidget#analysisPanel { background: #F5F8F5; }
QListWidget#workflowNav { background: #FFFFFF; border: 1px solid #DEE8DF;
    border-radius: 10px; padding: 5px 8px; }
QListWidget#workflowNav::item { color: #314C3E; padding: 9px 16px;
    margin: 2px 3px; border-radius: 7px; }
QListWidget#workflowNav::item:selected { background: #DDF1E4; color: #193C2C; }
QListWidget#workflowNav::item:hover { background: #ECF6EF; }
QFrame#parametersFooter { background: #F5F8F5; border-top: 1px solid #DEE8DF; }
QFrame#parametersFooter QLabel { color: #637668; }
QFrame#parametersFooter QPushButton { background: #277453; color: #FFFFFF;
    border: 1px solid #277453; border-radius: 8px; padding: 8px 24px; }
QFrame#parametersFooter QPushButton:hover { background: #1F6044; }
"""


def apply_light_palette(app):
    """Set every native fallback surface, including controls without a stylesheet."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    if hasattr(app.styleHints(), "setColorScheme"):
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = QPalette()
    roles = {
        QPalette.Window: COLORS["background"], QPalette.WindowText: COLORS["body"],
        QPalette.Base: COLORS["surface"], QPalette.AlternateBase: "#F8FBF8",
        QPalette.Text: COLORS["body"], QPalette.Button: COLORS["surface"],
        QPalette.ButtonText: COLORS["body"], QPalette.Highlight: COLORS["selected"],
        QPalette.HighlightedText: COLORS["heading"], QPalette.ToolTipBase: COLORS["surface"],
        QPalette.ToolTipText: COLORS["heading"], QPalette.PlaceholderText: COLORS["muted"],
        QPalette.Light: COLORS["surface"], QPalette.Midlight: COLORS["subtle"],
        QPalette.Mid: COLORS["border"], QPalette.Dark: "#A8BDAE",
        QPalette.Shadow: "#C2D2C7", QPalette.Link: COLORS["primary"],
        QPalette.LinkVisited: COLORS["primary"], QPalette.BrightText: COLORS["heading"],
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#89968B"))
    app.setPalette(palette)
