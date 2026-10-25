"""Check closed dropdown wheel protection in the bundled four-tool application."""
import json,traceback
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QWidget,QComboBox,QFontComboBox,QVBoxLayout,QScrollArea
from PySide6.QtTest import QTest


def verify_inputs(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);app=QApplication.instance();checks=[];tested=0
    host=QWidget(window);host.setWindowFlags(Qt.Window);layout=QVBoxLayout(host)
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    def wheel(widget,dy=-120,pixel=False):
        point=widget.rect().center();event=QWheelEvent(QPointF(point),QPointF(widget.mapToGlobal(point)),QPoint(0,dy) if pixel else QPoint(),QPoint() if pixel else QPoint(0,dy),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
        app.sendEvent(widget,event);app.processEvents()
    try:
        window.timer.stop();check('应用已安装全局下拉框滚轮保护',hasattr(app,'combo_wheel_guard'))
        for key in ('category','numeric','word','shap'):
            tool=window.open_module(key)
            if key=='word':tool.add_indicator()
            app.processEvents();combos=list(dict.fromkeys(tool.findChildren(QComboBox)+[c for b in window.boards.values() for c in b.findChildren(QComboBox)]))
            count=0
            for combo in combos:
                if combo.count()<2:continue
                before=(combo.currentIndex(),combo.currentText());combo.setFocus()
                for dy,pixel in [(-120,False),(120,False),(-24,True),(24,True)]:wheel(combo,dy,pixel)
                if (combo.currentIndex(),combo.currentText())!=before:raise AssertionError(key+'下拉值被滚轮更改')
                if combo.isEditable():
                    wheel(combo.lineEdit());wheel(combo.lineEdit(),24,True)
                    if (combo.currentIndex(),combo.currentText())!=before:raise AssertionError(key+'可输入下拉值被滚轮更改')
                count+=1
            tested+=count;check(key+'模块及主界面下拉框滚轮不改值',count>0)
        area=QScrollArea();area.setWidgetResizable(True);body=QWidget();body.setMinimumHeight(1800);bl=QVBoxLayout(body);combo=QComboBox();combo.addItems(['A','B','C']);combo.setCurrentIndex(1);bl.addWidget(combo);bl.addStretch();area.setWidget(body);layout.addWidget(area);host.resize(400,300);host.show();app.processEvents()
        wheel(combo);check('下拉框上滚轮继续滚动父页面',area.verticalScrollBar().value()>0 and combo.currentIndex()==1)
        area.verticalScrollBar().setValue(0);combo.setFocus();QTest.keyClick(combo,Qt.Key_Down);check('键盘选择仍正常',combo.currentIndex()==2)
        combo.clear();combo.addItems([str(i) for i in range(80)]);combo.setMaxVisibleItems(6);combo.showPopup();app.processEvents();view=combo.view();bar=view.verticalScrollBar();before=bar.value();index=combo.currentIndex();wheel(view.viewport());check('展开列表可滚动且未直接改值',bar.value()>before and combo.currentIndex()==index)
        target=view.indexAt(QPoint(10,view.viewport().height()//2));QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=view.visualRect(target).center());app.processEvents();check('点击选项仍正常',combo.currentIndex()==target.row())
        report=dict(passed=True,checks=checks,dropdown_checks=tested)
    except Exception:report=dict(passed=False,checks=checks,dropdown_checks=tested,traceback=traceback.format_exc())
    finally:host.close();host.deleteLater()
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['passed']
