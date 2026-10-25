"""Four peer tools; each instance owns its configuration, tasks and results."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QStackedWidget, QMessageBox,
)

from .config import ROOT


MODULES = (
    ("category", "自定义类别数列", "设置各数字的数量，随机打乱排列，复制或保存数列。"),
    ("numeric", "均数 / 标准差模拟数据", "设置均数、标准差、例数和上下限，生成并核对模拟数值。"),
    ("word", "Word 一键生成 Excel", "导入 Word 汇总表，核对两组参数，生成并导出模拟病例。"),
    ("shap", "模拟数据生图", "配置数据、模型及每张图的样式，生成数据与 SHAP 图表。"),
)


class DesktopWindow(QMainWindow):
    def __init__(self, config=None, output=None):
        super().__init__()
        self.shap_initial_config = deepcopy(config)
        self.shap_output = output
        self.modules = {}
        self.module_pages = {}
        self.current_module = None
        self.setWindowTitle("科研数据工具集")
        self.resize(1460, 980)
        self.setMinimumSize(1120, 760)
        self.setWindowIcon(QIcon(str(ROOT / "assets" / "icon.png")))
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setStyleSheet("QFrame { background:white; border-bottom:1px solid #DFE7ED; }")
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 14, 24, 14)
        self.home_button = QPushButton("← 返回首页")
        self.home_button.clicked.connect(self.show_home)
        row.addWidget(self.home_button)
        self.title = QLabel("科研数据工具集")
        self.title.setStyleSheet("font-size:20px;font-weight:700;color:#142F32;border:none;")
        row.addWidget(self.title)
        row.addStretch()
        self.module_hint = QLabel("四个独立工具 · 本机运行")
        self.module_hint.setObjectName("muted")
        row.addWidget(self.module_hint)
        layout.addWidget(header)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.home_page = self.make_home()
        self.stack.addWidget(self.home_page)
        self.show_home()

    def make_home(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(48, 32, 48, 32)
        outer.addStretch(1)
        title = QLabel("选择一个工具，开始工作。")
        title.setStyleSheet("font-size:30px;font-weight:700;color:#142F32;")
        outer.addWidget(title)
        note = QLabel("每个工具单独设置参数、生成数据和保存结果。返回首页后，本次参数与结果仍会保留。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        outer.addWidget(note)
        outer.addSpacing(24)
        grid = QGridLayout()
        grid.setSpacing(22)
        self.launch_buttons = {}
        for index, (key, name, description) in enumerate(MODULES):
            card = QFrame()
            card.setObjectName("card")
            body = QVBoxLayout(card)
            body.setContentsMargins(26, 24, 26, 24)
            number = QLabel(f"0{index + 1}")
            number.setStyleSheet("font-size:15px;font-weight:700;color:#0D7668;")
            body.addWidget(number)
            heading = QLabel(name)
            heading.setStyleSheet("font-size:22px;font-weight:600;color:#142F32;")
            body.addWidget(heading)
            text = QLabel(description)
            text.setObjectName("muted")
            text.setWordWrap(True)
            body.addWidget(text)
            body.addSpacing(18)
            launch = QPushButton("进入工具  →")
            launch.setObjectName("primary")
            launch.setAccessibleName(name)
            launch.clicked.connect(lambda checked=False, k=key: self.open_module(k))
            body.addWidget(launch)
            self.launch_buttons[key] = launch
            grid.addWidget(card, index // 2, index % 2)
        outer.addLayout(grid)
        outer.addStretch(2)
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
                tool = MainWindow(self.shap_initial_config, self.shap_output)
                tool.setWindowFlags(Qt.Widget)
                tool.setMinimumSize(0, 0)
            page = QWidget()
            layout = QVBoxLayout(page)
            inset = 0 if key == "shap" else 24
            layout.setContentsMargins(inset, inset, inset, inset)
            layout.addWidget(tool)
            self.modules[key] = tool
            self.module_pages[key] = page
            self.stack.addWidget(page)
        self.current_module = key
        self.stack.setCurrentWidget(self.module_pages[key])
        name = next(m[1] for m in MODULES if m[0] == key)
        self.title.setText(name)
        self.module_hint.setText("独立参数 · 独立结果")
        self.home_button.show()
        self.setWindowTitle(name + " · 科研数据工具集")
        return self.modules[key]

    def show_home(self):
        self.current_module = None
        self.stack.setCurrentWidget(self.home_page)
        self.title.setText("科研数据工具集")
        self.module_hint.setText("四个独立工具 · 本机运行")
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
