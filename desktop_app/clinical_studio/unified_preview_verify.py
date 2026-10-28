"""Native acceptance checks for shared editors and pre-confirmation Word drafts."""
import json,traceback
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from .editor_dialogs import EditorDialog
from .merged_table_verify import save_fixture
from .word_batch_engine import W,generate_batch,export_batch
from .typed_field_ui import convert


def verify_unified_preview(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);app=QApplication.instance();checks=[]
    def check(name,passed):
        checks.append(dict(name=name,passed=bool(passed)));print(name,bool(passed),flush=True)
        if not passed:raise AssertionError(name)
    def pump():
        for _ in range(4):app.processEvents()
    report=dict(passed=False)
    try:
        window.timer.stop()
        for key in ('category','numeric','shap'):
            tool=window.open_module(key);pump();errors=[]
            def inspect():
                dialog=app.activeModalWidget()
                try:
                    check(key+'统一原生编辑窗口',isinstance(dialog,EditorDialog) and dialog.isWindow() and dialog.graphicsProxyWidget() is None and dialog.parentWidget() is window)
                    check(key+'标题和底部操作可见',dialog.header.isVisible() and dialog.footer.isVisible())
                    if key=='category':check('少量类别全部展开',tool.table.verticalScrollBar().maximum()==0 and tool.table.viewport().height()>=sum(tool.table.rowHeight(i) for i in range(tool.table.rowCount())))
                    dialog.grab().save(str(root/(key+'-editor.png')))
                except Exception:errors.append(traceback.format_exc())
                finally:
                    if dialog:dialog.accept()
            QTimer.singleShot(150,inspect);window.advanced(key)
            if errors:raise AssertionError(errors[0])
        path=save_fixture(root/'preview-fixture.docx')
        with ZipFile(path) as archive:document=ET.fromstring(archive.read('word/document.xml'))
        body=document.find(W+'body')
        for i,table in enumerate(list(body),1):
            p=ET.Element(W+'p');ET.SubElement(ET.SubElement(p,W+'r'),W+'t').text=f'表{i} 导入预览示例';body.insert(list(body).index(table),p)
        p=ET.SubElement(body,W+'p');ET.SubElement(ET.SubElement(p,W+'r'),W+'t').text='对照组20例，BMI（22.8±3.1）kg/m²；试验组20例，BMI（22.5±2.9）kg/m²。'
        with ZipFile(path,'w') as archive:archive.writestr('word/document.xml',ET.tostring(document))
        tool=window.open_module('word');tool.use_word_prose.setChecked(True);tool.decimal_mode.setCurrentIndex(tool.decimal_mode.findData('source'));tool.use_word_sizes.setChecked(True);tool.import_word(path);pump()
        check('未确认组别已扫描四表与正文',not tool.groups_confirmed and len(tool.word_scan['tables'])==4 and bool(tool.preview_draft['fields']) and bool(tool.preview_draft['prose_document']['studies'][0]['variables']))
        check('候选组别不自动确认',[e.text() for e in tool.group_inputs]==['对照组','试验组'] and not tool.generate_button.isEnabled() and not tool.typed_specs)
        window.grab().save(str(root/'word-unconfirmed.png'))
        errors=[]
        def edit_preview():
            dialog=getattr(tool,'scan_dialog',None)
            try:
                check('导入预览使用统一原生窗口',isinstance(dialog,EditorDialog) and dialog.graphicsProxyWidget() is None and dialog.parentWidget() is window)
                dialog.grab().save(str(root/'word-preview.png'))
                field=next(f for f in dialog.fields.typed_specs if f['table']==1 and f['name']=='年龄（岁）' and f['group']=='对照组');field['mean']=61.23;field['classification']='预览已核对'
                variable=next(v for v in dialog.prose.study()['variables'] if v['name']=='BMI');variable['cells']['对照组']['mean']=24.5
                dialog.accept()
            except Exception:errors.append(traceback.format_exc());dialog.reject()
        QTimer.singleShot(180,edit_preview);tool.open_scan_preview();pump()
        if errors:raise AssertionError(errors[0])
        check('保存草稿后仍不能生成',not tool.groups_confirmed and not tool.generate_button.isEnabled())
        tool.use_candidate_groups();check('填入候选后仍待确认',not tool.groups_confirmed)
        tool.confirm_groups();pump();check('明确确认后才应用识别结果',tool.groups_confirmed)
        check('预览表格修改已保留',next(f for f in tool.typed_specs if f['table']==1 and f['name']=='年龄（岁）' and f['group']=='对照组')['mean']==61.23)
        check('预览文字修改已保留',next(v for v in tool.prose_table_editor.study()['variables'] if v['name']=='BMI')['cells']['对照组']['mean']==24.5)
        tool.set_typed_fields([convert(f,'excluded') if f.get('aggregate_pending') else f for f in tool.typed_specs])
        config=tool.get_config();result=generate_batch(config)
        check('确认后两路字段共同生成40例',len(result['rows'])==40 and 'BMI' in result['columns'] and '尿潴留' in result['columns'])
        check('表名保留到配置',len(config.get('table_titles',{}))==4)
        export_batch(result,root/'preview-cases.xlsx');check('Excel导出成功',(root/'preview-cases.xlsx').exists())
        window.grab().save(str(root/'word-confirmed.png'));report['passed']=True
    except Exception:report['traceback']=traceback.format_exc()
    report['checks']=checks;(root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report['passed']
