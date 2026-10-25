"""Native Word-to-synthetic-case workflow in the existing data tools page."""
from copy import deepcopy
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)
from .widgets import scroll
from .word_batch_engine import (
    default_batch_config, read_word, generate_batch, export_batch, validate_batch, group_names,
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
        super().__init__();self.name=config['name'];self.fields={};layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.shared_note=QLabel('本组共用第一个组别的基础资料规则；例数、有效率与复发率仍可分别设置。');self.shared_note.setWordWrap(True);self.shared_note.hide();layout.addWidget(self.shared_note)
        self.sections=QTabWidget();layout.addWidget(self.sections,1)
        group=QGroupBox('组别、性别与病情程度');group.setStyleSheet('QGroupBox{padding:18px 12px 12px;} QLineEdit{padding:4px 8px;min-height:20px;}');form=QFormLayout(group)
        for key,label,value in [('n','本组例数',config['n']),('male','男性占比 %（其余为女性）',config['male']),('light','轻度占比 %',config['severity'][0]),('medium','中度占比 %',config['severity'][1]),('severe','重度占比 %',config['severity'][2])]:
            field=QLineEdit(str(value));self.fields[key]=field;form.addRow(label,field)
        self.sections.addTab(scroll(group),'性别与病情')
        age_page=QWidget();al=QVBoxLayout(age_page)
        note=QLabel('年龄取整数，占比合计100%。可设置10–20、20–30；共用边界20归入后一段，最后一段包含上限。');note.setWordWrap(True);al.addWidget(note)
        self.age=EditableRows('年龄区间（岁）',['下限','上限','占比 %'],[[r['lower'],r['upper'],r['percent']] for r in config['age']]);al.addWidget(self.age);self.sections.addTab(scroll(age_page),'年龄区间')
        course_page=QWidget();cl=QVBoxLayout(course_page)
        self.course=EditableRows('病程区间',['下限','上限','占比 %'],[[r['lower'],r['upper'],r['percent']] for r in config['course']]);cl.addWidget(self.course)
        self.course_digits=QSpinBox();self.course_digits.setRange(0,4);self.course_digits.setValue(config['course_digits']);cf=QFormLayout();cf.addRow('病程小数位',self.course_digits);cl.addLayout(cf);self.sections.addTab(scroll(course_page),'病程区间')
        extent_page=QWidget();el=QVBoxLayout(extent_page)
        self.extent_mode=QComboBox()
        for label,value in [('暂不生成，Excel 保留空列','blank'),('按自定义类别及比例生成','category'),('按数值区间及比例生成','range')]:self.extent_mode.addItem(label,value)
        self.extent_mode.setCurrentIndex(max(0,self.extent_mode.findData(config.get('extent_mode','category'))));el.addWidget(self.extent_mode)
        self.extent=EditableRows('病变范围类别',['类别名称','占比 %'],[[r['label'],r['percent']] for r in config['extent']]);el.addWidget(self.extent)
        self.extent_ranges=EditableRows('病变范围数值区间',['下限','上限','占比 %'],[[r['lower'],r['upper'],r['percent']] for r in config.get('extent_ranges',[dict(lower=1,upper=3,percent=100.)])]);el.addWidget(self.extent_ranges)
        self.extent_digits=QSpinBox();self.extent_digits.setRange(0,4);self.extent_digits.setValue(config.get('extent_digits',0))
        self.extent_precision=QWidget();ef=QFormLayout(self.extent_precision);ef.addRow('病变范围小数位',self.extent_digits);el.addWidget(self.extent_precision);el.addStretch()
        def extent_changed():
            mode=self.extent_mode.currentData();self.extent.setVisible(mode=='category');self.extent_ranges.setVisible(mode=='range');self.extent_precision.setVisible(mode=='range')
        self.extent_mode.currentIndexChanged.connect(extent_changed);extent_changed();self.sections.addTab(scroll(extent_page),'病变范围')
        outcomes=QGroupBox('最后两列的病例结果');of=QFormLayout(outcomes)
        for key,label in [('effective','有效占比 %（其余为无效）'),('recurrence','复发占比 %（其余为未复发）')]:
            field=QLineEdit(str(config[key]));self.fields[key]=field;of.addRow(label,field)
        self.recurrence_scope=QComboBox();self.recurrence_scope.addItem('该组全部病例','all');self.recurrence_scope.addItem('该组治疗有效者','effective');self.recurrence_scope.setCurrentIndex(max(0,self.recurrence_scope.findData(config.get('recurrence_scope','all'))));of.addRow('复发比例的计算分母',self.recurrence_scope)
        of.addRow(QLabel('Excel 的“总有效率”填有效/无效，“复发率”填复发/未复发。'))
        self.sections.addTab(scroll(outcomes),'有效与复发')
    def values(self,baseline=None):
        if baseline is not None:
            result=deepcopy(baseline);result.update(name=self.name,n=int(self.fields['n'].text()),effective=float(self.fields['effective'].text()),recurrence=float(self.fields['recurrence'].text()),recurrence_scope=self.recurrence_scope.currentData());return result
        f={k:v.text().strip() for k,v in self.fields.items()}
        def ranges(editor):return [dict(lower=float(a),upper=float(b),percent=float(c)) for a,b,c in editor.values()]
        return dict(name=self.name,n=int(f['n']),male=float(f['male']),severity=[float(f[k]) for k in ('light','medium','severe')],effective=float(f['effective']),recurrence=float(f['recurrence']),age=ranges(self.age),course=ranges(self.course),course_digits=self.course_digits.value(),extent=[dict(label=a,percent=float(b)) for a,b in self.extent.values()],extent_mode=self.extent_mode.currentData(),extent_ranges=ranges(self.extent_ranges),extent_digits=self.extent_digits.value(),recurrence_scope=self.recurrence_scope.currentData())


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
        super().__init__();self.worker=None;self.result=None;self.source='';self.config=default_batch_config();self.pending_source=None;self.groups_confirmed=True
        layout=QVBoxLayout(self)
        intro=QLabel('导入 Word 表格，按你配置的人数与基本资料生成所选组别的病例，再一次导出 Excel。')
        intro.setWordWrap(True);layout.addWidget(intro)
        row=QHBoxLayout();self.import_button=button('导入 Word（.docx）',self.pick_word,row)
        self.load_button=button('载入配置',self.load_config,row);self.save_button=button('保存配置',self.save_config,row);self.change_groups_button=button('修改组别',self.edit_groups,row);self.change_groups_button.hide();row.addStretch();layout.addLayout(row)
        options=QHBoxLayout();self.use_word_sizes=QCheckBox('采用 Word 表中的例数');self.use_word_rates=QCheckBox('采用 Word 表中的有效／复发比例');options.addWidget(self.use_word_sizes);options.addWidget(self.use_word_rates);options.addStretch();layout.addLayout(options)
        self.source_label=QLabel('先导入Word，填写并确认本次组别，再核对指标与生成人数。');self.source_label.setWordWrap(True);layout.addWidget(self.source_label)
        self.group_panel=QGroupBox('1 · 填写并确认本次要生成的组别');gp=QVBoxLayout(self.group_panel)
        note=QLabel('每个输入框填写一个Word中的组别原名，可添加或删除。确认后才识别指标列名。');note.setWordWrap(True);gp.addWidget(note)
        self.group_rows=QWidget();self.group_rows_layout=QVBoxLayout(self.group_rows);self.group_rows_layout.setContentsMargins(0,0,0,0);self.group_inputs=[]
        self.group_area=scroll(self.group_rows);gp.addWidget(self.group_area)
        actions=QHBoxLayout();self.add_group_button=button('＋ 添加组别',self.add_group_input,actions);self.match_groups_button=button('匹配Word表格',self.match_groups,actions);self.confirm_groups_button=button('确认组别，识别指标列名',self.confirm_groups,actions);actions.addStretch();gp.addLayout(actions)
        self.match_summary=QLabel('');self.match_summary.setWordWrap(True);gp.addWidget(self.match_summary)
        self.match_report=QPlainTextEdit();self.match_report.setReadOnly(True);gp.addWidget(self.match_report,1)
        layout.addWidget(self.group_panel,1);self.group_panel.hide()
        self.match_timer=QTimer(self);self.match_timer.setSingleShot(True);self.match_timer.timeout.connect(self.match_groups)
        self.pages=QTabWidget();layout.addWidget(self.pages,1)
        basics=QWidget();base_layout=QVBoxLayout(basics);form=QFormLayout()
        self.common_n=QSpinBox();self.common_n.setRange(2,5000);self.common_n.setValue(70);self.same_size=QCheckBox('所选组别使用相同例数');self.same_size.setChecked(True);self.shared_basics=QCheckBox('共用第一个组别的基础资料规则（性别、年龄、病程、病情程度和病变范围）');self.shared_basics.setChecked(True)
        self.total_label=QLabel('')
        counts=QHBoxLayout();counts.addWidget(QLabel('每组例数'));counts.addWidget(self.common_n);counts.addWidget(self.same_size);counts.addWidget(self.total_label);counts.addStretch();base_layout.addLayout(counts)
        self.seed=QLineEdit('12');self.unit=QLineEdit('月');self.seed.setMaximumWidth(160);self.unit.setMaximumWidth(100);seedrow=QHBoxLayout();seedrow.addWidget(QLabel('随机种子'));seedrow.addWidget(self.seed);seedrow.addWidget(QLabel('病程单位'));seedrow.addWidget(self.unit);seedrow.addWidget(self.shared_basics);seedrow.addStretch();base_layout.addLayout(seedrow)
        self.common_n.valueChanged.connect(self.sync_group_controls);self.same_size.toggled.connect(self.sync_group_controls);self.shared_basics.toggled.connect(self.sync_group_controls)
        self.group_tabs=QTabWidget();base_layout.addWidget(self.group_tabs);self.group_editors=[]
        self.pages.addTab(basics,'1 · 人数与基本资料')
        self.set_groups(self.config['groups']);self.sync_group_controls()
        metrics=QWidget();ml=QVBoxLayout(metrics)
        tip=QLabel('每个指标须配置全部所选组别。双击指标列名即可修改，同一指标的各组列名同步更新。小数位 0～4；奇数／偶数须为 0 位。上下限非必填。表头、均数和标准差均可修改；空白统计值必须补全。')
        tip.setWordWrap(True);ml.addWidget(tip)
        self.metrics=QTableWidget(0,len(self.HEADERS));self.metrics.setHorizontalHeaderLabels(self.HEADERS)
        self.metrics.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed|QAbstractItemView.SelectedClicked)
        self.metrics.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i in range(len(self.HEADERS)):self.metrics.setColumnWidth(i,135 if i in (1,9) else 95)
        self.metrics.setColumnWidth(1,240);self.metrics.setColumnWidth(2,150);self.metrics.setColumnWidth(0,45);self.metrics.verticalHeader().setDefaultSectionSize(44);self.metrics.verticalHeader().setMinimumSectionSize(44);ml.addWidget(self.metrics,1)
        self.metrics.cellChanged.connect(self.metric_name_changed)
        row=QHBoxLayout();button('＋ 添加指标（全部组别）',self.add_indicator,row);button('删除选中的指标（全部组别）',self.remove_indicator,row);row.addStretch();ml.addLayout(row)
        self.pages.addTab(metrics,'2 · Word 指标核对')
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setPlainText('导入后显示识别报告。基本资料的初始比例为示例，请核对后生成。')
        self.pages.addTab(self.log,'识别报告')
        preview=QWidget();pl=QVBoxLayout(preview)
        self.preview_note=QLabel('尚未生成数据。');self.preview_note.setWordWrap(True);pl.addWidget(self.preview_note)
        self.preview=QTableWidget();self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers);pl.addWidget(self.preview,1)
        self.audit=QPlainTextEdit();self.audit.setReadOnly(True);self.audit.setMaximumHeight(160);pl.addWidget(self.audit)
        row=QHBoxLayout();self.copy_button=button('复制完整数据（含表头）',self.copy_data,row);self.export_button=button('导出 Excel',self.export_data,row);row.addStretch();pl.addLayout(row)
        self.copy_button.setEnabled(False);self.export_button.setEnabled(False)
        self.pages.addTab(preview,'3 · 生成与导出')
        self.column_hint=QLabel('Excel 列顺序：编号、分组、性别、年龄、病程、病情程度、病变范围 → Word 前后指标 → 总有效率（有效/无效）、复发率（复发/未复发）');self.column_hint.setWordWrap(True);layout.addWidget(self.column_hint)
        row=QHBoxLayout();self.generate_button=button('生成模拟病例数据',self.generate,row);self.generate_button.setObjectName('primary')
        self.cancel_button=button('取消生成',self.cancel,row);self.cancel_button.setEnabled(False);row.addStretch();layout.addLayout(row)
        self.message=QLabel('');self.message.setWordWrap(True);layout.addWidget(self.message)
    def set_groups(self,groups):
        while self.group_tabs.count():
            w=self.group_tabs.widget(0);self.group_tabs.removeTab(0);w.deleteLater()
        self.group_editors=[GroupSettings(g) for g in groups]
        for editor in self.group_editors:
            self.group_tabs.addTab(editor,editor.name)
            editor.fields['n'].textChanged.connect(self.update_total)
        if hasattr(self,'common_n'):
            equal=len({g['n'] for g in groups})==1;self.same_size.blockSignals(True);self.same_size.setChecked(equal);self.same_size.blockSignals(False)
            self.common_n.blockSignals(True);self.common_n.setValue(groups[0]['n']);self.common_n.blockSignals(False)
            self.sync_group_controls()
    def update_total(self):
        if not getattr(self,'group_editors',None):return
        try:
            counts=[int(e.fields['n'].text()) for e in self.group_editors]
            self.total_label.setText(' + '.join(f'{e.name} {n} 例' for e,n in zip(self.group_editors,counts))+f' = {sum(counts)} 行病例')
        except ValueError:self.total_label.setText('请填写有效例数')

    def sync_group_controls(self,*args):
        editors=getattr(self,'group_editors',[])
        self.common_n.setEnabled(self.same_size.isChecked())
        for index,e in enumerate(editors):
            if self.same_size.isChecked():e.fields['n'].setText(str(self.common_n.value()))
            e.fields['n'].setReadOnly(self.same_size.isChecked())
            e.fields['n'].setVisible(not self.same_size.isChecked())
            e.fields['n'].parentWidget().layout().labelForField(e.fields['n']).setVisible(not self.same_size.isChecked())
            shared=index>0 and self.shared_basics.isChecked()
            e.shared_note.setVisible(shared)
            for k in ('male','light','medium','severe'):e.fields[k].setEnabled(not shared)
            for control in (e.age,e.course,e.course_digits,e.extent_mode,e.extent,e.extent_ranges,e.extent_digits):control.setEnabled(not shared)
        self.update_total()

    def metric_name_changed(self,row,col):
        if col in (3,4):
            entry=self.metrics.item(row,col)
            if entry is None:return
            try:
                value=float(entry.text());valid=math.isfinite(value) and (col!=4 or value>=0)
            except ValueError:valid=False
            blocked=self.metrics.blockSignals(True)
            entry.setBackground(QColor('transparent') if valid else QColor('#FADEDA'))
            entry.setToolTip('' if valid else 'Word 中未识别或输入无效；生成前请补全有效均数和非负标准差。')
            self.metrics.blockSignals(blocked)
            return
        if col!=1:return
        entry=self.metrics.item(row,col)
        if entry is None:return
        old=entry.data(Qt.UserRole);new=entry.text().strip()
        if old is None or old==new:return
        self.metrics.blockSignals(True)
        for i in range(self.metrics.rowCount()):
            other=self.metrics.item(i,1)
            if other and (i==row or other.text()==old):other.setText(new);other.setData(Qt.UserRole,new)
        self.metrics.blockSignals(False)

    def set_indicators(self,specs):
        self.metrics.setRowCount(0)
        for spec in specs:self.append_spec(spec)
    def append_spec(self,spec):
        i=self.metrics.rowCount();self.metrics.insertRow(i)
        for j,key in enumerate(self.KEYS):
            if key in ('group','parity'):
                combo=QComboBox()
                for title,value in ([(e.name,e.name) for e in self.group_editors] if key=='group' else [('任意数值','any'),('奇数','odd'),('偶数','even')]):combo.addItem(title,value)
                combo.setCurrentIndex(max(0,combo.findData(spec.get(key))));self.metrics.setCellWidget(i,j,combo)
            else:
                entry=item(spec.get(key,''))
                if key=='name':
                    entry.setData(Qt.UserRole,spec.get(key,''));entry.setFlags(entry.flags()|Qt.ItemIsEditable);entry.setToolTip('双击修改此Excel指标列名；同一指标的所有组别同步更新。')
                self.metrics.setItem(i,j,entry)
    def add_indicator(self):
        existing={self.metrics.item(i,1).text() for i in range(self.metrics.rowCount()) if self.metrics.item(i,1)}
        k=1
        while f'自定义指标{k}' in existing:k+=1
        for group in [e.name for e in self.group_editors]:self.append_spec(dict(table=0,name=f'自定义指标{k}',group=group,mean=10,sd=2,digits=2,lower=None,upper=None,parity='any',raw='手工配置'))
    def remove_indicator(self):
        names={self.metrics.item(i.row(),1).text() for i in self.metrics.selectedIndexes() if self.metrics.item(i.row(),1)}
        for i in reversed(range(self.metrics.rowCount())):
            if self.metrics.item(i,1).text() in names:self.metrics.removeRow(i)
    def get_config(self):
        if not self.groups_confirmed:raise ValueError('请先填写并确认本次Word的组别，再识别指标。')
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
            first=self.group_editors[0].values();groups=[first]+[e.values(first if self.shared_basics.isChecked() else None) for e in self.group_editors[1:]]
            config=dict(version=1,seed=int(self.seed.text().strip()),source=self.source,course_unit=self.unit.text().strip(),groups=groups,indicators=specs,shared_basics=self.shared_basics.isChecked(),same_group_size=self.same_size.isChecked(),import_options=dict(sizes=self.use_word_sizes.isChecked(),rates=self.use_word_rates.isChecked()))
        except (ValueError,TypeError) as exc:raise ValueError('请补全有效数字；例数、小数位和种子须为整数，只有上下限可留空。') from exc
        validate_batch(config)
        return config
    def pick_word(self):
        path,_=QFileDialog.getOpenFileName(self,'选择 Word 汇总表','','Word (*.docx)')
        if path:self.import_word(path)
    def add_group_input(self,name=''):
        if len(self.group_inputs)>=20:
            self.message.setText('最多支持20个组别。');return
        if not isinstance(name,str):name=''
        row=QWidget();row.setFixedHeight(44);line=QHBoxLayout(row);line.setContentsMargins(0,0,0,0)
        entry=QLineEdit(name);entry.setFixedHeight(40);entry.setPlaceholderText('填写Word中的组别原名，如观察组、常规治疗组');line.addWidget(entry,1)
        remove=QPushButton('删除');remove.setFixedHeight(40);line.addWidget(remove)
        self.group_rows_layout.addWidget(row);self.group_inputs.append(entry);self.resize_group_inputs()
        def drop():
            self.group_inputs.remove(entry);self.group_rows_layout.removeWidget(row);row.deleteLater();self.resize_group_inputs();self.match_groups()
        remove.clicked.connect(drop)
        entry.textChanged.connect(lambda:self.match_timer.start(200))
        return entry

    def resize_group_inputs(self):
        height=max(48,len(self.group_inputs)*50)
        self.group_rows.setMinimumHeight(height);self.group_area.setFixedHeight(min(156,height))

    def show_group_selection(self,names):
        self.match_timer.stop()
        for i in reversed(range(self.group_rows_layout.count())):
            widget=self.group_rows_layout.takeAt(i).widget();widget.deleteLater()
        self.group_inputs=[]
        for name in names:self.add_group_input(name)
        self.groups_confirmed=False;self.pages.hide();self.group_panel.show();self.generate_button.setEnabled(False)
        self.match_groups()

    def edit_groups(self):
        if self.is_running():return
        if self.source:
            self.pending_source=self.source;self.show_group_selection([e.name for e in self.group_editors])

    def import_word(self,path):
        if self.is_running():return
        try:
            imported=read_word(path,[],parse_indicators=False)
            self.pending_source=imported.source;self.source_label.setText(f'已导入：{Path(imported.source).name} · Word共{imported.table_count}张表，请填写本次组别。')
            self.source_label.setToolTip(imported.source);self.change_groups_button.hide()
            self.show_group_selection(['']);self.message.setText('请填写组别原名，可增加多个组别；确认后自动填充指标列名。')
        except Exception as exc:self.message.setText('导入失败：'+str(exc))

    def match_groups(self):
        if not self.pending_source:return None
        try:
            names=[e.text().strip() for e in self.group_inputs]
            filled=[n for n in names if n]
            if filled:group_names(filled)
            imported=read_word(self.pending_source,filled,parse_indicators=False)
            matched=sum(count>0 for count in imported.group_matches.values());table_hits=sum(bool(t['groups']) for t in imported.table_matches)
            self.match_summary.setText(f'Word表格总数：{imported.table_count} · 匹配到的组别：{matched}/{len(filled)}个 · 匹配表格：{table_hits}张 · 组别数据行：{sum(imported.group_matches.values())}行')
            lines=[f'{name}：{count}行，出现于{sum(name in t["groups"] for t in imported.table_matches)}张表' for name,count in imported.group_matches.items()]
            lines+=['', '逐表匹配：']+[f'表{t["table"]}：'+('、'.join(f'{name}（{count}行）' for name,count in t['groups'].items()) or '未匹配到所选组别') for t in imported.table_matches]
            self.match_report.setPlainText('\n'.join(lines));self.confirm_groups_button.setEnabled(bool(filled) and len(filled)==len(names) and all(imported.group_matches.values()))
            return imported
        except Exception as exc:
            self.match_summary.setText(str(exc));self.confirm_groups_button.setEnabled(False);return None

    def confirm_groups(self):
        if self.is_running():return
        try:
            names=group_names([e.text() for e in self.group_inputs]);matched=self.match_groups()
            if matched is None or any(not matched.group_matches.get(g) for g in names):
                raise ValueError('有组别未在Word任何表格中匹配到，请核对组名。')
            imported=read_word(self.pending_source,names)
            previous={e.name:e for e in self.group_editors};groups=[]
            for g in default_batch_config(names)['groups']:
                if g['name'] in previous:
                    try:g=previous[g['name']].values()
                    except ValueError:pass
                else:g['n']=self.common_n.value()
                if self.use_word_sizes.isChecked() and g['name'] in imported.group_sizes:g['n']=imported.group_sizes[g['name']]
                for key,rate in imported.outcome_rates.get(g['name'],{}).items():
                    if self.use_word_rates.isChecked():g['effective' if key=='总有效率' else 'recurrence']=rate
                groups.append(g)
            self.set_groups(groups);self.set_indicators(imported.indicators);self.source=imported.source;self.groups_confirmed=True
            self.group_panel.hide();self.pages.show();self.generate_button.setEnabled(True);self.change_groups_button.show()
            count=len({s['name'] for s in imported.indicators})
            self.source_label.setText(f'Word共{imported.table_count}张表 · 已确认{len(names)}个组别：'+ '、'.join(names))
            self.log.setPlainText(self.match_summary.text()+'\n'+self.match_report.toPlainText()+'\n\n'+'\n'.join(imported.messages))
            self.log.appendPlainText('Word例数（仅供核对）：'+json.dumps(imported.group_sizes,ensure_ascii=False)+'\nWord结局比例（仅供核对）：'+json.dumps(imported.outcome_rates,ensure_ascii=False))
            self.message.setText(f'已匹配{len(names)}个组别，识别{count}个指标，Excel共{9+count}列。双击“指标列名”可修改，各组同步更新。')
            self.pages.setCurrentIndex(1)
        except Exception as exc:self.message.setText('组别确认失败：'+str(exc))

    def load_config(self):
        path,_=QFileDialog.getOpenFileName(self,'载入批量工具配置','','JSON (*.json)')
        if not path:return
        try:
            config=json.loads(Path(path).read_text(encoding='utf-8'));validate_batch(config)
            self.shared_basics.setChecked(config.get('shared_basics',False));self.set_groups(config['groups']);self.same_size.setChecked(config.get('same_group_size',len({g['n'] for g in config['groups']})==1));self.use_word_sizes.setChecked(config.get('import_options',{}).get('sizes',False));self.use_word_rates.setChecked(config.get('import_options',{}).get('rates',False));self.set_indicators(config['indicators']);self.seed.setText(str(config['seed']));self.unit.setText(config.get('course_unit','月'));self.source=config.get('source','');self.groups_confirmed=True;self.pending_source=self.source;self.group_panel.hide();self.pages.show();self.generate_button.setEnabled(True);self.change_groups_button.setVisible(bool(self.source));self.source_label.setText('配置来源：'+path);self.message.setText('已载入配置。已有生成结果保持原样，重新生成后更新。')
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
        for control in [self.generate_button,self.import_button,self.load_button,self.save_button,self.change_groups_button]:control.setEnabled(True)
        self.generate_button.setEnabled(self.groups_confirmed)
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
            from .feedback import copy_text
            text='\n'.join('\t'.join(str(v) for v in row) for row in [self.result['columns']]+self.result['rows'])
            copy_text(self,text,'复制成功，已复制全部数据及表头。');self.message.setText('复制成功，已复制全部数据及表头，可粘贴到 Excel。')
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
