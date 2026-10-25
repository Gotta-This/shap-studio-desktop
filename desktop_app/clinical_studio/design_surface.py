"""Render the actual Penpot layout, with live Qt controls at its measured anchors."""
import html
import json
import math
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QRectF,QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QTextDocument, QFont
from PySide6.QtWidgets import (
    QWidget, QGraphicsView, QGraphicsScene, QFrame, QPushButton, QLineEdit,
    QTableWidget, QHeaderView, QAbstractItemView,QScrollArea,
)

LAYOUT=json.loads((Path(__file__).parent/'assets/penpot-layout.json').read_text(encoding='utf-8'))


class DesignBoard(QWidget):
    def __init__(self,index,shell=True):
        super().__init__();self.index=index;self.is_shell=shell;self.spec=deepcopy(LAYOUT['boards'][index])
        self.setFixedSize(int(self.spec['width']),int(self.spec['height']))
        self.hidden_shapes=set();self.overrides={};self.documents={};self.controls={};self.anchors=[]

    def shape_at(self,x,y,kind=None):
        return next(s for s in self.spec['shapes'] if abs(s['x']-x)<1 and abs(s['y']-y)<1 and (kind is None or s['type']==kind))

    def text(self,x,y,value):
        shape=self.shape_at(x,y,'text');self.overrides[shape['id']]=str(value);self.update()

    def suppress(self,x,y,w,h):
        area=QRectF(x-.5,y-.5,w+1,h+1)
        for s in self.spec['shapes']:
            if area.contains(QRectF(s['x'],s['y'],s['width'],s['height'])):self.hidden_shapes.add(s['id'])

    def place(self,widget,rect,name):
        widget.setParent(self)
        x,y,w,h=rect
        if self.is_shell and x>=224 and y>=76:y-=76 if y>=200 else 56
        rect=(x,y,w,h)
        widget.setGeometry(*map(int,rect));widget.setObjectName(name)
        widget.setFont(QFont('Noto Sans SC'))
        self.controls[name]=widget;self.anchors.append(dict(name=name,rect=list(rect)))
        widget.show();return widget

    def hotspot(self,rect,action,name):
        button=QPushButton(self);button.setAccessibleName(name)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet('QPushButton{border:none;background:transparent;padding:0;} QPushButton:focus{border:none;outline:none;background:transparent;}')
        button.clicked.connect(action);return self.place(button,rect,name)

    def input(self,x,y,w,key):
        self.suppress(x+1,y+1,w-2,40)
        editor=QLineEdit(self);editor.setAccessibleName(key)
        editor.setStyleSheet("QLineEdit{border:none;border-radius:0;background:transparent;padding:0;min-height:0;color:#193C2C;font-size:14px;font-weight:400;}")
        self.place(editor,(x+12,y+8,w-24,26),key);return editor

    def table(self,rect,headers,widths,key):
        self.suppress(*rect)
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide();table.setShowGrid(False);table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setStretchLastSection(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.horizontalHeader().setFixedHeight(40);table.verticalHeader().setDefaultSectionSize(44)
        table.setStyleSheet('QTableWidget{border:none;border-radius:0;background:white;alternate-background-color:#F9FBF9;font-size:12px;} QTableWidget::item{padding:0 14px;border-bottom:1px solid #DEE8DF;} QHeaderView::section{background:#ECF6EF;color:#738477;border:0;padding:0 14px;font-size:11px;font-weight:500;text-align:left;}')
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        for i,width in enumerate(widths):table.setColumnWidth(i,width)
        self.place(table,rect,key);return table

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not self.is_shell:return
        if 'sidebar-footer' in self.controls and self.controls['sidebar-footer'].parentWidget() is self:self.controls['sidebar-footer'].setGeometry(20,self.height()-110,184,90)
        if 'word-workflow' in self.controls:self.controls['word-workflow'].setGeometry(260,130,1144,max(500,self.height()-154))

    def shape_rect(self,shape):
        rect=QRectF(shape['x'],shape['y'],shape['width'],shape['height'])
        if not self.is_shell:return rect
        if shape['x']==0 and shape['height']>=960:rect.setHeight(self.height())
        elif shape['x']>=224:
            if shape['y']==0 and shape['height']==76:rect.setHeight(44)
            elif shape['y']==111 and shape['type']=='text':rect=QRectF(260,52,900,42)
            elif shape['y']==156 and shape['type']=='text':rect=QRectF(260,96,930,20)
            elif shape['y']>=200:rect.translate(0,-76)
            elif shape['y']>=76:rect.translate(0,-56)
            elif shape['type']=='text':rect.translate(0,-16)
        return rect

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor(self.spec['fill']))
        for shape in self.spec['shapes']:
            if shape['id'] in self.hidden_shapes:continue
            rect=self.shape_rect(shape)
            fills=shape.get('fills') or [];color=fills[0].get('fillColor','#FFFFFF') if fills else '#FFFFFF'
            if shape['type']=='text':
                text=self.overrides.get(shape['id'],shape.get('text',''))
                size=float(shape.get('fontSize') or 14);weight=shape.get('fontWeight') or '400'
                if self.is_shell and shape['x']>=224 and shape['y']==111:size=28
                elif self.is_shell and shape['x']>=224 and shape['y']==156:size=13
                cache=(text,size,weight,color,rect.width())
                doc=self.documents.get(cache)
                if doc is None:
                    doc=QTextDocument();doc.setDocumentMargin(0)
                    doc.setDefaultStyleSheet(f'body {{margin:0;font-family:"Noto Sans SC";font-size:{size}px;font-weight:{weight};color:{color};line-height:150%;}}')
                    doc.setHtml('<body>'+html.escape(text).replace(' ','&nbsp;').replace('\n','<br>')+'</body>');doc.setTextWidth(rect.width())
                    self.documents[cache]=doc
                painter.save();painter.translate(rect.x(),rect.y());doc.drawContents(painter);painter.restore()
            else:
                painter.setBrush(QColor(color) if fills else Qt.NoBrush)
                strokes=shape.get('strokes') or []
                if strokes:
                    stroke=strokes[0];painter.setPen(QPen(QColor(stroke.get('strokeColor','#DEE8DF')),float(stroke.get('strokeWidth',1))))
                else:painter.setPen(Qt.NoPen)
                radius=shape.get('radius') or 0
                painter.drawRoundedRect(rect,radius,radius)


class DesignView(QGraphicsView):
    def __init__(self,board,parent=None):
        super().__init__(parent);self.board=board
        self.setFrameShape(QFrame.NoFrame);self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setAlignment(Qt.AlignLeft|Qt.AlignTop);self.setTransformationAnchor(QGraphicsView.NoAnchor);self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setStyleSheet('QGraphicsView{border:0;background:#F5F8F5;}')
        scene=QGraphicsScene(self);scene.setSceneRect(0,0,1440,960);scene.addWidget(board);self.setScene(scene)
        self.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
        self.footer=board.controls.get('sidebar-footer')
        if self.footer:self.footer.setParent(self.viewport());self.footer.show()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_layout()

    def showEvent(self,event):
        super().showEvent(event);self.update_layout()

    def update_layout(self):
        factor=max(0.1,self.viewport().width()/1440)
        minimum=800 if self.board.index==3 else 928
        height=max(minimum,math.floor(self.viewport().height()/factor))
        self.board.setFixedHeight(height);self.scene().setSceneRect(0,0,1440,height)
        self.resetTransform();self.scale(factor,factor)
        if self.footer:
            self.footer.setGeometry(round(20*factor),self.viewport().height()-round(110*factor),round(184*factor),round(90*factor))
            self.footer.setStyleSheet(f'QLabel{{background:#FFFFFF;color:#738477;font-size:{max(9,round(11*factor))}px;padding:0;}}')
            self.footer.raise_()


class DesignRegion(DesignBoard):
    """A scrollable portion of a design, keeping its measured typography."""
    def __init__(self,source,rect):
        super().__init__(source.index,shell=False)
        x,y,w,h=rect;area=QRectF(x,y,w,h)
        self.spec=deepcopy(source.spec);self.spec['fill']='#FFFFFF'
        self.spec['shapes']=[deepcopy(s) for s in source.spec['shapes'] if area.contains(QRectF(s['x'],s['y'],s['width'],s['height']))]
        for shape in self.spec['shapes']:shape['x']-=x;shape['y']-=y
        self.base_y={s['id']:s['y'] for s in self.spec['shapes']}
        self.setFixedSize(w,h);source.suppress(*rect)

    def expand_below(self,start,delta,min_height):
        for shape in self.spec['shapes']:
            original=self.base_y[shape['id']]
            shape['y']=original+(delta if original>=start else 0)
        height=max((s['y']+s['height'] for s in self.spec['shapes']),default=0)
        self.setFixedHeight(max(min_height,int(height)+2));self.update()


class ParameterScrollArea(QScrollArea):
    """Let wheel/trackpad gestures over a full-height table scroll its panel."""
    def route_wheel(self,widget):widget.installEventFilter(self)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Wheel:
            amount=event.pixelDelta().y() or event.angleDelta().y()/120*self.verticalScrollBar().singleStep()*3
            if amount:
                bar=self.verticalScrollBar();bar.setValue(bar.value()-int(amount));event.accept();return True
        return super().eventFilter(watched,event)
