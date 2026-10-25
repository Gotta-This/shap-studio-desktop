"""The approved Penpot screens, connected to the complete existing workflows."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import json
import math
import shutil

from PySide6.QtCore import Qt,QTimer,QRectF,QPointF
from PySide6.QtGui import QColor,QFont,QPainter,QPixmap,QPen
from PySide6.QtWidgets import (
    QMainWindow,QWidget,QStackedWidget,QDialog,QVBoxLayout,QHBoxLayout,QDialogButtonBox,QPushButton,
    QFileDialog,QMessageBox,QMenu,QLineEdit,QTableWidgetItem,QPlainTextEdit,
    QComboBox,QFontComboBox,QCheckBox,QDoubleSpinBox,QSpinBox,QApplication,QAbstractItemView,QScrollArea,QFrame,QLabel,QRadioButton,
)
from .design_surface import DesignBoard,DesignView,DesignRegion,ParameterScrollArea
from .config import ROOT,PLOT_NAMES

PLOT_ORDER=['bar','summary','force','waterfall','dependence_protective','dependence_risk']
KEY_FOR_BOARD={0:None,1:'category',2:'numeric',3:'word',4:'shap',5:'shap',6:'shap',7:'shap',8:None}


def set_field(field,value):
    from .widgets import ColorField,FileField
    e=field.editor
    if isinstance(e,(ColorField,FileField)):e.text.setText('' if value is None else str(value))
    elif field.key=='font_family':e.setCurrentFont(QFont(value[0] if isinstance(value,list) else str(value)))
    elif hasattr(field,'pair'):
        for spin,v in zip(field.pair,value):spin.setValue(v)
    elif isinstance(e,QDoubleSpinBox):
        v=float(value)*(100 if field.percent else 1)
        if not math.isfinite(v) or not e.minimum()<=v<=e.maximum():raise ValueError('数值超出允许范围')
        e.setValue(v)
    elif isinstance(e,QSpinBox):
        if int(value)!=float(value) or not e.minimum()<=int(value)<=e.maximum():raise ValueError('请输入允许范围内的整数')
        e.setValue(int(value))
    elif isinstance(e,QCheckBox):e.setChecked(bool(value))
    elif isinstance(e,QComboBox):e.setCurrentIndex(e.findData(value))
    else:e.setText(str(value))


class Binding:
    def __init__(self,editor,getter,setter,parse=str,format_value=None):
        self.editor,self.getter,self.setter,self.parse=editor,getter,setter,parse
        self.format=format_value or (lambda v:format(v,'.8g') if isinstance(v,float) else str(v))
        self.dirty=False;editor.textEdited.connect(self.edited);self.refresh()
    def edited(self,*args):self.dirty=True
    def commit(self):
        if self.dirty:
            value=self.parse(self.editor.text());self.setter(value);self.dirty=False
    def refresh(self):
        if not self.dirty and not self.editor.hasFocus():
            value=self.format(self.getter())
            if self.editor.text()!=value:self.editor.setText(value)


class MiniHistogram(QWidget):
    def __init__(self):
        super().__init__();self.values=[];self.setAccessibleName('数据分布图：横轴数值，纵轴频数')
    def distribution(self):
        low,high=(min(self.values),max(self.values)) if self.values else (0.,1.)
        if low==high:
            padding=max(abs(low)*.05,1.);low-=padding;high+=padding
        counts=[0]*8
        for v in self.values:counts[min(7,int((v-low)/(high-low)*8))]+=1
        peak=max(counts) or 1
        step=max(1,math.ceil(peak/4));top=step*math.ceil(peak/step)
        return dict(low=low,high=high,counts=counts,top=top,step=step)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        font=QFont('Noto Sans SC');font.setPixelSize(10);p.setFont(font)
        d=self.distribution();plot=QRectF(48,14,max(1,self.width()-80),max(1,self.height()-59))
        for value in range(0,d['top']+1,d['step']):
            y=plot.bottom()-value/d['top']*plot.height();p.setPen(QPen(QColor('#DEE8DF'),.7));p.drawLine(QPointF(plot.left(),y),QPointF(plot.right(),y))
            p.setPen(QColor('#637668'));p.drawText(QRectF(17,y-8,25,16),Qt.AlignRight|Qt.AlignVCenter,str(value))
        p.setPen(Qt.NoPen);bar_width=plot.width()/8
        for i,n in enumerate(d['counts']):
            h=plot.height()*n/d['top'];p.setBrush(QColor('#277453' if n==max(d['counts']) else '#A8D4B8'))
            if n:p.drawRoundedRect(QRectF(plot.left()+i*bar_width+2,plot.bottom()-h,bar_width-4,h),3,3)
        p.setPen(QPen(QColor('#738477'),1));p.drawLine(plot.bottomLeft(),plot.bottomRight());p.drawLine(plot.bottomLeft(),plot.topLeft())
        for i in range(3):
            x=plot.left()+plot.width()*i/2;value=d['low']+(d['high']-d['low'])*i/2
            p.drawLine(QPointF(x,plot.bottom()),QPointF(x,plot.bottom()+4))
            p.drawText(QRectF(x-38,plot.bottom()+6,76,18),Qt.AlignCenter,f'{value:.4g}')
        p.setPen(QColor('#314C3E'));p.drawText(QRectF(plot.left(),self.height()-18,plot.width(),18),Qt.AlignCenter,'数值')
        p.save();p.translate(8,plot.center().y());p.rotate(-90);p.drawText(QRectF(-40,-9,80,18),Qt.AlignCenter,'频数');p.restore()
        if not self.values:p.drawText(plot,Qt.AlignCenter,'生成后显示分布')


class RemoveCategoryButton(QPushButton):
    """A clear vector minus in a 28px target, with a larger clickable cell."""
    def __init__(self,row,enabled):
        super().__init__();self.row=row;self.setEnabled(enabled)
        self.setAccessibleName(f'删除第{row+1}个类别');self.setToolTip('删除这个类别' if enabled else '至少保留一个类别')
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self.setStyleSheet('QPushButton{border:0;background:transparent;padding:0;}')
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#F9FBF9' if self.row%2 else '#FFFFFF'))
        active=self.isEnabled() and (self.underMouse() or self.isDown())
        p.setPen(QPen(QColor('#DEE8DF'),1));p.drawLine(0,self.height()-1,self.width(),self.height()-1)
        box=QRectF((self.width()-28)/2,(self.height()-28)/2,28,28)
        p.setPen(QPen(QColor('#E3BFB9' if active else '#DEE8DF'),1));p.setBrush(QColor('#FAEDE9' if active else '#F1F7F3'));p.drawRoundedRect(box,7,7)
        color='#B34334' if active else ('#277453' if self.isEnabled() else '#B8C8BD')
        p.setPen(QPen(QColor(color),2,Qt.SolidLine,Qt.RoundCap));p.drawLine(QPointF(box.center().x()-5,box.center().y()),QPointF(box.center().x()+5,box.center().y()))
        if self.hasFocus():p.setPen(QPen(QColor('#277453'),1,Qt.DotLine));p.setBrush(Qt.NoBrush);p.drawRoundedRect(box.adjusted(-2,-2,2,2),8,8)


class PlotImage(QWidget):
    def __init__(self):super().__init__();self.path=None;self.pixmap=QPixmap()
    def show_path(self,path):
        path=str(path) if path else None
        if path!=self.path:self.path=path;self.pixmap=QPixmap(path) if path else QPixmap();self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        if not self.pixmap.isNull():
            image=self.pixmap.scaled(self.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation)
            p.drawPixmap((self.width()-image.width())//2,(self.height()-image.height())//2,image)
        else:
            p.setPen(QColor('#738477'));p.drawText(self.rect(),Qt.AlignCenter,'生成后显示实际图表')


class DesktopWindow(QMainWindow):
    def __init__(self,config=None,output=None):
        super().__init__();self.setWindowTitle('科研数据工具集');self.resize(1440,960);self.setMinimumSize(1008,672)
        self.initial_config=deepcopy(config);self.initial_output=output
        self.modules={};self.module_pages={};self.boards={};self.views={};self.bindings={};self.current_module=None;self.board_index=0
        self.launch_buttons={};self.nav_buttons={};self.style_key='bar';self.image_index=0;self._last_state=None
        self.stack=QStackedWidget();self.setCentralWidget(self.stack);self.show_board(0,commit=False)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(200)

    def controller(self,key):
        if key not in self.modules:
            if key=='category':
                from .data_tools import CategoryTool
                tool=CategoryTool()
            elif key=='numeric':
                from .data_tools import NumericTool
                tool=NumericTool()
            elif key=='word':
                from .word_batch import WordBatchTool
                tool=WordBatchTool()
            else:
                from .app import MainWindow
                tool=MainWindow(self.initial_config,self.initial_output,embedded=True)
                tool.setWindowFlags(Qt.Widget);tool.setMinimumSize(0,0)
            tool.setParent(self);tool.hide();self.modules[key]=tool
        return self.modules[key]

    def bind(self,b,x,y,w,name,getter,setter,parse=str,format_value=None):
        editor=b.input(x,y,w,name);binding=Binding(editor,getter,setter,parse,format_value)
        self.bindings.setdefault(b.index,[]).append(binding);return editor

    def bind_field(self,b,x,y,w,name,section,key,parse=float):
        def field():
            tool=self.controller('shap')
            forms={'data':tool.data_editor.general,'model':tool.model_form,'explanation':tool.explanation_form,'export':tool.export_form}
            return forms[section].fields[key]
        return self.bind(b,x,y,w,name,lambda:field().value(),lambda v:set_field(field(),v),parse)

    def commit(self):
        try:
            for board in self.boards.values():
                for control in board.controls.values():
                    if control.property('input-errors'):raise ValueError('请修正表格中标红的所有无效参数。')
            for control in self.boards[self.board_index].controls.values():
                if control.property('input-error'):raise ValueError(control.property('input-error'))
            for binding in self.bindings.get(self.board_index,[]):binding.commit()
            return True
        except (ValueError,TypeError,OverflowError) as exc:
            QMessageBox.warning(self,'请检查参数','请填写有效数值。\n'+str(exc));return False

    def show_home(self):self.show_board(0)
    def open_module(self,key):
        self.show_board({'category':1,'numeric':2,'word':3,'shap':4}[key]);return self.modules[key]

    def show_board(self,index,commit=True):
        if commit and not self.commit():return
        key=KEY_FOR_BOARD[index]
        if key:self.controller(key)
        if index not in self.boards:
            board=DesignBoard(index);self.boards[index]=board;self.build_shell(board)
            getattr(self,'build_'+['home','category','numeric','word','data','model','style','results','system'][index])(board)
            view=DesignView(board);self.views[index]=view;self.stack.addWidget(view)
            if key and key not in self.module_pages:self.module_pages[key]=board
        self.board_index=index;self.current_module=key;self.stack.setCurrentWidget(self.views[index])
        if index==6:
            editor=self.style_editor();editor.selector.setCurrentIndex(editor.selector.findData(self.style_key))
        self.home_button=self.boards[index].controls['nav-home']
        self.nav_buttons={None:self.home_button,**{k:self.boards[index].controls['nav-'+k] for k in ('category','numeric','word','shap')}}
        for name,button in self.nav_buttons.items():
            button.setChecked(name==key);button.clearFocus()
        self.setWindowTitle(self.boards[index].spec['name'].split(' · ',1)[-1]+' · 科研数据工具集')
        self._last_state=None;self.refresh(force=True)

    def build_shell(self,b):
        # Use the same image as the packaged application, replacing the drawn glyph.
        if b.index==0:b.text(1252,125,'欢迎回来宝宝 🥰')
        b.suppress(24,28,44,40)
        brand=PlotImage();brand.show_path(ROOT/'assets'/'icon.png')
        b.place(brand,(24,28,40,40),'brand-icon')
        # Hide the original status badge, local-execution card and wide footer.
        b.suppress(1230,12,160,48)
        for shape in b.spec['shapes']:
            if (shape['x']<224 and shape['y']>=767) or (shape['x']>=224 and shape['y']>=890):b.hidden_shapes.add(shape['id'])
        footer=QLabel('独立参数 · 独立结果 · 自主导出\n科研数据工具集 / UI 2.0\ndbq / 科研工作空间')
        footer.setWordWrap(True);footer.setAlignment(Qt.AlignLeft|Qt.AlignBottom)
        footer.setStyleSheet('QLabel{background:transparent;color:#738477;font-size:11px;line-height:140%;padding:0;}')
        b.place(footer,(20,b.height()-110,184,90),'sidebar-footer')
        for i,(name,target) in enumerate([('home',0),('category',1),('numeric',2),('word',3),('shap',4)]):
            button=b.hotspot((16,141+i*56,192,44),lambda checked=False,t=target:self.show_board(t),'nav-'+name)
            button.setCheckable(True)
            button.setStyleSheet('QPushButton{border:none;background:transparent;padding:0;} QPushButton:focus{border:none;outline:none;background:transparent;}')
        if b.index:
            b.hotspot((1240,120,140,28),lambda:self.parameter_menu(),'all-parameters')
            b.controls['all-parameters'].setToolTip('全部参数、配置文件与更多操作')
        if b.index in (4,5,6,7):
            for i in range(4):b.hotspot((260+i*278,203,264,44),lambda checked=False,t=i+4:self.show_board(t),'step-'+str(i+1))

    def build_home(self,b):
        for i,key in enumerate(('category','numeric','word','shap')):
            x=284+(i%2)*584;y=528+(i//2)*227
            self.launch_buttons[key]=b.hotspot((x,y,142,42),lambda checked=False,k=key:self.open_module(k),'launch-'+key)
    def build_system(self,b):pass

    def build_category(self,b):
        tool=self.modules['category']
        self.category_region=DesignRegion(b,(284,302,392,420))
        self.category_scroll=ParameterScrollArea();self.category_scroll.setFrameShape(QFrame.NoFrame)
        self.category_scroll.setWidgetResizable(False);self.category_scroll.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.category_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_scroll.setStyleSheet('QScrollArea{border:0;background:white;}')
        self.category_scroll.setWidget(self.category_region)
        b.place(self.category_scroll,(284,302,402,420),'category-parameters')
        region=self.category_region
        self.category_table=region.table((0,0,392,128),['类别值','数量',''],[125,197,70],'categories')
        self.category_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_scroll.route_wheel(self.category_table.viewport())
        self.category_scroll.route_wheel(self.category_table.horizontalHeader().viewport())
        self.category_table.cellChanged.connect(self.category_changed)
        region.hotspot((0,146,140,42),self.add_category,'add-category')
        self.bind(region,0,265,392,'category-seed',tool.seed.text,tool.seed.setText)
        for name in ('categories','add-category','category-seed'):b.controls[name]=region.controls[name]
        b.hotspot((284,770,392,42),lambda:self.generate('category'),'generate-category')
        b.hotspot((1117,234,90,42),tool.result.copy,'copy-category')
        b.hotspot((1219,234,156,42),tool.result.save,'save-category')
        b.suppress(748,415,632,255)
        self.category_output=QPlainTextEdit();self.category_output.setReadOnly(True)
        self.category_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.category_output.setToolTip('每行一个数值；点击复制后可直接粘贴到 Excel 的一列中。')
        self.category_output.setStyleSheet('QPlainTextEdit{background:#F8FBF8;border:1px solid #DEE8DF;border-radius:10px;padding:22px;color:#193C2C;font-size:20px;font-weight:500;}')
        b.place(self.category_output,(748,415,632,255),'category-values')
        details=b.hotspot((748,700,250,30),self.category_report,'category-report')
        details.setToolTip('查看原 R 代码的前10行、数据结构与各类别计数')
        self.sync_categories()

    def category_report(self):
        dialog=QDialog(self);dialog.setWindowTitle('类别数列 · 原代码结果核对');dialog.resize(720,650)
        layout=QVBoxLayout(dialog);text=QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText(self.modules['category'].original_report());layout.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.accept);layout.addWidget(buttons)
        dialog.exec();dialog.deleteLater()

    def sync_categories(self):
        tool=self.modules['category'];table=self.category_table;table.blockSignals(True);table.setRowCount(tool.table.rowCount())
        for row in range(tool.table.rowCount()):
            for col in (0,1):table.setItem(row,col,QTableWidgetItem(tool.table.item(row,col).text()))
            button=RemoveCategoryButton(row,table.rowCount()>1)
            button.clicked.connect(lambda checked=False,r=row:self.remove_category(r))
            table.setCellWidget(row,2,button)
        table.blockSignals(False)
        delta=44*(table.rowCount()-2)
        table.setFixedHeight(40+44*table.rowCount())
        self.category_region.expand_below(146,delta,420)
        self.category_region.controls['add-category'].move(0,146+delta)
        self.category_region.controls['category-seed'].move(12,273+delta)
    def category_changed(self,row,col):
        if col<2:
            tool=self.modules['category'];tool.table.item(row,col).setText(self.category_table.item(row,col).text())
    def add_category(self):
        self.modules['category'].add_row('1','1');self.sync_categories()
        self.category_scroll.ensureWidgetVisible(self.category_region.controls['add-category'],0,12)
    def remove_category(self,row):
        if self.modules['category'].table.rowCount()>1:self.modules['category'].table.removeRow(row);self.sync_categories()

    def build_numeric(self,b):
        tool=self.modules['numeric']
        def set_count(value):
            if not tool.n.minimum()<=value<=tool.n.maximum():raise ValueError('例数须在 2–5000 之间')
            tool.n.setValue(value)
        def set_digits(value):
            if tool.digits.findText(value)<0:raise ValueError('小数位数须在 0–4 之间')
            tool.digits.setCurrentText(value)
        for x,y,w,name,getter,setter,parse in [
            (284,325,392,'numeric-n',tool.n.value,set_count,int),
            (284,417,184,'numeric-mean',tool.mean.text,tool.mean.setText,str),
            (492,417,184,'numeric-sd',tool.sd.text,tool.sd.setText,str),
            (284,509,184,'numeric-min',tool.lower.text,tool.lower.setText,str),
            (492,509,184,'numeric-max',tool.upper.text,tool.upper.setText,str),
            (284,601,184,'numeric-digits',tool.digits.currentText,set_digits,str),
            (492,601,184,'numeric-seed',tool.seed.text,tool.seed.setText,str)]:self.bind(b,x,y,w,name,getter,setter,parse)
        b.suppress(284,678,392,76);b.suppress(284,770,392,42)
        self.numeric_target=QRadioButton('按均数标准差');self.numeric_range=QRadioButton('按最大最小值')
        for widget,rect,name in [(self.numeric_target,(284,679,192,30),'numeric-target-mode'),(self.numeric_range,(484,679,192,30),'numeric-range-mode')]:
            widget.setStyleSheet('QRadioButton{font-size:12px;spacing:7px;background:white;}');b.place(widget,rect,name)
        self.numeric_target.setChecked(tool.target.isChecked());self.numeric_range.setChecked(tool.range_mode.isChecked())
        self.numeric_target.toggled.connect(lambda checked:tool.target.setChecked(True) if checked else None)
        self.numeric_range.toggled.connect(lambda checked:tool.range_mode.setChecked(True) if checked else None)
        self.numeric_mode_note=QLabel();self.numeric_mode_note.setWordWrap(True)
        self.numeric_mode_note.setStyleSheet('font-size:11px;color:#738477;background:transparent;');b.place(self.numeric_mode_note,(284,717,392,34),'numeric-mode-note')
        def button(text,rect,name,action,primary=False):
            control=QPushButton(text);control.setCursor(Qt.PointingHandCursor)
            color='background:#277453;color:white;border:1px solid #277453;' if primary else 'background:white;color:#277453;border:1px solid #DEE8DF;'
            control.setStyleSheet('QPushButton{'+color+'border-radius:9px;padding:0;font-size:14px;font-weight:500;} QPushButton:disabled{background:#F0F4F0;color:#97A69B;border-color:#DEE8DF;}')
            control.clicked.connect(action);return b.place(control,rect,name)
        button('生成数据',(284,770,280,42),'generate-numeric',lambda:self.generate('numeric'),True)
        button('停止',(576,770,100,42),'stop-numeric',tool.stop_generation)
        button('复制',(1117,234,90,42),'copy-numeric',tool.result.copy)
        b.hotspot((1220,234,156,42),tool.result.save,'save-numeric')
        b.suppress(748,400,632,440)
        for text,rect,name in [('生成的数据 · 每行一个',(748,400,296,24),'numeric-data-title'),('数据分布',(1068,400,312,24),'numeric-distribution-title'),('目标与实际',(1068,667,312,24),'numeric-statistics-title')]:
            label=QLabel(text);label.setStyleSheet('font-size:13px;font-weight:500;color:#193C2C;');b.place(label,rect,name)
        self.numeric_output=QPlainTextEdit();self.numeric_output.setReadOnly(True);self.numeric_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.numeric_output.setPlaceholderText('生成的数据将逐行显示在这里，可直接复制到 Excel。')
        self.numeric_output.setStyleSheet('QPlainTextEdit{background:#F8FBF8;border:1px solid #DEE8DF;border-radius:10px;padding:14px;color:#193C2C;font-size:16px;}')
        b.place(self.numeric_output,(748,430,296,398),'numeric-values')
        self.histogram=MiniHistogram();b.place(self.histogram,(1068,430,312,226),'numeric-distribution')
        self.numeric_stats=b.table((1068,700,312,128),['指标','目标值','实际值','偏差'],[78]*4,'numeric-statistics')
        self.numeric_stats.setStyleSheet(self.numeric_stats.styleSheet().replace('padding:0 14px','padding:0 5px').replace('font-size:12px','font-size:11px'))
        self.numeric_stats.setEditTriggers(QAbstractItemView.NoEditTriggers)

    def build_word(self,b):
        tool=self.modules['word']
        b.suppress(250,200,1160,690)
        tool.setObjectName('word-workflow');tool.setAttribute(Qt.WA_StyledBackground,True)
        tool.setMinimumSize(0,0)
        b.place(tool,(260,206,1144,b.height()-154),'word-workflow')
        # Keep import/generate/save entry names for keyboard and automation routing.
        b.controls['import-word']=tool.import_button
        b.controls['generate-word']=tool.generate_button
        b.controls['save-word']=tool.export_button
        self.word_table=tool.metrics

    def word_changed(self,row,col):
        tool=self.modules['word'];text=self.word_table.item(row,col).text()
        mapping={2:1,3:3,4:4,5:6,6:7}
        if col in mapping:tool.metrics.item(row,mapping[col]).setText(text)
        elif col==1:
            group=tool.metrics.cellWidget(row,2).currentData()
            next(e for e in tool.group_editors if e.name==group).fields['n'].setText(text)
        elif col==0:
            combo=tool.metrics.cellWidget(row,2);i=combo.findData(text)
            if i>=0:combo.setCurrentIndex(i)

    def build_data(self,b):
        for x,w,name,key,parse in [(284,190,'sample-size','n_samples',int),(498,190,'positive-rate','positive_rate',float),(712,225,'data-seed','random_seed',int),(961,410,'id-name','id_name',str)]:
            self.bind_field(b,x,359,w,name,'data',key,parse)
        self.data_table=b.table((284,545,1096,216),['变量名称','阳性均数','阳性 SD','阴性均数','阴性 SD','阳性下限','阳性上限','阴性下限','阴性上限','处理方式','小数位'],[180]+[118]*8+[150,100],'continuous-variables')
        self.data_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.data_table.horizontalHeader().setStretchLastSection(False)
        self.data_table.cellChanged.connect(self.feature_changed)
        self.data_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self.feature_menu)
        self.data_table.setToolTip('向右滚动可编辑阴性边界、处理方式 int/round/none 和小数位；两组边界独立。')
        self.parameter_button(b,'样本、字段与全部变量参数…',(970,471,410,34),'data-parameters',1)
        b.hotspot((1145,818,235,42),lambda:self.show_board(5),'next-model')

    def table_error(self,table,row,col,error=None):
        errors=dict(table.property('input-errors') or {})
        key=f'{row}:{col}'
        if error:errors[key]=str(error)
        else:errors.pop(key,None)
        table.setProperty('input-errors',errors)
        item=table.item(row,col)
        if item:
            item.setBackground(QColor('#FADEDA') if error else QColor('transparent'))
            item.setToolTip(str(error) if error else '')

    def feature_changed(self,row,col):
        editor=self.modules['shap'].data_editor;editor.commit_feature();index=self.continuous_indices[row]
        f=editor.data['features'][index];text=self.data_table.item(row,col).text().strip()
        try:
            if col==0:
                if not text:raise ValueError('变量名称不能为空')
                old=f['name'];f['name']=text
                if editor.current==index:editor.name.setText(text)
                self.rename_reference(old,text)
            elif col in (9,10):
                key='transform' if col==9 else 'digits'
                value=text if col==9 else int(text)
                if col==9 and value not in ('int','round','none'):raise ValueError('处理方式为 int、round 或 none')
                if col==10 and not 0<=value<=10:raise ValueError('小数位须在 0–10 之间')
                f[key]=value
                if editor.current==index:set_field(editor.detail_forms['processing'].fields[key],value)
            else:
                group,key={1:('positive','mean'),2:('positive','std'),3:('negative','mean'),4:('negative','std'),5:('positive','min'),6:('positive','max'),7:('negative','min'),8:('negative','max')}[col]
                value=float(text)
                if not math.isfinite(value) or (key=='std' and value<0):raise ValueError('请输入有限数值，标准差不能为负')
                if editor.current==index:set_field(editor.detail_forms[group].fields[key],value)
                f[group][key]=value
            self.table_error(self.data_table,row,col)
        except (ValueError,OverflowError) as exc:self.table_error(self.data_table,row,col,exc)

    def rename_reference(self,old,new):
        tool=self.modules['shap']
        field=tool.explanation_form.fields['protective_feature']
        if field.value()==old:field.editor.setEditText(new)
        editor=tool.style_editor;editor.commit()
        for style in editor.config['plots'].values():
            for key in ('feature','interaction_feature'):
                if style.get(key)==old:style[key]=new
        editor.current=None;editor.switch()

    def parameter_button(self,b,text,rect,name,page):
        button=QPushButton(text)
        button.setStyleSheet('QPushButton{background:#ECF6EF;color:#277453;border:1px solid #C6DEC9;border-radius:8px;font-size:13px;padding:4px;}')
        button.clicked.connect(lambda:self.advanced('shap',page))
        return b.place(button,rect,name)

    def feature_menu(self,point):
        row=self.data_table.indexAt(point).row()
        if row>=0:
            menu=QMenu(self);menu.addAction('该变量的全部参数…',lambda:self.advanced('shap',1,feature=self.continuous_indices[row]))
            menu.exec(self.data_table.viewport().mapToGlobal(point))

    def build_model(self,b):
        self.parameter_button(b,'完整模型、SHAP 与分类变量参数…',(284,552,480,36),'model-parameters',2)
        for x,y,w,name,section,key,parse in [
            (284,377,230,'test-size','model','test_size',float),(538,377,250,'split-seed','model','split_seed',int),
            (284,473,230,'max-iter','model','max_iter',int),(538,473,250,'regularization','model','C',float),
            (860,377,238,'background-size','explanation','background_max_samples',int),(1122,377,258,'background-seed','explanation','background_seed',int),
            (860,473,238,'plot-seed','export','random_seed',int),(1122,473,258,'sample-index','export','sample_index',int)]:self.bind_field(b,x,y,w,name,section,key,parse)
        self.binary_table=b.table((284,671,1096,128),['变量名称','阳性概率','阴性概率','类别编码'],[370,240,240,246],'binary-variables')
        self.binary_table.cellChanged.connect(self.binary_changed)
        b.hotspot((260,818,160,42),lambda:self.show_board(4),'back-data')
        b.hotspot((1145,818,235,42),lambda:self.show_board(6),'next-style')

    def binary_changed(self,row,col):
        editor=self.modules['shap'].data_editor;editor.commit_feature();index=self.binary_indices[row];f=editor.data['features'][index]
        text=self.binary_table.item(row,col).text().strip()
        try:
            key=['name','positive_p','negative_p','values'][col]
            value=text if col==0 else ([float(v.strip()) for v in text.split('/')] if col==3 else float(text))
            if col==0 and not text:raise ValueError('变量名称不能为空')
            if col in (1,2) and not 0<=value<=1:raise ValueError('概率为 0–1 之间的小数')
            if col==3 and (len(value)!=2 or value[0]==value[1] or not all(math.isfinite(v) for v in value)):raise ValueError('需要两个不同的有限数值编码')
            if editor.current==index:
                if col==0:editor.name.setText(text)
                else:set_field(editor.detail_forms['binary'].fields[key],value)
            if col==0:self.rename_reference(f['name'],value)
            f[key]=value;self.table_error(self.binary_table,row,col)
        except (ValueError,OverflowError) as exc:self.table_error(self.binary_table,row,col,exc)

    def style_editor(self):return self.modules['shap'].style_editor
    def style_field(self,key):return self.style_editor().fields[key]
    def select_style(self,key):
        if not self.commit():return
        editor=self.style_editor();editor.commit();self.style_key=key
        editor.selector.setCurrentIndex(editor.selector.findData(key));self.refresh(force=True)
    def set_style(self,key,value):
        if (key.endswith('color') or key in ('background','positive_light','negative_light')) and not QColor(value).isValid():raise ValueError('无效颜色：'+str(value))
        editor=self.style_editor()
        if key in editor.overrides:editor.overrides[key].setChecked(True)
        set_field(editor.fields[key],value)
    def color_key(self):return {'bar':'bar_color','summary':'high_color','force':'positive_color','waterfall':'positive_color','dependence_protective':'point_color','dependence_risk':'point_color','common':'bar_color'}[self.style_key]
    def width_key(self):return 'edge_width' if self.style_key=='bar' else ('line_width' if self.style_key in ('force','waterfall') else 'axis_width')

    def build_style(self,b):
        # The selection marker and preview colors belong to this window only.
        b.spec=deepcopy(b.spec)
        editor=self.style_editor();editor.selector.setCurrentIndex(editor.selector.findData(self.style_key))
        # Replace only the active-row fill; every measured row remains in its design location.
        self.style_selection=b.shape_at(276,431,'rectangle')
        for i,key in enumerate(['common']+PLOT_ORDER):b.hotspot((276,380+i*51,238,42),lambda checked=False,k=key:self.select_style(k),'plot-'+key)
        self.bind(b,574,378,162,'plot-color',lambda:self.style_field(self.color_key()).value(),lambda v:self.set_style(self.color_key(),v))
        b.hotspot((749,378,165,42),self.pick_color,'choose-color')
        self.color_swatch=QWidget();b.place(self.color_swatch,(749,378,165,42),'color-swatch');self.color_swatch.setAttribute(Qt.WA_TransparentForMouseEvents)
        # The approved design uses a font dropdown, not a substituted text field.
        b.suppress(575,476,340,40)
        fonts=QFontComboBox();fonts.setEditable(True)
        fonts.setStyleSheet('QFontComboBox{background:transparent;border:0;border-radius:0;padding:0 12px;font-size:14px;min-height:0;color:#193C2C;} QLineEdit{border:0;background:transparent;padding:0;font-size:14px;min-height:0;}')
        b.place(fonts,(574,475,342,42),'plot-font')
        binding=Binding(fonts.lineEdit(),lambda:self.style_field('font_family').value()[0],lambda v:self.set_style('font_family',[v]));fonts.activated.connect(binding.edited)
        self.bindings.setdefault(b.index,[]).append(binding)
        fonts.setToolTip('全部字体回退和自定义字体文件在右上角参数菜单中设置。')
        self.bind(b,574,571,159,'plot-font-size',lambda:self.style_field('font_size').value(),lambda v:self.set_style('font_size',v),float)
        self.bind(b,757,571,159,'plot-line-width',lambda:self.style_field(self.width_key()).value(),lambda v:self.set_style(self.width_key(),v),float)
        for i,x in enumerate([574,757]):
            def setter(v,index=i):
                pair=list(self.style_field('figsize').value());pair[index]=v;self.set_style('figsize',pair)
            self.bind(b,x,667,159,'plot-'+['width','height'][i],lambda index=i:self.style_field('figsize').value()[index],setter,float)
        b.hotspot((574,761,160,42),self.restore_style,'restore-style')
        b.text(590,771,'恢复默认与继承')
        b.hotspot((750,761,166,42),self.apply_style,'apply-style')
        self.parameter_button(b,'当前图全部颜色、字体、线条与布局…',(574,818,342,38),'style-parameters',3)
        self.parameter_button(b,'导出格式 / DPI / 局部样本…',(984,818,396,38),'export-parameters','export')
        b.suppress(975,350,410,385)
        self.style_preview=PlotImage();b.place(self.style_preview,(984,355,396,365),'real-style-preview')

    def pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        color=QColorDialog.getColor(QColor(self.style_field(self.color_key()).value()),self,'选择颜色')
        if color.isValid():self.set_style(self.color_key(),color.name().upper());self.refresh(force=True)
    def apply_style(self):
        if self.commit():self.style_editor().commit();self.refresh(force=True)
    def restore_style(self):
        if not self.commit():return
        editor=self.style_editor();editor.commit()
        if self.style_key!='common':
            specific=editor.config['plots'][self.style_key]
            from .config import default_config
            defaults=default_config()['plots']['plots'][self.style_key]
            for key in editor.config['common']:
                if key in defaults:specific[key]=deepcopy(defaults[key])
                else:specific.pop(key,None)
            editor.current=None;editor.switch()
        else:
            from .config import default_config
            editor.config['common'].update(deepcopy(default_config()['plots']['common']))
            editor.current=None;editor.switch()
        self.refresh(force=True)

    def build_results(self,b):
        b.suppress(284,510,700,312);self.plot_image=PlotImage();b.place(self.plot_image,(284,505,700,311),'actual-plot')
        b.hotspot((835,437,140,28),self.choose_image,'choose-image')
        self.parameter_button(b,'完整数据 / 模型评估 / SHAP 结果…',(284,840,500,38),'result-details',4)
        self.save_options=[]
        for i in range(4):
            shape=b.shape_at(1056,492+i*50,'text');b.hidden_shapes.add(shape['id'])
            box=QCheckBox(shape['text'].replace('☑  ',''));box.setChecked(True)
            box.setStyleSheet('QCheckBox{font-size:12px;color:#314C3E;background:transparent;spacing:8px;}')
            b.place(box,(1056,490+i*50,328,30),'export-option-'+str(i));self.save_options.append(box)
        b.hotspot((1056,724,324,42),self.save_results,'save-results')
        b.hotspot((1056,780,324,42),self.save_image,'save-image')
        self.run_again=b.hotspot((1134,309,240,42),lambda:self.generate('shap'),'run-analysis')
        self.run_again.setText('生成数据并分析');self.run_again.setStyleSheet('QPushButton{background:#277453;color:white;border:none;border-radius:9px;font-size:14px;font-weight:500;}')

    def choose_image(self):
        tool=self.modules['shap'];images=[p for p in (tool.result.images or []) if p.suffix=='.png'] if tool.result else []
        menu=QMenu(self)
        for i,path in enumerate(images):menu.addAction(path.stem,lambda index=i:self.set_image(index))
        if images:menu.exec(self.cursor().pos())
    def set_image(self,index):self.image_index=index;self.refresh(force=True)
    def save_image(self):
        if not self.plot_image.path:QMessageBox.information(self,'尚无图表','请先生成数据与图表。');return
        from .app import ImagePreview
        preview=ImagePreview(self.plot_image.path,self);preview.save()
    def save_results(self):
        result=self.modules['shap'].result
        if result is None:QMessageBox.information(self,'尚无结果','请先生成数据与图表。');return
        if not any(b.isChecked() for b in self.save_options):QMessageBox.information(self,'选择保存内容','请至少选择一项保存内容。');return
        destination=QFileDialog.getExistingDirectory(self,'保存全部结果')
        if not destination:return
        target=Path(destination)/result.folder.name
        if target.exists():
            import uuid
            target=target.with_name(target.name+'_'+uuid.uuid4().hex[:6])
        for file in result.folder.rglob('*'):
            if not file.is_file():continue
            relative=file.relative_to(result.folder)
            kind=1 if relative.parts[0]=='figures' else (2 if file.name=='parameters.json' else (0 if file.suffix in ('.csv','.xlsx') else 3))
            if self.save_options[kind].isChecked():
                path=target/relative;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,path)
        self.last_saved_results=target;QMessageBox.information(self,'已保存',str(target))

    def generate(self,key):
        if not self.commit():return
        tool=self.modules[key]
        if key=='shap':
            tool.start_analysis();self.show_board(7,commit=False)
        else:tool.generate()
        self.refresh(force=True)

    def parameter_menu(self):
        key=self.current_module
        if not key:return
        menu=QMenu(self);menu.addAction('全部参数…',lambda:self.advanced(key))
        if key=='shap':
            tool=self.modules[key]
            menu.addAction('重新生成数据与图表',lambda:self.generate('shap'))
            menu.addAction('载入配置…',lambda:self.backend_action(tool.import_config));menu.addAction('保存全部配置…',lambda:self.backend_action(tool.export_config))
            menu.addAction('结果保存目录…',lambda:self.backend_action(tool.choose_output))
            menu.addAction('仅生成并保存数据',lambda:self.backend_action(lambda:tool.start_analysis(data_only=True)))
            menu.addAction('使用已有模型重新绘图',lambda:self.backend_action(lambda:tool.start_analysis(redraw=True)))
            menu.addAction('运行日志',lambda:self.advanced(key,5));menu.addAction('结果明细与模型评估',lambda:self.advanced(key,4))
        elif key=='word':
            tool=self.modules[key];menu.addAction('载入配置…',lambda:self.backend_action(tool.load_config));menu.addAction('保存全部配置…',lambda:self.backend_action(tool.save_config))
            menu.addAction('查看/复制病例数据',lambda:self.advanced(key,3));menu.addAction('取消生成',tool.cancel)
        elif key=='numeric':menu.addAction('查看/复制完整数列',lambda:self.advanced(key))
        else:
            menu.addAction('前10行、数据结构与类别计数…',self.category_report)
            menu.addAction('复制与排列格式',lambda:self.advanced(key))
        menu.exec(self.cursor().pos())
    def backend_action(self,fn):
        if self.commit():fn();self.refresh(force=True)

    def advanced(self,key,page=None,feature=None):
        if not self.commit():return
        if key=='word':
            tool=self.controller(key)
            tool.pages.setCurrentIndex(page if page is not None else 0)
            tool.setFocus();return
        export_tab=page=='export'
        if export_tab:page=3
        tool=self.controller(key);dialog=QDialog(self);dialog.setWindowTitle('全部参数 · '+{'category':'自定义类别数列','numeric':'均数 / 标准差模拟数据','word':'Word 一键生成 Excel','shap':'模拟数据生图'}[key]);dialog.resize(1180,800)
        layout=QVBoxLayout(dialog)
        if key=='shap':
            from .theme import SHAP_DIALOG_STYLE
            dialog.setObjectName('shapParameters');dialog.setStyleSheet(SHAP_DIALOG_STYLE)
            dialog.setAttribute(Qt.WA_StyledBackground,True);dialog.setSizeGripEnabled(True)
            dialog.resize(1280,860);dialog.setMinimumSize(960,640)
            layout.setContentsMargins(18,18,18,12);layout.setSpacing(12)
        body=tool.takeCentralWidget() if key=='shap' else tool
        body.setParent(dialog);body.show();layout.addWidget(body)
        if key=='shap':tool.advanced_host=dialog
        if key=='shap':
            if page is not None:tool.nav.setCurrentRow(page)
            else:tool.nav.setCurrentRow({4:1,5:2,6:3,7:4}.get(self.board_index,0))
            if page==3:
                tool.style_editor.selector.setCurrentIndex(tool.style_editor.selector.findData(self.style_key))
                tool.style_sections.setCurrentIndex(1 if export_tab else 0)
            if feature is not None:tool.data_editor.list.setCurrentRow(feature)
        elif key=='word' and page is not None:tool.pages.setCurrentIndex(page)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.accept)
        if key=='shap':
            footer=QFrame();footer.setObjectName('parametersFooter');row=QHBoxLayout(footer)
            row.setContentsMargins(6,12,6,0)
            hint=QLabel('修改会自动保留，完成设置后可关闭此窗口。');hint.setWordWrap(True)
            row.addWidget(hint,1);row.addWidget(buttons)
            buttons.button(QDialogButtonBox.Close).setText('完成');buttons.button(QDialogButtonBox.Close).setMinimumWidth(108)
            layout.addWidget(footer)
        else:layout.addWidget(buttons)
        # Enter commits numeric editors; it must never activate a dialog's first
        # import/generate button as an implicit default action.
        for button in dialog.findChildren(QPushButton):button.setAutoDefault(False);button.setDefault(False)
        dialog.exec()
        if key=='shap':
            try:tool.collect_config()
            except ValueError as exc:QMessageBox.warning(self,'请检查参数',str(exc))
        body.hide();layout.removeWidget(body)
        if key=='shap':
            tool.setCentralWidget(body);body.show();del tool.advanced_host
        else:tool.setParent(self)
        tool.hide();dialog.deleteLater()
        if key=='category':self.sync_categories()
        if key=='shap' and self.board_index==6:
            editor=self.style_editor();editor.selector.setCurrentIndex(editor.selector.findData(self.style_key))
        self.refresh(force=True)

    def update_table(self,table,rows):
        snapshot=tuple(tuple(str(v) for v in row) for row in rows)
        if table.property('snapshot')==snapshot or table.property('input-error') or table.property('input-errors'):return
        if table.hasFocus() or table.isAncestorOf(QApplication.focusWidget()):return
        table.blockSignals(True);table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,v in enumerate(row):table.setItem(i,j,QTableWidgetItem(str(v)))
        table.setProperty('snapshot',snapshot);table.blockSignals(False)

    def refresh(self,force=False):
        b=self.boards.get(self.board_index)
        if b is None:return
        if self.board_index==6 and 'shap' in self.modules:
            editor=self.style_editor()
            index=editor.selector.findData(self.style_key)
            if editor.selector.currentIndex()!=index:editor.selector.setCurrentIndex(index)
        for binding in self.bindings.get(self.board_index,[]):binding.refresh()
        key=self.current_module
        if key is None:return
        tool=self.modules[key]
        if key=='category':
            values=tool.result.values;counts=Counter(values);items=list(counts.items())
            b.text(748+16,302+36,str(len(values)))
            for i in range(2):
                x=916+168*i;value,count=items[i] if len(items)>i else ('—',0)
                b.text(x+16,316,'类别 '+str(value).removesuffix('.0'));b.text(x+16,338,count)
            b.text(748,263,f'{len(values)} 个数值 · {len(counts)} 个类别')
            if self.category_output.toPlainText()!=tool.result.output.toPlainText():self.category_output.setPlainText(tool.result.output.toPlainText())
            b.text(760,706,tool.error.text() or '✓ 数量核对通过')
        elif key=='numeric':
            from .data_tools_engine import statistics
            values=tool.result.values
            busy=tool.is_running();b.controls['generate-numeric'].setEnabled(not busy);b.controls['generate-numeric'].setText('正在生成…' if busy else '生成数据')
            b.controls['stop-numeric'].setEnabled(busy and not tool.worker.isInterruptionRequested())
            self.numeric_target.setChecked(tool.target.isChecked());self.numeric_range.setChecked(tool.range_mode.isChecked())
            target=tool.target.isChecked()
            b.controls['numeric-mean'].setEnabled(target);b.controls['numeric-sd'].setEnabled(target)
            self.numeric_mode_note.setText('调整数值以逼近目标均数和样本标准差，生成后核对偏差。' if target else '在最小值与最大值之间均匀随机生成，不约束均数和标准差。')
            if self.numeric_output.toPlainText()!=tool.result.output.toPlainText():self.numeric_output.setPlainText(tool.result.output.toPlainText())
            mean,sd=statistics(values) if values else (None,None)
            for x,value in [(764,'—' if mean is None else f'{mean:.4f}'),(932,'—' if sd is None else f'{sd:.4f}'),(1100,len(values))]:b.text(x,338,value)
            if self.histogram.values!=values:self.histogram.values=list(values);self.histogram.update()
            if values:
                options=getattr(tool,'result_options',{})
                target_mean=options.get('mean') if options.get('mode')=='target' else None;target_sd=options.get('sd') if options.get('mode')=='target' else None
                rows=[['均数','—' if target_mean is None else f'{target_mean:g}',f'{mean:.4f}','—' if target_mean is None else f'{mean-target_mean:+.4f}'],['标准差','—' if target_sd is None else f'{target_sd:g}',f'{sd:.4f}','—' if target_sd is None else f'{sd-target_sd:+.4f}']]
            else:rows=[['均数','—','—','—'],['标准差','—','—','—']]
            self.update_table(self.numeric_stats,rows)
            stopped=tool.result.message.text() if tool.result.message.text().startswith('已停止') else ''
            b.text(748,263,tool.error.text() or ('正在生成数据…' if busy else (stopped or ('实际统计结果 · 数据可逐行复制' if values else '生成后显示数据及实际统计结果'))))
        elif key=='word':
            tool.update_total()
        elif key=='shap':
            if self.board_index==4:
                editor=tool.data_editor;features=editor.data['features'];self.continuous_indices=[i for i,f in enumerate(features) if f['kind']=='continuous']
                rows=[[f['name'],f['positive']['mean'],f['positive']['std'],f['negative']['mean'],f['negative']['std'],f['positive']['min'],f['positive']['max'],f['negative']['min'],f['negative']['max'],f['transform'],f['digits']] for f in features if f['kind']=='continuous']
                self.update_table(self.data_table,rows);b.text(284,824,f"连续变量 {len(rows)} 项   ·   二分类变量 {len(features)-len(rows)} 项   ·   编码与命名均可编辑")
            elif self.board_index==5:
                features=tool.data_editor.data['features'];self.binary_indices=[i for i,f in enumerate(features) if f['kind']=='binary']
                self.update_table(self.binary_table,[[f['name'],f['positive_p'],f['negative_p'],' / '.join(str(v) for v in f['values'])] for f in features if f['kind']=='binary'])
            elif self.board_index==6:
                selected=0 if self.style_key=='common' else PLOT_ORDER.index(self.style_key)+1
                self.style_selection['y']=380+selected*51
                title={'common':'全局默认样式','bar':'SHAP 重要性','summary':'SHAP 蜂群图','force':'单样本力图','waterfall':'单样本瀑布图','dependence_protective':'保护性依赖图','dependence_risk':'风险性依赖图'}[self.style_key]
                b.text(574,293,title);b.text(574,323,'所有图的默认样式' if self.style_key=='common' else '当前图覆盖全局默认样式')
                color=self.style_field(self.color_key()).value();self.color_swatch.setStyleSheet(f'background:{color};border-radius:8px;')
                for s in b.spec['shapes']:
                    if s['type']=='rectangle' and s['x']==1059 and 380<=s['y']<670:
                        s['fills']=[{'fillColor':color}]
                b.text(574,352,{'bar':'条形颜色','summary':'高特征值颜色','force':'正贡献颜色','waterfall':'正贡献颜色','dependence_protective':'散点颜色','dependence_risk':'散点颜色','common':'公共条形颜色'}[self.style_key])
                b.text(757,545,{'edge_width':'边框线宽','line_width':'连接线宽','axis_width':'坐标轴线宽'}[self.width_key()])
                b.text(984,293,'上次生成的实际图表')
                b.text(984,323,'修改后请重新生成或用已有模型重绘')
                result=tool.result
                filename=self.style_editor().config['plots'].get(self.style_key,{}).get('filename')
                image=next((p for p in (result.images or []) if p.suffix=='.png' and p.stem==filename),None) if result else None
                self.style_preview.show_path(image)
                b.text(994,784,'修改参数后需重新绘图')
            elif self.board_index==7:
                result=tool.result;busy=bool(tool.worker and tool.worker.isRunning())
                b.text(284,293,'正在生成…' if busy else ('本次生成完成' if result else '准备生成'))
                images=[p for p in result.images or [] if p.suffix=='.png'] if result else []
                b.text(285,328,tool.status.text() if busy else (f'{len(result.data)} 行数据     {int(result.data[result.config["data"]["label_name"]].sum())} 个阳性样本     {len(images)} 张图表     配置已记录' if result else '确认数据、模型与图表样式后，开始生成。'))
                try:changed=result is not None and tool.collect_config()!=result.config
                except (ValueError,TypeError):changed=True
                self.run_again.setVisible(not busy and (result is None or changed))
                self.run_again.setText('重新生成' if changed else '生成数据并分析')
                self.plot_image.show_path(images[self.image_index%len(images)] if images else None)
                b.text(847,442,f'{self.image_index%len(images)+1:02} / {len(images):02}' if images else '00 / 00')
                b.text(1240+12,125,'生成中…' if busy else ('生成已完成' if result else '尚未生成'))
        b.update()

    def closeEvent(self,event):
        busy=[key for key,t in self.modules.items() if (t.is_running() if hasattr(t,'is_running') else bool(getattr(t,'worker',None) and t.worker.isRunning()))]
        if busy:QMessageBox.information(self,'任务仍在运行','请等待当前任务完成后关闭。');event.ignore()
        else:event.accept()
