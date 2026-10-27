"""One editable view per Word source table, backed by the existing import models."""
from collections import defaultdict
from copy import deepcopy
import math
from PySide6.QtCore import Qt,QTimer,QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QGroupBox,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QComboBox,QLineEdit,QPushButton,QSizePolicy,QDialog)
from .typed_field_ui import TYPES,FieldDialog

HEADERS=['输出列名','组别','数据类型','生成规则','Word原文']
NUMERIC_KEYS=[('mean','均数'),('sd','标准差'),('digits','小数位'),('lower','下限（可空）'),('upper','上限（可空）')]

class SourceTable(QTableWidget):
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.fit_columns()
    def fit_columns(self):
        if getattr(self,'fitting',False) or self.columnCount()!=5:return
        self.fitting=True
        try:
            metrics=self.fontMetrics()
            def content_width(col,low,high):
                texts=[self.horizontalHeaderItem(col).text()] if self.horizontalHeaderItem(col) else []
                texts.extend(self.item(row,col).text() for row in range(self.rowCount()) if self.item(row,col))
                return min(high,max(low,max((metrics.horizontalAdvance(text)+28 for text in texts),default=low)))
            name=content_width(0,74,240);group=content_width(1,64,150);raw=content_width(4,88,230)
            types=116;rule=300;preferred_rule=300
            for row in range(self.rowCount()):
                cell=self.cellWidget(row,2);combo=cell.findChild(QComboBox) if cell else None
                if combo:types=max(types,combo.fontMetrics().horizontalAdvance(combo.currentText())+62)
                cell=self.cellWidget(row,3)
                if cell:
                    minimum=int(cell.property('ruleMinimumWidth') or 300)
                    rule=max(rule,minimum)
                    summary=cell.findChild(QLabel,'rule-summary')
                    desired=min(680,summary.fontMetrics().horizontalAdvance(summary.text())+155) if summary else minimum+72
                    preferred_rule=max(preferred_rule,minimum,desired)
            # Content determines the natural table width. Extra window space is
            # used only until inputs and summaries have enough room to read.
            natural=[name,group,types,preferred_rule,raw]
            chrome=self.verticalHeader().width()+self.frameWidth()*2+16
            if not self.property('userResizeWidth'):
                self.setMaximumWidth(sum(natural)+chrome)
            widths=[min(name,88),min(group,76),types,rule,min(raw,100)]
            remaining=max(0,self.viewport().width()-sum(widths)-2)
            for col,preferred in ((0,name),(1,group),(4,raw),(3,preferred_rule)):
                extra=min(remaining,max(0,preferred-widths[col]));widths[col]+=extra;remaining-=extra
            for col,width in enumerate(widths):
                if self.columnWidth(col)!=width:self.setColumnWidth(col,width)
            # Wrapped text grows only its own row; short categories stay compact.
            for row in range(self.rowCount()):
                cell=self.cellWidget(row,3)
                height=42
                if cell:
                    layout=cell.layout()
                    if layout:height=max(height,layout.heightForWidth(widths[3]) if layout.hasHeightForWidth() else layout.sizeHint().height())
                for col in (0,1,4):
                    item=self.item(row,col)
                    if item:
                        bounds=metrics.boundingRect(QRect(0,0,max(20,widths[col]-24),10000),Qt.TextWordWrap,item.text())
                        height=max(height,bounds.height()+16)
                height=max(64 if cell and cell.property('ruleMinimumWidth') else 48,height+4)
                if self.rowHeight(row)!=height:self.setRowHeight(row,height)
            if not self.property('userResizeHeight'):
                scrollbar=self.horizontalScrollBar().sizeHint().height() if sum(widths)>self.viewport().width() else 0
                self.setFixedHeight(min(490,self.horizontalHeader().height()+sum(self.rowHeight(r) for r in range(self.rowCount()))+scrollbar+4))
        finally:self.fitting=False


class WordSourceTables(QWidget):
    def __init__(self,tool):
        super().__init__();self.tool=tool;self.tables={};self.blocks={};self.records={};self.numeric_inputs={};self.selected=None;self.writing=False
        self.box=QVBoxLayout(self);self.box.setContentsMargins(0,0,0,0);self.box.setSpacing(16);self.box.setAlignment(Qt.AlignTop)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        for model in (tool.metrics.model(),tool.typed_table.model(),tool.categories.model()):
            model.dataChanged.connect(self.schedule);model.rowsInserted.connect(self.schedule);model.rowsRemoved.connect(self.schedule);model.modelReset.connect(self.schedule)
        self.refresh()
    def schedule(self,*args):
        if not self.writing:self.timer.start(0)
    def collect(self):
        t=self.tool;records=[]
        for i in range(t.metrics.rowCount()):
            f={key:(t.metrics.cellWidget(i,j).currentData() if t.metrics.cellWidget(i,j) else t.metrics.item(i,j).text() if t.metrics.item(i,j) else '') for j,key in enumerate(t.KEYS)}
            f['table']=int(f['table']) if str(f['table']).isdigit() else 0;f['kind']='mean_sd'
            records.append(('numeric',i,f))
        records.extend(('typed',i,f) for i,f in enumerate(t.typed_specs))
        categories={}
        for i in range(t.categories.rowCount()):
            values=[t.categories.item(i,j).text() for j in range(5)];name,group,label,weight,raw=values
            f=categories.setdefault((name,group),dict(table=0,name=name,group=group,kind='category',labels=[],weights=[],raw=raw,confirmed=True,rows=[]))
            f['labels'].append(label);f['weights'].append(float(weight));f['rows'].append(i)
        records.extend(('category',f['rows'][0],f) for f in categories.values())
        return records
    def refresh(self):
        if self.writing:return
        self.timer.stop();old={key:(table.property('userResizeHeight'),table.property('userResizeWidth'),table.horizontalScrollBar().value(),table.verticalScrollBar().value()) for key,table in self.tables.items()}
        self.writing=True
        try:
            while self.box.count():
                item=self.box.takeAt(0)
                if item.widget():item.widget().hide();item.widget().deleteLater()
            self.tables={};self.blocks={};self.records={};self.numeric_inputs={}
            groups=defaultdict(list)
            for origin,index,f in self.collect():groups[int(f.get('table') or 0)].append((origin,index,f))
            for key in self.tool.table_titles:
                if str(key).isdigit():groups.setdefault(int(key),[])
            if not groups:
                label=QLabel('导入并应用识别结果后，按 Word 原表分别展示；也可添加手工指标。');label.setWordWrap(True);self.box.addWidget(label)
            for source,records in sorted(groups.items(),key=lambda pair:(pair[0]==0,pair[0])):
                title=self.tool.table_titles.get(str(source)) or self.tool.table_titles.get(source) or next((f.get('table_title') for _,_,f in records if f.get('table_title')),None) or (f'表{source}' if source else '手工指标 / 正文补充资料')
                block=QGroupBox();layout=QVBoxLayout(block);layout.setContentsMargins(10,12,10,10)
                heading=QLabel(title);heading.setTextFormat(Qt.PlainText);heading.setWordWrap(True);heading.setStyleSheet('font-weight:600;font-size:15px;');heading.setToolTip(title);layout.addWidget(heading)
                self.blocks[source]=block;self.box.addWidget(block)
                if not records:
                    empty=QLabel('这张表暂无已应用的指标，可在导入预览中核对原表。');empty.setWordWrap(True);layout.addWidget(empty);continue
                table=SourceTable(len(records),5);table.setHorizontalHeaderLabels([HEADERS[0],'数据集',*HEADERS[2:]] if self.tool.ungrouped else HEADERS);table.setWordWrap(True);table.setSelectionBehavior(QTableWidget.SelectRows)
                table.setEditTriggers(QTableWidget.DoubleClicked|QTableWidget.EditKeyPressed)
                table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive);table.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
                for col,width in enumerate((170,95,160,480,210)):table.setColumnWidth(col,width)
                self.tables[source]=table;self.records[source]=records
                for row,(origin,index,f) in enumerate(records):
                    name=QTableWidgetItem(f['name']);name.setToolTip('双击修改输出列名；仅同步本表同一指标的各组名称。');table.setItem(row,0,name)
                    group=QTableWidgetItem(f['group']);group.setFlags(group.flags()&~Qt.ItemIsEditable);table.setItem(row,1,group)
                    combo=QComboBox()
                    for kind,label in TYPES:combo.addItem(label,kind)
                    combo.setCurrentIndex(max(0,combo.findData(f['kind'])));combo.setFixedHeight(36)
                    type_cell=QWidget();type_layout=QHBoxLayout(type_cell);type_layout.setContentsMargins(4,0,4,0);type_layout.setAlignment(Qt.AlignVCenter);type_layout.addWidget(combo);table.setCellWidget(row,2,type_cell)
                    combo.currentIndexChanged.connect(lambda _,s=source,r=row,c=combo:self.change_kind(s,r,c.currentData()))
                    raw=QTableWidgetItem(f.get('raw',''));raw.setFlags(raw.flags()&~Qt.ItemIsEditable);raw.setToolTip(f.get('raw','')+'\n'+f.get('review_note',''));table.setItem(row,4,raw)
                    if f['kind']=='mean_sd':
                        table.setCellWidget(row,3,self.numeric_rule(source,row,origin,index,f));table.setRowHeight(row,78)
                    else:
                        table.setCellWidget(row,3,self.other_rule(source,row,f));table.setRowHeight(row,68)
                        if not f.get('confirmed',True):name.setBackground(QColor('#FFF0D8'))
                table.itemChanged.connect(lambda item,s=source:self.rename(s,item))
                table.itemSelectionChanged.connect(lambda s=source:self.select(s))
                height=min(490,max(170,table.horizontalHeader().height()+sum(table.rowHeight(i) for i in range(table.rowCount()))+26))
                previous=old.get(source)
                if previous:
                    if previous[0]:height=int(previous[0]);table.setProperty('userResizeHeight',height)
                    if previous[1]:table.setFixedWidth(int(previous[1]));table.setProperty('userResizeWidth',previous[1])
                table.setFixedHeight(height);layout.addWidget(table);table.fit_columns()
                table.fit_timer=QTimer(table);table.fit_timer.setSingleShot(True);table.fit_timer.timeout.connect(table.fit_columns);table.fit_timer.start(0)
                if previous:table.horizontalScrollBar().setValue(previous[2]);table.verticalScrollBar().setValue(previous[3])
        finally:self.writing=False
    def numeric_rule(self,source,row,origin,index,f):
        panel=QWidget();grid=QHBoxLayout(panel);grid.setContentsMargins(8,5,8,5);grid.setSpacing(8);inputs={}
        panel.setProperty('ruleMinimumWidth',524)
        for offset,(key,label) in enumerate(NUMERIC_KEYS):
            cell=QWidget();line=QVBoxLayout(cell);line.setContentsMargins(0,0,0,0);line.setSpacing(3);line.addWidget(QLabel(label.replace('（可空）','')))
            value=f.get(key);entry=QLineEdit('' if value is None else str(value));entry.setMinimumWidth(54 if key=='digits' else 76);entry.setFixedHeight(30);entry.setToolTip('可留空，不限制范围' if key in ('lower','upper') else label);entry.setObjectName(f'rule-{key}');inputs[key]=entry;line.addWidget(entry);grid.addWidget(cell,1 if key=='digits' else 2)
        parity=QComboBox()
        for label,key in [('任意数值','any'),('奇数','odd'),('偶数','even')]:parity.addItem(label,key)
        parity.setCurrentIndex(max(0,parity.findData(f.get('parity','any'))));parity.setFixedHeight(30);parity.setMinimumWidth(110)
        cell=QWidget();line=QVBoxLayout(cell);line.setContentsMargins(0,0,0,0);line.setSpacing(3);line.addWidget(QLabel('数值类型'));line.addWidget(parity);grid.addWidget(cell,2)
        self.numeric_inputs[(source,row)]=inputs
        def update(*args):
            self.writing=True
            try:
                valid=True;parsed={}
                for key,entry in inputs.items():
                    text=entry.text().strip()
                    try:
                        value=int(text) if key=='digits' else float(text) if text else None
                        good=(value is None and key in ('lower','upper')) or value is not None and math.isfinite(value) and (key!='sd' or value>=0) and (key!='digits' or 0<=value<=4)
                    except ValueError:value=None;good=False
                    valid=valid and good;parsed[key]=value;entry.setStyleSheet('' if good else 'QLineEdit{border:1px solid #D49D50;background:#FFF6E8;}')
                mode=parity.currentData()
                if parsed['lower'] is not None and parsed['upper'] is not None and parsed['lower']>parsed['upper']:valid=False
                if mode!='any' and parsed['digits']!=0:valid=False
                if origin=='numeric':
                    for key,entry in inputs.items():self.tool.metrics.item(index,self.tool.KEYS.index(key)).setText(entry.text())
                    self.tool.metrics.cellWidget(index,8).setCurrentIndex(self.tool.metrics.cellWidget(index,8).findData(mode))
                else:
                    field=self.tool.typed_specs[index];field.update(parsed,parity=mode,confirmed=bool(valid))
                panel.setToolTip('' if valid else '本行参数待补全或修正')
                item=self.tables[source].item(row,0);blocked=self.tables[source].blockSignals(True);item.setBackground(QColor('transparent' if valid else '#FFF0D8'));self.tables[source].blockSignals(blocked)
            finally:self.writing=False
        for entry in inputs.values():entry.textEdited.connect(update)
        parity.currentIndexChanged.connect(update)
        # Render validity without changing the stored confirmation until editing.
        ready=all(f.get(key) not in (None,'') for key in ('mean','sd')) and f.get('confirmed',True)
        panel.setToolTip('' if ready else '本行参数待补全或修正')
        if not ready:
            self.tables[source].item(row,0).setBackground(QColor('#FFF0D8'))
            for key in ('mean','sd'):
                if f.get(key) in (None,''):inputs[key].setStyleSheet('QLineEdit{border:1px solid #D49D50;background:#FFF6E8;}')
        return panel
    def other_rule(self,source,row,f):
        panel=QWidget();line=QHBoxLayout(panel);line.setContentsMargins(8,6,8,6);summary=QLabel();summary.setObjectName('rule-summary');summary.setWordWrap(True);summary.setTextFormat(Qt.PlainText)
        if f['kind']=='excluded':text='仅保留原文和来源，不生成病例列'
        elif f.get('aggregate_pending'):text='汇总项：联合规则待确认'
        elif f.get('labels'):
            parts=[];n=f.get('source_n')
            for label,weight in zip(f.get('labels',[]),f.get('weights',[])):
                if weight is None:parts.append(str(label)+'：待填写');continue
                suffix=f'，约{n*weight/100:.0f}例' if n else ''
                parts.append(f'{label}：{weight:.2f}'.rstrip('0').rstrip('.')+'%'+suffix)
            text='；'.join(parts)
        elif f['kind']=='quantile':text=f"Q1：{f.get('q1')}；中位数：{f.get('median')}；Q3：{f.get('q3')}"
        else:text=f.get('review_note') or '规则待配置'
        summary.setText(text);summary.setToolTip(f.get('review_note',''));line.addWidget(summary,1)
        action=QPushButton('编辑参数' if f.get('confirmed',True) else '确认 / 补全参数');action.setMinimumWidth(115);action.clicked.connect(lambda:self.edit_rule(source,row));line.addWidget(action)
        return panel
    def select(self,source):
        table=self.tables[source];row=table.currentRow()
        if 0<=row<len(self.records[source]):self.selected=(source,self.records[source][row][2]['name'])
    def rename(self,source,item):
        if self.writing or item.column()!=0:return
        origin,index,f=self.records[source][item.row()];old=f['name'];new=item.text().strip()
        if not new or old==new:return
        self.writing=True
        try:
            for i in range(self.tool.metrics.rowCount()):
                if self.tool.metrics.item(i,1).text()==old and self.source_number(self.tool.metrics.item(i,0).text())==source:
                    blocked=self.tool.metrics.blockSignals(True);entry=self.tool.metrics.item(i,1);entry.setText(new);entry.setData(Qt.UserRole,new);self.tool.metrics.blockSignals(blocked)
            for field in self.tool.typed_specs:
                if field.get('table',0)==source:
                    if field['name']==old:field['name']=new
                    if field.get('from_field')==old:field['from_field']=new
            self.tool.set_typed_fields(self.tool.typed_specs)
            if origin=='category':
                for i in f['rows']:self.tool.categories.item(i,0).setText(new)
        finally:self.writing=False
        if self.selected==(source,old):self.selected=(source,new)
        self.schedule()
    @staticmethod
    def source_number(value):return int(value) if str(value).isdigit() else 0
    def change_kind(self,source,row,kind):
        if self.writing:return
        origin,index,f=self.records[source][row]
        try:
            if origin=='numeric':self.tool.convert_numeric_field(self.tool.metrics.cellWidget(index,8),kind)
            elif origin=='typed':self.tool.change_typed_kind(index,kind)
        except ValueError as error:self.tool.show_generation_error(error)
        self.schedule()
    def edit_rule(self,source,row):
        origin,index,f=self.records[source][row]
        if origin=='typed':self.tool.edit_typed_field(index)
        elif origin=='category':
            dialog=FieldDialog(f,self.tool);dialog.sync.setChecked(False);dialog.sync.hide();self.tool.field_dialog=dialog
            try:accepted=dialog.exec()==QDialog.Accepted
            finally:self.tool.field_dialog=None;dialog.deleteLater()
            if accepted:
                result=dialog.result_field;specs=[]
                for key,items in self.category_specs().items():specs.append(result if key==(f['name'],f['group']) else items)
                self.tool.set_categoricals(specs)
        self.schedule()
    def category_specs(self):return {(f['name'],f['group']):f for origin,_,f in self.collect() if origin=='category'}
    def remove_selected(self):
        if self.selected is None:return False
        source,name=self.selected;self.selected=None
        for i in reversed(range(self.tool.metrics.rowCount())):
            if self.source_number(self.tool.metrics.item(i,0).text())==source and self.tool.metrics.item(i,1).text()==name:self.tool.metrics.removeRow(i)
        self.tool.set_typed_fields([f for f in self.tool.typed_specs if not (f.get('table',0)==source and (f['name']==name or f.get('from_field')==name))])
        self.tool.set_categoricals([f for f in self.category_specs().values() if f['name']!=name or source!=0]);self.schedule();return True
