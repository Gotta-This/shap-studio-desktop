"""Native offline tools for category shuffling and statistical simulation."""
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QSpinBox, QComboBox, QRadioButton, QPlainTextEdit, QTabWidget, QApplication,
)
from .data_tools_engine import category_numbers, category_summary, numeric_numbers, statistics, format_values
from .widgets import scroll


class NumberWorker(QThread):
    result_ready=Signal(object)
    failed=Signal(str)
    def __init__(self, options, parent=None):
        super().__init__(parent); self.options=options
    def run(self):
        try:
            self.result_ready.emit((self.options,numeric_numbers(**self.options)))
        except Exception as exc:
            self.failed.emit(str(exc))


class ResultPanel(QGroupBox):
    def __init__(self):
        super().__init__('生成结果 · 可直接复制')
        self.values=[];self.digits=None
        layout=QVBoxLayout(self)
        self.summary=QLabel('尚未生成数据');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.details=QLabel('');self.details.setWordWrap(True);layout.addWidget(self.details)
        row=QHBoxLayout();row.addWidget(QLabel('排列格式'))
        self.format=QComboBox()
        for title,value in [('每行一个数字','line'),('逗号分隔','comma'),('空格分隔','space'),('R 向量 c(...)','r')]:
            self.format.addItem(title,value)
        row.addWidget(self.format);row.addStretch();layout.addLayout(row)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setPlaceholderText('生成后的数列显示在这里，可全选复制。');layout.addWidget(self.output,1)
        row=QHBoxLayout();select=QPushButton('全选');copy=QPushButton('复制全部');copy.setObjectName('primary');row.addWidget(select);row.addStretch();row.addWidget(copy);layout.addLayout(row)
        self.message=QLabel('');self.message.setWordWrap(True);layout.addWidget(self.message)
        self.format.currentIndexChanged.connect(self.render)
        select.clicked.connect(self.output.selectAll);copy.clicked.connect(self.copy)
    def render(self):
        self.output.setPlainText(format_values(self.values,self.format.currentData(),self.digits) if self.values else '')
    def set_values(self,values,digits=None):
        self.values=values;self.digits=digits;self.message.clear();self.render()
    def copy(self):
        if self.values:
            QApplication.clipboard().setText(self.output.toPlainText());self.message.setText('已复制全部数据。')
        else:self.message.setText('请先生成数据。')


class CategoryTool(QWidget):
    def __init__(self):
        super().__init__();layout=QHBoxLayout(self)
        group=QGroupBox('自定义类别与数量');left=QVBoxLayout(group)
        label=QLabel('按每个数字的指定数量创建数列，再随机打乱顺序。');label.setWordWrap(True);left.addWidget(label)
        self.table=QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['数字','数量']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);left.addWidget(self.table,1)
        row=QHBoxLayout();add=QPushButton('＋ 添加数字');remove=QPushButton('删除选中行');row.addWidget(add);row.addWidget(remove);left.addLayout(row)
        self.seed=QLineEdit('12');self.seed.setPlaceholderText('留空，每次生成新排列');form=QFormLayout();form.addRow('随机种子（可选）',self.seed);left.addLayout(form)
        hint=QLabel('同样参数和种子可复现；与 HTML 第一个工具一致。\n与 R 相同种子的具体排列不同。总数量上限 100,000。');hint.setWordWrap(True);left.addWidget(hint)
        self.generate_button=QPushButton('生成随机数列');self.generate_button.setObjectName('primary');left.addWidget(self.generate_button)
        self.error=QLabel('');self.error.setWordWrap(True);self.error.setStyleSheet('color:#B34334');left.addWidget(self.error)
        self.code=QLabel('');self.code.setWordWrap(True);left.addWidget(self.code)
        self.result=ResultPanel();layout.addWidget(group,1);layout.addWidget(self.result,2)
        add.clicked.connect(lambda:self.add_row());remove.clicked.connect(self.remove_row);self.generate_button.clicked.connect(self.generate)
        self.add_row('1','28');self.add_row('0','93');self.generate()
    def add_row(self,value='',count=''):
        row=self.table.rowCount();self.table.insertRow(row);self.table.setItem(row,0,QTableWidgetItem(value));self.table.setItem(row,1,QTableWidgetItem(count))
    def remove_row(self):
        for row in sorted({x.row() for x in self.table.selectedIndexes()},reverse=True):
            if self.table.rowCount()>1:self.table.removeRow(row)
    def generate(self):
        try:
            categories=[]
            for row in range(self.table.rowCount()):
                v=self.table.item(row,0);c=self.table.item(row,1)
                if v is None or c is None:raise ValueError('请填写每行数字与数量。')
                categories.append((float(v.text()),int(c.text())))
            values=category_numbers(categories,self.seed.text());self.error.clear()
            self.result.set_values(values);self.result.summary.setText(f'总观测数：{len(values)} · 类别数：{len(set(values))}')
            self.result.details.setText(category_summary(values))
            self.code.setText('numbers <- c('+', '.join(f'rep({v:g}, {n})' for v,n in categories)+')')
        except (ValueError,OverflowError) as exc:self.error.setText(str(exc))


class NumericTool(QWidget):
    def __init__(self):
        super().__init__();self.worker=None;layout=QHBoxLayout(self)
        group=QGroupBox('模拟数据参数');left=QVBoxLayout(group);fields=QGroupBox();form=QFormLayout(fields)
        self.mean=QLineEdit('27.92');self.sd=QLineEdit('14.87');self.n=QSpinBox();self.n.setRange(2,5000);self.n.setValue(70)
        self.digits=QComboBox();self.digits.addItems(['0','1','2','3','4'])
        self.lower=QLineEdit('7');self.upper=QLineEdit('50')
        for field in [self.lower,self.upper]:field.setPlaceholderText('不限制（可留空）')
        for title,widget in [('均数',self.mean),('标准差',self.sd),('例数',self.n),('小数点后位数',self.digits),('最小值',self.lower),('最大值',self.upper)]:form.addRow(title,widget)
        form.setLabelAlignment(Qt.AlignRight);left.addWidget(fields)
        modes=QHBoxLayout();self.target=QRadioButton('按均数标准差');self.range_mode=QRadioButton('按最大最小值');self.target.setChecked(True)
        modes.addWidget(self.target);modes.addWidget(self.range_mode);left.addLayout(modes)
        self.target.toggled.connect(self.mode_changed)
        self.generate_button=QPushButton('生成模拟数据');self.generate_button.setObjectName('primary');left.addWidget(self.generate_button)
        self.error=QLabel('');self.error.setWordWrap(True);self.error.setStyleSheet('color:#B34334');left.addWidget(self.error)
        note=QLabel('样本标准差使用 n−1。统计目标为近似匹配，结果不保证正态分布。\n\n上下限可留空；按范围均匀随机模式需填写两个边界。\n\n生成结果仅为模拟数据，请核对实际统计值与偏差。');note.setWordWrap(True);left.addWidget(note);left.addStretch()
        self.result=ResultPanel();layout.addWidget(group,1);layout.addWidget(self.result,2)
        self.generate_button.clicked.connect(self.generate)
    def mode_changed(self):
        self.mean.setEnabled(self.target.isChecked());self.sd.setEnabled(self.target.isChecked())
    def generate(self):
        if self.is_running():return
        try:
            options=dict(n=self.n.value(),digits=int(self.digits.currentText()),mean=float(self.mean.text()) if self.target.isChecked() else 0.,sd=float(self.sd.text()) if self.target.isChecked() else 0.,lower=float(self.lower.text()) if self.lower.text().strip() else None,upper=float(self.upper.text()) if self.upper.text().strip() else None,mode='target' if self.target.isChecked() else 'range')
        except ValueError:self.error.setText('请填写有效数字；上下限可以留空。');return
        self.error.clear();self.generate_button.setEnabled(False);self.generate_button.setText('正在生成…')
        self.worker=NumberWorker(options,self);self.worker.result_ready.connect(self.show_result);self.worker.failed.connect(self.error.setText);self.worker.finished.connect(self.finished);self.worker.start()
    def show_result(self,payload):
        options,values=payload;mean,sd=statistics(values);self.result.set_values(values,options['digits'])
        self.result.summary.setText(f'实际均数：{mean:.4f} · 样本标准差：{sd:.4f} · 例数：{len(values)}')
        detail=f'实际范围：{min(values):g} ～ {max(values):g}'
        if options['mode']=='target':detail+=f"\n均数偏差：{mean-options['mean']:+.4f} · 标准差偏差：{sd-options['sd']:+.4f}"
        else:detail+='\n均匀随机抽样，不约束均数和标准差。'
        self.result.details.setText(detail);self.result.message.setText('已生成，请核对实际统计结果。')
    def finished(self):
        self.generate_button.setEnabled(True);self.generate_button.setText('生成模拟数据')
    def is_running(self):
        return self.worker is not None and self.worker.isRunning()


class DataToolsPage(QWidget):
    def __init__(self):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        note=QLabel('独立数据工具 · 无需运行模型分析 · 参数与结果在切换工具时保留');note.setWordWrap(True);layout.addWidget(note)
        self.tabs=QTabWidget();self.category=CategoryTool();self.numeric=NumericTool()
        self.tabs.addTab(scroll(self.category),'自定义类别数列');self.tabs.addTab(scroll(self.numeric),'均数 / 标准差模拟数据');layout.addWidget(self.tabs,1)
    def is_running(self):return self.numeric.is_running()
