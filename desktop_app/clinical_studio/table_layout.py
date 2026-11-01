"""Content-sized table columns and leading row actions throughout the desktop UI."""
from PySide6.QtCore import QObject,QTimer,Qt,QRect
from PySide6.QtWidgets import (QWidget,QTableView,QLineEdit,QComboBox,QAbstractSpinBox,
    QPushButton,QLabel,QHeaderView,QBoxLayout,QCalendarWidget,QStyle,QStyleOptionViewItem)


def calendar_view(widget):
    owner=widget
    while owner is not None:
        if isinstance(owner,QCalendarWidget):return True
        owner=owner.parentWidget()
    return False


def control_width(widget):
    """Use the control's content, instead of an expanding cell's current width."""
    fm=widget.fontMetrics()
    if isinstance(widget,QLineEdit):return max(84,min(200,fm.horizontalAdvance(widget.text() or '0000.00')+32))
    if isinstance(widget,QAbstractSpinBox):return max(84,fm.horizontalAdvance(widget.text())+40)
    if isinstance(widget,QComboBox):return max(92,fm.horizontalAdvance(widget.currentText())+52)
    if isinstance(widget,QPushButton):return max(40,fm.horizontalAdvance(widget.text())+30)
    if isinstance(widget,QLabel):return max(36,min(420,fm.horizontalAdvance(widget.text())+12))
    layout=widget.layout()
    if layout:
        sizes=[]
        for i in range(layout.count()):
            item=layout.itemAt(i)
            if item.widget():sizes.append(control_width(item.widget()))
            elif item.layout():sizes.append(item.layout().minimumSize().width())
        margins=layout.contentsMargins();spacing=max(0,layout.spacing())
        horizontal=isinstance(layout,QBoxLayout) and layout.direction() in (QBoxLayout.LeftToRight,QBoxLayout.RightToLeft)
        width=(sum(sizes)+spacing*max(0,len(sizes)-1)) if horizontal else max(sizes,default=0)
        return max(widget.minimumWidth(),width+margins.left()+margins.right())
    return max(40,widget.minimumSizeHint().width())


def is_delete_action(widget):
    buttons=[widget] if isinstance(widget,QPushButton) else widget.findChildren(QPushButton)
    return any('删除' in (b.text()+b.accessibleName()+b.toolTip()) or b.text().strip() in ('−','－','-') for b in buttons)


class ContentColumns(QObject):
    def __init__(self,table):
        super().__init__(table);self.table=table;self.model=None;self.fitting=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.fit)
        self.schedule()
    def schedule(self):
        if not self.fitting:self.timer.start(0)
    def fit(self):
        t=self.table;model=t.model()
        if model is None:return
        if self.model is not model:
            self.model=model
            for signal in (model.dataChanged,model.rowsInserted,model.rowsRemoved,model.columnsInserted,model.columnsRemoved,model.modelReset,model.layoutChanged,model.headerDataChanged):
                signal.connect(lambda *args:self.schedule())
        # Source tables contain their own responsive multi-control rule layout.
        if hasattr(t,'fit_columns'):
            t.fit_columns();return
        if self.fitting:return
        self.fitting=True
        try:
            header=t.horizontalHeader();header.setStretchLastSection(False);header.setMinimumSectionSize(40)
            header.setSectionResizeMode(QHeaderView.Interactive)
            t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            rows=model.rowCount();sample=list(range(min(rows,200)))
            if rows>200:sample+=list(range(max(200,rows-40),rows))
            fm=t.fontMetrics();actions=[]
            for col in range(model.columnCount()):
                text=str(model.headerData(col,Qt.Horizontal,Qt.DisplayRole) or '')
                width=fm.horizontalAdvance(text)+32
                for row in sample:
                    index=model.index(row,col);value=model.data(index,Qt.DisplayRole)
                    text='' if value is None else str(value)
                    width=max(width,min(480,max((fm.horizontalAdvance(line) for line in text.splitlines()),default=0)+32))
                    if model.flags(index)&Qt.ItemIsEditable:width=max(width,84)
                    option=QStyleOptionViewItem();option.initFrom(t);option.widget=t
                    option.rect=QRect(0,0,10000,10000)
                    size=t.itemDelegateForIndex(index).sizeHint(option,index)
                    width=max(width,min(480,size.width()+8))
                    if model.data(index,Qt.CheckStateRole) is not None:
                        indicator=t.style().pixelMetric(QStyle.PM_IndicatorWidth,None,t)
                        width=max(width,min(480,fm.horizontalAdvance(text)+32+indicator+8),54)
                    widget=t.indexWidget(index)
                    if widget:
                        width=max(width,control_width(widget)+12)
                        if is_delete_action(widget) and col not in actions:actions.append(col)
                width=max(44,width)
                if t.columnWidth(col)!=width:t.setColumnWidth(col,width)
            if t.property('wrapContentRows'):
                t.resizeRowsToContents()
                padding=int(t.property('rowTextPadding') or 20)
                for row in range(rows):
                    height=max(t.verticalHeader().defaultSectionSize(),t.rowHeight(row))
                    for col in range(model.columnCount()):
                        index=model.index(row,col);value=model.data(index,Qt.DisplayRole)
                        if value is None:continue
                        text=str(value);available=max(30,t.columnWidth(col)-32)
                        if model.data(index,Qt.CheckStateRole) is not None:
                            available=max(30,available-t.style().pixelMetric(QStyle.PM_IndicatorWidth,None,t)-8)
                        bounds=fm.boundingRect(QRect(0,0,available,10000),Qt.TextWordWrap|Qt.TextWrapAnywhere,text)
                        height=max(height,bounds.height()+padding)
                    if t.rowHeight(row)!=height:t.setRowHeight(row,height)
            # Reorder visually, preserving logical model indices and edit handlers.
            for target,col in enumerate(actions):
                visual=header.visualIndex(col)
                if visual!=target:header.moveSection(visual,target)
        finally:self.fitting=False


def fit_table_columns(table):
    if calendar_view(table):return
    if not hasattr(table,'content_columns'):table.content_columns=ContentColumns(table)
    table.content_columns.schedule()
