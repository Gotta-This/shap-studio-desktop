"""SHAP 分析工作台：完整离线桌面界面。"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import traceback
import uuid

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QFont, QFontDatabase, QPixmap, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QStackedWidget, QFrame, QFormLayout, QGroupBox, QComboBox, QTabWidget,
    QTableView, QHeaderView, QSplitter, QFileDialog, QMessageBox, QLineEdit, QDialog,
    QProgressBar, QPlainTextEdit, QScrollArea, QGridLayout, QMenu, QAbstractItemView,
)

from .config import ROOT, PLOT_NAMES, default_config, load_config, save_config, validate
from .widgets import ParamForm, ValueField, scroll


STYLE = """
QWidget { font-family: 'Noto Sans CJK SC', 'PingFang SC', sans-serif; font-size: 13px; color: #1E293B; }
QMainWindow, #workspace { background: #F4F7FA; }
#sidebar { background: #102B2C; }
#brand { color: #F8FAFC; font-size: 20px; font-weight: 700; }
#brandSub { color: #9AC5BF; font-size: 12px; }
#nav { background: transparent; border: none; outline: none; color: #C4D8D5; }
#nav::item { padding: 15px 18px; margin: 3px 10px; border-radius: 7px; }
#nav::item:selected { background: #21514D; color: #FFFFFF; }
#nav::item:hover { background: #193E3B; }
#localBadge { color: #A7D7C5; background: #173E39; border-radius: 7px; padding: 12px; }
#pageTitle { font-size: 25px; font-weight: 700; color: #142F32; }
#muted { color: #64748B; }
#card, QGroupBox { background: white; border: 1px solid #DFE7ED; border-radius: 10px; }
QGroupBox { margin-top: 16px; padding: 18px 12px 12px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QLabel { background: transparent; }
QPushButton { background: white; border: 1px solid #CDD9E1; border-radius: 6px; padding: 8px 13px; }
QPushButton:hover { background: #EDF5F4; border-color: #7BAFA6; }
QPushButton:disabled { background: #EFF3F6; color: #94A3B8; border-color: #E2E8F0; }
#primary { background: #0D7668; color: white; font-weight: 600; border-color: #0D7668; }
#primary:hover { background: #0A6257; }
#primary:disabled { background: #92BBB5; color: white; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: white; border: 1px solid #CCD8E0; border-radius: 5px; padding: 6px; min-height: 21px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #0D9488; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { color: #91A0AE; background: #F5F7F9; }
QComboBox QAbstractItemView { background: white; selection-background-color: #D7EEE9; color: #1E293B; }
QCheckBox { spacing: 7px; }
QTabWidget::pane { border: 1px solid #DFE7ED; background: white; border-radius: 7px; }
QTabBar::tab { background: #EDF2F6; padding: 10px 17px; margin-right: 3px; }
QTabBar::tab:selected { background: white; color: #0D7668; border-bottom: 2px solid #0D7668; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: white; }
QTableView { background: white; alternate-background-color: #F6F9FB; border: 1px solid #DFE7ED; gridline-color: #EAF0F4; selection-background-color: #D9EFEB; selection-color: #173E39; }
QHeaderView::section { background: #F1F5F8; border: none; border-bottom: 1px solid #DDE5EB; padding: 9px; font-weight: 600; }
QPlainTextEdit { background: #15282F; color: #CEE3DD; border: none; border-radius: 8px; padding: 12px; font-family: Menlo, monospace; }
QProgressBar { background: #E5EDEA; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #0D9488; }
"""


def muted(text):
    label = QLabel(text); label.setObjectName("muted"); label.setWordWrap(True)
    return label


def card(title, text):
    widget = QFrame(); widget.setObjectName("card")
    layout = QVBoxLayout(widget); layout.setContentsMargins(20, 18, 20, 18)
    layout.addWidget(muted(title))
    value = QLabel(text); value.setStyleSheet("font-size:25px;font-weight:700;color:#164E48")
    layout.addWidget(value)
    return widget, value


class DataTableModel(QAbstractTableModel):
    def __init__(self, frame):
        super().__init__(); self.frame = frame

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.frame)
    def columnCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.frame.columns)
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        if role == Qt.DisplayRole:
            value = self.frame.iloc[index.row(), index.column()]
            return f"{value:.6g}" if isinstance(value, float) else str(value)
        if role == Qt.TextAlignmentRole: return int(Qt.AlignVCenter | Qt.AlignLeft)
        return None
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole: return None
        return str(self.frame.columns[section]) if orientation == Qt.Horizontal else str(section+1)


class FeatureEditor(QWidget):
    def __init__(self, data):
        super().__init__(); self.data=data; self.current=-1; self.detail_forms={}
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.general=ParamForm({k:v for k,v in data.items() if k != "features"})
        general_box=QGroupBox("样本与字段设置"); form_layout=QVBoxLayout(general_box); form_layout.addWidget(self.general)
        self.tabs=QTabWidget()
        layout.addWidget(self.tabs)
        splitter=QSplitter(Qt.Horizontal)
        left=QWidget(); ll=QVBoxLayout(left); ll.setContentsMargins(0,0,10,0)
        ll.addWidget(QLabel("输入特征")); self.list=QListWidget(); ll.addWidget(self.list)
        buttons=QHBoxLayout(); self.add_button=QPushButton("添加特征"); remove=QPushButton("删除")
        buttons.addWidget(self.add_button); buttons.addWidget(remove); ll.addLayout(buttons)
        order_buttons=QHBoxLayout(); up=QPushButton("上移"); down=QPushButton("下移")
        order_buttons.addWidget(up); order_buttons.addWidget(down); ll.addLayout(order_buttons)
        up.clicked.connect(lambda:self.move_feature(-1)); down.clicked.connect(lambda:self.move_feature(1))
        menu=QMenu(self)
        menu.addAction("连续变量",lambda:self.add_feature("continuous"))
        menu.addAction("二分类变量",lambda:self.add_feature("binary"))
        self.add_button.setMenu(menu); remove.clicked.connect(self.remove_feature)
        self.detail_holder=QWidget(); self.detail_layout=QVBoxLayout(self.detail_holder); self.detail_layout.setContentsMargins(5,0,0,0)
        splitter.addWidget(left); splitter.addWidget(self.detail_holder); splitter.setSizes([220,660])
        self.tabs.addTab(splitter,"各特征的分布参数")
        self.tabs.addTab(scroll(general_box),"样本数量与字段设置")
        self.list.currentRowChanged.connect(self.select)
        self.refresh_list(0)

    def refresh_list(self, selected):
        self.list.blockSignals(True); self.list.clear()
        for feature in self.data["features"]:
            self.list.addItem(("◦  " if feature["kind"]=="continuous" else "◇  ")+feature["name"])
        self.list.setCurrentRow(selected); self.list.blockSignals(False)
        self.current=-1; self.select(selected)

    def commit_feature(self):
        if self.current < 0 or not self.detail_forms: return
        feature=self.data["features"][self.current]
        feature["name"]=self.name.text().strip()
        for key, form in self.detail_forms.items():
            if key in ("positive","negative"): feature[key]=form.values()
            else: feature.update(form.values())
        if self.list.item(self.current):
            self.list.item(self.current).setText(("◦  " if feature["kind"]=="continuous" else "◇  ")+feature["name"])

    def commit(self):
        self.commit_feature(); self.data.update(self.general.values())

    def select(self, index):
        self.commit_feature()
        self.current=index; self.detail_forms={}
        while self.detail_layout.count():
            item=self.detail_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if index<0 or index>=len(self.data["features"]): return
        feature=self.data["features"][index]
        header=QFormLayout(); self.name=QLineEdit(feature["name"]); header.addRow("特征名称",self.name)
        header_widget=QWidget(); header_widget.setLayout(header); self.detail_layout.addWidget(header_widget)
        if feature["kind"]=="continuous":
            groups=QHBoxLayout()
            for key,title in [("positive","阳性组（结局 = 1）"),("negative","阴性组（结局 = 0）")]:
                box=QGroupBox(title); bl=QVBoxLayout(box)
                form=ParamForm({k:float(v) for k,v in feature[key].items()})
                self.detail_forms[key]=form; bl.addWidget(form); groups.addWidget(box)
            self.detail_layout.addLayout(groups)
            form=ParamForm({k:feature[k] for k in ("transform","digits")})
            self.detail_forms["processing"]=form; self.detail_layout.addWidget(form)
            self.detail_layout.addWidget(muted("先按正态分布抽样，再把越界值压到上下限，最后取整或保留小数。两组参数独立设置。"))
        else:
            form=ParamForm({k:feature[k] for k in ("values","positive_p","negative_p")},labels={"values":"二分类数值编码"})
            self.detail_forms["binary"]=form; self.detail_layout.addWidget(form)
            self.detail_layout.addWidget(muted("概率针对上方的第二个编码；第一个编码的概率为 1 − 当前概率。"))
        self.detail_layout.addStretch()

    def add_feature(self, kind):
        self.commit_feature()
        feature=dict(key=uuid.uuid4().hex,name=f"新特征{len(self.data['features'])+1}",kind=kind)
        if kind=="continuous":
            feature.update(positive=dict(mean=1.,std=1.,min=-5.,max=5.),negative=dict(mean=0.,std=1.,min=-5.,max=5.),transform="round",digits=1)
        else: feature.update(values=[0,1],positive_p=.7,negative_p=.5)
        self.data["features"].append(feature); self.refresh_list(len(self.data["features"])-1)

    def remove_feature(self):
        if self.current<0: return
        if len(self.data["features"])<=1:
            QMessageBox.information(self,"保留一个特征","至少需要一个输入特征。"); return
        self.commit_feature(); index=self.current
        del self.data["features"][index]; self.current=-1
        self.refresh_list(min(index,len(self.data["features"])-1))

    def move_feature(self,direction):
        index=self.current; target=index+direction
        if index<0 or target<0 or target>=len(self.data["features"]):return
        self.commit_feature(); features=self.data["features"]
        features[index],features[target]=features[target],features[index]
        self.current=-1; self.refresh_list(target)


class AnalysisWorker(QThread):
    progress=Signal(str); completed=Signal(object); failed=Signal(str)
    def __init__(self,config,output,previous=None,data_only=False):
        super().__init__(); self.config=config; self.output=output; self.previous=previous; self.data_only=data_only
    def run(self):
        try:
            from .engine import run_analysis
            self.completed.emit(run_analysis(self.config,self.output,self.progress.emit,self.previous,self.data_only))
        except Exception:
            self.failed.emit(traceback.format_exc())


class ImagePreview(QDialog):
    def __init__(self,path,parent=None):
        super().__init__(parent); self.path=Path(path); self.setWindowTitle(self.path.name); self.resize(1180,800)
        layout=QVBoxLayout(self)
        self.image=QLabel(); self.image.setAlignment(Qt.AlignCenter)
        pix=QPixmap(str(path)); self.original=pix
        self.image.setPixmap(pix.scaled(1120,700,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        layout.addWidget(scroll(self.image))
        row=QHBoxLayout(); save=QPushButton("另存此图…"); original=QPushButton("原始尺寸"); fit=QPushButton("适应窗口")
        row.addWidget(original); row.addWidget(fit); row.addStretch(); row.addWidget(save); layout.addLayout(row)
        original.clicked.connect(lambda:self.image.setPixmap(self.original))
        fit.clicked.connect(lambda:self.image.setPixmap(self.original.scaled(self.width()-60,self.height()-100,Qt.KeepAspectRatio,Qt.SmoothTransformation)))
        save.clicked.connect(self.save)
    def save(self):
        destination,_=QFileDialog.getSaveFileName(self,"另存图片",self.path.name,"PNG 图片 (*.png)")
        if destination and Path(destination).resolve()!=self.path.resolve(): shutil.copy2(self.path,destination)


class MainWindow(QMainWindow):
    def __init__(self,config=None,output=None):
        super().__init__(); self.config=deepcopy(config or default_config()); self.result=None; self.worker=None
        self.output_root=str(output or (Path.home()/"Documents"/"SHAP分析结果"))
        self.setWindowTitle("SHAP 分析工作台"); self.resize(1460,980); self.setMinimumSize(1120,760)
        icon=ROOT/"assets"/"icon.png"
        if icon.exists(): self.setWindowIcon(QIcon(str(icon)))
        base=QWidget(); outer=QHBoxLayout(base); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(210)
        sl=QVBoxLayout(sidebar); sl.setContentsMargins(0,28,0,20)
        brand=QLabel("SHAP 工作台"); brand.setObjectName("brand"); brand.setContentsMargins(24,0,0,0); sl.addWidget(brand)
        sub=QLabel("数据生成 · 模型解释"); sub.setObjectName("brandSub"); sub.setContentsMargins(24,8,0,20); sl.addWidget(sub)
        self.nav=QListWidget(); self.nav.setObjectName("nav")
        self.nav.addItems(["概览", "数据参数", "模型与解释", "图表样式", "结果与导出", "运行日志", "数据工具集"])
        sl.addWidget(self.nav)
        badge=QLabel("●  本地计算\n\n数据与结果保存在本机"); badge.setObjectName("localBadge"); badge.setContentsMargins(14,8,10,8)
        sl.addWidget(badge); version=QLabel("    版本 1.0.0 · 离线桌面版"); version.setObjectName("brandSub"); sl.addWidget(version)
        outer.addWidget(sidebar)
        workspace=QWidget(); workspace.setObjectName("workspace"); wl=QVBoxLayout(workspace); wl.setContentsMargins(28,24,28,16); wl.setSpacing(14)
        top=QHBoxLayout(); self.page_title=QLabel("分析概览"); self.page_title.setObjectName("pageTitle"); top.addWidget(self.page_title); top.addStretch()
        self.import_button=QPushButton("载入配置"); self.save_button=QPushButton("保存配置"); self.run_button=QPushButton("生成数据并分析"); self.run_button.setObjectName("primary")
        for button in (self.import_button,self.save_button,self.run_button): top.addWidget(button)
        wl.addLayout(top)
        self.stack=QStackedWidget(); wl.addWidget(self.stack,1)
        self.status=QLabel("就绪 · 调整参数后开始分析"); self.status.setObjectName("muted"); wl.addWidget(self.status)
        self.progress=QProgressBar(); self.progress.setRange(0,1); self.progress.setValue(0); self.progress.setTextVisible(False); wl.addWidget(self.progress)
        outer.addWidget(workspace,1); self.setCentralWidget(base)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True)
        self.build_pages()
        self.nav.currentRowChanged.connect(self.navigate); self.nav.setCurrentRow(0)
        self.run_button.clicked.connect(lambda:self.start_analysis())
        self.import_button.clicked.connect(self.import_config); self.save_button.clicked.connect(self.export_config)

    def build_pages(self):
        # 导入配置后重建参数页，已保存的结果仍保留。
        for i in range(self.stack.count()-1,-1,-1):
            widget=self.stack.widget(i); self.stack.removeWidget(widget)
            if widget is not self.log and widget is not getattr(self,"data_tools_page",None): widget.deleteLater()
        self.build_overview()
        self.data_editor=FeatureEditor(self.config["data"]); self.stack.addWidget(scroll(self.data_editor))
        self.model_page=self.make_model_page(); self.stack.addWidget(self.model_page)
        self.style_page=self.make_style_page(); self.stack.addWidget(self.style_page)
        self.results_page=self.make_results_page(); self.stack.addWidget(self.results_page)
        self.stack.addWidget(self.log)
        if not hasattr(self,"data_tools_page"):
            from .data_tools import DataToolsPage
            self.data_tools_page=DataToolsPage()
        self.stack.addWidget(self.data_tools_page)
        if self.result: self.show_result(self.result)

    def build_overview(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,0,0); layout.setSpacing(18)
        hero=QFrame(); hero.setObjectName("card"); hl=QVBoxLayout(hero); hl.setContentsMargins(28,25,28,25)
        title=QLabel("把每一次分析，连同参数一起保存。"); title.setStyleSheet("font-size:23px;font-weight:600;color:#164E48")
        hl.addWidget(title); hl.addWidget(muted("完整保留模拟数据、逻辑回归和 SHAP 解释流程。所有数据分布与图表样式都可以在界面中调整。")); layout.addWidget(hero)
        cards=QHBoxLayout(); self.stat_values=[]
        for title,text in [("默认样本量",str(self.config["data"]["n_samples"])),("输入特征",str(len(self.config["data"]["features"]))),("可生成图表","6 张"),("最近运行","尚未运行")]:
            widget,value=card(title,text); cards.addWidget(widget); self.stat_values.append(value)
        layout.addLayout(cards)
        workflow=QGroupBox("使用流程"); fl=QVBoxLayout(workflow)
        for title,text in [("01  设置数据","逐个设置连续变量两组的均值、标准差、边界与数值处理，以及分类变量的编码与概率。"),
                           ("02  配置分析与样式","调整训练集划分、逻辑回归和 SHAP 参数，统一或单独设置每张图的样式。"),
                           ("03  运行并保存","生成数据、模型评估和六张图，自动保存参数、Excel、CSV、图片与颜色核对报告。")]:
            label=QLabel(title); label.setStyleSheet("font-size:15px;font-weight:600;margin-top:10px"); fl.addWidget(label); fl.addWidget(muted(text))
        layout.addWidget(workflow)
        path_box=QGroupBox("结果保存位置"); pl=QVBoxLayout(path_box); row=QHBoxLayout()
        self.output_edit=QLineEdit(self.output_root); choose=QPushButton("选择目录…"); row.addWidget(self.output_edit,1); row.addWidget(choose)
        choose.clicked.connect(self.choose_output); pl.addLayout(row)
        pl.addWidget(muted("每次运行创建独立目录，包含完整参数快照；已有结果不会被覆盖。")); layout.addWidget(path_box)
        actions=QHBoxLayout(); self.data_button=QPushButton("仅生成并保存数据"); self.redraw_button=QPushButton("使用已有模型重新绘图"); self.redraw_button.setEnabled(self.result is not None and self.result.model is not None)
        actions.addWidget(self.data_button); actions.addWidget(self.redraw_button); actions.addStretch()
        self.data_button.clicked.connect(lambda:self.start_analysis(data_only=True)); self.redraw_button.clicked.connect(lambda:self.start_analysis(redraw=True))
        layout.addLayout(actions); layout.addWidget(muted("默认数据为模拟数据；模型方向与性能反映当前生成参数。应用无需联网，也不需要用户自行配置运行环境。")); layout.addStretch()
        self.stack.addWidget(scroll(page))

    def make_model_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,0,0)
        tabs=QTabWidget(); names=[f["name"] for f in self.config["data"]["features"]]
        self.model_form=ParamForm(self.config["model"],names)
        self.explanation_form=ParamForm(self.config["explanation"],names)
        tabs.addTab(scroll(self.model_form),"数据划分与逻辑回归"); tabs.addTab(scroll(self.explanation_form),"SHAP 背景与默认特征")
        layout.addWidget(tabs)
        layout.addWidget(muted("L1 / ElasticNet 可使用 saga；L1 也可使用 liblinear。SHAP 解释的是 log-odds。模型系数方向不代表统计显著性。"))
        return page

    def make_style_page(self):
        from .widgets import StyleEditor
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,0,0)
        global_config=self.config["plots"]
        self.export_form=ParamForm({k:global_config[k] for k in ("dpi","formats","random_seed","sample_index")})
        self.export_form.setMaximumHeight(210)
        layout.addWidget(self.export_form)
        self.style_editor=StyleEditor(global_config,[f["name"] for f in self.config["data"]["features"]])
        layout.addWidget(self.style_editor,1)
        layout.addWidget(muted("PNG 始终保留用于界面预览；SVG / PDF 按勾选导出。透明散点与背景混合后会比原始色值浅。"))
        return page

    def make_results_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,0,0)
        toolbar=QHBoxLayout(); self.result_hint=muted("运行分析后，这里将显示数据、评估指标和图表。")
        toolbar.addWidget(self.result_hint,1)
        open_folder=QPushButton("打开结果目录"); copy=QPushButton("另存完整结果…")
        toolbar.addWidget(open_folder); toolbar.addWidget(copy); open_folder.clicked.connect(self.open_results); copy.clicked.connect(self.copy_results)
        layout.addLayout(toolbar)
        self.result_tabs=QTabWidget(); layout.addWidget(self.result_tabs,1)
        self.data_table=QTableView(); self.coefficient_table=QTableView(); self.prediction_table=QTableView()
        for table in (self.data_table,self.coefficient_table,self.prediction_table):
            table.setAlternatingRowColors(True); table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.gallery=QWidget(); self.gallery_layout=QGridLayout(self.gallery); self.gallery_layout.setSpacing(18)
        self.metrics_label=QLabel("尚无模型结果"); self.metrics_label.setTextFormat(Qt.PlainText); self.metrics_label.setWordWrap(True); self.metrics_label.setAlignment(Qt.AlignTop); self.metrics_label.setMargin(24)
        self.result_tabs.addTab(scroll(self.gallery),"图表预览"); self.result_tabs.addTab(self.data_table,"完整数据")
        self.result_tabs.addTab(scroll(self.metrics_label),"模型评估"); self.result_tabs.addTab(self.coefficient_table,"模型系数")
        self.result_tabs.addTab(self.prediction_table,"测试集预测")
        return page

    def collect_config(self):
        self.data_editor.commit()
        self.config["model"].update(self.model_form.values())
        self.config["explanation"].update(self.explanation_form.values())
        self.config["plots"].update(self.export_form.values()); self.style_editor.commit()
        return deepcopy(self.config)

    def navigate(self,index):
        if index<0:return
        try:
            if hasattr(self,"style_editor"):
                self.collect_config()
            if index in (2,3):
                # 数据特征可增删改名，进入参数页时更新可选特征列表。
                new=self.make_model_page() if index==2 else self.make_style_page()
                old=self.stack.widget(index); self.stack.removeWidget(old); self.stack.insertWidget(index,new); old.deleteLater()
        except ValueError as exc:
            self.status.setText(str(exc))
        self.stack.setCurrentIndex(index)
        self.page_title.setText(["分析概览","数据参数","模型与解释","图表样式","结果与导出","运行日志","数据工具集"][index])
        for button in (self.import_button,self.save_button,self.run_button):
            button.setVisible(index != 6)

    def choose_output(self):
        path=QFileDialog.getExistingDirectory(self,"选择结果保存位置",self.output_edit.text())
        if path:self.output_edit.setText(path)

    def export_config(self):
        try:config=self.collect_config(); validate(config)
        except Exception as exc: QMessageBox.warning(self,"配置未保存",str(exc)); return
        path,_=QFileDialog.getSaveFileName(self,"保存全部参数配置","SHAP分析参数.json","JSON (*.json)")
        if path:save_config(config,path); self.status.setText("全部参数配置已保存。")

    def import_config(self):
        path,_=QFileDialog.getOpenFileName(self,"载入参数配置","","JSON (*.json)")
        if not path:return
        try:config=load_config(path)
        except Exception as exc:QMessageBox.warning(self,"无法载入配置",str(exc));return
        self.config=config; self.output_root=self.output_edit.text(); index=max(0,self.nav.currentRow()); self.build_pages(); self.stack.setCurrentIndex(index)
        self.status.setText("已载入全部参数；最近结果仍对应原运行快照。")

    def set_busy(self,busy):
        self.stack.setEnabled(not busy); self.import_button.setEnabled(not busy); self.save_button.setEnabled(not busy); self.run_button.setEnabled(not busy)
        self.nav.setEnabled(not busy)
        self.progress.setRange(0,0 if busy else 1)
        if not busy:self.progress.setValue(1)

    def start_analysis(self,data_only=False,redraw=False):
        if self.worker and self.worker.isRunning():return
        try:
            config=self.collect_config(); validate(config)
            output=self.output_edit.text().strip()
            if not output:raise ValueError("请先选择结果保存目录。")
            if redraw and (self.result is None or self.result.model is None):raise ValueError("请先完成一次完整分析。")
            if redraw and any(config[key]!=self.result.config[key] for key in ("data","model")):
                raise ValueError("数据或模型参数已修改，请点击“生成数据并分析”。只修改样式时可单独重新绘图。")
        except Exception as exc:QMessageBox.warning(self,"请检查参数",str(exc));return
        self.output_root=output; self.set_busy(True); self.log.appendPlainText("\n—— 新任务 ——")
        self.worker=AnalysisWorker(config,output,self.result if redraw else None,data_only)
        self.worker.progress.connect(self.on_progress); self.worker.completed.connect(self.on_complete); self.worker.failed.connect(self.on_failure)
        self.worker.start()

    def on_progress(self,message):
        self.status.setText(message); self.log.appendPlainText(message)

    def on_complete(self,result):
        self.result=result; self.set_busy(False); self.show_result(result)
        self.redraw_button.setEnabled(result.model is not None)
        self.status.setText(f"已保存至 {result.folder}"); self.log.appendPlainText(f"保存位置：{result.folder}")
        for message in result.messages or []:self.log.appendPlainText("提示："+message)
        self.nav.setCurrentRow(4)

    def on_failure(self,error):
        self.set_busy(False); self.log.appendPlainText(error); self.status.setText("运行失败，详细原因见运行日志。")
        QMessageBox.warning(self,"分析未完成",error.strip().splitlines()[-1])

    def show_result(self,result):
        self.stat_values[0].setText(str(len(result.data))); self.stat_values[1].setText(str(len(result.features)))
        pngs=[p for p in result.images or [] if p.suffix.lower()==".png"]
        self.stat_values[2].setText(f"{len(pngs)} 张"); self.stat_values[3].setText("已完成")
        self.data_table.setModel(DataTableModel(result.data))
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.result_hint.setText(f"本次结果：{result.folder.name} · 参数已随结果保存")
        while self.gallery_layout.count():
            item=self.gallery_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        for i,path in enumerate(pngs):
            tile=QFrame(); tile.setObjectName("card"); tl=QVBoxLayout(tile)
            image=QLabel(); image.setAlignment(Qt.AlignCenter)
            image.setPixmap(QPixmap(str(path)).scaled(485,290,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            tl.addWidget(image); label=QLabel(path.name); label.setWordWrap(True); tl.addWidget(label)
            button=QPushButton("查看大图 / 另存…"); button.clicked.connect(lambda checked=False,p=path:ImagePreview(p,self).exec()); tl.addWidget(button)
            self.gallery_layout.addWidget(tile,i//2,i%2)
        if not pngs:self.gallery_layout.addWidget(muted("本次仅生成数据，或全部图表已关闭。"),0,0)
        if result.model is None:
            self.metrics_label.setText("本次仅生成数据，尚未训练模型。")
            self.coefficient_table.setModel(None); self.prediction_table.setModel(None)
        else:
            import pandas as pd
            m=result.metrics; sample=m.get("sample_prediction",{})
            self.metrics_label.setText(f"准确率  {m['accuracy']:.4f}\nROC-AUC  {m['auc']:.4f}\n\n训练集  {m['n_train']} 行\n测试集  {m['n_test']} 行\n截距  {m['intercept']:.6f}\n迭代次数  {m['iterations']}\n\n混淆矩阵（行 = 真实，列 = 预测；顺序 0、1）\n{m['confusion_matrix']}\n\n分类报告\n{pd.DataFrame(m['classification_report']).T.to_string()}\n\n局部样本预测\n{json.dumps(sample,ensure_ascii=False,indent=2)}\n\n颜色核对  {'通过' if all(a['passed'] for a in result.audit.values()) else '部分未通过，见报告'}\n\n完整明细见结果目录的“运行报告.txt”。")
            self.coefficient_table.setModel(DataTableModel(result.coefficients)); self.prediction_table.setModel(DataTableModel(result.predictions))
            for table in (self.coefficient_table,self.prediction_table):table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def open_results(self):
        if self.result:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.folder)))
        else:QMessageBox.information(self,"暂无结果","请先生成数据或运行分析。")

    def copy_results(self):
        if not self.result:QMessageBox.information(self,"暂无结果","请先生成数据或运行分析。");return
        destination=QFileDialog.getExistingDirectory(self,"另存完整结果")
        if destination:
            try:
                from .engine import copy_results
                path=copy_results(self.result,destination); self.status.setText(f"完整结果已另存至 {path}")
            except Exception as exc:QMessageBox.warning(self,"保存失败",str(exc))

    def closeEvent(self,event):
        if self.data_tools_page.is_running():
            QMessageBox.information(self,"任务仍在运行","请等待模拟数据生成完成后关闭应用。");event.ignore();return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self,"任务仍在运行","请等待当前分析完成后关闭应用。");event.ignore()
        else:event.accept()


def create_application(argv):
    app=QApplication.instance() or QApplication(argv)
    app.setApplicationName("SHAP 分析工作台"); app.setOrganizationName("ClinicalStudio")
    for font in (ROOT/"assets").glob("NotoSansCJKsc-*.otf"):
        QFontDatabase.addApplicationFont(str(font))
    # 字体下拉框与绘图引擎共享这些随 Matplotlib 打包的字体。
    import matplotlib
    for font in (Path(matplotlib.get_data_path())/"fonts"/"ttf").glob("DejaVu*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    return app
