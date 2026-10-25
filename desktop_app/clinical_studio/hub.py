"""Four peer tools; each instance owns its configuration, tasks and results."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QStackedWidget, QMessageBox, QButtonGroup,
)

from .config import ROOT
from .widgets import scroll


MODULES = (
    ("category", "自定义类别数列", "设置各数字的数量，随机打乱排列，复制或保存数列。"),
    ("numeric", "均数 / 标准差模拟数据", "设置均数、标准差、例数和上下限，生成并核对模拟数值。"),
    ("word", "Word 一键生成 Excel", "导入 Word 汇总表，核对两组参数，生成并导出模拟病例。"),
    ("shap", "模拟数据生图", "配置数据、模型及每张图的样式，生成数据与 SHAP 图表。"),
)


class LegacyDesktopWindow(QMainWindow):
    def __init__(self, config=None, output=None):
        super().__init__()
        self.shap_initial_config = deepcopy(config)
        self.shap_output = output
        self.modules = {}
        self.module_pages = {}
        self.current_module = None
        self.setWindowTitle("科研数据工具集")
        self.resize(1440, 920)
        self.setMinimumSize(1120, 760)
        self.setWindowIcon(QIcon(str(ROOT / "assets" / "icon.png")))
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("appSidebar"); sidebar.setFixedWidth(224)
        side = QVBoxLayout(sidebar); side.setContentsMargins(16, 28, 16, 20); side.setSpacing(10)
        brand_row = QHBoxLayout()
        mark = QLabel("研"); mark.setObjectName("brandMark"); mark.setFixedSize(40, 40); mark.setAlignment(Qt.AlignCenter)
        brand_row.addWidget(mark)
        brand_text = QVBoxLayout(); brand_text.setSpacing(2)
        brand = QLabel("科研数据工具集"); brand.setObjectName("brand")
        sub = QLabel("RESEARCH STUDIO"); sub.setObjectName("brandSub"); sub.setStyleSheet("font-size:9px;")
        brand_text.addWidget(brand); brand_text.addWidget(sub); brand_row.addLayout(brand_text)
        side.addLayout(brand_row); side.addSpacing(24)
        label = QLabel("我的工具"); label.setObjectName("muted"); side.addWidget(label)
        self.nav_buttons = {}; self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        for number, (key, name) in enumerate([(None, "工作台"), *[(k, n) for k, n, _ in MODULES]]):
            text = ("⌂   " if key is None else f"{number:02}   ") + name.replace("均数 / 标准差模拟数据", "均数 / 标准差模拟").replace("Word 一键生成 Excel", "Word 转 Excel")
            button = QPushButton(text); button.setObjectName("moduleNav"); button.setCheckable(True)
            button.setAccessibleName(name); button.setMinimumHeight(44)
            button.clicked.connect(lambda checked=False, k=key: self.show_home() if k is None else self.open_module(k))
            self.nav_buttons[key] = button; self.nav_group.addButton(button); side.addWidget(button)
        side.addStretch()
        badge = QLabel("本机运行 · 安心保存\n\n四个工具独立保留参数\n和生成结果，随时切换。")
        badge.setObjectName("localBadge"); badge.setWordWrap(True); side.addWidget(badge)
        side.addSpacing(14)
        foot = QLabel("dbq / 科研工作空间"); foot.setObjectName("muted"); side.addWidget(foot)
        layout.addWidget(sidebar)
        body = QWidget(); body_layout = QVBoxLayout(body); body_layout.setContentsMargins(0,0,0,0); body_layout.setSpacing(0)
        header = QFrame(); header.setObjectName("appHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(28, 14, 28, 14)
        self.home_button = QPushButton("← 返回首页")
        self.home_button.clicked.connect(self.show_home)
        row.addWidget(self.home_button)
        self.title = QLabel("科研数据工具集")
        self.title.setObjectName("sectionTitle")
        row.addWidget(self.title)
        row.addStretch()
        self.module_hint = QLabel("四个独立工具 · 本机运行")
        self.module_hint.setObjectName("moduleBadge")
        row.addWidget(self.module_hint)
        body_layout.addWidget(header)
        self.stack = QStackedWidget()
        body_layout.addWidget(self.stack, 1)
        layout.addWidget(body, 1)
        self.setCentralWidget(root)
        self.home_page = self.make_home()
        self.home_scroll = scroll(self.home_page)
        self.stack.addWidget(self.home_scroll)
        self.show_home()

    def make_home(self):
        page = QWidget(); page.setObjectName("homePage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(32, 26, 32, 24); outer.setSpacing(14)
        title = QLabel("工作台"); title.setObjectName("pageTitle")
        outer.addWidget(title)
        note = QLabel("从一个工具开始，让数据准备和科研制图更有条理。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        outer.addWidget(note)
        hero = QFrame(); hero.setObjectName("hero"); hl = QVBoxLayout(hero); hl.setContentsMargins(28,20,28,24)
        hero_title = QLabel("把时间留给研究。"); hero_title.setObjectName("heroTitle"); hl.addWidget(hero_title)
        hero_text = QLabel("选择独立工具，设置参数，核对结果，再保存你的工作。"); hero_text.setObjectName("heroText"); hero_text.setWordWrap(True); hl.addWidget(hero_text)
        outer.addWidget(hero); outer.addSpacing(4)
        grid = QGridLayout()
        grid.setSpacing(20); grid.setColumnStretch(0,1); grid.setColumnStretch(1,1)
        self.launch_buttons = {}
        for index, (key, name, description) in enumerate(MODULES):
            card = QFrame()
            card.setObjectName("card")
            body = QVBoxLayout(card)
            body.setContentsMargins(24, 20, 24, 20); body.setSpacing(12)
            number = QLabel(f"0{index + 1}")
            number.setObjectName("moduleBadge"); number.setFixedWidth(60); body.addWidget(number,0,Qt.AlignLeft)
            heading = QLabel(name)
            heading.setObjectName("sectionTitle"); heading.setWordWrap(True)
            body.addWidget(heading)
            text = QLabel(description)
            text.setObjectName("muted")
            text.setWordWrap(True)
            body.addWidget(text)
            body.addStretch()
            launch = QPushButton("进入工具  →")
            launch.setObjectName("primary")
            launch.setAccessibleName(name)
            launch.clicked.connect(lambda checked=False, k=key: self.open_module(k))
            launch.setFixedWidth(155); body.addWidget(launch)
            self.launch_buttons[key] = launch
            grid.addWidget(card, index // 2, index % 2)
        outer.addLayout(grid)
        outer.addStretch(1)
        footer = QLabel("独立参数 · 独立结果 · 自主导出"); footer.setObjectName("muted"); outer.addWidget(footer)
        return page

    def open_module(self, key):
        if key not in {m[0] for m in MODULES}:
            raise ValueError(f"未知工具：{key}")
        if key not in self.modules:
            if key == "category":
                from .data_tools import CategoryTool
                tool = CategoryTool()
            elif key == "numeric":
                from .data_tools import NumericTool
                tool = NumericTool()
            elif key == "word":
                from .word_batch import WordBatchTool
                tool = WordBatchTool()
            else:
                from .app import MainWindow
                tool = MainWindow(self.shap_initial_config, self.shap_output, embedded=True)
                tool.setWindowFlags(Qt.Widget)
                tool.setMinimumSize(0, 0)
            page = QWidget()
            layout = QVBoxLayout(page)
            inset = 0 if key == "shap" else 20
            layout.setContentsMargins(inset, inset, inset, inset)
            if key != "shap":
                name, description = next((n, d) for k,n,d in MODULES if k == key)
                heading = QLabel(name); heading.setObjectName("pageTitle"); heading.setWordWrap(True); layout.addWidget(heading)
                note = QLabel(description); note.setObjectName("muted"); note.setWordWrap(True); layout.addWidget(note)
            layout.addWidget(tool, 1)
            self.modules[key] = tool
            self.module_pages[key] = page
            self.stack.addWidget(page)
        self.current_module = key
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(self.module_pages[key])
        name = next(m[1] for m in MODULES if m[0] == key)
        self.title.setText("dbq  /  " + name)
        self.module_hint.setText("独立参数 · 独立结果")
        self.home_button.show()
        self.setWindowTitle(name + " · 科研数据工具集")
        return self.modules[key]

    def show_home(self):
        self.current_module = None
        self.stack.setCurrentWidget(self.home_scroll)
        self.nav_buttons[None].setChecked(True)
        self.title.setText("dbq  /  工作台")
        self.module_hint.setText("●  本地模式")
        self.home_button.hide()
        self.setWindowTitle("科研数据工具集")

    def closeEvent(self, event):
        running = []
        for key, tool in self.modules.items():
            busy = tool.is_running() if hasattr(tool, "is_running") else bool(getattr(tool, "worker", None) and tool.worker.isRunning())
            if busy:
                running.append(next(m[1] for m in MODULES if m[0] == key))
        if running:
            QMessageBox.information(self, "任务仍在运行", "请等待以下工具完成任务后关闭：\n" + "\n".join(running))
            event.ignore()
        else:
            event.accept()


# The approved Penpot layout is the application entry; the former layout stays
# available only as a source reference during migration.
from .strict_ui import DesktopWindow
