"""Mint date picker with a native popup, complete calendar and keyboard input."""
from datetime import date, timedelta
from PySide6.QtCore import Qt, QDate, QPoint, QPointF, QRect, QEvent, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QStackedWidget, QWidget, QLabel, QPushButton, QLineEdit,
    QGraphicsDropShadowEffect, QMenu, QWidgetAction)
from PySide6.QtCore import Signal
from .editor_dialogs import native_owner


def calendar_icon():
    pix = QPixmap(36, 36); pix.fill(Qt.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing); p.scale(2, 2)
    p.setPen(QPen(QColor('#789187'), 1.25, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawRoundedRect(3, 4, 12, 11, 2, 2); p.drawLine(3, 8, 15, 8)
    p.drawLine(6, 2, 6, 5); p.drawLine(12, 2, 12, 5)
    p.end(); pix.setDevicePixelRatio(2); return QIcon(pix)


def anchor_rect(widget):
    """Map embedded shell controls through their graphics proxy, including scroll."""
    owner = widget.window(); proxy = owner.graphicsProxyWidget()
    if proxy is not None and proxy.scene() is not None and proxy.scene().views():
        view = proxy.scene().views()[0]
        point = widget.mapTo(owner, QPoint())
        top = view.viewport().mapToGlobal(view.mapFromScene(proxy.mapToScene(QPointF(point))))
        bottom = view.viewport().mapToGlobal(view.mapFromScene(proxy.mapToScene(QPointF(point + widget.rect().bottomRight()))))
        return QRect(top, bottom)
    return QRect(widget.mapToGlobal(QPoint()), widget.size())


def popup_position(anchor, size, available):
    x = max(available.left()+6, min(anchor.left(), available.right()-size.width()-5))
    y = anchor.bottom()+6
    if y+size.height() > available.bottom()-5:
        y = anchor.top()-size.height()-6
    return QPoint(x, max(available.top()+6, min(y, available.bottom()-size.height()-5)))


class DatePopup(QMenu):
    def __init__(self, value=None, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self._result=QDialog.Rejected
        self.setObjectName('datePopup'); self.setWindowTitle('选择日期')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.result_value = value
        self.selected = QDate.fromString(value, 'yyyy-MM-dd') if value else QDate()
        self.cursor = self.selected if self.selected.isValid() else QDate.currentDate()
        self.page = QDate(self.cursor.year(), self.cursor.month(), 1)
        self.mode = 'days'; self.decade = self.page.year()//10*10
        self.setFixedWidth(344)
        self.setStyleSheet('''
            QMenu#datePopup {background:transparent;border:0;padding:0;}
            QFrame#dateCard {background:white;border:1px solid #DEE8DF;border-radius:12px;}
            QFrame#dateCard QWidget {font-size:13px;color:#314C3E;background:transparent;}
            QFrame#dateCard QPushButton {background:transparent;border:0;border-radius:6px;padding:0;min-height:0;font-size:13px;}
            QFrame#dateCard QPushButton:hover {background:#EDF7F0;color:#195D42;}
            QFrame#dateCard QPushButton:focus {border:1px solid #8DBDA2;}
            QFrame#dateCard QPushButton:disabled {color:#CCD5CF;}
            QFrame#dateCard QPushButton[outside="true"] {color:#A8B5AC;}
            QFrame#dateCard QPushButton[today="true"] {border:1px solid #82B49A;color:#277453;}
            QFrame#dateCard QPushButton:checked {background:#277453;color:white;border:1px solid #277453;font-weight:600;}
            QFrame#dateCard QPushButton#dateHeading {font-weight:600;color:#193C2C;}
            QFrame#dateCard QPushButton#dateArrow {color:#789187;font-size:19px;}
            QFrame#dateCard QPushButton#dateShortcut {color:#277453;}
            QFrame#dateCard QLineEdit {background:white;border:1px solid #DEE8DF;border-radius:6px;padding:5px 9px;min-height:0;selection-background-color:#DDF1E4;}
            QFrame#dateCard QLineEdit:focus {border-color:#277453;}
            QFrame#dateCard QLineEdit[invalid="true"] {border-color:#BE725A;}
            QFrame#dateCard QLabel#dateError {color:#A85F47;font-size:11px;}
            QFrame#dateCard QLabel#dateWeek {color:#879B8E;font-size:12px;}
            QFrame#dateCard QFrame#dateDivider {background:#ECF1ED;border:0;}
        ''')
        content=QWidget();content.setFixedWidth(344)
        outer = QVBoxLayout(content); outer.setContentsMargins(8, 8, 8, 8)
        card = QFrame(); card.setObjectName('dateCard'); outer.addWidget(card)
        shadow = QGraphicsDropShadowEffect(card); shadow.setBlurRadius(15); shadow.setOffset(0, 3)
        shadow.setColor(QColor(25, 60, 44, 22)); card.setGraphicsEffect(shadow)
        body = QVBoxLayout(card); body.setContentsMargins(12, 12, 12, 10); body.setSpacing(8)
        self.input = QLineEdit(value or ''); self.input.setPlaceholderText('输入日期  YYYY-MM-DD')
        self.input.setAccessibleName('输入日期，格式为年-月-日'); self.input.setFixedHeight(32)
        self.input.returnPressed.connect(self.commit_input); self.input.textEdited.connect(lambda _:self.clear_error())
        body.addWidget(self.input)
        nav = QHBoxLayout(); nav.setSpacing(2)
        self.previous_year = self.make_button('«', lambda:self.move_page(-12), 'dateArrow', 24)
        self.previous_month = self.make_button('‹', lambda:self.move_page(-1), 'dateArrow', 24)
        self.year_button = self.make_button('', self.pick_year, 'dateHeading')
        self.month_button = self.make_button('', self.pick_month, 'dateHeading')
        self.next_month = self.make_button('›', lambda:self.move_page(1), 'dateArrow', 24)
        self.next_year = self.make_button('»', lambda:self.move_page(12), 'dateArrow', 24)
        for b, name in [(self.previous_year,'上一年'),(self.previous_month,'上一月'),(self.next_month,'下一月'),(self.next_year,'下一年')]:
            b.setAccessibleName(name); b.setToolTip(name)
        for b in (self.previous_year,self.previous_month): nav.addWidget(b)
        nav.addWidget(self.year_button,1); nav.addWidget(self.month_button,1)
        for b in (self.next_month,self.next_year): nav.addWidget(b)
        body.addLayout(nav)
        self.pages = QStackedWidget(); self.pages.setFixedHeight(238); body.addWidget(self.pages)
        days = QWidget(); grid = QGridLayout(days); grid.setContentsMargins(0,0,0,0); grid.setHorizontalSpacing(4); grid.setVerticalSpacing(2)
        for col, text in enumerate('一二三四五六日'):
            label = QLabel(text); label.setObjectName('dateWeek'); label.setAlignment(Qt.AlignCenter); label.setFixedHeight(20)
            grid.addWidget(label,0,col)
        self.days = []
        for i in range(42):
            b = self.make_button('', lambda _,i=i:self.choose(self.days[i].date_value), width=36)
            b.setFixedHeight(32); b.setCheckable(True); b.installEventFilter(self)
            grid.addWidget(b,1+i//7,i%7,Qt.AlignCenter); self.days.append(b)
        self.pages.addWidget(days)
        self.months = self.make_grid(12, self.choose_month); self.pages.addWidget(self.months)
        self.years = self.make_grid(12, self.choose_year); self.pages.addWidget(self.years)
        divider = QFrame(); divider.setObjectName('dateDivider'); divider.setFixedHeight(1); body.addWidget(divider)
        foot = QHBoxLayout(); foot.setSpacing(4)
        self.today_button = self.make_button('今天', lambda:self.choose(QDate.currentDate()), 'dateShortcut')
        self.tomorrow_button = self.make_button('明天', lambda:self.choose(QDate.currentDate().addDays(1)), 'dateShortcut')
        self.clear_button = self.make_button('清除日期', lambda:self.choose(None), 'dateShortcut')
        self.today_button.setFixedWidth(44); self.tomorrow_button.setFixedWidth(44); self.clear_button.setFixedWidth(72)
        foot.addWidget(self.today_button); foot.addWidget(self.tomorrow_button); foot.addStretch(); foot.addWidget(self.clear_button)
        body.addLayout(foot)
        self.error = QLabel(''); self.error.setObjectName('dateError'); self.error.setFixedHeight(16); body.addWidget(self.error)
        action=QWidgetAction(self);action.setDefaultWidget(content);self.addAction(action)
        self.render(); self.adjustSize()

    def make_button(self, text, callback, name='', width=None):
        b = QPushButton(text); b.setObjectName(name); b.setFixedHeight(28); b.setAutoDefault(False)
        if width is not None: b.setFixedWidth(width)
        b.clicked.connect(callback); return b

    def make_grid(self, count, callback):
        page = QWidget(); layout = QGridLayout(page); layout.setContentsMargins(0,4,0,4); layout.setSpacing(8)
        page.buttons = []
        for i in range(count):
            b = self.make_button('', lambda _,i=i:callback(i)); b.setFixedHeight(44); b.setCheckable(True)
            layout.addWidget(b,i//3,i%3); page.buttons.append(b)
        return page

    @staticmethod
    def restyle(widget):
        widget.style().unpolish(widget); widget.style().polish(widget); widget.update()

    def render(self):
        self.pages.setCurrentIndex({'days':0,'months':1,'years':2}[self.mode])
        self.year_button.setText(f'{self.decade} – {self.decade+9}' if self.mode=='years' else f'{self.page.year()} 年')
        self.month_button.setText(f'{self.page.month()} 月'); self.month_button.setVisible(self.mode!='years')
        self.previous_year.setVisible(self.mode=='days'); self.next_year.setVisible(self.mode=='days')
        step = 10 if self.mode=='years' else 1
        self.previous_month.setEnabled(self.decade>1 if self.mode=='years' else self.page.year()>1 or (self.mode=='days' and self.page.month()>1))
        self.next_month.setEnabled(self.decade+step<=9999 if self.mode=='years' else self.page.year()<9999 or (self.mode=='days' and self.page.month()<12))
        self.previous_year.setEnabled(self.page.year()>1); self.next_year.setEnabled(self.page.year()<9999)
        self.previous_month.setAccessibleName('上一月' if self.mode=='days' else '上一年' if self.mode=='months' else '上一组年份')
        self.next_month.setAccessibleName('下一月' if self.mode=='days' else '下一年' if self.mode=='months' else '下一组年份')
        first = self.page.addDays(1-self.page.dayOfWeek())
        for i,b in enumerate(self.days):
            value = first.addDays(i); b.date_value = value; b.setText(str(value.day()) if value.isValid() else '')
            b.setEnabled(value.isValid() and 1<=value.year()<=9999); b.setAccessibleName(value.toString('yyyy-MM-dd')); b.setToolTip(value.toString('yyyy-MM-dd'))
            b.setProperty('outside',value.month()!=self.page.month()); b.setProperty('today',value==QDate.currentDate())
            b.setChecked(self.selected.isValid() and value==self.selected); self.restyle(b)
        for i,b in enumerate(self.months.buttons):
            b.setText(f'{i+1} 月'); b.setChecked(self.selected.year()==self.page.year() and self.selected.month()==i+1)
        for i,b in enumerate(self.years.buttons):
            year = self.decade-1+i; b.setText(str(year)); b.setEnabled(1<=year<=9999)
            b.setChecked(self.selected.year()==year); b.setProperty('outside',year<self.decade or year>self.decade+9); self.restyle(b)

    def move_page(self, delta):
        if self.mode=='years': self.decade = max(1,min(9990,self.decade+10*(1 if delta>0 else -1)))
        else:
            value = self.page.addMonths(delta if self.mode=='days' else 12*delta)
            if value.isValid(): self.page = value
        self.render()

    def pick_year(self):
        self.mode='years' if self.mode!='years' else 'days'; self.decade=max(1,self.page.year()//10*10); self.render()

    def pick_month(self):
        self.mode='months' if self.mode!='months' else 'days'; self.render()

    def choose_month(self, index):
        self.page=QDate(self.page.year(),index+1,1); self.mode='days'; self.render()

    def choose_year(self, index):
        year=self.decade-1+index
        if 1<=year<=9999: self.page=QDate(year,self.page.month(),1); self.mode='months'; self.render()

    def choose(self, value):
        if value is not None and (not value.isValid() or not 1<=value.year()<=9999): return
        self.result_value = value.toString('yyyy-MM-dd') if value is not None else None
        self.accept()

    def clear_error(self):
        self.error.clear(); self.input.setProperty('invalid',False); self.restyle(self.input)

    def commit_input(self):
        text=self.input.text().strip()
        if not text: self.choose(None); return
        value=QDate.fromString(text,'yyyy-MM-dd')
        if not value.isValid() or value.toString('yyyy-MM-dd')!=text:
            self.error.setText('请输入有效日期，例如 2026-11-07')
            self.input.setProperty('invalid',True); self.restyle(self.input); return
        self.choose(value)

    def eventFilter(self, watched, event):
        if event.type()==QEvent.KeyPress and watched in self.days:
            key=event.key(); value=watched.date_value
            if key in (Qt.Key_Left,Qt.Key_Right,Qt.Key_Up,Qt.Key_Down):
                value=value.addDays({Qt.Key_Left:-1,Qt.Key_Right:1,Qt.Key_Up:-7,Qt.Key_Down:7}[key])
            elif key in (Qt.Key_PageUp,Qt.Key_PageDown): value=value.addMonths(-1 if key==Qt.Key_PageUp else 1)
            elif key in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Space): self.choose(value); return True
            else: return super().eventFilter(watched,event)
            if value.isValid() and 1<=value.year()<=9999:
                self.cursor=value; self.page=QDate(value.year(),value.month(),1); self.render()
                next(b for b in self.days if b.date_value==value).setFocus()
            return True
        return super().eventFilter(watched,event)

    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(0,self.focus_input)

    def focus_input(self):
        self.input.setFocus();self.input.selectAll()

    def accept(self):
        self._result=QDialog.Accepted;self.close()

    def reject(self):
        self._result=QDialog.Rejected;self.close()

    def result(self):
        return self._result

    def exec_at(self, anchor):
        self.adjustSize()
        screen=QApplication.screenAt(anchor.center()) or self.screen()
        position=popup_position(anchor,self.sizeHint(),screen.availableGeometry())
        self.input.setFocus(); self.input.selectAll()
        self.exec(position)
        return self._result


class DateButton(QPushButton):
    changed=Signal(object)
    def __init__(self,value=None,parent=None):
        super().__init__(parent); self.value=None; self.date_popup=None
        self.setObjectName('todoDate'); self.setMinimumHeight(34); self.setIcon(calendar_icon()); self.setIconSize(QSize(18,18))
        self.setStyleSheet('QPushButton#todoDate{text-align:left;padding:5px 9px;}')
        self.setAccessibleName('选择日期'); self.set_date(value,notify=False); self.clicked.connect(self.pick)

    def set_date(self,value,notify=True):
        if value is not None: value=date.fromisoformat(value).isoformat()
        self.value=value; self.setText(value or '选择日期')
        self.setToolTip(value or '选择日期；可直接输入、使用快捷日期或清除')
        if notify: self.changed.emit(value)

    def pick(self):
        popup=DatePopup(self.value,native_owner(self)); self.date_popup=popup
        try:
            if popup.exec_at(anchor_rect(self))==QDialog.Accepted: self.set_date(popup.result_value)
        finally:
            self.date_popup=None; popup.deleteLater()
