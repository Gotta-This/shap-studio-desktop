"""Exercise selected-group Word import using an entirely synthetic document."""
import json,time,traceback
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog,QLineEdit
from .word_batch_engine import W


def verify_groups(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);checks=[];app=QApplication.instance()
    original_open,original_save=QFileDialog.getOpenFileName,QFileDialog.getSaveFileName
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    def pump():app.processEvents()
    def wait(tool):
        end=time.monotonic()+120
        while tool.is_running() and time.monotonic()<end:pump();time.sleep(.01)
        pump();check('后台任务正常结束',not tool.is_running())
    def shot(name):pump();window.grab().save(str(root/(name+'.png')))
    try:
        doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body')
        names=['观察组','常规治疗组','强化治疗组']
        tables=[ [('编号','组别','例数','治疗前','治疗后')]+[(str(i+1),g,'8',f'{10+i}±2',f'{8+i}±1') for i,g in enumerate(names)],
                 [('组别','氧合指数')]+[(g,f'{200+i*10}±10') for i,g in enumerate(names)],
                 [('说明','没有组别的表格')] ]
        for rows in tables:
            table=ET.SubElement(body,W+'tbl')
            for values in rows:
                row=ET.SubElement(table,W+'tr')
                for value in values:
                    cell=ET.SubElement(row,W+'tc');p=ET.SubElement(cell,W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=value
        source=root/'synthetic-groups.docx'
        with ZipFile(source,'w') as z:z.writestr('word/document.xml',ET.tostring(doc))
        window.timer.stop();tool=window.open_module('word');tool.decimal_mode.setCurrentIndex(tool.decimal_mode.findData('source'));pump()
        QFileDialog.getOpenFileName=lambda *a,**kw:(str(source),'Word');tool.import_button.click();pump()
        check('导入后先填写组别且不自动解析指标',tool.group_panel.isVisible() and not tool.groups_confirmed and tool.metrics.rowCount()==0)
        check('导入自动填入全部候选组别',[e.text() for e in tool.group_inputs]==names)
        check('确认前禁止生成',not tool.generate_button.isEnabled())
        tool.show_group_selection(names)
        match=tool.match_groups();check('3张表与3个组别精确匹配',match.table_count==3 and match.group_matches==dict.fromkeys(names,2))
        check('显示逐表匹配与未匹配表格','表3：未匹配' in tool.match_report.toPlainText() and '3/3' in tool.match_summary.text())
        shot('01-select-groups')
        tool.confirm_groups_button.click();pump()
        check('确认后为三个实际组别建立配置',[e.name for e in tool.group_editors]==names and tool.groups_confirmed)
        check('三项指标各有三个组配置',tool.metrics.rowCount()==9)
        check('各组均数来自对应Word行',[tool.metrics.item(i,3).text() for i in range(3)]==['10.0','11.0','12.0'])
        cell=tool.metrics.item(0,1);tool.metrics.editItem(cell);pump();editor=tool.metrics.findChild(QLineEdit)
        check('指标列名可打开实际编辑框',editor is not None)
        editor.setText('自定义治疗前指标');QTest.keyClick(editor,Qt.Key_Return);pump()
        check('列名修改同步三个组别',all(tool.metrics.item(i,1).text()=='自定义治疗前指标' for i in range(3)))
        tool.common_n.setValue(8);shot('02-edit-indicators')
        tool.generate_button.click();wait(tool);check('生成24行且组别各8行',tool.result is not None and Counter(row[1] for row in tool.result['rows'])==dict.fromkeys(names,8))
        result=tool.result;check('9个组别指标的统计偏差合理',all(abs(c['mean_error'])<.02 and abs(c['sd_error'])<.02 for c in result['checks'] if 'actual_mean' in c))
        output=root/'custom-groups.xlsx';QFileDialog.getSaveFileName=lambda *a,**kw:(str(output),'Excel');tool.export_button.click();wait(tool)
        from openpyxl import load_workbook
        book=load_workbook(output,data_only=True);data=list(book.worksheets[0].values)
        check('Excel采用编辑后的指标列名','自定义治疗前指标' in data[0])
        check('Excel各单元格等于生成结果',list(data[0])==result['columns'] and [list(row) for row in data[1:]]==[[None if v=='' else v for v in row] for row in result['rows']]);book.close()
        shot('03-generated-export')
        window.open_module('numeric');window.open_module('word');check('切换工具保留组别与结果',tool.result is result and [e.name for e in tool.group_editors]==names)
        passed=True;report=dict(passed=True,checks=checks)
    except Exception:passed=False;report=dict(passed=False,checks=checks,traceback=traceback.format_exc())
    finally:QFileDialog.getOpenFileName=original_open;QFileDialog.getSaveFileName=original_save
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return passed
