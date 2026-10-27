"""Shared native editor shell with a scrollable body and persistent actions."""
from PySide6.QtCore import Qt,QTimer,QObject,QEvent
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QDialogButtonBox,QLineEdit,QHeaderView)
from .resizable_fields import enable_content_scroll,keep_user_height,prepare_outer_layout


def native_owner(widget):
    owner=widget.window() if widget is not None else None
    proxy=owner.graphicsProxyWidget() if owner is not None else None
    if proxy is not None and proxy.scene() is not None and proxy.scene().views():
        return proxy.scene().views()[0].window()
    return owner


class EditorDialog(QDialog):
    def __init__(self,parent,title,subtitle='',size=(920,740)):
        super().__init__(native_owner(parent),Qt.Dialog|Qt.WindowTitleHint|Qt.WindowCloseButtonHint)
        self.setObjectName('editorDialog');self.setWindowTitle(title);self.setWindowModality(Qt.ApplicationModal)
        self.resize(*size);self.setMinimumSize(560,380)
        self.setStyleSheet('''
            QDialog#editorDialog { background:#F5F8F5; }
            QWidget#editorHeader, QWidget#editorFooter { background:white; }
            QLabel#editorHeading { color:#193C2C; font-size:21px; font-weight:600; }
            QLabel#editorSubtitle { color:#637668; font-size:12px; }
        ''')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.header=QWidget();self.header.setObjectName('editorHeader');head=QVBoxLayout(self.header);head.setContentsMargins(24,20,24,18);head.setSpacing(5)
        heading=QLabel(title);heading.setTextFormat(Qt.PlainText);heading.setWordWrap(True);heading.setObjectName('editorHeading');head.addWidget(heading)
        if subtitle:
            hint=QLabel(subtitle);hint.setTextFormat(Qt.PlainText);hint.setWordWrap(True);hint.setObjectName('editorSubtitle');head.addWidget(hint)
        outer.addWidget(self.header)
        self.content=QWidget();self.body_layout=QVBoxLayout(self.content);self.body_layout.setContentsMargins(20,16,20,16);self.body_layout.setSpacing(12)
        self.content_scroll=enable_content_scroll(self.content);outer.addWidget(self.content_scroll,1)
        self.footer=QWidget();self.footer.setObjectName('editorFooter');self.footer_layout=QHBoxLayout(self.footer);self.footer_layout.setContentsMargins(24,16,24,20);self.footer_layout.setSpacing(12);outer.addWidget(self.footer)
    def add_buttons(self,save='完成',cancel=None):
        flags=QDialogButtonBox.Ok|(QDialogButtonBox.Cancel if cancel else QDialogButtonBox.NoButton)
        buttons=QDialogButtonBox(flags);ok=buttons.button(QDialogButtonBox.Ok);ok.setText(save);ok.setObjectName('primary')
        if cancel:buttons.button(QDialogButtonBox.Cancel).setText(cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        self.footer_layout.addStretch();self.footer_layout.addWidget(buttons);return buttons
    def showEvent(self,event):
        super().showEvent(event)
        screen=self.screen()
        if screen:
            available=screen.availableGeometry();self.resize(min(self.width(),available.width()-40),min(self.height(),available.height()-60))


def get_text(parent,title,label,text=''):
    dialog=EditorDialog(parent,title,'',size=(640,300));message=QLabel(label);message.setWordWrap(True);dialog.body_layout.addWidget(message)
    entry=QLineEdit(text);dialog.body_layout.addWidget(entry);dialog.add_buttons('确认','取消');entry.setFocus();entry.selectAll()
    try:
        accepted=dialog.exec()==QDialog.Accepted
        return entry.text(),accepted
    finally:dialog.deleteLater()


def enable_category_expansion(table,limit=6):
    """Show short category lists in full, respecting a manually resized height."""
    def sync(*args):
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        header=max(40,table.horizontalHeader().sizeHint().height(),table.horizontalHeader().height())
        # Style/layout passes can reserve extra viewport margins after Show.
        # Measure that chrome instead of assuming it is only the header/frame.
        chrome=max(header+2*table.frameWidth(),table.height()-table.viewport().height())
        height=chrome+sum(table.rowHeight(i) for i in range(min(limit,table.rowCount())))+6
        table.setFixedHeight(keep_user_height(table,height))
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        parent=table.parentWidget()
        if parent and parent.isVisible():
            for label in parent.findChildren(QLabel,options=Qt.FindDirectChildrenOnly):
                if label.wordWrap():
                    label.setMinimumHeight(0)
                    label.setMinimumHeight(max(0,label.heightForWidth(label.width())))
                    label.setAlignment(Qt.AlignLeft|Qt.AlignTop)
    timer=QTimer(table);timer.setSingleShot(True);timer.timeout.connect(sync);table.category_timer=timer
    table.model().rowsInserted.connect(lambda *args:timer.start(0));table.model().rowsRemoved.connect(lambda *args:timer.start(0))
    class ShowSync(QObject):
        def eventFilter(self,watched,event):
            if event.type() in (QEvent.Show,QEvent.StyleChange,QEvent.Resize):timer.start(0)
            return False
    table.category_show_sync=ShowSync(table);table.installEventFilter(table.category_show_sync)
    if table.parentWidget():table.parentWidget().installEventFilter(table.category_show_sync)
    prepare_outer_layout(table)
    timer.start(0)
    table.category_expansion=sync
