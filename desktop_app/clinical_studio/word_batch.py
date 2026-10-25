"""Native Word-to-synthetic-case workflow in the existing data tools page."""
from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)
from .widgets import scroll
from .word_batch_engine import (
    GROUPS, default_batch_config, read_word, generate_batch, export_batch, validate_batch,
)


def item(value):
    return QTableWidgetItem('' if value is None else str(value))


def button(text, action, layout):
    b=QPushButton(text);b.clicked.connect(action);layout.addWidget(b)
    return b


class EditableRows(QGroupBox):
    def __init__(self,title,headers,rows):
        super().__init__(title)
        layout=QVBoxLayout(self)
        self.table=QTableWidget(0,len(headers));self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(150);layout.addWidget(self.table)
        actions=QHBoxLayout();button('＋ 添加',lambda:self.add(['']*len(headers)),actions)
        button('删除选中行',self.remove,actions);actions.addStretch();layout.addLayout(actions)
        for row in rows:self.add(row)
    def add(self,values):
        i=self.table.rowCount();self.table.insertRow(i)
        for j,v in enumerate(values):self.table.setItem(i,j,item(v))
    def remove(self):
        for i in sorted({v.row() for v in self.table.selectedIndexes()},reverse=True):self.table.removeRow(i)
    def values(self):
        return [[self.table.item(i,j).text().strip() if self.table.item(i,j) else '' for j in range(self.table.columnCount())] for i in range(self.table.rowCount())]


class GroupSettings(QWidget):
    def __init__(self,config):
        super().__init__();self.name=config['name'];layout=QVBoxLayout(self)
        group=QGroupBox('组别与分类比例');form=QFormLayout(group);self.fields={}
        for key,label,value in [('n','例数（2～5000）',config['n']),('male','男性占比 %（其余为女性）',config['male']),('light','轻度占比 %',config['severity'][0]),('medium','中度占比 %',config['severity'][1]),('severe','重度占比 %',config['severity'][2]),('effective','有效占比 %',config['effective']),('recurrence','复发占比 %（全组为分母）',config['recurrence'])]:
            field=QLineEdit(str(value));self.fields[key]=field;form.addRow(label,field)
        layout.addWidget(group)
        note=QLabel('年龄与病程的区间均包含两端，区间不能重叠；每类配置的占比须合计 100%。\n按比例分配整数人数后随机打乱；例如 70 例的 50% 会精确分配为 35 例。')
        note.setWordWrap(True);layout.addWidget(note)
        self.age=EditableRows('年龄区间（岁，整数）',['下限','上限','占比 %'],[[r['lower'],r['upper'],r['percent']] for r in config['age']]);layout.addWidget(self.age)
        self.course=EditableRows('病程区间',['下限','上限','占比 %'],[[r['lower'],r['upper'],r['percent']] for r in config['course']]);layout.addWidget(self.course)
        row=QHBoxLayout();row.addWidget(QLabel('病程小数位'));self.course_digits=QSpinBox();self.course_digits.setRange(0,4);self.course_digits.setValue(config['course_digits']);row.addWidget(self.course_digits);row.addStretch();layout.addLayout(row)
        self.extent=EditableRows('病变范围',['类别名称','占比 %'],[[r['label'],r['percent']] for r in config['extent']]);layout.addWidget(self.extent)
        layout.addStretch()
    def values(self):
        f={k:v.text().strip() for k,v in self.fields.items()}
        def ranges(editor):
            return [dict(lower=float(a),upper=float(b),percent=float(c)) for a,b,c in editor.values()]
        return dict(name=self.name,n=int(f['n']),male=float(f['male']),severity=[float(f[k]) for k in ('light','medium','severe')],effective=float(f['effective']),recurrence=float(f['recurrence']),age=ranges(self.age),course=ranges(self.course),course_digits=self.course_digits.value(),extent=[dict(label=a,percent=float(b)) for a,b in self.extent.values()])


class BatchWorker(QThread):
    ready=Signal(object)
    failed=Signal(str)
    progress=Signal(str)
    def __init__(self,config,parent=None):
        super().__init__(parent);self.config=deepcopy(config)
    def run(self):
        try:self.ready.emit(generate_batch(self.config,self.progress.emit,self.isInterruptionRequested))
        except Exception as exc:self.failed.emit(str(exc))


class ExportWorker(QThread):
    ready=Signal(str)
    failed=Signal(str)
    def __init__(self,result,path,parent=None):
        super().__init__(parent);self.result=result;self.path=path
    def run(self):
        try:self.ready.emit(str(export_batch(self.result,self.path)))
        except Exception as exc:self.failed.emit('导出失败：'+str(exc))


class WordBatchTool(QWidget):
    HEADERS=['表','指标列名','分组','均数','标准差','小数位','下限（可空）','上限（可空）','数值类型','Word 原文']
    KEYS=['table','name','group','mean','sd','digits','lower','upper','parity','raw']
    def __init__(self):
        super().__init__();self.worker=None;self.result=None;self.source='';self.config=default_batch_config()
        layout=QVBoxLayout(self)
        intro=QLabel('导入 Word → 核对指标和基本资料 → 生成模拟病例 → 导出 Excel。各组均数／标准差独立近似匹配，不还原原始病例或前后相关性。')
        intro.setWordWrap(True);layout.addWidget(intro)
        row=QHBoxLayout();self.import_button=button('导入 Word（.docx）',self.pick_word,row)
        self.load_button=button('载入配置',self.load_config,row);self.save_button=button('保存配置',self.save_config,row);row.addStretch();layout.addLayout(row)
        self.source_label=QLabel('尚未导入 Word；也可在指标页手动添加。');self.source_label.setWordWrap(True);layout.addWidget(self.source_label)
        self.pages=QTabWidget();layout.addWidget(self.pages,1)
        basics=QWidget();base_layout=QVBoxLayout(basics);form=QFormLayout()
        self.seed=QLineEdit('12');self.unit=QLineEdit('月');form.addRow('随机种子（可重复生成）',self.seed);form.addRow('病程单位',self.unit);base_layout.addLayout(form)
        self.group_tabs=QTabWidget();base_layout.addWidget(self.group_tabs);self.group_editors=[]
        self.pages.addTab(basics,'1 · 基本资料与比例')
        self.set_groups(self.config['groups'])
        metrics=QWidget();ml=QVBoxLayout(metrics)
        tip=QLabel('每个指标须有两组配置。小数位 0～4；奇数／偶数须为 0 位。上下限非必填。表头、均数和标准差均可修改；空白统计值必须补全。')
        tip.setWordWrap(True);ml.addWidget(tip)
        self.metrics=QTableWidget(0,len(self.HEADERS));self.metrics.setHorizontalHeaderLabels(self.HEADERS)
        self.metrics.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i in range(len(self.HEADERS)):self.metrics.setColumnWidth(i,135 if i in (1,9) else 95)
        self.metrics.setColumnWidth(1,220);self.metrics.setColumnWidth(0,45);ml.addWidget(self.metrics,1)
        row=QHBoxLayout();button('＋ 添加指标（两组）',self.add_indicator,row);button('删除选中的指标（两组）',self.remove_indicator,row);row.addStretch();ml.addLayout(row)
        self.pages.addTab(metrics,'2 · Word 指标核对')
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setPlainText('导入后显示识别报告。基本资料的初始比例为示例，请核对后生成。')
        self.pages.addTab(self.log,'3 · 识别报告')
        preview=QWidget();pl=QVBoxLayout(preview)
        self.preview_note=QLabel('尚未生成数据。');self.preview_note.setWordWrap(True);pl.addWidget(self.preview_note)
        self.preview=QTableWidget();self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers);pl.addWidget(self.preview,1)
        self.audit=QPlainTextEdit();self.audit.setReadOnly(True);self.audit.setMaximumHeight(160);pl.addWidget(self.audit)
        row=QHBoxLayout();self.copy_button=button('复制完整数据（含表头）',self.copy_data,row);self.export_button=button('导出 Excel',self.export_data,row);row.addStretch();pl.addLayout(row)
        self.copy_button.setEnabled(False);self.export_button.setEnabled(False)
        self.pages.addTab(preview,'4 · 数据预览与导出')
        row=QHBoxLayout();self.generate_button=button('生成模拟病例数据',self.generate,row);self.generate_button.setObjectName('primary')
        self.cancel_button=button('取消生成',self.cancel,row);self.cancel_button.setEnabled(False);row.addStretch();layout.addLayout(row)
        self.message=QLabel('');self.message.setWordWrap(True);layout.addWidget(self.message)
    def set_groups(self,groups):
        while self.group_tabs.count():
            w=self.group_tabs.widget(0);self.group_tabs.removeTab(0);w.deleteLater()
        self.group_editors=[GroupSettings(g) for g in groups]
        for editor in self.group_editors:self.group_tabs.addTab(scroll(editor),editor.name)
    def set_indicators(self,specs):
        self.metrics.setRowCount(0)
        for spec in specs:self.append_spec(spec)
    def append_spec(self,spec):
        i=self.metrics.rowCount();self.metrics.insertRow(i)
        for j,key in enumerate(self.KEYS):
            if key in ('group','parity'):
                combo=QComboBox()
                for title,value in ([(g,g) for g in GROUPS] if key=='group' else [('任意数值','any'),('奇数','odd'),('偶数','even')]):combo.addItem(title,value)
                combo.setCurrentIndex(max(0,combo.findData(spec.get(key))));self.metrics.setCellWidget(i,j,combo)
            else:self.metrics.setItem(i,j,item(spec.get(key,'')))
    def add_indicator(self):
        existing={self.metrics.item(i,1).text() for i in range(self.metrics.rowCount()) if self.metrics.item(i,1)}
        k=1
        while f'自定义指标{k}' in existing:k+=1
        for group in GROUPS:self.append_spec(dict(table=0,name=f'自定义指标{k}',group=group,mean=10,sd=2,digits=2,lower=None,upper=None,parity='any',raw='手工配置'))
    def remove_indicator(self):
        names={self.metrics.item(i.row(),1).text() for i in self.metrics.selectedIndexes() if self.metrics.item(i.row(),1)}
        for i in reversed(range(self.metrics.rowCount())):
            if self.metrics.item(i,1).text() in names:self.metrics.removeRow(i)
    def get_config(self):
        specs=[]
        try:
            for i in range(self.metrics.rowCount()):
                spec={}
                for j,key in enumerate(self.KEYS):
                    widget=self.metrics.cellWidget(i,j)
                    value=widget.currentData() if widget else (self.metrics.item(i,j).text().strip() if self.metrics.item(i,j) else '')
                    if key in ('table','digits'):value=int(value)
                    elif key in ('mean','sd'):value=float(value)
                    elif key in ('lower','upper'):value=float(value) if value else None
                    spec[key]=value
                specs.append(spec)
            config=dict(version=1,seed=int(self.seed.text().strip()),source=self.source,course_unit=self.unit.text().strip(),groups=[e.values() for e in self.group_editors],indicators=specs)
        except (ValueError,TypeError) as exc:raise ValueError('请补全有效数字；例数、小数位和种子须为整数，只有上下限可留空。') from exc
        validate_batch(config)
        return config
    def pick_word(self):
        path,_=QFileDialog.getOpenFileName(self,'选择 Word 汇总表','','Word (*.docx)')
        if path:self.import_word(path)
    def import_word(self,path):
        if self.is_running():return
        try:
            imported=read_word(path)
            # Preserve users' baseline settings across imports; update only table-derived sizes/rates.
            try:groups=[editor.values() for editor in self.group_editors]
            except ValueError:groups=default_batch_config()['groups']
            for g in groups:
                if g['name'] in imported.group_sizes:g['n']=imported.group_sizes[g['name']]
                for key,rate in imported.outcome_rates.get(g['name'],{}).items():
                    g['effective' if key=='总有效率' else 'recurrence']=rate
            self.set_groups(groups);self.set_indicators(imported.indicators);self.source=imported.source
            self.source_label.setText(f'来源：{imported.source}')
            self.log.setPlainText('\n'.join(imported.messages))
            self.message.setText(f'读取 {imported.table_count} 张表，识别 {len(imported.indicators)//2} 个指标。请核对两组配置；基本资料区间和比例不会从正文自动推断。')
            self.pages.setCurrentIndex(1)
        except Exception as exc:self.message.setText('导入失败：'+str(exc))
    def load_config(self):
        path,_=QFileDialog.getOpenFileName(self,'载入批量工具配置','','JSON (*.json)')
        if not path:return
        try:
            config=json.loads(Path(path).read_text(encoding='utf-8'));validate_batch(config)
            self.set_groups(config['groups']);self.set_indicators(config['indicators']);self.seed.setText(str(config['seed']));self.unit.setText(config.get('course_unit','月'));self.source=config.get('source','');self.source_label.setText('配置来源：'+path);self.message.setText('已载入配置。已有生成结果保持原样，重新生成后更新。')
        except Exception as exc:self.message.setText('载入失败：'+str(exc))
    def save_config(self):
        try:config=self.get_config()
        except ValueError as exc:self.message.setText(str(exc));return
        path,_=QFileDialog.getSaveFileName(self,'保存批量工具配置','批量模拟配置.json','JSON (*.json)')
        if not path:return
        if not path.lower().endswith('.json'):path+='.json'
        try:Path(path).write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');self.message.setText('配置已保存：'+path)
        except Exception as exc:self.message.setText('保存失败：'+str(exc))
    def generate(self):
        if self.is_running():return
        try:config=self.get_config()
        except ValueError as exc:self.message.setText(str(exc));return
        self.worker=BatchWorker(config,self);self.worker.ready.connect(self.show_result);self.worker.failed.connect(self.message.setText);self.worker.progress.connect(lambda s:self.message.setText('正在生成：'+s));self.worker.finished.connect(self.finished)
        self.generate_button.setEnabled(False);self.cancel_button.setEnabled(True);self.import_button.setEnabled(False);self.load_button.setEnabled(False);self.save_button.setEnabled(False)
        self.message.setText('正在生成…');self.worker.start()
    def cancel(self):
        if self.is_running():self.worker.requestInterruption();self.cancel_button.setEnabled(False);self.message.setText('正在取消；完成当前指标后停止。')
    def finished(self):
        for control in [self.generate_button,self.import_button,self.load_button,self.save_button]:control.setEnabled(True)
        self.cancel_button.setEnabled(False)
    def show_result(self,result):
        self.result=result
        self.preview.setColumnCount(len(result['columns']));self.preview.setHorizontalHeaderLabels(result['columns']);self.preview.setRowCount(min(200,len(result['rows'])))
        for i,row in enumerate(result['rows'][:200]):
            for j,value in enumerate(row):self.preview.setItem(i,j,item(f'{value:g}' if isinstance(value,float) else value))
        self.preview_note.setText(f"模拟数据：{len(result['rows'])} 行，{len(result['columns'])} 列。预览最多显示 200 行；复制和导出包含全部数据。参数修改后需重新生成，导出始终使用本次生成快照。")
        lines=[]
        for check in result['checks']:
            if 'actual_mean' in check:lines.append(f"{check['group']} · {check['field']}：均数 {check['actual_mean']:.4f}（偏差 {check['mean_error']:+.4f}），标准差 {check['actual_sd']:.4f}（偏差 {check['sd_error']:+.4f}）")
        self.audit.setPlainText('\n'.join(lines));self.copy_button.setEnabled(True);self.export_button.setEnabled(True);self.pages.setCurrentIndex(3);self.message.setText('生成完成。请核对统计偏差；数据仅为模拟，不是 Word 对应的原始病例。')
    def copy_data(self):
        if self.result:
            text='\n'.join('\t'.join(str(v) for v in row) for row in [self.result['columns']]+self.result['rows'])
            QApplication.clipboard().setText(text);self.message.setText('已复制全部数据及表头，可粘贴到 Excel。')
    def export_data(self):
        if not self.result:return
        if self.is_running():
            self.message.setText('请等待当前任务完成后再导出。');return
        path,_=QFileDialog.getSaveFileName(self,'导出模拟病例 Excel','模拟病例数据.xlsx','Excel (*.xlsx)')
        if not path:return
        if not path.lower().endswith('.xlsx'):path+='.xlsx'
        self.worker=ExportWorker(self.result,path,self)
        self.worker.ready.connect(lambda p:self.message.setText('已导出：'+p+'（包含模拟病例数据、统计核对、生成配置）'))
        self.worker.failed.connect(self.message.setText);self.worker.finished.connect(self.finished)
        for control in [self.generate_button,self.import_button,self.load_button,self.save_button]:control.setEnabled(False)
        self.message.setText('正在导出 Excel…');self.worker.start()
    def is_running(self):return self.worker is not None and self.worker.isRunning()
