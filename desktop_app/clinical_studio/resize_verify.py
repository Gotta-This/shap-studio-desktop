"""Exercise resize grips in the real app, including the graphics-scene page shells."""
import json,traceback
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QMouseEvent,QWheelEvent
from PySide6.QtWidgets import QApplication,QScrollArea,QPlainTextEdit,QTableView,QTableWidget
from PySide6.QtTest import QTest


def verify_resize(window,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);app=QApplication.instance();checks=[]
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)});print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def pump():
        for _ in range(3):app.processEvents()
    def drag(field,dx=0,dy=500):
        pump();check('字段显示拖动手柄',hasattr(field,'resize_grip'))
        grip=field.resize_grip;point=grip.rect().center();global_point=grip.mapToGlobal(point)
        QTest.mousePress(grip,Qt.LeftButton,pos=point)
        move=QMouseEvent(QEvent.MouseMove,QPointF(point+QPoint(dx,dy)),QPointF(global_point+QPoint(dx,dy)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
        app.sendEvent(grip,move);QTest.mouseRelease(grip,Qt.LeftButton,pos=grip.rect().center());pump()
    def area(field):
        parent=field.parentWidget()
        while parent is not None and not isinstance(parent,QScrollArea):parent=parent.parentWidget()
        return parent
    report={'passed':False,'platform':app.platformName()}
    try:
        window.timer.stop()
        window.open_module('category');pump();field=window.category_output;field.setPlainText('1\n2\n3')
        drag(field,dy=650);check('工具1放大后外层可滚动',window.views[1].verticalScrollBar().maximum()>0)
        check('工具1数据保持',field.toPlainText()=='1\n2\n3')
        window.grab().save(str(output/'category-resized.png'))
        table=window.category_table;drag(table,dy=600)
        check('工具1分类表外层可滚动',window.category_scroll.verticalScrollBar().maximum()>0)
        check('工具1按钮没有被表格覆盖',window.category_region.controls['add-category'].y()>table.height())
        window.open_module('numeric');pump();field=window.numeric_output;field.setPlainText('10\n20')
        drag(field,dx=500,dy=600)
        check('工具2外层横向和纵向滚动',window.views[2].horizontalScrollBar().maximum()>0 and window.views[2].verticalScrollBar().maximum()>0)
        check('工具2数据保持',field.toPlainText()=='10\n20');window.grab().save(str(output/'numeric-resized.png'))
        tool=window.open_module('word');tool.pages.setCurrentIndex(tool.PROSE_PAGE);pump();editor=tool.prose_table_editor
        editor.source.setPlainText('拉伸不改变原文');editor.evidence.setPlainText('来源信息保持')
        evidence_height=editor.evidence.height();status_height=editor.status.height()
        drag(editor.source,dy=300);drag(editor.table,dy=450)
        check('工具3相邻文字区域不被挤压',editor.evidence.height()==evidence_height and editor.status.height()==status_height)
        check('工具3外层内容可滚动',area(editor.table).verticalScrollBar().maximum()>0)
        check('工具3原文和来源保持',editor.source.toPlainText()=='拉伸不改变原文' and editor.evidence.toPlainText()=='来源信息保持')
        area(editor.table).verticalScrollBar().setValue(0);pump();window.grab().save(str(output/'word-resized.png'))
        source_height=editor.source.height()
        for width,height in ((1440,1250),(1100,800),(1600,1100),(1010,1000),(1440,960)):
            window.resize(width,height);pump();board=window.boards[3];view=window.views[3]
            check('窗口缩放后页面边界同步 '+str((width,height)),board.graphicsProxyWidget().size().toSize()==board.size() and view.sceneRect().size().toSize()==board.size())
            check('窗口缩放后原文尺寸保持 '+str((width,height)),editor.source.height()==source_height and editor.source.toPlainText()=='拉伸不改变原文')
        window.resize(1440,1250);pump();window.grab().save(str(output/'word-window-enlarged.png'))
        for field in (editor.source,editor.table,editor.evidence,editor.status):
            drag(field,dx=-250,dy=80-field.height())
        panels=editor.table.parentWidget().layout()
        check('缩小后表格从容器顶部排列',editor.table.y()<=panels.contentsMargins().top()+1)
        check('缩小后来源和提示紧接表格',editor.evidence.y()-editor.table.geometry().bottom()-1<=panels.spacing()+1 and editor.status.y()-editor.evidence.geometry().bottom()-1<=panels.spacing()+1)
        check('缩小后外层滚动范围收回',area(editor.source).verticalScrollBar().maximum()<=5)
        window.grab().save(str(output/'word-prose-shrunk.png'))
        tool.add_indicator();pump()
        for page,fields,name in ((tool.TABLE_PAGE,tuple(tool.source_tables.tables.values()),'table'),(tool.SOURCES_PAGE,(tool.rule_table,tool.log),'sources')):
            tool.pages.setCurrentIndex(page);pump()
            for field in fields:
                if field.isVisible():drag(field,dx=-200,dy=80-field.height())
            body=area(fields[0]).widget();caption=body.layout().itemAt(0).widget()
            check(name+'缩小后说明紧靠顶部',caption.y()<=body.layout().contentsMargins().top()+1 and caption.height()<=caption.sizeHint().height()+1)
            window.grab().save(str(output/('word-'+name+'-shrunk.png')))
        window.open_module('shap');pump();table=window.data_table;value=table.item(0,0).text();drag(table,dy=650)
        check('工具4放大表格后外层可滚动',window.views[4].verticalScrollBar().maximum()>0)
        check('工具4表格值保持',table.item(0,0).text()==value);window.grab().save(str(output/'shap-resized.png'))
        probe=QTableWidget(100,20,window);probe.setWindowFlags(Qt.Window);probe.resize(500,300)
        for column in range(20):probe.setColumnWidth(column,300)
        probe.show();pump()
        try:
            for axis,delta,bar in (('横向',QPoint(-3,0),probe.horizontalScrollBar()),('纵向',QPoint(0,-3),probe.verticalScrollBar())):
                bar.setValue(100);viewport=probe.viewport();point=viewport.rect().center()
                for phase in (Qt.ScrollUpdate,Qt.ScrollMomentum):
                    before=bar.value()
                    wheel=QWheelEvent(QPointF(point),QPointF(viewport.mapToGlobal(point)),delta,QPoint(),Qt.NoButton,Qt.NoModifier,phase,False)
                    app.sendEvent(viewport,wheel);pump()
                    check(axis+'触控板像素滚动 '+str(phase),bar.value()==before+3)
                before=bar.value();angle=QPoint(-120,0) if delta.x() else QPoint(0,-120)
                app.sendEvent(viewport,QWheelEvent(QPointF(point),QPointF(viewport.mapToGlobal(point)),QPoint(),angle,Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False));pump()
                check(axis+'鼠标滚轮小步滚动',0<bar.value()-before<=48)
        finally:probe.close();probe.deleteLater()
        report['passed']=True
    except Exception:report['traceback']=traceback.format_exc()
    report['checks']=checks;(output/'resize-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report['passed']
