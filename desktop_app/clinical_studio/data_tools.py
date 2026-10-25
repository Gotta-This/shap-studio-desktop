"""Independent category and numerical tool widgets."""
import csv
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QSpinBox, QComboBox, QRadioButton, QPlainTextEdit, QApplication, QFileDialog, QSplitter,
)
from .data_tools_engine import category_numbers, category_summary, numeric_numbers, statistics, format_values
from .widgets import scroll
from .theme import COLORS


class DistributionPreview(QWidget):
    """Native UI histogram of the generated values; does not change saved data."""
    def __init__(self):
        super().__init__(); self.values=[]; self.setMinimumHeight(120); self.setMaximumHeight(175)
        self.setAccessibleName('生成数值的实际分布')

    def paintEvent(self,event):
        if not self.values:return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        low,high=min(self.values),max(self.values);counts=[0]*12
        for value in self.values:
            counts[min(11,int((value-low)/(high-low)*12)) if high>low else 5]+=1
        peak=max(counts);w=(self.width()-36)/12;bottom=self.height()-25
        painter.setPen(QColor(COLORS['muted']));painter.drawText(8,self.height()-5,f'{low:g}')
        painter.drawText(self.width()-85,self.height()-23,77,20,Qt.AlignRight,f'{high:g}')
        painter.setPen(Qt.NoPen)
        for i,count in enumerate(counts):
            h=(bottom-12)*count/peak;painter.setBrush(QColor(COLORS['primary'] if count==peak else '#A8D4B8'))
            painter.drawRoundedRect(int(18+i*w),int(bottom-h),max(2,int(w-5)),int(h),4,4)


def split_panels(layout, left, result):
    splitter=QSplitter(Qt.Horizontal);splitter.setChildrenCollapsible(False)
    splitter.addWidget(scroll(left));splitter.addWidget(result)
    splitter.widget(0).setMinimumWidth(315);result.setMinimumWidth(360)
    splitter.setStretchFactor(0,2);splitter.setStretchFactor(1,3);splitter.setSizes([410,650])
    layout.addWidget(splitter);return splitter


class NumberWorker(QThread):
    result_ready=Signal(object)
    failed=Signal(str)
    cancelled=Signal()
    def __init__(self, options, parent=None):
        super().__init__(parent); self.options=options
    def run(self):
        from .data_tools_engine import GenerationCancelled
        try:
            values=numeric_numbers(**self.options,cancelled=self.isInterruptionRequested)
            if self.isInterruptionRequested():raise GenerationCancelled()
            self.result_ready.emit((self.options,values))
        except GenerationCancelled:self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class ResultPanel(QGroupBox):
    def __init__(self, column_name='Value', default_name='模拟数列', histogram=False):
        super().__init__('生成结果 · 可直接复制')
        self.values=[];self.digits=None;self.column_name=column_name;self.default_name=default_name;self.last_save_path=None;self.csv_r_style=False
        layout=QVBoxLayout(self)
        self.summary=QLabel('尚未生成数据');self.summary.setWordWrap(True);self.summary.setObjectName('sectionTitle');layout.addWidget(self.summary)
        self.details=QLabel('');self.details.setWordWrap(True);layout.addWidget(self.details)
        self.histogram=DistributionPreview() if histogram else None
        if self.histogram is not None:layout.addWidget(self.histogram);self.histogram.hide()
        row=QHBoxLayout();row.addWidget(QLabel('排列格式'))
        self.format=QComboBox()
        for title,value in [('每行一个数字','line'),('逗号分隔','comma'),('空格分隔','space'),('R 向量 c(...)','r')]:
            self.format.addItem(title,value)
        row.addWidget(self.format);row.addStretch();layout.addLayout(row)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setPlaceholderText('生成后的数列显示在这里，可全选复制。');layout.addWidget(self.output,1)
        row=QHBoxLayout();select=QPushButton('全选');self.copy_button=QPushButton('复制全部');self.save_button=QPushButton('保存数据…');self.copy_button.setObjectName('primary');row.addWidget(select);row.addStretch();row.addWidget(self.save_button);row.addWidget(self.copy_button);layout.addLayout(row)
        self.message=QLabel('');self.message.setWordWrap(True);layout.addWidget(self.message)
        self.format.currentIndexChanged.connect(self.render)
        select.clicked.connect(self.output.selectAll);self.copy_button.clicked.connect(self.copy);self.save_button.clicked.connect(self.save)
    def render(self):
        self.output.setPlainText(format_values(self.values,self.format.currentData(),self.digits) if self.values else '')
    def set_values(self,values,digits=None):
        self.values=values;self.digits=digits;self.message.clear();self.render()
        if self.histogram is not None:
            self.histogram.values=list(values);self.histogram.setVisible(bool(values));self.histogram.update()
    def copy(self):
        from .feedback import copy_text,notify
        if self.values:
            copy_text(self,self.output.toPlainText());self.message.setText('复制成功，已复制全部数据。')
        else:
            self.message.setText('请先生成数据。');notify(self,'尚无数据，请先生成。',success=False)

    def save(self):
        if not self.values:self.message.setText('请先生成数据。');return
        initial=str(self.last_save_path or Path.home()/'Documents'/(self.default_name+'.csv'))
        filename,kind=QFileDialog.getSaveFileName(self,'保存生成数据',initial,'CSV (*.csv);;Excel (*.xlsx)')
        if not filename:return
        path=Path(filename)
        if path.suffix.lower() not in ('.csv','.xlsx'):path=path.with_suffix('.xlsx' if 'xlsx' in kind else '.csv')
        try:
            if path.suffix.lower()=='.xlsx':
                from openpyxl import Workbook
                book=Workbook();sheet=book.active;sheet.title='生成数据';sheet.append([self.column_name])
                for value in self.values:sheet.append([value])
                sheet.freeze_panes='A2';sheet.column_dimensions['A'].width=24
                if self.digits is not None:
                    for cell in sheet['A'][1:]:cell.number_format='0'+('.'+'0'*self.digits if self.digits else '')
                book.save(path);book.close()
            else:
                with path.open('w',encoding='utf-8' if self.csv_r_style else 'utf-8-sig',newline='') as stream:
                    if self.csv_r_style:
                        csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator='\n').writerow([self.column_name])
                        csv.writer(stream,lineterminator='\n').writerows([[format_values([v])] for v in self.values])
                    else:
                        writer=csv.writer(stream);writer.writerow([self.column_name]);writer.writerows([[v] for v in self.values])
            self.last_save_path=path;self.message.setText('已保存：'+str(path))
        except Exception as exc:self.message.setText('保存失败：'+str(exc))


class CategoryTool(QWidget):
    def __init__(self):
        super().__init__();layout=QHBoxLayout(self)
        group=QGroupBox('自定义类别与数量');left=QVBoxLayout(group)
        label=QLabel('按每个数字的指定数量创建数列，再随机打乱顺序。');label.setWordWrap(True);left.addWidget(label)
        self.table=QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['数字','数量']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);left.addWidget(self.table,1)
        row=QHBoxLayout();add=QPushButton('＋ 添加数字');remove=QPushButton('删除选中行');row.addWidget(add);row.addWidget(remove);left.addLayout(row)
        self.seed=QLineEdit('12');self.seed.setPlaceholderText('留空，每次生成新排列');form=QFormLayout();form.addRow('随机种子（可选）',self.seed);left.addLayout(form)
        hint=QLabel('同样参数和种子可复现；与 R 3.6 及以上默认 set.seed / sample 一致。\n每行一个数值，可直接复制至 Excel。总数量上限 100,000。');hint.setWordWrap(True);left.addWidget(hint)
        self.generate_button=QPushButton('生成随机数列');self.generate_button.setObjectName('primary');left.addWidget(self.generate_button)
        self.error=QLabel('');self.error.setWordWrap(True);self.error.setStyleSheet('color:#B34334');left.addWidget(self.error)
        self.code=QLabel('');self.code.setWordWrap(True);left.addWidget(self.code)
        self.result=ResultPanel('RandomValue','random_numbers_28_93_57');self.result.csv_r_style=True;self.splitter=split_panels(layout,group,self.result)
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

    def original_report(self):
        from collections import Counter
        values=self.result.values
        head='\n'.join(f'{i+1:>3} {format_values([v])}' for i,v in enumerate(values[:10]))
        counts=Counter(values)
        table='\n'.join(f'{format_values([v])}: {counts[v]}' for v in sorted(counts))
        return ('前10行数据:\n    RandomValue\n'+head+'\n\n数据结构:\n'
            +f"'data.frame': {len(values)} obs. of 1 variable:\n $ RandomValue: num "
            +' '.join(format_values([v]) for v in values[:10])+'\n\n各类别计数:\n'+table
            +f'\n\n文件包含 {len(values)} 个观测值\n\n完整数列（每行一个，无行号）:\n'+format_values(values))


class NumericTool(QWidget):
    def __init__(self):
        super().__init__();self.worker=None;layout=QHBoxLayout(self)
        group=QGroupBox('模拟数据参数');left=QVBoxLayout(group);fields=QGroupBox();form=QFormLayout(fields)
        self.mean=QLineEdit('27.92');self.sd=QLineEdit('14.87');self.n=QSpinBox();self.n.setRange(2,5000);self.n.setValue(70)
        self.digits=QComboBox();self.digits.addItems(['0','1','2','3','4'])
        self.lower=QLineEdit('7');self.upper=QLineEdit('50')
        self.seed=QLineEdit();self.seed.setPlaceholderText('留空，每次生成新数据')
        for field in [self.lower,self.upper]:field.setPlaceholderText('不限制（可留空）')
        for title,widget in [('均数',self.mean),('标准差',self.sd),('例数',self.n),('小数点后位数',self.digits),('最小值',self.lower),('最大值',self.upper)]:form.addRow(title,widget)
        form.addRow('随机种子（可选）',self.seed)
        form.setLabelAlignment(Qt.AlignRight);left.addWidget(fields)
        modes=QHBoxLayout();self.target=QRadioButton('按均数标准差');self.range_mode=QRadioButton('按最大最小值');self.target.setChecked(True)
        modes.addWidget(self.target);modes.addWidget(self.range_mode);left.addLayout(modes)
        self.target.toggled.connect(self.mode_changed)
        self.generate_button=QPushButton('生成模拟数据');self.generate_button.setObjectName('primary');left.addWidget(self.generate_button)
        self.stop_button=QPushButton('停止');self.stop_button.setEnabled(False);left.addWidget(self.stop_button)
        self.stop_button.clicked.connect(self.stop_generation)
        self.error=QLabel('');self.error.setWordWrap(True);self.error.setStyleSheet('color:#B34334');left.addWidget(self.error)
        note=QLabel('样本标准差使用 n−1。统计目标为近似匹配，结果不保证正态分布。\n\n上下限可留空；按范围均匀随机模式需填写两个边界。\n\n生成结果仅为模拟数据，请核对实际统计值与偏差。');note.setWordWrap(True);left.addWidget(note);left.addStretch()
        self.result=ResultPanel('Value','均数标准差模拟数据',histogram=True);self.splitter=split_panels(layout,group,self.result)
        self.generate_button.clicked.connect(self.generate)
    def mode_changed(self):
        self.mean.setEnabled(self.target.isChecked());self.sd.setEnabled(self.target.isChecked())
    def generate(self):
        if self.is_running():return
        try:
            options=dict(n=self.n.value(),digits=int(self.digits.currentText()),mean=float(self.mean.text()) if self.target.isChecked() else 0.,sd=float(self.sd.text()) if self.target.isChecked() else 0.,lower=float(self.lower.text()) if self.lower.text().strip() else None,upper=float(self.upper.text()) if self.upper.text().strip() else None,mode='target' if self.target.isChecked() else 'range')
            options['seed']=self.seed.text() if self.seed.text().strip() else None
        except ValueError:self.error.setText('请填写有效数字；上下限可以留空。');return
        self.error.clear();self.generate_button.setEnabled(False);self.generate_button.setText('正在生成…')
        self.stop_button.setEnabled(True)
        self.worker=NumberWorker(options,self);self.worker.result_ready.connect(self.show_result);self.worker.failed.connect(self.error.setText);self.worker.cancelled.connect(self.stopped);self.worker.finished.connect(self.finished);self.worker.start()
    def stop_generation(self):
        if self.is_running():self.worker.requestInterruption();self.stop_button.setEnabled(False)
    def stopped(self):
        self.result.message.setText('已停止生成。'+('上次结果已保留。' if self.result.values else ''))
    def show_result(self,payload):
        if self.worker and self.worker.isInterruptionRequested():self.stopped();return
        options,values=payload;self.result_options=dict(options);mean,sd=statistics(values);self.result.set_values(values,options['digits'])
        self.result.summary.setText(f'实际均数：{mean:.4f} · 样本标准差：{sd:.4f} · 例数：{len(values)}')
        detail=f'实际范围：{min(values):g} ～ {max(values):g}'
        if options['mode']=='target':detail+=f"\n均数偏差：{mean-options['mean']:+.4f} · 标准差偏差：{sd-options['sd']:+.4f}"
        else:detail+='\n均匀随机抽样，不约束均数和标准差。'
        self.result.details.setText(detail);self.result.message.setText('已生成，请核对实际统计结果。')
    def finished(self):
        self.generate_button.setEnabled(True);self.generate_button.setText('生成模拟数据');self.stop_button.setEnabled(False)
    def is_running(self):
        return self.worker is not None and self.worker.isRunning()


