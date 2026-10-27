"""Packaged acceptance checks for synthetic tables in all three requested layouts."""
import json,time,traceback
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from collections import Counter
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QFileDialog
from .word_batch_engine import W
from .typed_field_ui import FieldDialog


def verify_table_types(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);app=QApplication.instance();checks=[];old_save=QFileDialog.getSaveFileName
    def check(label,ok):
        checks.append(dict(name=label,passed=bool(ok)));print(label, bool(ok),flush=True)
        if not ok:raise AssertionError(label)
    def save(path,rows,title=''):
        doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body')
        if title:ET.SubElement(ET.SubElement(ET.SubElement(body,W+'p'),W+'r'),W+'t').text=title
        table=ET.SubElement(body,W+'tbl')
        for row in rows:
            tr=ET.SubElement(table,W+'tr')
            for value in row:
                text,span=value if isinstance(value,tuple) else (value,1);tc=ET.SubElement(tr,W+'tc')
                if span>1:ET.SubElement(ET.SubElement(tc,W+'tcPr'),W+'gridSpan',{W+'val':str(span)})
                ET.SubElement(ET.SubElement(ET.SubElement(tc,W+'p'),W+'r'),W+'t').text=text
        with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(doc))
    def load(filename,rows,names,title=''):
        path=root/filename;save(path,rows,title);tool.import_word(path);tool.show_group_selection(names)
        tool.confirm_groups();app.processEvents();check(filename+'组别识别成功',tool.groups_confirmed)
    def wait():
        end=time.monotonic()+120
        while tool.is_running() and time.monotonic()<end:app.processEvents();time.sleep(.01)
        app.processEvents();check('后台任务完成',not tool.is_running())
    try:
        window.timer.stop();tool=window.open_module('word');tool.use_word_sizes.setChecked(True)
        load('phased.docx',[[('项目',1),('试验组(n=59)',2),('对照组(n=59)',2)],['项目','治疗前','治疗后','治疗前','治疗后'],['头晕目眩','4.09±0.64','1.49±0.35*','4.15±0.60','2.39±0.25*']],['试验组','对照组'])
        check('前后表按项目展开两列',{f['name'] for f in tool.typed_specs}=={'前-头晕目眩','后-头晕目眩'})
        tool.generate_button.click();wait();check('前后表生成118例',tool.result is not None and len(tool.result['rows'])==118)
        load('efficacy.docx',[['组别','例数(n)','基本痊愈','显效','有效','无效','总有效率'],['试验组','59','22(37.29)','15(25.42)','18(30.51)','4(6.78)','55(93.22)'],['对照组','59','15(25.42)','9(15.25)','22(37.29)','13(22.03)','46(77.97)']],['试验组','对照组'])
        check('新Word清空前后表结果',tool.result is None)
        tool.generate_button.click();wait();r=tool.result;cols=r['columns']
        for group,total in [('试验组',55),('对照组',46)]:
            rows=[v for v in r['rows'] if v[1]==group]
            check(group+'总有效人数等于分级合计',sum(v[cols.index('总有效率')]=='有效' for v in rows)==total and all((v[cols.index('总有效率')]=='有效')==(v[cols.index('疗效分级')]!='无效') for v in rows))
        load('baseline.docx',[['项目','训练集(n=237)','验证集(n=101)','统计值','P'],['年龄（月）','85.09±16.44','84.70±17.03','t=0.197','0.844'],['性别','134(56.54)','54(53.47)','χ²=0.161','0.688'],['白细胞计数','13.50(10.80,15.50)','13.00(11.10,14.90)','Z=0.606','0.545']],['训练集','验证集'])
        try:tool.get_config();blocked=False
        except ValueError:blocked=True
        check('不猜测性别和四分位数含义',blocked)
        index=next(i for i,f in enumerate(tool.typed_specs) if f['name']=='性别');combo=tool.typed_table.cellWidget(index,3);combo.setCurrentIndex(combo.findData('gender'));app.processEvents()
        index=next(i for i,f in enumerate(tool.typed_specs) if f['kind']=='quantile')
        def accept_dialog():
            dialog=getattr(tool,'field_dialog',None)
            if isinstance(dialog,FieldDialog):dialog.apply()
        QTimer.singleShot(100,accept_dialog)
        def close_stuck_dialog():
            dialog=getattr(tool,'field_dialog',None)
            if isinstance(dialog,FieldDialog):
                print('dialog error:',dialog.error.text(),flush=True);dialog.reject()
        watchdog=QTimer(window);watchdog.setSingleShot(True);watchdog.timeout.connect(close_stuck_dialog)
        watchdog.start(3000);tool.edit_typed_field(index);watchdog.stop();app.processEvents()
        check('确认一行不会确认另一组分位数参数',sum(f['confirmed'] for f in tool.typed_specs if f['kind']=='quantile')==1)
        index=next(i for i,f in enumerate(tool.typed_specs) if f['kind']=='quantile' and not f['confirmed'])
        QTimer.singleShot(100,accept_dialog);watchdog.start(3000);tool.edit_typed_field(index);watchdog.stop();app.processEvents()
        check('各行分别确认后参数完整',all(f['confirmed'] for f in tool.typed_specs))
        window.grab().save(str(root/'typed-fields.png'))
        tool.generate_button.click();wait();r=tool.result;cols=r['columns']
        check('基线表仅输出项目列',cols==['编号','分组','年龄（月）','性别','白细胞计数'])
        check('统计值与P不生成病例字段','P' not in cols and '统计值' not in cols)
        for group,n,male in [('训练集',237,134),('验证集',101,54)]:
            rows=[v for v in r['rows'] if v[1]==group];check(group+'人数和男女数量正确',len(rows)==n and Counter(v[cols.index('性别')] for v in rows)=={'男':male,'女':n-male})
        check('四分位数实际值可核对',all(abs(v['actual_q1']-v['target_q1'])<.006 and abs(v['actual_median']-v['target_median'])<.006 and abs(v['actual_q3']-v['target_q3'])<.006 for v in r['checks'] if 'actual_q1' in v))
        output=root/'baseline-cases.xlsx';QFileDialog.getSaveFileName=lambda *a,**kw:(str(output),'Excel');tool.export_button.click();wait()
        from openpyxl import load_workbook
        book=load_workbook(output,data_only=True);data=list(book.worksheets[0].values);check('Excel保留文字类型及338条记录',len(data)==339 and data[1][cols.index('性别')] in ('男','女'));book.close()
        config=root/'field-types.json';QFileDialog.getSaveFileName=lambda *a,**kw:(str(config),'JSON');tool.save_button.click();check('字段类型与参数保存',len(json.loads(config.read_text(encoding='utf-8'))['typed_fields'])==6)
        window.grab().save(str(root/'baseline-result.png'))
        load('vertical-subcategories.docx',[['项目','对照组（25例）','试验组（25例）','统计值','P值'],['年龄','44.84±9.75','46.40±10.18','0.554','0.582'],['性别','','','0.325','0.569'],['男','15（60.00）','13（52.00）','',''],['女','10（40.00）','12（48.00）','',''],['手术方式','','','',''],['腹腔镜','19（76.00）','17（68.00）','',''],['开腹','6（24.00）','8（32.00）','','']],['对照组','试验组'])
        check('25例组名与分类子行合并为三个指标',len(tool.typed_specs)==6 and {f['name'] for f in tool.typed_specs}=={'年龄','性别','手术方式'} and all(f['confirmed'] for f in tool.typed_specs))
        tool.generate_button.click();wait();check('分类子行生成50例',tool.result is not None and len(tool.result['rows'])==50)
        load('slash-first-gender.docx',[['项目','对照组（n=15）','试验组（n=15）','统计值','P值'],['性别（男/女，例，构成比）','9/6','8/7','0.136','0.713'],['年龄（岁）','45.67±10.20','47.13±11.02','0.378','0.708'],['创伤类型（锐器伤/钝器伤/动物咬伤/其他，例，构成比）','7/4/3/1','5/5/4/1','0.587','0.899']],['对照组','试验组'])
        genders=[f for f in tool.typed_specs if f['name']=='性别']
        check('首行性别人数不再作为表头跳过',len(genders)==2 and [f['counts'] for f in genders]==[[9,6],[8,7]] and all(f['kind']=='gender' and f['confirmed'] for f in genders))
        check('分类最后一项不混入例和构成比',all(f['labels']==['锐器伤','钝器伤','动物咬伤','其他'] for f in tool.typed_specs if f['name']=='创伤类型'))
        window.grab().save(str(root/'first-gender.png'))
        tool.generate_button.click();wait();r=tool.result
        check('首行性别生成30例且两组男性人数为9和8',r is not None and len(r['rows'])==30 and [sum(row[r['columns'].index('性别')]=='男' for row in r['rows'] if row[1]==g) for g in ['对照组','试验组']]==[9,8])
        load('missing-separator.docx',[['组别','例数','肠鸣音恢复时间（h）'],['对照组','25','22.444.02'],['试验组','25','16.763.63'],['t','','5.241'],['P','','＜0.001']],['对照组','试验组'])
        check('缺少分隔符仍保留两组指标及原文',len(tool.typed_specs)==2 and tool.typed_specs[0]['raw']=='22.444.02' and all(f.get('mean') is None and f.get('sd') is None and not f['confirmed'] for f in tool.typed_specs))
        try:tool.get_config();blocked=False
        except ValueError:blocked=True
        check('缺失统计参数阻止生成',blocked)
        window.grab().save(str(root/'missing-separator.png'))
        dialog_errors=[]
        def fill_missing():
            dialog=getattr(tool,'field_dialog',None)
            if isinstance(dialog,FieldDialog):
                try:
                    check('补全弹窗保留原文且参数为空',dialog.inputs['mean'].text()=='' and dialog.inputs['sd'].text()=='')
                    dialog.inputs['mean'].setText('22.44');dialog.inputs['sd'].setText('4.02');dialog.apply()
                except Exception:dialog_errors.append(traceback.format_exc());dialog.reject()
        QTimer.singleShot(100,fill_missing);watchdog.start(3000);tool.edit_typed_field(0);watchdog.stop();app.processEvents()
        if dialog_errors:raise AssertionError(dialog_errors)
        check('人工补全仅应用本组数值',tool.typed_specs[0]['mean']==22.44 and tool.typed_specs[0]['sd']==4.02 and tool.typed_specs[1].get('mean') is None)
        load('complication-counts.docx',[['组别','例数','切口感染','恶心呕吐','总发生率'],['对照组','25','2（8.00）','4（16.00）','6（24.00）'],['试验组','25','0（0.00）','1（4.00）','1（4.00）']],['对照组','试验组'],'表4.两组并发症率比较 n，%')
        components=[f for f in tool.typed_specs if not f.get('aggregate_pending')]
        check('表名明确的并发症自动设为有无无需确认',len(components)==4 and all(f['kind']=='yesno' and f['confirmed'] and f['labels']==['有','无'] for f in components))
        check('总发生率仍保留待确认',sum(f.get('aggregate_pending',False) and not f['confirmed'] for f in tool.typed_specs)==2)
        window.grab().save(str(root/'complications-pending-total.png'))
        try:tool.get_config();blocked=False
        except ValueError:blocked=True
        check('保留总发生率待确认时仍阻止生成',blocked)
        from .typed_field_ui import convert
        tool.set_typed_fields([convert(f,'excluded') if f.get('aggregate_pending') else f for f in tool.typed_specs])
        tool.generate_button.click();wait();r=tool.result
        values=[row[r['columns'].index('恶心呕吐')] for row in r['rows'] if row[1]=='对照组'] if r else []
        check('无需确认单项即可生成有4例无21例',len(values)==25 and values.count('有')==4 and values.count('无')==21)
        load('inconsistent-complications.docx',[['组别','例数','恶心呕吐'],['对照组','25','4（20.00）'],['试验组','25','1（4.00）']],['对照组','试验组'],'表4 并发症比较')
        check('不一致的人数和百分比继续待核对',not tool.typed_specs[0]['confirmed'] and tool.typed_specs[1]['confirmed'])
        tool.generate();app.processEvents()
        from .editor_dialogs import EditorDialog
        error_dialog=getattr(tool,'validation_dialog',None)
        check('生成校验失败显示原生居中弹窗',isinstance(error_dialog,EditorDialog) and error_dialog.isVisible() and error_dialog.parentWidget() is window and error_dialog.graphicsProxyWidget() is None)
        error_dialog.grab().save(str(root/'generation-error-dialog.png'));error_dialog.accept();app.processEvents()
        load('neutral-binary.docx',[['组别','例数','止血成功','住院期间再出血'],['对照组','15','12（80.00%）','4（26.67%）'],['试验组','15','15（100.00%）','1（6.67%）']],['对照组','试验组'])
        check('普通人数百分比自动使用1和0',len(tool.typed_specs)==4 and all(f['kind']=='binary01' and f['confirmed'] and f['labels']==[1,0] for f in tool.typed_specs))
        window.grab().save(str(root/'neutral-binary.png'))
        tool.generate_button.click();wait();r=tool.result
        values=[row[r['columns'].index('止血成功')] for row in r['rows'] if row[1]=='对照组'] if r else []
        check('止血成功15例按12个1和3个0生成',len(values)==15 and all(type(v) is int for v in values) and values.count(1)==12 and values.count(0)==3)
        from .merged_table_verify import save_fixture
        from .word_source_tables import HEADERS
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QLabel
        source=root/'two-source-tables.docx'
        save_fixture(source,[[['项目','对照组（25例）','试验组（25例）'],['年龄','50±4','51±5'],['感染','4（16.00）','1（4.00）']],[['组别','例数','恢复时间'],['对照组','25','10±2'],['试验组','25','11±2']]])
        with ZipFile(source) as archive:document=ET.fromstring(archive.read('word/document.xml'))
        body=document.find(W+'body')
        for i,table in enumerate(list(body),1):
            title=ET.Element(W+'p');ET.SubElement(ET.SubElement(title,W+'r'),W+'t').text='表1.两组一般资料比较' if i==1 else '表2.两组患者痉挛控制情况、恢复指标比较（x̄±s）';body.insert(list(body).index(table),title)
        with ZipFile(source,'w') as archive:archive.writestr('word/document.xml',ET.tostring(document))
        tool.import_word(source);tool.confirm_groups();app.processEvents();panel=tool.source_tables;panel.refresh()
        check('Word两张表分别显示五列统一表头',set(panel.tables)=={1,2} and all([table.horizontalHeaderItem(i).text() for i in range(5)]==HEADERS for table in panel.tables.values()))
        check('数值分类合并到原表且旧分区隐藏',panel.tables[1].rowCount()==4 and not tool.typed_label.isVisible() and not tool.typed_table.isVisible() and not tool.metrics.isVisible())
        value=panel.numeric_inputs[(1,0)]['mean'];value.selectAll();QTest.keyClicks(value,'52.75');app.processEvents()
        check('数值规则直接编辑且两组独立',tool.typed_specs[0]['mean']==52.75 and tool.typed_specs[1]['mean']==51.)
        window.grab().save(str(root/'source-table-layout.png'))
        pending=[dict(name='待填时间',group=g,table=1,kind='mean_sd',mean=None,sd=None,digits=2,lower=None,upper=None,raw='22.444.02',confirmed=False) for g in ['对照组','试验组']]
        tool.set_indicators([]);tool.set_typed_fields(pending);app.processEvents()
        def confirm_one():
            dialog=tool.field_dialog;dialog.inputs['mean'].setText('22.44');dialog.inputs['sd'].setText('4.02');dialog.sync.setChecked(True);dialog.apply()
        QTimer.singleShot(100,confirm_one);watchdog.start(3000);tool.edit_typed_field(0);watchdog.stop();app.processEvents()
        check('确认第一行不再确认或填充第二行',tool.typed_specs[0]['confirmed'] and not tool.typed_specs[1]['confirmed'] and tool.typed_specs[1]['mean'] is None and tool.typed_specs[1]['sd'] is None)
        panel.refresh()
        for key,text in [('mean','16.76'),('sd','3.63')]:QTest.keyClicks(panel.numeric_inputs[(1,1)][key],text)
        app.processEvents();check('第二行补全后各行独立确认',all(f['confirmed'] for f in tool.typed_specs) and tool.typed_specs[0]['mean']==22.44 and tool.typed_specs[1]['mean']==16.76)
        tool.generate_button.click();wait();check('两行各自补全后生成50例',tool.result is not None and len(tool.result['rows'])==50)
        report=dict(passed=True,checks=checks)
    except Exception:report=dict(passed=False,checks=checks,traceback=traceback.format_exc())
    finally:QFileDialog.getSaveFileName=old_save
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report['passed']
