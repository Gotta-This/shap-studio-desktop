"""Packaged acceptance check using only synthetic general-information paragraphs."""
import json,time,traceback
from pathlib import Path
from collections import Counter
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from PySide6.QtWidgets import QApplication
from .word_batch_engine import W,export_batch


def verify_prose(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);checks=[];app=QApplication.instance()
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    def document(path,n,bmi,bad_age=False):
        doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body')
        for group in ('观察组','常规治疗组'):
            age='61～78岁，平均（62.40±10.80）岁' if bad_age else '60～79岁，平均（67.00±3.00）岁'
            text=f'{group}{n}例，男{n//2}例、女{n-n//2}例；年龄{age}；BMI（{bmi}±3.10）kg/m²；呼吸衰竭类型Ⅰ型{n//2}例、Ⅱ型{n-n//2}例；机械通气方式经口气管插管{n//2}例、气管切开{n-n//2}例；APACHEⅡ评分（18.60±4.20）分，SOFA评分（7.20±2.10）分；入组前机械通气时间（52.60±15.40）h。'
            p=ET.SubElement(body,W+'p')
            for value in (text[:30],text[30:]):
                run=ET.SubElement(p,W+'r');ET.SubElement(run,W+'t').text=value
        with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(doc))
    def confirm(path):
        tool.import_word(path);tool.show_group_selection(['观察组','常规治疗组']);tool.confirm_groups();app.processEvents()
    try:
        window.timer.stop();tool=window.open_module('word');tool.use_word_sizes.setChecked(True)
        first=root/'synthetic-prose.docx';document(first,12,24.2);confirm(first)
        check('无表格也能按正文匹配两个组别',tool.groups_confirmed and '正文一般资料：2' in tool.match_summary.text())
        check('默认参数保持开启',not tool.leave_unknown_blank.isChecked() and tool.group_editors[0].fields['effective'].isEnabled())
        tool.leave_unknown_blank.setChecked(True)  # Exercise the optional blank policy explicitly.
        c=tool.get_config();check('各组例数来自正文',[g['n'] for g in c['groups']]==[12,12])
        check('按正文应用年龄范围和均数标准差',all(g['age'][0]['lower']==60 and g['age_stats']==dict(mean=67.,sd=3.) for g in c['groups']))
        check('正文建立8行数值参数和8行分类参数',tool.metrics.rowCount()==8 and tool.categories.rowCount()==8)
        tool.generate_button.click();end=time.monotonic()+120
        while tool.is_running() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        app.processEvents();check('实际按钮生成24行',not tool.is_running() and tool.result is not None and len(tool.result['rows'])==24)
        result=tool.result;fields=result['columns'];check('未识别基础字段留空',all(all(r[i]=='' for i in (4,5,6,-2,-1)) for r in result['rows']))
        for group in ('观察组','常规治疗组'):
            rows=[r for r in result['rows'] if r[1]==group]
            check(group+'性别人数正确',Counter(r[2] for r in rows)=={'男':6,'女':6})
            check(group+'分类人数正确',Counter(r[fields.index('呼吸衰竭类型')] for r in rows)=={'I型':6,'II型':6})
            check(group+'年龄均数标准差可核对',all(abs(v['mean_error'])<.3 and abs(v['sd_error'])<.5 for v in result['checks'] if v['group']==group and v['field']=='年龄' and 'mean_error' in v))
        output=root/'prose-cases.xlsx';export_batch(result,output)
        from openpyxl import load_workbook
        book=load_workbook(output,data_only=True);values=list(book.worksheets[0].values)
        check('Excel全部值等于生成快照',list(values[0])==fields and [list(r) for r in values[1:]]==[[None if v=='' else v for v in r] for r in result['rows']]);book.close()
        window.grab().save(str(root/'generated.png'))
        second=root/'changed-prose.docx';document(second,20,30.2);confirm(second)
        check('新Word清空旧结果',tool.result is None and not tool.export_button.isEnabled())
        c=tool.get_config();check('相同句式的新数字替换旧参数',[g['n'] for g in c['groups']]==[20,20] and all(s['mean']==30.2 for s in c['indicators'] if s['name']=='BMI'))
        tool.leave_unknown_blank.setChecked(False)
        table_doc=ET.Element(W+'document');body=ET.SubElement(table_doc,W+'body');table=ET.SubElement(body,W+'tbl')
        for values in [('组别','例数','本次评分'),('观察组','12','10±2'),('常规治疗组','12','11±2')]:
            tr=ET.SubElement(table,W+'tr')
            for value in values:
                tc=ET.SubElement(tr,W+'tc');p=ET.SubElement(tc,W+'p');run=ET.SubElement(p,W+'r');ET.SubElement(run,W+'t').text=value
        table_path=root/'table-only-no-basics.docx'
        with ZipFile(table_path,'w') as z:z.writestr('word/document.xml',ET.tostring(table_doc))
        confirm(table_path);check('每份新Word默认仍可生成基础资料',not tool.leave_unknown_blank.isChecked())
        check('无正文时全部基础字段标记为未识别',tool.get_config()['detected_basics']=={'观察组':[],'常规治疗组':[]})
        tool.generate_button.click();end=time.monotonic()+120
        while tool.is_running() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        app.processEvents();check('只有表格的Word能生成当前指标',not tool.is_running() and tool.result is not None and '本次评分' in tool.result['columns'])
        result=tool.result;basic_fields=['性别','年龄','病程','病情程度','总有效率','复发率']
        check('截图涉及的默认字段仍可正常生成',all(row[result['columns'].index(field)]!='' for row in result['rows'] for field in basic_fields))
        check('每个输出字段均有来源',set(row['column'] for row in result['config']['field_rules'])==set(result['columns']))
        check('有效和复发标明来自默认参数',all(any(row['column']==field and row['source']=='程序默认参数' for row in result['config']['field_rules']) for field in ('总有效率','复发率')))
        table_excel=root/'table-only-with-sources.xlsx';export_batch(result,table_excel);book=load_workbook(table_excel,data_only=True);values=list(book.worksheets[0].values)
        check('Excel默认字段有值且保存逐列来源',all(row[values[0].index(field)] is not None for row in values[1:] for field in basic_fields) and any(str(row[0]).startswith('field_rules[') for row in book['生成配置'].values));book.close()
        tool.pages.setCurrentIndex(tool.SOURCES_PAGE);app.processEvents();check('核对页覆盖生成快照的全部字段',tool.rule_table.rowCount()==len(result['config']['field_rules']))
        window.grab().save(str(root/'all-fields-and-sources.png'))
        invalid=root/'inconsistent-age.docx';document(invalid,25,22.8,True);confirm(invalid)
        try:tool.get_config();blocked=False
        except ValueError as exc:blocked='无法同时满足' in str(exc)
        check('原图年龄范围与标准差冲突会拦截',blocked)
        window.grab().save(str(root/'inconsistent-age.png'))
        report=dict(passed=True,checks=checks)
    except Exception:report=dict(passed=False,checks=checks,traceback=traceback.format_exc())
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['passed']
