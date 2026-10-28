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
        tool.import_word(path);tool.show_group_selection(['观察组','常规治疗组']);tool.confirm_groups();app.processEvents();tool.include_basics.setChecked(True)  # Explicitly exercise optional basic/outcome columns.
    try:
        window.timer.stop();tool=window.open_module('word');tool.decimal_mode.setCurrentIndex(tool.decimal_mode.findData('source'));tool.use_word_prose.setChecked(True);tool.use_word_sizes.setChecked(True)
        first=root/'synthetic-prose.docx';document(first,12,24.2);confirm(first)
        check('无表格也能按正文匹配两个组别',tool.groups_confirmed and '正文一般资料：2' in tool.match_summary.text())
        check('默认参数保持开启',not tool.leave_unknown_blank.isChecked() and tool.group_editors[0].fields['effective'].isEnabled())
        tool.leave_unknown_blank.setChecked(True)  # Exercise the optional blank policy explicitly.
        c=tool.get_config();check('各组例数来自正文',[g['n'] for g in c['groups']]==[12,12])
        check('按正文应用年龄范围和均数标准差',len([f for f in c['typed_fields'] if f['name']=='年龄' and f['lower']==60 and f['upper']==79 and f['mean']==67. and f['sd']==3.])==2)
        check('正文竖表保留10行数值规则和6行分类规则',sum(f['kind']=='mean_sd' for f in c['typed_fields'])==10 and sum(f['kind']=='category' for f in c['typed_fields'])==6 and tool.metrics.rowCount()==0 and tool.categories.rowCount()==0)
        tool.generate_button.click();end=time.monotonic()+120
        while tool.is_running() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        app.processEvents();check('实际按钮生成24行',not tool.is_running() and tool.result is not None and len(tool.result['rows'])==24)
        result=tool.result;fields=result['columns'];check('未识别基础字段留空',all(all(r[fields.index(name)]=='' for name in ('病程','病情程度','病变范围','总有效率','复发率')) for r in result['rows']))
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
        c=tool.get_config();check('相同句式的新数字替换旧参数',[g['n'] for g in c['groups']]==[20,20] and len([s for s in c['typed_fields'] if s['name']=='BMI' and s['mean']==30.2])==2)
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
        pediatric_text='选取108例患儿，随机均等分为对照组（54例）和观察组（54例）。对照组性别分布：男（25例）、女（29例）；年龄最小和最大分别4岁、13岁，平均（7.82±2.34）岁；病程范围介于4个月至3.5年，平均（1.47±0.73）年。观察组性别分布：男（27例）、女（27例）；年龄最小和最大分别5岁、12岁，平均（7.96±2.18）岁；病程范围介于3个月至4年，平均（1.52±0.81）年。两组上述差异均无统计学意义（P>0.05）。'
        doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body');ET.SubElement(ET.SubElement(ET.SubElement(body,W+'p'),W+'r'),W+'t').text=pediatric_text
        pediatric_path=root/'pediatric-ranges.docx'
        with ZipFile(pediatric_path,'w') as z:z.writestr('word/document.xml',ET.tostring(doc))
        tool.import_word(pediatric_path);tool.show_group_selection(['对照组','观察组']);tool.confirm_groups();app.processEvents()
        editor=tool.prose_table_editor;study=editor.study();vs={v['name']:v for v in study['variables']}
        check('括号例数明确报告且无推算提示',all(g['n']==54 and g['n_origin']=='reported' for g in study['groups']))
        check('性别类别清理括号且无重复指标',set(vs)=={'性别','年龄','病程'} and vs['性别']['labels']==['男','女'])
        check('年龄最小最大值识别',[(vs['年龄']['cells'][g]['lower'],vs['年龄']['cells'][g]['upper']) for g in ('对照组','观察组')]==[(4.,13.),(5.,12.)])
        check('病程月份换算成年',vs['病程']['unit']=='年' and vs['病程']['cells']['对照组']['lower']==4/12 and vs['病程']['cells']['观察组']['lower']==.25)
        config=tool.get_config();check('正文范围均数不误报冲突',len(config['typed_fields'])==6)
        tool.pages.setCurrentIndex(tool.PROSE_PAGE);app.processEvents();window.grab().save(str(root/'pediatric-preview.png'))
        editor.table.scrollToBottom();app.processEvents();window.grab().save(str(root/'pediatric-duration.png'))
        tool.generate_button.click();end=time.monotonic()+120
        while tool.is_running() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        app.processEvents();result=tool.result
        check('实际按钮生成108例',result is not None and len(result['rows'])==108)
        for group,male in [('对照组',25),('观察组',27)]:
            rows=[r for r in result['rows'] if r[1]==group];column=result['columns'].index('性别')
            check(group+'括号人数正确生成',Counter(r[column] for r in rows)=={'男':male,'女':54-male})
            for name in ('年龄','病程'):
                cell=vs[name]['cells'][group];column=result['columns'].index(name)
                check(group+name+'值均在原文范围内',all(cell['lower']<=r[column]<=cell['upper'] for r in rows))
        respiratory_text='两组患者一般资料比较：对照组25例，男15例、女10例；年龄平均（62.44±10.36）岁；BMI（22.80±3.10）kg/m²；呼吸衰竭类型Ⅰ型13例、Ⅱ型12例；机械通气方式经口气管插管18例、气管切开7例；APACHEⅡ评分（18.60±4.20）分，SOFA评分（7.20±2.10）分。试验组25例，男14例、女11例；年龄平均（63.10±11.20）岁；BMI（23.10±3.40）kg/m²；呼吸衰竭类型Ⅰ型12例、Ⅱ型13例；机械通气方式经口气管插管17例、气管切开8例；APACHEⅡ评分（18.90±4.50）分，SOFA评分（7.40±2.30）分。两组上述一般资料比较，差异均无统计学意义（P>0.05），具有可比性。'
        doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body');ET.SubElement(ET.SubElement(ET.SubElement(body,W+'p'),W+'r'),W+'t').text=respiratory_text
        respiratory_path=root/'respiratory-intro.docx'
        with ZipFile(respiratory_path,'w') as z:z.writestr('word/document.xml',ET.tostring(doc))
        tool.import_word(respiratory_path);tool.show_group_selection(['对照组','试验组']);tool.confirm_groups();app.processEvents()
        config=tool.get_config();check('一般资料比较开头不截断正文且识别14个组别字段',len(config['typed_fields'])==14)
        tool.pages.setCurrentIndex(tool.PROSE_PAGE);app.processEvents();window.grab().save(str(root/'respiratory-preview.png'))
        tool.generate_button.click();end=time.monotonic()+120
        while tool.is_running() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        app.processEvents();result=tool.result
        check('新案例实际生成50例',result is not None and len(result['rows'])==50)
        for group,counts in [('对照组',{'经口气管插管':18,'气管切开':7}),('试验组',{'经口气管插管':17,'气管切开':8})]:
            rows=[r for r in result['rows'] if r[1]==group];col=result['columns'].index('机械通气方式')
            check(group+'机械通气人数正确',Counter(r[col] for r in rows)==counts)
        report=dict(passed=True,checks=checks)
    except Exception:report=dict(passed=False,checks=checks,traceback=traceback.format_exc())
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['passed']
