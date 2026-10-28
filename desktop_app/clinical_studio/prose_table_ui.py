"""Editable vertical summary table, source evidence and validated JSON handoff."""
from copy import deepcopy
import json
from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPlainTextEdit,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QComboBox,
    QFileDialog,QInputDialog,QCheckBox,QSplitter)
from .editor_dialogs import get_text
from .prose_table_engine import (parse_document,validate_study,to_simulation_config,
    read_docx_text,save_document,load_document,PAIR,QUANTILE,RANGE)

TYPES={'mean_sd':'均数±标准差','category':'分类人数','quantile':'中位数(Q1,Q3)','range':'仅范围','unknown':'待补充'}


def format_value(v,cell,part):
    if not cell: return ''
    if part=='category': return str(cell.get('counts',{}).get(v['_label'],''))
    if part in ('lower','upper'): return str(cell.get(part,'')) if cell.get(part) is not None else ''
    if v['kind']=='mean_sd': return f"{cell['mean']:g}±{cell['sd']:g}" if 'mean' in cell and 'sd' in cell else ''
    if v['kind']=='quantile': return f"{cell['median']:g}({cell['q1']:g},{cell['q3']:g})" if all(k in cell for k in ('median','q1','q3')) else ''
    if v['kind']=='range': return f"{cell['lower']:g}～{cell['upper']:g}" if all(k in cell for k in ('lower','upper')) else ''
    return ''


class ProseTableEditor(QWidget):
    def __init__(self,parent=None,embedded=False):
        super().__init__(parent);self.document=None;self.rows=[];self.editing=False;self.stale=False;self.precision_mode=lambda:'source'
        self.setWindowTitle('正文转可编辑汇总表');self.resize(1280,900)
        self.setStyleSheet('QWidget{background:#F5F8F5;color:#193C2C;} QPlainTextEdit,QTableWidget{background:white;} QPushButton{padding:7px 12px;}')
        layout=QVBoxLayout(self)
        intro=QLabel('粘贴一项研究的正文，或导入 Word。空行分隔的文字会分别生成表格；组别分段请使用普通换行。');intro.setWordWrap(True);layout.addWidget(intro)
        self.source=QPlainTextEdit();self.source.setPlaceholderText('对照组男17例、女13例，年龄……；试验组……');self.source.setMaximumHeight(145);layout.addWidget(self.source)
        top=QHBoxLayout();layout.addLayout(top)
        self.add_button(top,'导入 Word 正文',self.import_word).setVisible(not embedded)
        self.add_button(top,'识别并生成竖表',self.convert)
        self.add_button(top,'填写自定义组名',self.custom_groups)
        self.add_button(top,'打开表格 JSON',self.open_json).setVisible(not embedded)
        self.add_button(top,'保存表格 JSON',self.save_json)
        self.add_button(top,'导出模拟模块配置',self.export_config).setVisible(not embedded)
        self.selector=QComboBox();self.selector.currentIndexChanged.connect(self.render);top.addWidget(self.selector)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.add_button(actions,'删除选中指标',self.remove_variable)
        self.add_button(actions,'添加指标',self.add_variable)
        self.add_button(actions,'确认选中单元格的当前值',self.resolve_cell)
        self.reviewed=QCheckBox('已核对未识别内容');self.reviewed.setChecked(False);self.reviewed.toggled.connect(self.review_unparsed);actions.addWidget(self.reviewed)
        hint=QLabel('双击数值、指标名、类别或单位即可修改；类型可切换。年龄范围属于年龄参数，分类展开行仍是同一个变量。点击单元格可查看原文。');hint.setWordWrap(True);layout.addWidget(hint)
        split=QWidget();panels=QVBoxLayout(split);panels.setContentsMargins(0,0,0,0);layout.addWidget(split,1)
        self.table=QTableWidget();self.table.setWordWrap(False);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive);self.table.verticalHeader().hide();self.table.setFixedHeight(300);panels.addWidget(self.table)
        self.evidence=QPlainTextEdit();self.evidence.setReadOnly(True);self.evidence.setPlaceholderText('点击表格单元格查看原文、来源和修改记录');self.evidence.setFixedHeight(120);panels.addWidget(self.evidence)
        self.status=QPlainTextEdit();self.status.setReadOnly(True);self.status.setFixedHeight(110);panels.addWidget(self.status)
        self.groups_override=None
        if embedded:self.source.setMaximumHeight(85)
        self.table.cellChanged.connect(self.cell_changed);self.table.currentCellChanged.connect(lambda r,c,*_:self.show_evidence(r,c))
        self.source.textChanged.connect(self.source_changed)

    def add_button(self,layout,label,callback):
        button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button);return button

    def study(self):
        index=self.selector.currentIndex()
        return self.document['studies'][index] if self.document and 0<=index<len(self.document['studies']) else None

    def source_changed(self):
        if self.document:
            self.stale=self.source.toPlainText()!=self.document['source_text']
            self.report()

    def custom_groups(self):
        value,ok=get_text(self,'组别原名','多个组名以逗号分隔，例如：A组,B组',text=','.join(self.groups_override or []))
        if ok:self.groups_override=[s.strip() for s in re.split('[,，]',value) if s.strip()] or None

    def import_word(self):
        path,_=QFileDialog.getOpenFileName(self,'选择 Word 正文','','Word (*.docx *.doc)')
        if path:
            try:self.source.setPlainText(read_docx_text(path));self.convert()
            except Exception as exc:self.status.setPlainText('导入失败：'+str(exc))

    def convert(self):
        if not self.source.toPlainText().strip():self.status.setPlainText('请先粘贴或导入正文。');return
        from .word_precision import prose_precision
        self.document=prose_precision(parse_document(self.source.toPlainText(),self.groups_override),self.precision_mode());self.stale=False;self.invalid_edit=None;self.refresh_selector()

    def refresh_selector(self):
        self.selector.blockSignals(True);self.selector.clear()
        for i,s in enumerate(self.document['studies']):self.selector.addItem(f'资料段 {i+1} · '+ ' / '.join(g['name'] for g in s['groups']))
        self.selector.blockSignals(False);self.render()

    def render(self):
        s=self.study();self.editing=True;self.table.blockSignals(True);self.table.clear();self.rows=[]
        if not s:
            self.reviewed.blockSignals(True);self.reviewed.setChecked(False);self.reviewed.blockSignals(False)
            self.table.setRowCount(0);self.table.blockSignals(False);self.editing=False;self.report();return
        groups=s['groups'];self.table.setColumnCount(5+len(groups));self.table.setHorizontalHeaderLabels(['指标','类别 / 参数','类型','单位']+[g['name'] for g in groups]+['提示'])
        self.rows=[(None,'n',None)]
        for vi,v in enumerate(s['variables']):
            if v['kind']=='category':
                self.rows.extend((vi,'category',label) for label in v['labels'])
            else:
                self.rows.append((vi,'summary',None))
                if v['name']=='年龄' or v['kind']=='quantile' or any(c.get('lower') is not None or c.get('upper') is not None for c in v['cells'].values()):
                    self.rows.extend([(vi,'lower',None),(vi,'upper',None)])
        self.table.setRowCount(len(self.rows))
        for ri,(vi,part,label) in enumerate(self.rows):
            v=s['variables'][vi] if vi is not None else None
            fixed={0:v['name'] if v else '样本量',1:label or {'n':'例数','summary':'统计值','lower':'下限（可空）','upper':'上限（可空）'}[part],3:v['unit'] if v else '例'}
            for col,value in fixed.items():
                item=QTableWidgetItem(value)
                if col==1 and part!='category' or v is None:item.setFlags(item.flags()&~Qt.ItemIsEditable)
                self.table.setItem(ri,col,item)
            if v:
                combo=QComboBox()
                for key,text in TYPES.items():combo.addItem(text,key)
                combo.setCurrentIndex(combo.findData(v['kind']));combo.currentIndexChanged.connect(lambda _,i=vi,c=combo:self.change_kind(i,c.currentData()))
                self.table.setCellWidget(ri,2,combo)
            for gi,g in enumerate(groups):
                cell=v['cells'].get(g['name']) if v else None
                value=str(g['n']) if v is None and g['n'] is not None else '' if v is None else format_value(dict(v,_label=label),cell,part)
                item=QTableWidgetItem(value)
                if not value and part not in ('lower','upper'):item.setBackground(QColor('#FFF0D8'));item.setToolTip('原文未报告或未识别，请补全')
                elif v is None and g['n_origin']=='inferred':item.setBackground(QColor('#FFF0D8'));item.setToolTip('由分类人数推算')
                self.table.setItem(ri,4+gi,item)
            messages=[]
            if v:
                for g in groups:
                    cell=v['cells'].get(g['name'])
                    if not cell:messages.append(g['name']+'缺失')
                    elif cell.get('issues'):messages.extend(cell['issues'])
                if v['kind']=='unknown':messages.append('只有名称，缺少参数')
                if v['kind']=='range':messages.append('仅范围，需补充统计类型和参数')
            else:messages=[g['name']+'例数为推算值' for g in groups if g['n_origin']=='inferred']
            item=QTableWidgetItem('；'.join(messages));item.setFlags(item.flags()&~Qt.ItemIsEditable);self.table.setItem(ri,4+len(groups),item)
        for col,width in enumerate([200,135,155,90]+[175]*len(groups)+[270]):self.table.setColumnWidth(col,width)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.reviewed.blockSignals(True);self.reviewed.setChecked(s.get('unparsed_reviewed',False));self.reviewed.blockSignals(False)
        self.table.blockSignals(False);self.editing=False;self.report()

    def cell_changed(self,row,col):
        if self.editing:return
        s=self.study();backup=deepcopy(s);vi,part,label=self.rows[row];v=s['variables'][vi] if vi is not None else None
        value=self.table.item(row,col).text().strip()
        try:
            if col==0 and v:v['name']=value
            elif col==1 and v and part=='category':
                if not value or value in v['labels']:raise ValueError('类别名称不能为空或重复')
                v['labels'][v['labels'].index(label)]=value
                for cell in v['cells'].values():
                    if label in cell['counts']:cell['counts'][value]=cell['counts'].pop(label)
            elif col==3 and v:v['unit']=value
            elif 4<=col<4+len(s['groups']):
                g=s['groups'][col-4]
                if v is None:
                    n=int(value)
                    if not 2<=n<=5000:raise ValueError('例数须为2～5000')
                    g.setdefault('edits',[]).append({'previous':g['n'],'value':n});g.update(n=n,n_origin='edited',issues=[])
                else:
                    cell=v['cells'].setdefault(g['name'],{'evidence':[],'issues':[]})
                    before=deepcopy(cell);cell.setdefault('edits',[]).append({'part':part,'value':value})
                    if part=='category':
                        if value:
                            number=int(value)
                            if number<0:raise ValueError('人数不能为负数')
                            cell.setdefault('counts',{})[label]=number
                        else:cell.setdefault('counts',{}).pop(label,None)
                    elif part in ('lower','upper'):cell[part]=float(value) if value else None
                    elif v['kind']=='mean_sd':
                        m=PAIR.fullmatch(value.replace(' ',''))
                        if not m:raise ValueError('请输入均数±标准差，如65.38±7.42')
                        cell.update(mean=float(m[1]),sd=float(m[2]),digits=max(len(x.split('.')[1]) if '.' in x else 0 for x in (m[1],m[2])))
                    elif v['kind']=='quantile':
                        m=QUANTILE.fullmatch(value.replace('（','(').replace('）',')').replace(' ',''))
                        if not m:raise ValueError('请输入中位数(Q1,Q3)')
                        cell.update(median=float(m[1]),q1=float(m[2]),q3=float(m[3]))
                    elif v['kind']=='range':
                        m=RANGE.fullmatch(value)
                        if not m:raise ValueError('请输入下限～上限')
                        cell.update(lower=float(m[1]),upper=float(m[2]))
                    else:raise ValueError('请先选择数据类型')
                    cell.pop('input_error',None);cell.pop('reviewed',None)
            self.render();self.table.setCurrentCell(row,col)
        except (ValueError,KeyError) as exc:
            self.document['studies'][self.selector.currentIndex()]=backup
            self.render()
            self.status.setPlainText('本次修改未应用，已保留修改前的值：'+str(exc))
            return
        self.invalid_edit=None

    def change_kind(self,index,kind):
        if self.editing:return
        v=self.study()['variables'][index];v['kind']=kind
        if kind=='category' and not v['labels']:v['labels']=['类别1','类别2']
        for cell in v['cells'].values():
            if kind=='category':cell.setdefault('counts',{})
        self.render()

    def add_variable(self):
        s=self.study()
        if not s:return
        name,ok=get_text(self,'添加指标','指标名称')
        if ok and name.strip():s['variables'].append(dict(name=name.strip(),kind='mean_sd',unit='',labels=[],cells={}));self.render()

    def remove_variable(self):
        row=self.table.currentRow()
        if row>=0 and self.rows[row][0] is not None:
            self.study()['variables'].pop(self.rows[row][0]);self.render()

    def resolve_cell(self):
        row,col=self.table.currentRow(),self.table.currentColumn();s=self.study()
        if row<0 or not 4<=col<4+len(s['groups']):return
        vi,_,_=self.rows[row]
        if vi is not None:
            cell=s['variables'][vi]['cells'].get(s['groups'][col-4]['name'])
            if cell:cell['issues']=[];cell['reviewed']=True
        self.render()

    def show_evidence(self,row,col):
        s=self.study()
        if not s or row<0 or row>=len(self.rows):return
        vi,_,_=self.rows[row]
        g=s['groups'][col-4] if 4<=col<4+len(s['groups']) else None
        obj=(s['variables'][vi]['cells'].get(g['name'],{}) if vi is not None and g else g or {})
        self.evidence.setPlainText('选中单元格的原文与修改记录：\n'+json.dumps(obj,ensure_ascii=False,indent=2)+'\n\n本资料段原文（保留不变）：\n'+s['source_text'])

    def review_unparsed(self,checked):
        if self.study():self.study()['unparsed_reviewed']=checked;self.report()

    def report(self):
        s=self.study()
        if not s:return
        result=validate_study(s)
        messages=(['输入文字已变化，请重新识别后再导出。'] if self.stale else [])
        messages+=['待补充 / 冲突：'+m for m in result['errors']]+['提示：'+m for m in result['warnings']]
        messages+=['原文注释：'+n['raw'] for n in s['notes']]
        self.status.setPlainText('\n'.join(messages) or '校验通过，可以导出模拟模块配置。')

    def check_export(self):
        if self.stale:raise ValueError('输入文字已变化，请重新识别。')
        if getattr(self,'invalid_edit',None):raise ValueError('请先更正无效的单元格修改。')
        if not self.study():raise ValueError('请先生成表格。')

    def save_json(self):
        try:
            self.check_export()
            path,_=QFileDialog.getSaveFileName(self,'保存含原文的结构化表格','','JSON (*.json)')
            if path:save_document(self.document,path);self.status.setPlainText('已保存表格、原文和缺失状态：'+path)
        except Exception as exc:self.status.setPlainText(str(exc))

    def open_json(self):
        path,_=QFileDialog.getOpenFileName(self,'打开结构化表格','','JSON (*.json)')
        if path:
            try:
                document=load_document(path);self.document=None;self.source.setPlainText(document['source_text']);self.document=document;self.stale=False;self.invalid_edit=None;self.refresh_selector()
            except Exception as exc:self.status.setPlainText('打开失败：'+str(exc))

    def export_config(self):
        try:
            self.check_export();config=to_simulation_config(self.study())
            path,_=QFileDialog.getSaveFileName(self,'导出当前资料段的模拟模块配置','','JSON (*.json)')
            if path:Path(path).write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');self.status.setPlainText('已导出兼容配置：'+path)
        except Exception as exc:self.status.setPlainText('暂不能导出模拟配置：\n'+str(exc))


def main():
    app=QApplication.instance() or QApplication([])
    editor=ProseTableEditor();editor.show();app.exec()


if __name__=='__main__':main()
