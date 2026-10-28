"""Fixed-size native sidebar items shared by every workspace page."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QFont,QPen,QPainterPath
from PySide6.QtWidgets import QPushButton


class SidebarButton(QPushButton):
    def __init__(self,label,mark):
        super().__init__();self.label=label;self.mark=mark;self.count=None
        self.setCheckable(True);self.setCursor(Qt.PointingHandCursor);self.setAccessibleName(label);self.setText(label)
        self.setStyleSheet('QPushButton{border:none;background:transparent;}')
    def set_count(self,count):
        if self.count!=count:self.count=count;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);active=self.isChecked()
        if active or self.underMouse():
            p.setPen(Qt.NoPen);p.setBrush(QColor('#DDF2E6' if active else '#EDF6EF'));p.drawRoundedRect(QRectF(self.rect()),11,11)
        color=QColor('#075641' if active else '#153F35');muted=QColor('#789187')
        if self.mark=='todo':
            p.setPen(Qt.NoPen);p.setBrush(QColor('#087B59'));p.drawRoundedRect(QRectF(17,13,19,19),5,5)
            p.setPen(QPen(Qt.white,1.8,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));path=QPainterPath(QPointF(21,22));path.lineTo(25,26);path.lineTo(32,18);p.drawPath(path)
        elif self.mark=='home':
            p.setPen(QPen(muted,1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));path=QPainterPath(QPointF(19,23));path.lineTo(24,18);path.lineTo(29,23);path.lineTo(29,30);path.lineTo(20,30);path.lineTo(20,23);p.drawPath(path)
        else:
            font=QFont(self.font());font.setPixelSize(12);font.setWeight(QFont.DemiBold);p.setFont(font);p.setPen(muted);p.drawText(QRectF(16,0,26,self.height()),Qt.AlignVCenter|Qt.AlignLeft,self.mark)
        font=QFont(self.font());font.setPixelSize(14 if self.mark in ('todo','home') else 13);font.setWeight(QFont.DemiBold if active else QFont.Medium);p.setFont(font);p.setPen(color)
        p.drawText(QRectF(48,0,self.width()-52-(34 if self.count is not None else 0),self.height()),Qt.AlignLeft|Qt.AlignVCenter,self.label)
        if self.count is not None:
            text=str(self.count);font.setPixelSize(11);font.setWeight(QFont.DemiBold);p.setFont(font)
            width=max(24,p.fontMetrics().horizontalAdvance(text)+12);rect=QRectF(self.width()-width-10,11,width,24)
            p.setPen(Qt.NoPen);p.setBrush(QColor('#C7E9D5' if active else '#ECF5EF'));p.drawRoundedRect(rect,6,6);p.setPen(QColor('#087B59'));p.drawText(rect,Qt.AlignCenter,text)
