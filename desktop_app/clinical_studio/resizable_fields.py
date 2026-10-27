"""Common drag grips for multiline editors/tables, with scrolling outer content."""
from PySide6.QtCore import QObject,QEvent,QPoint,QSize,Qt,QTimer
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import (QApplication,QWidget,QPlainTextEdit,QTextEdit,QTableView,
    QHeaderView,QScrollArea,QSplitter,QLayout,QDialog,QVBoxLayout,QLabel,QSizePolicy)


def keep_user_height(widget,default):
    return int(widget.property('userResizeHeight') or default)


def enable_content_scroll(widget):
    if widget.layout():
        widget.layout().setSizeConstraint(QLayout.SetMinimumSize)
        if isinstance(widget.layout(),QVBoxLayout):widget.layout().setAlignment(Qt.AlignTop)
    area=QScrollArea();area.setWidgetResizable(True);area.setFrameShape(QScrollArea.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded);area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setAlignment(Qt.AlignLeft|Qt.AlignTop);area.setWidget(widget)
    area.setProperty('resizableContent',True)
    return area


def prepare_outer_layout(widget):
    """Grow content inside its scroll area; never force the application window taller."""
    parent=widget.parentWidget()
    if parent is not None and parent.layout() is not None:
        for peer in parent.findChildren(QWidget,options=Qt.FindDirectChildrenOnly):
            if peer is not widget and isinstance(peer,(QPlainTextEdit,QTextEdit,QTableView)) and peer.isVisible():
                peer.setFixedHeight(peer.height())
    while parent is not None:
        if isinstance(parent,QScrollArea):break
        if parent.layout():
            parent.layout().setSizeConstraint(QLayout.SetMinimumSize)
            if isinstance(parent.layout(),QVBoxLayout):
                # Fixed-height fields cannot absorb the old stretch shares.
                # Keep blocks packed at the top and stop captions from growing
                # into the space released when a field is made smaller.
                parent.layout().setAlignment(Qt.AlignTop)
                for index in range(parent.layout().count()):
                    parent.layout().setStretch(index,0)
                    child=parent.layout().itemAt(index).widget()
                    if isinstance(child,QLabel):
                        policy=child.sizePolicy();policy.setVerticalPolicy(QSizePolicy.Maximum);child.setSizePolicy(policy)
            parent.layout().invalidate()
        if isinstance(parent,QDialog):
            if not parent.property('resizeScrollInstalled') and parent.layout():
                parent.setProperty('resizeScrollInstalled',True)
                content=QWidget();content.setLayout(parent.layout())
                layout=QVBoxLayout(parent);layout.setContentsMargins(0,0,0,0);layout.addWidget(enable_content_scroll(content))
            break
        parent=parent.parentWidget()


class FieldResizeGrip(QWidget):
    def __init__(self,target):
        super().__init__(target);self.target=target;self.start=None
        self.setObjectName('fieldResizeGrip');self.setAccessibleName('拖动调整文本框或表格大小')
        self.setToolTip('拖动调整宽度和高度；内容超出时可滚动外层区域')
        self.setFixedSize(20,20);self.setCursor(Qt.SizeFDiagCursor)
        self.setStyleSheet('QWidget#fieldResizeGrip{background:#ECF6EF;border-radius:3px;}')
        self.setAttribute(Qt.WA_StyledBackground,True);self.position()

    def position(self):
        self.move(max(0,self.target.width()-self.width()-2),max(0,self.target.height()-self.height()-2));self.raise_()

    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setPen(QPen(QColor('#277453'),1.6))
        for inset in (5,10,15):p.drawLine(17-inset,17,17,17-inset)

    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        self.start=event.globalPosition().toPoint();self.initial=QSize(self.target.size());self.factor=1.
        owner=self.target.window();proxy=owner.graphicsProxyWidget()
        if proxy is not None and proxy.scene() is not None and proxy.scene().views():
            self.factor=proxy.scene().views()[0].transform().m11() or 1.
        self.grabMouse();event.accept()

    def mouseMoveEvent(self,event):
        if self.start is None:return
        delta=event.globalPosition().toPoint()-self.start
        dx=round(delta.x()/self.factor);dy=round(delta.y()/self.factor)
        resize_field(self.target,self.initial.width()+dx,self.initial.height()+dy,abs(dx)>2,abs(dy)>2)
        event.accept()

    def mouseReleaseEvent(self,event):
        if self.start is not None:self.releaseMouse();self.start=None;event.accept()


def resize_field(widget,width,height,resize_width=True,resize_height=True):
    """The same path serves mouse drags and UI verification; values remain untouched."""
    width=max(140,min(5000,int(width)));height=max(80 if isinstance(widget,QTableView) else 60,min(5000,int(height)))
    before=widget.geometry();parent=widget.parentWidget()
    prepare_outer_layout(widget)
    # Vertical splitter children grow as content instead of squeezing neighbouring editors.
    if isinstance(parent,QSplitter) and parent.orientation()==Qt.Vertical:
        for i in range(parent.count()):
            peer=parent.widget(i)
            if peer is not widget:peer.setFixedHeight(peer.height())
    if resize_width:widget.setProperty('userResizeWidth',width);widget.setFixedWidth(width)
    if resize_height:widget.setProperty('userResizeHeight',height);widget.setFixedHeight(height)
    widget.resize(width if resize_width else widget.width(),height if resize_height else widget.height())
    if isinstance(widget,QTableView):
        widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    if isinstance(parent,QSplitter) and parent.orientation()==Qt.Vertical:
        parent.setFixedHeight(sum(parent.widget(i).height() for i in range(parent.count()))+parent.handleWidth()*(parent.count()-1))
    if parent is not None and hasattr(parent,'resize_content_field'):
        parent.resize_content_field(widget,before)
    current=widget.parentWidget()
    while current is not None:
        if current.layout():current.layout().invalidate();current.layout().activate()
        current.updateGeometry()
        if isinstance(current,QScrollArea):
            if current.widget():current.widget().updateGeometry()
            break
        current=current.parentWidget()
    widget.updateGeometry();widget.resize_grip.position() if hasattr(widget,'resize_grip') else None


class FieldResizeController(QObject):
    def attach(self,widget):
        if hasattr(widget,'resize_grip'):return
        if widget.window().windowType()==Qt.Popup:return
        widget.resize_grip=FieldResizeGrip(widget);widget.resize_grip.show()
        if isinstance(widget,QTableView):widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    def eventFilter(self,watched,event):
        if isinstance(watched,(QPlainTextEdit,QTextEdit,QTableView)):
            if event.type()==QEvent.Show:self.attach(watched)
            elif event.type()==QEvent.Resize and hasattr(watched,'resize_grip'):watched.resize_grip.position()
        return False


def install_resize_behavior(app):
    if not hasattr(app,'field_resize_controller'):
        app.field_resize_controller=FieldResizeController(app);app.installEventFilter(app.field_resize_controller)
    for widget in QApplication.allWidgets():
        if isinstance(widget,(QPlainTextEdit,QTextEdit,QTableView)):app.field_resize_controller.attach(widget)
