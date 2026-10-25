"""Render the actual Penpot layout, with live Qt controls at its measured anchors."""
import html
import json
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
    def __init__(self,index):
        super().__init__();self.index=index;self.spec=LAYOUT['boards'][index]
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
        widget.setParent(self);widget.setGeometry(*map(int,rect));widget.setObjectName(name)
        widget.setFont(QFont('Noto Sans SC'))
        self.controls[name]=widget;self.anchors.append(dict(name=name,rect=list(rect)))
        widget.show();return widget

    def hotspot(self,rect,action,name):
        button=QPushButton(self);button.setAccessibleName(name)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet('QPushButton{border:none;background:transparent;padding:0;} QPushButton:focus{border:1px dotted #277453;}')
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

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor(self.spec['fill']))
        for shape in self.spec['shapes']:
            if shape['id'] in self.hidden_shapes:continue
            fills=shape.get('fills') or [];color=fills[0].get('fillColor','#FFFFFF') if fills else '#FFFFFF'
            if shape['type']=='text':
                text=self.overrides.get(shape['id'],shape.get('text',''))
                size=float(shape.get('fontSize') or 14);weight=shape.get('fontWeight') or '400'
                cache=(text,size,weight,color,shape['width'])
                doc=self.documents.get(cache)
                if doc is None:
                    doc=QTextDocument();doc.setDocumentMargin(0)
                    doc.setDefaultStyleSheet(f'body {{margin:0;font-family:"Noto Sans SC";font-size:{size}px;font-weight:{weight};color:{color};line-height:150%;}}')
                    doc.setHtml('<body>'+html.escape(text).replace(' ','&nbsp;').replace('\n','<br>')+'</body>');doc.setTextWidth(shape['width'])
                    self.documents[cache]=doc
                painter.save();painter.translate(shape['x'],shape['y']);doc.drawContents(painter);painter.restore()
            else:
                painter.setBrush(QColor(color) if fills else Qt.NoBrush)
                strokes=shape.get('strokes') or []
                if strokes:
                    stroke=strokes[0];painter.setPen(QPen(QColor(stroke.get('strokeColor','#DEE8DF')),float(stroke.get('strokeWidth',1))))
                else:painter.setPen(Qt.NoPen)
                radius=shape.get('radius') or 0
                painter.drawRoundedRect(QRectF(shape['x'],shape['y'],shape['width'],shape['height']),radius,radius)


class DesignView(QGraphicsView):
    def __init__(self,board,parent=None):
        super().__init__(parent);self.board=board
        self.setFrameShape(QFrame.NoFrame);self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet('QGraphicsView{border:0;background:#F5F8F5;}')
        scene=QGraphicsScene(self);scene.setSceneRect(0,0,1440,960);scene.addWidget(board);self.setScene(scene)
        self.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.resetTransform();factor=min(self.viewport().width()/1440,self.viewport().height()/960)
        self.scale(factor,factor)


class DesignRegion(DesignBoard):
    """A scrollable portion of a design, keeping its measured typography."""
    def __init__(self,source,rect):
        super().__init__(source.index)
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
