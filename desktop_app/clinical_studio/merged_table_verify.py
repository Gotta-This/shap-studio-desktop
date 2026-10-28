"""Acceptance fixture for mixed vertical, flat and merged-header DOCX tables."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import json,traceback
from .word_batch_engine import W

BASELINE=[['项目','对照组（n=20）','试验组（n=20）','统计值','P值'],
 ['性别（男/女）','18（90.00）/2（10.00）','17（85.00）/3（15.00）','0.229','0.633'],
 ['年龄（岁）','58.35±10.41','57.80±10.98','0.163','0.872'],
 ['体重指数（kg/m²）','23.85±2.74','24.12±2.58','0.314','0.755'],
 ['疝侧别（左/右）','8（40.00）/12（60.00）','9（45.00）/11（55.00）','0.102','0.749'],
 ['病程（月）','12.46±6.32','11.81±5.94','0.335','0.739'],
 ['合并高血压','7（35.00）','6（30.00）','0.114','0.736'],
 ['合并糖尿病','4（20.00）','5（25.00）','0.143','0.705'],
 ['ASA分级（I/II/III）','8（40.00）/10（50.00）/2（10.00）','9（45.00）/9（45.00）/2（10.00）','0.111','0.946']]
PAIN=[['组别','例数','术后6h（分）','术后24h（分）','术后48h（分）'],
 ['对照组','20','4.15±0.81','3.10±0.69','2.40±0.56'],['试验组','20','3.50±0.69','2.40±0.60','1.45±0.51'],['t','','2.729','3.571','3.240'],['P','','0.010','<0.001','0.002']]
RECOVERY=[['组别','例数','首次下床活动时间（h）','首次肛门排气时间（h）','住院时间（d）'],
 ['对照组','20','18.60±3.70','22.85±4.32','4.35±0.81'],['试验组','20','14.25±3.11','18.40±3.90','3.70±0.57']]
COMPLICATIONS=[
 [{'text':'组别','vmerge':'restart'},{'text':'例数','vmerge':'restart'},('并发症',6),('SAS',2)],
 [{'text':'','vmerge':'continue'},{'text':'','vmerge':'continue'},'尿潴留','阴囊/腹股沟区血肿或水肿','恶心呕吐','腹胀','切口感染','总发生率','护理前（分）','出院前（分）'],
 ['对照组','20','2','2','1','2','0','7（35.00%）','52.45±5.19','44.80±4.56'],
 ['试验组','20','0','1','0','0','0','1（5.00%）','52.10±5.36','40.35±4.11'],
 ['t','','','','','','','','0.210','3.242'],['P','','','','','','','0.044*','0.835','0.002*']]


def save_fixture(path,tables=None):
    doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body')
    for rows in tables if tables is not None else (BASELINE,PAIN,RECOVERY,COMPLICATIONS):
        table=ET.SubElement(body,W+'tbl')
        for row in rows:
            tr=ET.SubElement(table,W+'tr')
            for value in row:
                value=value if isinstance(value,dict) else dict(text=value[0],span=value[1]) if isinstance(value,tuple) else dict(text=value)
                cell=ET.SubElement(tr,W+'tc');props=ET.SubElement(cell,W+'tcPr')
                if value.get('span',1)>1:ET.SubElement(props,W+'gridSpan',{W+'val':str(value['span'])})
                if value.get('vmerge'):ET.SubElement(props,W+'vMerge',{W+'val':value['vmerge']})
                ET.SubElement(ET.SubElement(ET.SubElement(cell,W+'p'),W+'r'),W+'t').text=value['text']
    with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(doc))
    return Path(path)


def verify_merged_tables(window,directory):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QFileDialog,QDialog
    from .typed_field_ui import FieldDialog
    from .word_batch_engine import generate_batch,export_batch,read_word
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);app=QApplication.instance();checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)));print(name,bool(value),flush=True)
        if not value:raise AssertionError(name)
    def pump():
        for _ in range(3):app.processEvents()
    report=dict(passed=False)
    try:
        window.timer.stop();tool=window.open_module('word');tool.decimal_mode.setCurrentIndex(tool.decimal_mode.findData('source'));tool.use_word_sizes.setChecked(True)
        path=save_fixture(root/'mixed-four-tables.docx');tool.import_word(path)
        tool.show_group_selection(['对照组','试验组']);tool.confirm_groups();pump()
        matched=read_word(path,['对照组','试验组'])
        check('四张表的两组均匹配',tool.groups_confirmed and matched.table_count==4 and all(len(row['groups'])==2 for row in matched.table_matches))
        check('原有两个横表识别六个指标',len({f['name'] for f in tool.get_config(validate=False)['indicators']})==6)
        check('竖表识别八个指标',len({f['name'] for f in tool.typed_specs if f['table']==1})==8)
        check('合并表头识别八个指标',len({f['name'] for f in tool.typed_specs if f['table']==4})==8)
        check('SAS只有护理前和出院前',set(f['name'] for f in tool.typed_specs if f.get('classification')=='SAS')=={'护理前（分）','出院前（分）'})
        try:tool.get_config();blocked=False
        except ValueError as exc:blocked='总发生率' in str(exc)
        check('汇总率未经确认阻止生成',blocked)
        tool.typed_table.item(next(i for i,f in enumerate(tool.typed_specs) if f['name']=='尿潴留'),6).setText('术后并发症');pump()
        check('上级分类可编辑并同步两组',all(f['classification']=='术后并发症' for f in tool.typed_specs if f['name']=='尿潴留'))
        for index in [i for i,f in enumerate(tool.typed_specs) if f['name']=='总发生率']:
            combo=tool.typed_table.cellWidget(index,3);combo.setCurrentIndex(combo.findData('excluded'))
        index=next(i for i,f in enumerate(tool.typed_specs) if f['name']=='疝侧别')
        outcome=[]
        def edit():
            dialog=getattr(tool,'field_dialog',None)
            if not dialog:return
            check('字段编辑使用独立原生窗口',dialog.isWindow() and dialog.graphicsProxyWidget() is None and dialog.parentWidget() is window)
            check('少量类别打开时完整展开',dialog.categories.verticalScrollBar().maximum()==0 and dialog.categories.viewport().height()>=sum(dialog.categories.rowHeight(i) for i in range(dialog.categories.rowCount())))
            dialog.grab().save(str(root/'field-editor.png'))
            dialog.categories.item(0,0).setText('左侧');dialog.categories.item(1,0).setText('右侧');dialog.classification.setText('一般资料');dialog.apply();outcome.append(dialog.result()==QDialog.Accepted)
        QTimer.singleShot(100,edit)
        QTimer.singleShot(3000,lambda:tool.field_dialog.reject() if getattr(tool,'field_dialog',None) is not None else None)
        tool.edit_typed_field(index);pump();check('实际对话框可修改类别',outcome==[True])
        check('修改类别不改变各组比例',all(abs(a-b)<1e-8 for a,b in zip(next(f for f in tool.typed_specs if f['name']=='疝侧别' and f['group']=='试验组')['weights'],[45.,55.])))
        window.grab().save(str(root/'matched-fields.png'))
        config=tool.get_config();result=generate_batch(config)
        check('生成两组共40例',len(result['rows'])==40)
        check('汇总率保留来源但不生成','总发生率' not in result['columns'] and any('总发生率' in r['column'] and '不生成' in r['column'] for r in config['field_rules']))
        for group,male,asa,urine in [('对照组',18,[8,10,2],2),('试验组',17,[9,9,2],0)]:
            rows=[row for row in result['rows'] if row[1]==group];cols=result['columns']
            check(group+'男女人数正确',sum(row[cols.index('性别')]=='男' for row in rows)==male)
            check(group+'ASA类别人数正确',[sum(row[cols.index('ASA分级')]==label for row in rows) for label in ('I','II','III')]==asa)
            check(group+'并发症有无人数正确',sum(row[cols.index('尿潴留')]=='有' for row in rows)==urine)
        output=root/'mixed-cases.xlsx';export_batch(result,output)
        from openpyxl import load_workbook
        book=load_workbook(output,data_only=True);check('Excel导出40例且无统计列',book.worksheets[0].max_row==41 and not {'P值','统计值','并发症','SAS'}&set(result['columns']));book.close()
        saved=root/'mixed-config.json';saved.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        old_open=QFileDialog.getOpenFileName
        try:
            QFileDialog.getOpenFileName=lambda *a,**kw:(str(saved),'JSON');tool.load_config();pump()
        finally:QFileDialog.getOpenFileName=old_open
        check('配置重载保留字段分类和原表头',tool.get_config()['typed_fields']==config['typed_fields'])
        tool.pages.setCurrentIndex(tool.SOURCES_PAGE);pump();window.grab().save(str(root/'field-sources.png'))
        report['passed']=True
    except Exception:report['traceback']=traceback.format_exc()
    report['checks']=checks;(root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report['passed']
