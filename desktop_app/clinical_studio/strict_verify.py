"""Exercise the real Penpot-derived controls, then all advanced parameters."""
from collections import Counter
import csv,json
from pathlib import Path
from copy import deepcopy

from PySide6.QtCore import QTimer,Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout

from .hub_verify import SuiteVerifier,make_word_fixture
from .ui_verify import UiVerifier
from .config import default_config


class StrictVerifier(SuiteVerifier):
    def __init__(self,hub,directory,app):
        super().__init__(hub,directory,app)
        hub.initial_output=str(self.root/'primary-runs')
    def categories(self):
        self.check('首页四个真实工具入口',len(self.hub.launch_buttons)==4 and not self.hub.modules)
        self.screenshot('设计还原_00_首页')
        tool=self.enter('category');b=self.hub.boards[1]
        self.check('默认121个数值逐行显示',len(self.hub.category_output.toPlainText().splitlines())==121 and Counter(self.hub.category_output.toPlainText().splitlines())=={'1':28,'0':93})
        self.click(b.controls['copy-category'])
        self.check('主页面复制成功提示可见',self.hub.copy_feedback.isVisible() and '复制成功' in self.hub.copy_feedback.text())
        (self.root/'工具1_原R默认参数_复制.txt').write_text(QApplication.clipboard().text(),encoding='utf-8')
        (self.root/'工具1_原R默认参数_统计.txt').write_text(tool.original_report(),encoding='utf-8')
        self.save_dialog(b.controls['save-category'],self.root/'工具1_原R默认参数.csv')
        self.screenshot('工具1_原R默认参数_逐行输出')
        self.verify_category_scrolling()
        self.table_value(self.hub.category_table,0,1,'11');self.table_value(self.hub.category_table,1,1,'9')
        self.type_text(b.controls['category-seed'],'44');self.click(b.controls['generate-category']);self.hub.refresh(force=True)
        self.check('设计表格修改后按准确类别数量生成',Counter(tool.result.values)=={1:11,0:9})
        self.click(b.controls['copy-category']);self.check('设计复制按钮与显示文本一致',QApplication.clipboard().text()==self.hub.category_output.toPlainText())
        copied=QApplication.clipboard().text()
        self.check('复制到Excel为单列20行且无表头',[float(row) for row in copied.splitlines()]==tool.result.values and all(len(row.split())==1 for row in copied.splitlines()))
        path=self.root/'工具1_类别数列.csv';self.save_dialog(b.controls['save-category'],path)
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
        self.check('设计保存按钮导出的类别数据一致',[float(r[0]) for r in rows[1:]]==tool.result.values)
        self.category_snapshot=(tool.seed.text(),tuple(tool.result.values));self.screenshot('设计还原_01_类别')
        QTimer.singleShot(100,lambda:self.step(self.numeric))

    def verify_category_scrolling(self):
        w=self.hub;b=w.boards[1];table=w.category_table;area=w.category_scroll
        generate=b.controls['generate-category'].geometry()
        self.click(b.controls['add-category'])
        self.check('添加类别会向下展开并推动参数',table.height()==172 and b.controls['add-category'].y()==190 and b.controls['category-seed'].y()==317 and area.verticalScrollBar().maximum()==0)
        self.screenshot('类别新增一行_参数下移')
        for _ in range(7):self.click(b.controls['add-category'])
        self.check('十个类别由大参数区域滚动且表格不单独滚动',table.rowCount()==10 and table.height()==480 and table.verticalScrollBar().maximum()==0 and area.verticalScrollBar().maximum()>0)
        area.verticalScrollBar().setValue(0)
        wheel=QWheelEvent(QPointF(30,60),QPointF(table.viewport().mapToGlobal(QPoint(30,60))),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        self.app.sendEvent(table.viewport(),wheel);self.app.processEvents()
        self.check('鼠标在表格上滚动也带动整个参数区域',area.verticalScrollBar().value()>0)
        self.screenshot('类别十行_整个参数区域滚动')
        area.ensureWidgetVisible(b.controls['category-seed']);self.app.processEvents()
        self.screenshot('类别十行_滚动到随机种子')
        self.check('生成按钮保持在卡片底部',b.controls['generate-category'].geometry()==generate)
        for _ in range(8):self.click(table.cellWidget(table.rowCount()-1,2))
        self.check('删除类别后恢复原高度与无滚动布局',table.rowCount()==2 and table.height()==128 and area.verticalScrollBar().maximum()==0)

    def verify_copy_dialog(self,key,page=None):
        if key=='word':
            tool=self.hub.modules[key];tool.pages.setCurrentIndex(tool.OUTPUT_PAGE);self.click(tool.copy_button)
            host=tool.window();self.check('Word复制成功提示在主流程可见',hasattr(host,'copy_feedback') and host.copy_feedback.isVisible());return
        errors=[]
        def operate():
            dialog=self.app.activeModalWidget()
            try:
                tool=self.hub.modules[key]
                button=tool.result.copy_button if key=='numeric' else tool.copy_button
                self.click(button)
                self.check(key+'复制成功提示显示在当前对话框',hasattr(dialog,'copy_feedback') and dialog.copy_feedback.isVisible() and '复制成功' in dialog.copy_feedback.text())
                dialog.grab().save(str(self.shots/(key+'_复制成功提示.png')))
            except Exception as exc:errors.append(exc)
            finally:dialog.accept()
        QTimer.singleShot(100,operate);self.hub.advanced(key,page)
        if errors:raise errors[0]

    def numeric(self):
        self.enter('numeric');b=self.hub.boards[2]
        for key,value in [('numeric-n','32'),('numeric-mean','10'),('numeric-sd','2'),('numeric-min','0'),('numeric-max','20'),('numeric-digits','2'),('numeric-seed','42')]:self.type_text(b.controls[key],value)
        self.click(b.controls['generate-numeric']);self.wait_for(self.hub.modules['numeric'],self.numeric_done)

    def numeric_done(self):
        self.hub.refresh(force=True);tool=self.hub.modules['numeric'];b=self.hub.boards[2]
        self.check('设计参数生成32个范围内数值',len(tool.result.values)==32 and all(0<=v<=20 for v in tool.result.values),error=tool.error.text())
        self.check('分布预览使用真实数据',self.hub.histogram.values==tool.result.values)
        path=self.root/'工具2_均数标准差.xlsx';self.save_dialog(b.controls['save-numeric'],path)
        from openpyxl import load_workbook
        book=load_workbook(path,data_only=True);values=[r[0] for r in list(book.active.values)[1:]];book.close()
        self.check('设计数值页保存的数据一致',values==tool.result.values)
        self.verify_copy_dialog('numeric')
        self.numeric_snapshot=(tool.mean.text(),tool.sd.text(),tool.n.value(),tool.seed.text(),tuple(tool.result.values))
        self.screenshot('设计还原_02_均数标准差');QTimer.singleShot(100,lambda:self.step(self.word))

    def word(self):
        tool=self.enter('word');tool.decimal_mode.setCurrentIndex(tool.decimal_mode.findData('source'));b=self.hub.boards[3]
        source=self.root/'工具3_测试Word.docx';make_word_fixture(source);self.save_dialog(b.controls['import-word'],source)
        tool.show_group_selection(['对照组','中药组']);tool.confirm_groups()
        self.hub.refresh(force=True)
        self.check('设计导入按钮识别两组指标',self.hub.word_table.rowCount()==2)
        tool.pages.setCurrentIndex(0);tool.same_size.setChecked(False)
        tool.group_editors[0].fields['n'].setText('14');tool.group_editors[1].fields['n'].setText('16')
        self.type_text(tool.seed,'77');self.click(b.controls['generate-word']);self.wait_for(tool,self.word_done)

    def word_done(self):
        tool=self.hub.modules['word'];self.hub.refresh(force=True)
        self.check('设计Word页面按两组例数生成',tool.result is not None and len(tool.result['rows'])==30,error=tool.message.text())
        self.word_export=self.root/'工具3_Word生成Excel.xlsx'
        self.save_dialog(self.hub.boards[3].controls['save-word'],self.word_export,must_exist=False);self.wait_for(tool,self.word_saved)

    def word_saved(self):
        self.verify_copy_dialog('word',3)
        super().word_saved()

    def start_shap(self):
        tool=self.enter('shap');b=self.hub.boards[4]
        for key,value in [('sample-size','240'),('positive-rate','0.30'),('data-seed','1234'),('id-name','Strict-ID')]:self.type_text(b.controls[key],value)
        self.table_value(self.hub.data_table,0,1,'80');self.table_value(self.hub.data_table,0,3,'50')
        self.click(b.controls['next-model']);b=self.hub.boards[5]
        for key,value in [('test-size','0.25'),('split-seed','321'),('max-iter','1400'),('regularization','0.8'),('background-size','100'),('background-seed','11'),('plot-seed','22'),('sample-index','2')]:self.type_text(b.controls[key],value)
        self.table_value(self.hub.binary_table,0,3,'0 / 2');self.click(b.controls['next-style'])
        b=self.hub.boards[6]
        colors=['#277453','#8D4772','#BE6534','#3969A5','#7555A7','#34817D']
        from .strict_ui import PLOT_ORDER
        self.quick_expected={}
        for i,key in enumerate(PLOT_ORDER):
            self.click(b.controls['plot-'+key])
            for name,value in [('plot-color',colors[i]),('plot-font-size',str(14+i)),('plot-line-width',str(round(1.8+i*.2,1))),('plot-width','8'),('plot-height','6')]:self.type_text(b.controls[name],value)
            self.combo(b.controls['plot-font'],'DejaVu Sans')
            self.click(b.controls['apply-style'])
            self.quick_expected[key]=deepcopy(tool.collect_config()['plots']['plots'][key])
            self.screenshot(f'设计还原_样式_{key}')
        self.quick_config=tool.collect_config()
        self.check('设计主页面保存数据及模型参数',self.quick_config['data']['n_samples']==240 and self.quick_config['data']['id_name']=='Strict-ID' and self.quick_config['model']['test_size']==.25)
        self.check('设计主表分别修改两组均数',self.quick_config['data']['features'][0]['positive']['mean']==80 and self.quick_config['data']['features'][0]['negative']['mean']==50)
        self.click(b.controls['step-4']);self.click(self.hub.boards[7].controls['run-analysis'])
        self.wait_for_shap()

    def wait_for_shap(self):
        tool=self.hub.modules['shap']
        if tool.worker and tool.worker.isRunning():QTimer.singleShot(200,self.wait_for_shap);return
        self.step(self.quick_result)

    def quick_result(self):
        tool=self.hub.modules['shap'];result=tool.result;self.hub.refresh(force=True)
        self.check('设计四步流程真实生成六图',result is not None and len(result.images)==6,error=tool.log.toPlainText())
        self.check('设计主页面设置与运行快照一致',result.config==self.quick_config)
        self.check('设计六图全部对象颜色核对通过',all(a['passed'] for a in result.audit.values()))
        self.check('设计导出页面预览真实生成的图片',self.hub.plot_image.path==str(result.images[0]))
        (self.root/'strict_primary_ui.json').write_text(json.dumps(dict(passed=True,config=self.quick_config,checks=self.checks),ensure_ascii=False,indent=2),encoding='utf-8')
        self.screenshot('设计还原_07_真实生成结果')
        # The primary design intentionally has concise fields. Exercise the actual
        # advanced dialog too, including every original setting and export format.
        tool.config=default_config();tool.build_pages();tool.nav.setCurrentRow(0)
        self.shap=UiVerifier(tool,self.root,self.app);original=self.shap.finish_report
        def finish(passed):
            original(passed)
            if not passed:self.report(False);return
            try:
                c=self.hub.modules['category'];n=self.hub.modules['numeric'];w=self.hub.modules['word']
                self.check('生图后类别参数与结果不变',(c.seed.text(),tuple(c.result.values))==self.category_snapshot)
                self.check('生图后数值参数与结果不变',(n.mean.text(),n.sd.text(),n.n.value(),n.seed.text(),tuple(n.result.values))==self.numeric_snapshot)
                self.check('生图后Word参数与结果不变',json.dumps(dict(config=w.get_config(),result=w.result),ensure_ascii=False,sort_keys=True)==self.word_snapshot)
                self.completed=True;self.report(True)
            except Exception as exc:self.fail(exc)
        self.shap.finish_report=finish
        QTimer.singleShot(200,self.shap.start)
        self.guard=QTimer();self.guard.setSingleShot(True);self.guard.timeout.connect(lambda:self.fail(TimeoutError('高级参数实测超时')));self.guard.start(180000)
        self.hub.advanced('shap',0);self.guard.stop()
