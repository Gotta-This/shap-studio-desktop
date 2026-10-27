"""Native controls for reviewing and changing per-case field types."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget,QLabel,QPushButton,QComboBox,QLineEdit,QSpinBox,QTableWidget,QTableWidgetItem,QHeaderView,QDialog,QDialogButtonBox,QVBoxLayout,QHBoxLayout,QFormLayout,QCheckBox,QSizePolicy)

TYPES=[('unknown','待选择类型'),('mean_sd','数值：均数±标准差'),('quantile','数值：中位数（Q1，Q3）'),('binary','二分类：确认类别'),('gender','分类：男 / 女'),('yesno','分类：有 / 无'),('binary01','分类编码：1 / 0'),('category','自定义多分类'),('derived','由其他分类派生')]
TYPES.append(('excluded','仅保留来源，不生成'))


def convert(field,kind):
    result=deepcopy(field);old=result.get('kind');result['kind']=kind
    if kind=='excluded':result['confirmed']=True
    elif kind in ('gender','yesno','binary01'):
        result['labels']={'gender':['男','女'],'yesno':['有','无'],'binary01':[1,0]}[kind]
        if len(result.get('weights',[]))!=2:result['weights']=[None,None]
        result['confirmed']=all(v is not None for v in result['weights']) and (old!=kind or result.get('confirmed',True))
    elif kind in ('binary','category'):
        result.setdefault('labels',['类别1','类别2']);result.setdefault('weights',[None,None]);result['confirmed']=False if old!=kind else result.get('confirmed',False)
    elif old!=kind:result['confirmed']=False
    if kind=='quantile' and all(result.get(k) is not None for k in ('q1','q3')):
        span=result['q3']-result['q1']
        if result.get('lower') is None:result['lower']=max(0,result['q1']-span) if result['q1']>=0 else result['q1']-span
        if result.get('upper') is None:result['upper']=result['q3']+span
    if result.get('aggregate_pending') and kind!='excluded':result['confirmed']=False
    return result


class FieldDialog(QDialog):
    def __init__(self,field,parent=None):
        # A proxy-owned QDialog is painted with a simulated Qt title bar. Own
        # this editor from the real desktop window so macOS supplies the frame.
        owner=parent.window() if parent is not None else None
        proxy=owner.graphicsProxyWidget() if owner is not None else None
        if proxy is not None and proxy.scene() is not None and proxy.scene().views():
            owner=proxy.scene().views()[0].window()
        super().__init__(owner,Qt.Dialog|Qt.WindowTitleHint|Qt.WindowCloseButtonHint)
        self.field=deepcopy(field);self.result_field=None
        self.setObjectName('fieldEditorDialog');self.setWindowTitle('编辑字段 · '+field['name'])
        self.setWindowModality(Qt.ApplicationModal);self.setMinimumSize(560,380);self.resize(720,640)
        self.setStyleSheet("""
            QDialog#fieldEditorDialog { background:#F5F8F5; }
            QWidget#fieldEditorHeader, QWidget#fieldEditorFooter { background:white; }
            QLabel#fieldEditorTitle { font-size:21px; font-weight:600; color:#193C2C; }
            QLabel#fieldEditorSubtitle, QLabel#fieldEditorPath { color:#637668; font-size:12px; }
            QWidget#fieldEditorSource { background:white; border:1px solid #DEE8DF; border-radius:9px; }
            QLabel#fieldEditorNote { color:#735626; background:#FFF5E4; border-radius:7px; padding:10px; }
            QLabel#fieldEditorError { color:#9C352B; background:#FDEEEB; border-radius:7px; padding:9px; }
            QDialog#fieldEditorDialog QTableView::item { padding:5px 12px; }
            QDialog#fieldEditorDialog QTableWidget QLineEdit { padding:0 7px; min-height:0; border-radius:3px; }
            QDialog#fieldEditorDialog QPushButton { min-width:80px; }
        """)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.header=QWidget();self.header.setObjectName('fieldEditorHeader');head=QVBoxLayout(self.header);head.setContentsMargins(24,20,24,18);head.setSpacing(5)
        title=QLabel(field['name']);title.setTextFormat(Qt.PlainText);title.setWordWrap(True);title.setObjectName('fieldEditorTitle');head.addWidget(title)
        subtitle=QLabel(field['group']+' · 字段类型与生成规则');subtitle.setTextFormat(Qt.PlainText);subtitle.setObjectName('fieldEditorSubtitle');head.addWidget(subtitle);outer.addWidget(self.header)
        self.content=QWidget();self.content_layout=QVBoxLayout(self.content);layout=self.content_layout;layout.setContentsMargins(24,18,24,18);layout.setSpacing(14)
        source=QWidget();source.setObjectName('fieldEditorSource');source_layout=QVBoxLayout(source);source_layout.setContentsMargins(14,12,14,12);source_layout.setSpacing(7)
        raw=QLabel('Word原文：'+field.get('raw',''));raw.setTextFormat(Qt.PlainText);raw.setTextInteractionFlags(Qt.TextSelectableByMouse);raw.setWordWrap(True);source_layout.addWidget(raw)
        path=QLabel('原表头：'+' → '.join(field.get('header_path',[]) or [field['name']]));path.setTextFormat(Qt.PlainText);path.setObjectName('fieldEditorPath');path.setWordWrap(True);source_layout.addWidget(path);layout.addWidget(source)
        settings=QFormLayout();settings.setHorizontalSpacing(18);settings.setVerticalSpacing(12);settings.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.classification=QLineEdit(field.get('classification',''));self.classification.setPlaceholderText('可选，例如：一般资料、并发症、SAS');settings.addRow('分类 / 上级表头',self.classification)
        self.kind=QComboBox()
        for key,label in TYPES:self.kind.addItem(label,key)
        self.kind.setCurrentIndex(max(0,self.kind.findData(field['kind'])));settings.addRow('数据类型',self.kind);layout.addLayout(settings)
        if field.get('review_note'):
            note=QLabel(field['review_note']);note.setTextFormat(Qt.PlainText);note.setObjectName('fieldEditorNote');note.setWordWrap(True);layout.addWidget(note)
        self.panel=QWidget();layout.addWidget(self.panel)
        self.error=QLabel();self.error.setObjectName('fieldEditorError');self.error.setWordWrap(True);self.error.hide();layout.addWidget(self.error)
        from .resizable_fields import enable_content_scroll
        self.content_scroll=enable_content_scroll(self.content);outer.addWidget(self.content_scroll,1)
        self.footer=QWidget();self.footer.setObjectName('fieldEditorFooter');footer=QVBoxLayout(self.footer);footer.setContentsMargins(24,16,24,20);footer.setSpacing(14)
        self.sync=QCheckBox('同步本表同名指标的类型与类别（各行数值、比例及确认状态独立）');self.sync.setChecked(True);footer.addWidget(self.sync)
        if field.get('source_kind')=='ungrouped_table':self.sync.setChecked(False);self.sync.hide()
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Cancel).setText('取消')
        confirm=self.buttons.button(QDialogButtonBox.Ok);confirm.setText('确认并应用');confirm.setObjectName('primary')
        self.buttons.accepted.connect(self.apply);self.buttons.rejected.connect(self.reject);footer.addWidget(self.buttons);outer.addWidget(self.footer)
        self.kind.currentIndexChanged.connect(self.rebuild);self.rebuild()

    def showEvent(self,event):
        super().showEvent(event);QTimer.singleShot(0,self.fit_content)

    def fit_content(self):
        self.content_layout.activate()
        screen=self.screen();available=screen.availableGeometry() if screen is not None else None
        height=self.header.sizeHint().height()+self.footer.sizeHint().height()+self.content_layout.sizeHint().height()+6
        limit=max(380,available.height()-80) if available is not None else 850
        width=min(720,available.width()-60) if available is not None else 720
        self.resize(max(560,width),max(380,min(height,limit)))

    def rebuild(self):
        old=self.panel;self.panel=QWidget();self.content_layout.replaceWidget(old,self.panel);old.deleteLater()
        form=QFormLayout(self.panel);form.setContentsMargins(0,0,0,0);form.setVerticalSpacing(12);form.setHorizontalSpacing(18);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.inputs={};self.categories=None;kind=self.kind.currentData();f=convert(self.field,kind)
        def entry(key,label,value=None):
            e=QLineEdit('' if value is None else str(value));self.inputs[key]=e;form.addRow(label,e)
        if kind=='excluded':
            note=QLabel('保留原文、表头和参数供核对，不输出此病例列，也不影响其他字段生成。');note.setWordWrap(True);form.addRow(note)
        elif kind in ('mean_sd','quantile'):
            for key,label in ([('mean','均数'),('sd','标准差')] if kind=='mean_sd' else [('q1','第1四分位数 Q1'),('median','中位数'),('q3','第3四分位数 Q3')]):entry(key,label,f.get(key))
            for key,label in [('lower','下限（均数型可留空）'),('upper','上限（均数型可留空）')]:entry(key,label,f.get(key))
            self.numeric_parity=None
            if kind=='mean_sd':
                self.numeric_parity=QComboBox()
                for label,value in [('任意数值','any'),('奇数','odd'),('偶数','even')]:self.numeric_parity.addItem(label,value)
                self.numeric_parity.setCurrentIndex(max(0,self.numeric_parity.findData(f.get('parity','any'))));form.addRow('数值类型',self.numeric_parity)
            self.digits=QSpinBox();self.digits.setRange(0,4);self.digits.setValue(f.get('digits',2));form.addRow('小数位（0为整数）',self.digits)
            if kind=='quantile':
                note=QLabel('请确认原文括号内是Q1、Q3。尾部上下限是模拟假设，不是原文的最小/最大值；可修改后确认。');note.setWordWrap(True);form.addRow(note)
        elif kind=='derived':
            entry('from_field','来源字段',f.get('from_field',''));entry('positive_labels','计为有效的类别（用、分隔）','、'.join(f.get('positive_labels',[])))
        else:
            note=QLabel('原组例数：'+str(f.get('source_n') or '未报告')+'。类别顺序与原文一致；按当前例数换算人数后随机打乱。');note.setWordWrap(True);note.setObjectName('fieldEditorPath');form.addRow(note)
            self.categories=QTableWidget(0,2);self.categories.setHorizontalHeaderLabels(['输出类别','占比（%）']);self.categories.verticalHeader().hide();self.categories.verticalHeader().setDefaultSectionSize(40)
            self.categories.setMinimumWidth(340);self.categories.setAlternatingRowColors(True)
            for label,weight in zip(f.get('labels',['类别1','类别2']),f.get('weights',[None,None])):self.add_category(label,weight)
            form.addRow(self.categories)
            actions=QWidget();row=QHBoxLayout(actions);row.setContentsMargins(0,0,0,0);row.setSpacing(10)
            add=QPushButton('＋ 添加类别');add.clicked.connect(lambda:self.add_category('',None));row.addWidget(add)
            drop=QPushButton('删除选中类别');drop.clicked.connect(self.remove_category);row.addWidget(drop);row.addStretch();form.addRow(actions)
            QTimer.singleShot(0,self.sync_category_height)
        QTimer.singleShot(0,self.fit_content)

    def sync_category_height(self):
        from .resizable_fields import keep_user_height
        table=self.categories
        if table is None:return
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Fixed);table.setColumnWidth(1,150)
        header=max(table.horizontalHeader().sizeHint().height(),table.horizontalHeader().height(),40)
        height=header+sum(table.rowHeight(i) for i in range(min(6,table.rowCount())))+2*table.frameWidth()+6
        table.setFixedHeight(keep_user_height(table,height))
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_layout.invalidate()

    def add_category(self,label,weight):
        i=self.categories.rowCount();self.categories.insertRow(i);self.categories.setItem(i,0,QTableWidgetItem(str(label)));self.categories.setItem(i,1,QTableWidgetItem('' if weight is None else f'{weight:.12g}'))
        self.sync_category_height()
        if self.isVisible():QTimer.singleShot(0,self.fit_content)

    def remove_category(self):
        self.categories.removeRow(self.categories.currentRow());self.sync_category_height();QTimer.singleShot(0,self.fit_content)

    def apply(self):
        try:
            kind=self.kind.currentData();f=convert(self.field,kind);f['confirmed']=True
            f['classification']=self.classification.text().strip()
            if f.get('aggregate_pending') and kind!='excluded':raise ValueError('总发生率的联合生成规则尚未确认，请先选择“仅保留来源，不生成”，或取消后删除此项。不能独立随机生成汇总率。')
            if kind=='unknown':raise ValueError('请选择数据类型。')
            if kind=='excluded':pass
            elif kind in ('mean_sd','quantile'):
                for key,e in self.inputs.items():f[key]=float(e.text()) if e.text().strip() else None
                f['digits']=self.digits.value()
                if kind=='mean_sd':f['parity']=self.numeric_parity.currentData()
                required=('mean','sd') if kind=='mean_sd' else ('q1','median','q3','lower','upper')
                if any(f.get(k) is None for k in required):raise ValueError('请补全数值参数。')
            elif kind=='derived':
                f['from_field']=self.inputs['from_field'].text().strip();f['positive_labels']=self.inputs['positive_labels'].text().split('、');f['labels']=['有效','无效']
            else:
                f['labels']=[self.categories.item(i,0).text().strip() for i in range(self.categories.rowCount())]
                f['weights']=[float(self.categories.item(i,1).text()) for i in range(self.categories.rowCount())]
                if kind=='binary01':f['labels']=[int(v) for v in f['labels']]
                if kind in ('binary','gender','yesno','binary01') and len(f['labels'])!=2:raise ValueError('二分类需要两个类别。')
                if any(not str(v).strip() for v in f['labels']) or len(set(f['labels']))!=len(f['labels']) or any(v<0 for v in f['weights']) or abs(sum(f['weights'])-100)>1e-6:raise ValueError('类别不能空白或重复，比例必须合计100%。')
            self.result_field=f;self.accept()
        except (ValueError,AttributeError) as exc:
            self.error.setText('请检查参数：'+str(exc));self.error.show();self.content_scroll.ensureWidgetVisible(self.error)


class TypedFieldControls:
    def setup_typed_fields(self,layout):
        self.typed_specs=[];self.typed_label=QLabel('其他表格字段：可更改数值、四分位数、男/女、有/无及自定义分类');layout.addWidget(self.typed_label)
        self.typed_table=QTableWidget(0,7);self.typed_table.setHorizontalHeaderLabels(['来源','输出列名','组别','数据类型','生成规则','Word原文','分类 / 上级表头']);self.typed_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for i,w in enumerate((60,220,130,220,200,240)):self.typed_table.setColumnWidth(i,w)
        self.typed_table.verticalHeader().setDefaultSectionSize(44);layout.addWidget(self.typed_table,1);self.typed_table.cellChanged.connect(self.typed_name_changed);self.set_typed_fields([])
    def set_typed_fields(self,fields):
        self.typed_specs=[convert(f,f['kind']) for f in fields];table=self.typed_table;table.blockSignals(True);table.setRowCount(0)
        table.horizontalHeaderItem(2).setText('数据集' if fields and all(f.get('source_kind')=='ungrouped_table' for f in fields) else '组别')
        for i,f in enumerate(self.typed_specs):
            table.insertRow(i)
            for col,value in ((0,str(f.get('table',0))),(1,f['name']),(2,f['group']),(5,f.get('raw','')),(6,f.get('classification',''))):
                item=QTableWidgetItem(value);item.setToolTip(value+'\n原表头：'+' → '.join(f.get('header_path',[]))+'\n'+f.get('review_note',''))
                if col not in (1,6):item.setFlags(item.flags()&~Qt.ItemIsEditable)
                table.setItem(i,col,item)
            kinds=QComboBox()
            for key,label in TYPES:kinds.addItem(label,key)
            kinds.setCurrentIndex(max(0,kinds.findData(f['kind'])));kinds.currentIndexChanged.connect(lambda _,row=i,c=kinds:self.change_typed_kind(row,c.currentData()));table.setCellWidget(i,3,kinds)
            edit=QPushButton('编辑参数' if f.get('confirmed') else '汇总项：待确认' if f.get('aggregate_pending') else '确认类别 / 参数');edit.setToolTip(f.get('review_note','双击分类列可修改上级分类；类别名称在此编辑'));edit.clicked.connect(lambda _,row=i:self.edit_typed_field(row));table.setCellWidget(i,4,edit)
            if not f.get('confirmed'):table.item(i,1).setBackground(QColor('#FFF0D8'))
        table.blockSignals(False);table.setVisible(bool(fields));self.typed_label.setVisible(bool(fields))
        self.metrics.setVisible(bool(self.metrics.rowCount()) or not fields)
        if hasattr(self,'source_tables'):self.source_tables.schedule()
    def typed_name_changed(self,row,col):
        if col not in (1,6) or row>=len(self.typed_specs):return
        if col==6:
            name=self.typed_specs[row]['name'];value=self.typed_table.item(row,6).text().strip()
            self.typed_table.blockSignals(True)
            for i,field in enumerate(self.typed_specs):
                if field['name']==name:field['classification']=value;self.typed_table.item(i,6).setText(value)
            self.typed_table.blockSignals(False);return
        old=self.typed_specs[row]['name'];new=self.typed_table.item(row,1).text().strip()
        self.typed_table.blockSignals(True)
        for i,f in enumerate(self.typed_specs):
            if f['name']==old:f['name']=new;self.typed_table.item(i,1).setText(new)
            if f.get('from_field')==old:f['from_field']=new
        self.typed_table.blockSignals(False)
    def change_typed_kind(self,row,kind):
        if row>=len(self.typed_specs):return
        name=self.typed_specs[row]['name'];source=self.typed_specs[row].get('table')
        for i,f in enumerate(self.typed_specs):
            if f['name']==name and f.get('table')==source:self.typed_specs[i]=convert(f,kind)
        for i,f in enumerate(self.typed_specs):
            if f['name']!=name or f.get('table')!=source:continue
            combo=self.typed_table.cellWidget(i,3);combo.blockSignals(True);combo.setCurrentIndex(combo.findData(kind));combo.blockSignals(False)
            self.typed_table.cellWidget(i,4).setText('编辑参数' if f.get('confirmed') else '确认类别 / 参数')
            self.typed_table.item(i,1).setBackground(QColor('transparent' if f.get('confirmed') else '#FFF0D8'))
        if hasattr(self,'source_tables'):self.source_tables.schedule()
    def edit_typed_field(self,row):
        dialog=FieldDialog(self.typed_specs[row],self)
        self.field_dialog=dialog
        try:
            accepted=dialog.exec()==QDialog.Accepted
        finally:
            self.field_dialog=None;dialog.deleteLater()
        if not accepted:return
        result=dialog.result_field;self.typed_specs[row]=result
        if dialog.sync.isChecked():
            for i,f in enumerate(self.typed_specs):
                if i==row or f['name']!=result['name'] or f.get('table')!=result.get('table'):continue
                other=convert(f,result['kind'])
                # Synchronizing schema never confirms a peer's missing parameters.
                other['confirmed']=bool(f.get('confirmed',False) and f['kind']==result['kind'])
                other['classification']=result.get('classification','')
                if other.get('aggregate_pending') and result['kind']!='excluded':other['confirmed']=False
                if result['kind'] in ('category','binary','gender','yesno','binary01'):
                    if len(other.get('weights',[]))!=len(result['labels']):other['weights']=[None]*len(result['labels']);other['confirmed']=False
                    other['labels']=deepcopy(result['labels'])
                required=('mean','sd') if other['kind']=='mean_sd' else ('q1','median','q3','lower','upper') if other['kind']=='quantile' else ()
                if any(not isinstance(other.get(key),(int,float)) or isinstance(other.get(key),bool) or not math.isfinite(other[key]) for key in required):other['confirmed']=False
                if other['kind'] in ('category','binary','gender','yesno','binary01') and any(value is None for value in other.get('weights',[])):other['confirmed']=False
                self.typed_specs[i]=other
        self.set_typed_fields(self.typed_specs)
    def convert_numeric_field(self,combo,kind):
        row=next((i for i in range(self.metrics.rowCount()) if self.metrics.cellWidget(i,8) is combo),None)
        if row is None:return
        name=self.metrics.item(row,1).text();source=self.metrics.item(row,0).text();fields=list(self.typed_specs)
        for i in reversed(range(self.metrics.rowCount())):
            if self.metrics.item(i,1).text()!=name or self.metrics.item(i,0).text()!=source:continue
            def val(col):return self.metrics.item(i,col).text() if self.metrics.item(i,col) else ''
            f=dict(table=int(val(0)) if val(0).isdigit() else 0,name=name,group=self.metrics.cellWidget(i,2).currentData(),kind='mean_sd',mean=float(val(3)) if val(3) else None,sd=float(val(4)) if val(4) else None,digits=int(val(5)),lower=float(val(6)) if val(6) else None,upper=float(val(7)) if val(7) else None,raw=val(9),confirmed=True)
            fields.append(convert(f,kind));self.metrics.removeRow(i)
        self.set_typed_fields(fields)
