"""Verify the packaged drag/replace dialog with actual visible Qt controls."""
from pathlib import Path
import json,time,traceback
from copy import deepcopy
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from PySide6.QtCore import QTimer,QMimeData,QUrl,QPoint,QPointF,Qt
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtTest import QTest
from .word_batch_engine import generate_batch
from .word_replace_dialog import WordReplaceDialog


def verify_word_drop(window,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);checks=[]
    app=QApplication.instance();tool=window.open_module('word');app.processEvents()
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)});print(name, bool(value),flush=True)
        if not value:raise AssertionError(name)
    def fixture(path,mean):
        ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        root=ET.Element(ns+'document');body=ET.SubElement(root,ns+'body')
        text=f'对照组25例，男14例、女11例，年龄（{mean}±10.2）岁；试验组25例，男15例、女10例，年龄（57.9±9.8）岁。'
        ET.SubElement(ET.SubElement(ET.SubElement(body,ns+'p'),ns+'r'),ns+'t').text=text
        table=ET.SubElement(body,ns+'tbl')
        for values in (('项目','对照组(n=25)','试验组(n=25)'),('CRP','56.68±15.19','56.49±13.86')):
            row=ET.SubElement(table,ns+'tr')
            for value in values:ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(row,ns+'tc'),ns+'p'),ns+'r'),ns+'t').text=value
        with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
    def drag(path):
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(path.resolve()))])
        enter=QDragEnterEvent(QPoint(8,8),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(tool.import_button,enter)
        check('拖入单个docx可接受',enter.isAccepted())
        event=QDropEvent(QPointF(8,8),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(tool.import_button,event)
        check('拖放回调返回后才显示弹窗',not isinstance(app.activeModalWidget(),WordReplaceDialog))
        return mime
    report={'passed':False,'platform':app.platformName()}
    try:
        old=output/'原始Word.docx';new=output/'替换Word.docx';fixture(old,58.6);fixture(new,59.6)
        tool.use_word_prose.setChecked(True);tool.import_word(old);tool.show_group_selection(['对照组','试验组']);tool.confirm_groups()
        check('正文竖表自动显示',tool.inline_prose_active)
        check('五个页签顺序正确',[tool.pages.tabText(i) for i in range(tool.pages.count())]==['1 · 基础资料','2 · 表格匹配','3 · 文字匹配','4 · 全部字段以及来源','5 · 生成与导出'])
        table_before=deepcopy(tool.typed_specs);editor=tool.prose_table_editor
        editor.source.setPlainText(editor.source.toPlainText().replace('58.6','59.1'))
        tool.pages.setCurrentIndex(tool.SOURCES_PAGE);app.processEvents()
        check('文字待识别时仍显示表格字段',any(tool.rule_table.item(i,0).text()=='CRP' for i in range(tool.rule_table.rowCount())))
        check('修改文字不清除表格编辑结果',tool.typed_specs==table_before)
        editor.convert();config=tool.get_config()
        check('重新识别文字后保留表格匹配',tool.typed_specs==table_before)
        check('配置分别保存表格和文字',bool(config['table_match']['typed_fields']) and bool(config['prose_document']))
        check('来源页同时标出表格与正文',any(r['source'].startswith('Word表') for r in config['field_rules']) and any(r['source'].startswith('Word正文') for r in config['field_rules']))
        tool.pages.setCurrentIndex(tool.TABLE_PAGE);app.processEvents();window.grab().save(str(output/'table-after-text-edit.png'))
        tool.pages.setCurrentIndex(tool.PROSE_PAGE);app.processEvents();window.grab().save(str(output/'text-and-table.png'))
        # Verify cancel retains real generated data as well as editable source parameters.
        tool.result=generate_batch(tool.get_config());before=tool.get_config();result=tool.result
        check('生成数据同时包含表格和文字字段','CRP' in result['columns'] and '年龄' in result['columns'] and len(result['rows'])==50)
        for action in ('cancel','confirm'):
            seen=[];errors=[]
            responder=QTimer(tool);responder.setInterval(50)
            def respond(action=action):
                dialog=app.activeModalWidget()
                if not isinstance(dialog,WordReplaceDialog):return
                responder.stop();seen.append(True)
                try:
                    check(action+'：弹窗属于真实主窗口',dialog.parentWidget() is window)
                    check(action+'：弹窗内容可见',dialog.message.isVisible() and dialog.message.width()>100 and dialog.message.height()>20)
                    check(action+'：文字与按钮完整',len(dialog.message.text())>25 and dialog.cancel_button.isVisible() and dialog.confirm_button.isVisible())
                    check(action+'：默认保留当前内容',dialog.cancel_button.isDefault() and not dialog.confirm_button.isDefault())
                    dialog.grab().save(str(output/(action+'-dialog.png')))
                    QTest.mouseClick(dialog.cancel_button if action=='cancel' else dialog.confirm_button,Qt.LeftButton)
                except Exception as exc:errors.append(str(exc));dialog.reject()
            responder.timeout.connect(respond);responder.start()
            # Hard timeout rejects a malformed dialog so package verification cannot hang.
            watchdog=QTimer(tool);watchdog.setSingleShot(True)
            def timeout():
                errors.append('弹窗验证超时')
                modal=app.activeModalWidget()
                if modal:modal.close()
            watchdog.timeout.connect(timeout);watchdog.start(5000)
            mime=drag(new);deadline=time.monotonic()+5.5
            while not seen and not errors and time.monotonic()<deadline:
                app.processEvents();QTest.qWait(10)
            watchdog.stop();responder.stop();watchdog.deleteLater();responder.deleteLater()
            check(action+'：确认弹窗已响应',bool(seen) and not errors)
            if action=='cancel':
                check('取消保留完整编辑配置',tool.get_config()==before)
                check('取消保留生成结果',tool.result is result)
                check('取消保留旧Word',tool.source==str(old.resolve()))
            else:
                check('确认后导入新Word',tool.pending_source==str(new.resolve()))
                check('确认后清除旧数据',tool.result is None and tool.metrics.rowCount()==0 and tool.prose_table_editor.document is None)
        window.grab().save(str(output/'after-replace.png'))
        report['passed']=True
    except Exception:
        report['traceback']=traceback.format_exc()
    report['checks']=checks
    (output/'word-drop-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['passed']
