"""Editable import drafts remain separate until the user confirms their groups."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QLabel,QPlainTextEdit
from .editor_dialogs import EditorDialog
from .typed_field_ui import TypedFieldControls
from .prose_table_ui import ProseTableEditor
from .word_scan import scan_report
from .widgets import scroll


class PreviewFields(TypedFieldControls,QWidget):
    def __init__(self,fields):
        super().__init__();layout=QVBoxLayout(self);self.metrics=QTableWidget();self.metrics.hide()
        self.setup_typed_fields(layout);self.set_typed_fields(fields)
        self.typed_label.setText('可修改字段名、类型、类别和上级分类。这里只保存识别草稿；未分组数据是内部数据集标识，不是原文组别。')
        self.typed_table.setMinimumHeight(280)
        self.metrics.hide()


class WordScanDialog(EditorDialog):
    def __init__(self,parent,scan,draft):
        super().__init__(parent,'Word 导入预览','可先检查原表和修改识别草稿。有组别时再确认组别；无分组竖表只需核对例数。',size=(1160,850))
        self.scan=scan;self.draft=deepcopy(draft);self.tabs=QTabWidget();self.body_layout.setAlignment(Qt.AlignmentFlag(0));self.body_layout.addWidget(self.tabs,1)
        overview=QWidget();layout=QVBoxLayout(overview)
        summary=QLabel('候选组别：'+('、'.join(scan['candidates']) or ('无分组竖表，无需填写组名' if scan.get('has_ungrouped') else '未识别，可返回手动填写')));summary.setWordWrap(True);layout.addWidget(summary)
        self.inventory=QTableWidget(len(scan['tables']),4);self.inventory.setHorizontalHeaderLabels(['表名','表格方向','行 / 列','候选组别']);self.inventory.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.inventory.setEditTriggers(QTableWidget.NoEditTriggers);self.inventory.setFixedHeight(180);layout.addWidget(self.inventory)
        self.inventory.horizontalHeader().setStretchLastSection(True)
        for column,width in enumerate((280,220,100)):self.inventory.setColumnWidth(column,width)
        for i,table in enumerate(scan['tables']):
            for j,value in enumerate((table['title'],table['orientation'],f"{len(table['rows'])} / {table['columns']}",'、'.join(table['groups']))):self.inventory.setItem(i,j,QTableWidgetItem(value))
        self.raw=QTableWidget();self.raw.setEditTriggers(QTableWidget.NoEditTriggers);self.raw.setMinimumHeight(260);layout.addWidget(self.raw)
        self.inventory.currentCellChanged.connect(lambda row,*_:self.show_raw(row));self.tabs.addTab(scroll(overview),'表名与原表')
        self.fields=PreviewFields(draft['fields']);self.tabs.addTab(scroll(self.fields),'表格识别草稿')
        self.prose=ProseTableEditor(embedded=True);self.prose.precision_mode=lambda:parent.decimal_mode.currentData();self.prose.source.setPlainText(draft['prose_document']['source_text']);self.prose.document=deepcopy(draft['prose_document']);self.prose.stale=draft.get('prose_stale',False);self.prose.refresh_selector();self.tabs.addTab(scroll(self.prose),'文字识别草稿')
        text=QPlainTextEdit();text.setReadOnly(True);text.setPlainText(scan['prose_text']);self.tabs.addTab(text,'完整正文')
        self.add_buttons('保存预览草稿','取消')
        if scan['tables']:self.inventory.setCurrentCell(0,0);self.show_raw(0)
    def show_raw(self,index):
        if not 0<=index<len(self.scan['tables']):return
        table=self.scan['tables'][index];self.raw.setColumnCount(table['columns']);self.raw.setRowCount(len(table['rows']));self.raw.setHorizontalHeaderLabels([f'列{i+1}' for i in range(table['columns'])])
        for r,row in enumerate(table['rows']):
            for c,value in enumerate(row):self.raw.setItem(r,c,QTableWidgetItem(value))
        self.raw.resizeColumnsToContents()
    def accept(self):
        self.draft['fields']=deepcopy(self.fields.typed_specs)
        if self.prose.document:
            self.draft['prose_document']=deepcopy(self.prose.document);self.draft['prose_document']['source_text']=self.prose.source.toPlainText();self.draft['prose_stale']=self.prose.stale
        super().accept()
