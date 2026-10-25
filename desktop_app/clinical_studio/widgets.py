"""可复用的参数编辑控件。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QColorDialog, QFileDialog, QCheckBox, QComboBox, QFontComboBox,
    QDoubleSpinBox, QSpinBox, QScrollArea, QTabWidget, QLabel,
)

LABELS = {
    "font_family": "字体", "font_file": "自定义字体文件", "font_size": "图内文字字号",
    "title_size": "标题字号", "label_size": "坐标轴标题字号", "tick_size": "刻度字号",
    "title_weight": "标题字重", "title_pad": "标题间距", "xlabel_pad": "横轴标题间距",
    "text_color": "文字颜色", "value_text_color": "瀑布图内部数值颜色", "background": "背景颜色",
    "axis_color": "坐标轴颜色", "axis_width": "坐标轴线宽", "tick_width": "刻度线宽",
    "tick_length": "刻度长度", "line_color": "普通线 / 连接线颜色", "line_width": "普通线 / 连接线宽",
    "line_style": "普通线型", "grid": "显示背景网格", "grid_color": "网格颜色", "grid_width": "网格线宽",
    "grid_style": "网格线型", "baseline_color": "零基线 / 参考线颜色", "baseline_width": "零基线 / 参考线宽",
    "baseline_style": "零基线型", "baseline_alpha": "零基线透明度", "point_size": "散点面积（pt²）",
    "point_alpha": "散点透明度", "point_color": "单色散点颜色", "low_color": "低特征值颜色",
    "high_color": "高特征值颜色", "positive_color": "正贡献颜色", "negative_color": "负贡献颜色",
    "positive_light": "力图正贡献分隔线", "negative_light": "力图负贡献分隔线",
    "edge_width": "色块边框线宽", "separator_width": "力图分隔线宽", "bar_color": "条形填充颜色",
    "figsize": "图片尺寸（宽 × 高 / 英寸）", "enabled": "生成这张图", "filename": "保存文件名（不含后缀）",
    "title": "图标题", "xlabel": "横轴标题", "colorbar_label": "颜色条标题", "bar_height": "条形高度",
    "value_format": "数值格式（如 .3f）", "text_rotation": "力图文字旋转角度",
    "contribution_threshold": "力图标签贡献阈值", "title_y": "力图标题相对位置", "content_top": "力图内容上边界",
    "ylim": "力图纵向范围", "axis_y": "力图横轴纵向位置", "base_label_y": "瀑布图基准值标签位置",
    "prediction_label_y": "瀑布图预测值标签位置", "feature": "依赖图展示特征", "interaction_feature": "依赖图交互着色特征",
    "n_samples": "总样本数", "positive_rate": "阳性比例", "random_seed": "随机种子",
    "label_name": "结局列名", "positive_name": "阳性结局显示名称", "negative_name": "阴性结局显示名称",
    "id_name": "患者 ID 列名", "id_prefix": "ID 前缀", "id_width": "ID 数字补零位数", "id_start": "ID 起始编号",
    "test_size": "测试集比例", "stratify": "按结局分层划分", "split_seed": "数据划分随机种子",
    "random_state": "模型随机种子", "max_iter": "最大迭代次数", "solver": "优化求解器",
    "C": "正则化强度倒数 C", "tol": "收敛容差", "fit_intercept": "拟合截距", "penalty": "正则化方式",
    "l1_ratio": "ElasticNet 的 L1 比例", "class_weight": "类别权重", "threshold": "阳性分类阈值",
    "background_max_samples": "SHAP 背景样本上限", "background_seed": "背景抽样随机种子",
    "protective_feature": "默认保护因素展示特征", "sample_index": "局部解释样本索引（从 0 开始）",
    "dpi": "图片清晰度（DPI）", "formats": "图片导出格式", "mean": "均值", "std": "标准差",
    "min": "下限（clip）", "max": "上限（clip）", "digits": "保留小数位数", "transform": "数值处理方式",
    "positive_p": "阳性组取第二个编码的概率", "negative_p": "阴性组取第二个编码的概率",
}

OPTIONS = {
    "solver": [(v, v) for v in ["lbfgs", "liblinear", "newton-cg", "newton-cholesky", "sag", "saga"]],
    "penalty": [("L2 正则化", "l2"), ("L1 正则化", "l1"), ("ElasticNet", "elasticnet"), ("无正则化", "none")],
    "class_weight": [("不加权", "none"), ("按类别频数平衡", "balanced")],
    "transform": [("向零取整（原始 astype(int)）", "int"), ("四舍五入", "round"), ("保留原始小数", "none")],
    "title_weight": [("常规", "normal"), ("粗体", "bold")],
}


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(widget)
    return area


class ColorField(QWidget):
    def __init__(self, value):
        super().__init__()
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.text = QLineEdit(str(value)); self.text.setMinimumWidth(105)
        self.button = QPushButton(); self.button.setFixedSize(34, 30)
        layout.addWidget(self.button); layout.addWidget(self.text)
        self.button.clicked.connect(self.pick)
        self.text.textChanged.connect(self.repaint_swatch)
        self.repaint_swatch()

    def repaint_swatch(self):
        color = QColor(self.text.text())
        self.button.setStyleSheet(f"background:{color.name() if color.isValid() else '#FFFFFF'};border:1px solid #CBD5E1;border-radius:6px")

    def pick(self):
        color = QColorDialog.getColor(QColor(self.text.text()), self, "选择颜色")
        if color.isValid(): self.text.setText(color.name().upper())

    def value(self):
        if not QColor(self.text.text()).isValid():
            raise ValueError(f"无效颜色：{self.text.text()}")
        return self.text.text()


class FileField(QWidget):
    def __init__(self, value):
        super().__init__()
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.text = QLineEdit(value or ""); self.text.setPlaceholderText("留空使用已安装字体或内置中文字体")
        button = QPushButton("选择…"); button.setFixedWidth(65)
        layout.addWidget(self.text); layout.addWidget(button)
        button.clicked.connect(self.pick)

    def pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择字体", "", "字体 (*.ttf *.otf *.ttc)")
        if path: self.text.setText(path)

    def value(self): return self.text.text().strip() or None


class ValueField(QWidget):
    """根据配置类型生成控件，避免参数只能在 JSON 中编辑。"""
    def __init__(self, key, value, features=()):
        super().__init__()
        self.key, self.initial = key, value
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.percent = key in ("positive_rate", "test_size", "positive_p", "negative_p")
        if key.endswith("color") or key in ("background", "positive_light", "negative_light"):
            self.editor = ColorField(value)
        elif key == "font_file":
            self.editor = FileField(value)
        elif key == "font_family":
            from PySide6.QtGui import QFontDatabase
            self.editor = QFontComboBox()
            available=set(QFontDatabase.families())
            chosen=next((family for family in value if family in available),self.editor.currentFont().family())
            self.editor.setCurrentFont(QFont(chosen))
            self._font_edited=False
            self.editor.activated.connect(lambda _:setattr(self,"_font_edited",True))
            self.editor.currentFontChanged.connect(lambda _:setattr(self,"_font_edited",True))
        elif key == "formats":
            self.editor = QWidget(); boxes = QHBoxLayout(self.editor); boxes.setContentsMargins(0, 0, 0, 0)
            self.format_boxes = {}
            for fmt in ("png", "svg", "pdf"):
                box = QCheckBox(fmt.upper()); box.setChecked(fmt in value)
                boxes.addWidget(box); self.format_boxes[fmt] = box
        elif key in ("feature", "interaction_feature", "protective_feature"):
            self.editor = QComboBox(); self.editor.setEditable(True)
            self.editor.addItem("自动选择 / 无交互着色", None)
            for name in features: self.editor.addItem(name, name)
            index = self.editor.findData(value)
            if index >= 0: self.editor.setCurrentIndex(index)
            elif value: self.editor.setEditText(str(value))
        elif key in OPTIONS or key.endswith("style"):
            self.editor = QComboBox()
            for label, data in OPTIONS.get(key, [("实线", "-"), ("虚线", "--"), ("点线", ":"), ("点划线", "-.")]):
                self.editor.addItem(label, data)
            self.editor.setCurrentIndex(max(0, self.editor.findData(value)))
        elif isinstance(value, bool):
            self.editor = QCheckBox("启用"); self.editor.setChecked(value)
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            self.editor = QWidget(); row = QHBoxLayout(self.editor); row.setContentsMargins(0, 0, 0, 0)
            self.pair = []
            for i, item in enumerate(value):
                field = QDoubleSpinBox(); field.setRange(-1e6, 1e6); field.setDecimals(3); field.setValue(float(item))
                field.setKeyboardTracking(False); row.addWidget(field); self.pair.append(field)
                if i == 0: row.addWidget(QLabel("×" if key == "figsize" else "至"))
        elif isinstance(value, int) and key not in ("mean", "std", "min", "max"):
            if "seed" in key or key == "random_state":
                self.editor = QLineEdit(str(value)); self.editor.setPlaceholderText("0～4294967295")
            else:
                self.editor = QSpinBox(); self.editor.setRange(0, 1000000); self.editor.setValue(value)
                self.editor.setKeyboardTracking(False)
        elif isinstance(value, float) or key in ("mean", "std", "min", "max"):
            self.editor = QDoubleSpinBox(); self.editor.setDecimals(6)
            self.editor.setRange(-1e9, 1e9)
            if self.percent:
                self.editor.setRange(0, 100); self.editor.setSuffix(" %")
            elif "alpha" in key or key in ("l1_ratio", "threshold", "contribution_threshold"):
                self.editor.setRange(0, 1); self.editor.setSingleStep(.05)
            else: self.editor.setSingleStep(.1)
            self.editor.setValue(value*100 if self.percent else value)
            self.editor.setKeyboardTracking(False)
        else:
            self.editor = QLineEdit("" if value is None else str(value))
        layout.addWidget(self.editor)
        self.setMinimumWidth(240)
        self.setMaximumWidth(760)

    def value(self):
        editor, key = self.editor, self.key
        if isinstance(editor, (ColorField, FileField)): return editor.value()
        if key == "font_family":
            if not self._font_edited:return list(self.initial)
            selected = editor.currentFont().family()
            return list(dict.fromkeys([selected, *self.initial[1:], "Noto Sans CJK SC", "DejaVu Sans"]))
        if key == "formats": return [fmt for fmt, box in self.format_boxes.items() if box.isChecked()]
        if key in ("feature", "interaction_feature", "protective_feature"):
            if editor.currentIndex() == 0 and editor.currentText() == editor.itemText(0): return None
            return editor.currentText().strip() or None
        if isinstance(editor, QComboBox): return editor.currentData()
        if isinstance(editor, QCheckBox): return editor.isChecked()
        if hasattr(self, "pair"):
            values=[field.value() for field in self.pair]
            if key == "values":
                values=[int(value) if value.is_integer() else value for value in values]
            return values
        if isinstance(editor, QDoubleSpinBox): return editor.value()/100 if self.percent else editor.value()
        if isinstance(editor, QSpinBox): return editor.value()
        if "seed" in key or key == "random_state":
            try: return int(editor.text())
            except ValueError: raise ValueError("随机种子必须是整数。")
        return editor.text()


class ParamForm(QWidget):
    def __init__(self, values, features=(), labels=None):
        super().__init__()
        self.fields = {}
        self.form = QFormLayout(self)
        self.form.setContentsMargins(18, 18, 18, 18)
        self.form.setVerticalSpacing(14)
        self.form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for key, value in values.items():
            field = ValueField(key, value, features)
            self.fields[key] = field
            self.form.addRow((labels or {}).get(key, LABELS.get(key, key)), field)

    def values(self): return {key: field.value() for key, field in self.fields.items()}


class StyleEditor(QWidget):
    """每个公共样式字段都可在每张图中独立覆盖。"""
    def __init__(self, config, features):
        super().__init__()
        from .config import PLOT_NAMES
        self.config, self.features = config, features
        self.current, self.fields, self.overrides = None, {}, {}
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.selector = QComboBox()
        self.selector.addItem("公共样式 · 所有图的默认设置", "common")
        for key, label in PLOT_NAMES.items(): self.selector.addItem(label, key)
        layout.addWidget(self.selector)
        tip = QLabel("每张图默认继承公共设置。勾选“单独设置”后，仅对该图生效。不同图只使用适用的参数。")
        tip.setWordWrap(True); tip.setObjectName("muted"); layout.addWidget(tip)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs)
        self.selector.currentIndexChanged.connect(self.switch)
        self.switch()

    def commit(self):
        if self.current is None: return
        if self.current == "common":
            self.config["common"].update({key: f.value() for key, f in self.fields.items()})
        else:
            specific = self.config["plots"][self.current]
            for key, field in self.fields.items():
                if key not in self.config["common"] or self.overrides[key].isChecked():
                    specific[key] = field.value()
                else: specific.pop(key, None)

    def switch(self):
        self.commit()
        self.current = self.selector.currentData()
        self.fields, self.overrides = {}, {}
        while self.tabs.count():
            widget=self.tabs.widget(0); self.tabs.removeTab(0); widget.deleteLater()
        common = self.config["common"]
        specific = {} if self.current == "common" else self.config["plots"][self.current]
        merged = {**common, **specific}
        groups = {"颜色": [], "字体与文字": [], "线条与散点": [], "尺寸与布局": [], "本图参数": []}
        for key in merged:
            if key not in common: group="本图参数"
            elif key.endswith("color") or key in ("background", "positive_light", "negative_light"): group="颜色"
            elif key.startswith("font") or key in ("title_size", "label_size", "tick_size", "title_weight"): group="字体与文字"
            elif key in ("figsize", "title_pad", "xlabel_pad"): group="尺寸与布局"
            else: group="线条与散点"
            groups[group].append(key)
        for group, keys in groups.items():
            if not keys: continue
            body = QWidget(); form=QFormLayout(body); form.setContentsMargins(18,18,18,18); form.setVerticalSpacing(14)
            for key in keys:
                field=ValueField(key,merged[key],self.features); self.fields[key]=field
                if self.current != "common" and key in common:
                    row=QWidget(); box=QHBoxLayout(row); box.setContentsMargins(0,0,0,0)
                    override=QCheckBox("单独设置"); override.setChecked(key in specific)
                    field.setEnabled(override.isChecked()); override.toggled.connect(field.setEnabled)
                    self.overrides[key]=override
                    box.addWidget(field,1); box.addWidget(override)
                    form.addRow(LABELS.get(key,key),row)
                else: form.addRow(LABELS.get(key,key),field)
            self.tabs.addTab(scroll(body),group)
