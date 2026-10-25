"""Offscreen verification of module four, usable in the standalone Mac bundle."""
from copy import deepcopy
import json,time,sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox,QDialog
from .config import default_config,save_config
from .strict_ui import set_field


def verify(window,directory):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    checks=[];app=QApplication.instance()
    def check(name,ok,**details):
        checks.append(dict(name=name,passed=bool(ok),**details))
        if not ok:raise AssertionError(name)
    def pump():app.processEvents()
    def edit(widget,text):widget.setText(str(text));widget.textEdited.emit(str(text));widget.clearFocus();pump()
    def shot(name):pump();window.grab().save(str(root/(name+'.png')))
    def dialog_edit(button,fn):
        error=[]
        def operate():
            try:
                dialog=app.activeModalWidget()
                check('完整参数对话框实际打开',isinstance(dialog,QDialog))
                fn();shot('advanced-'+str(len(checks)))
            except Exception as exc:error.append(exc)
            finally:app.activeModalWidget().accept()
        QTimer.singleShot(100,operate);button.click()
        if error:raise error[0]
    original_warning=QMessageBox.warning;original_info=QMessageBox.information
    original_save=QFileDialog.getSaveFileName;original_dir=QFileDialog.getExistingDirectory;original_open=QFileDialog.getOpenFileName
    QMessageBox.warning=lambda *args: (_ for _ in ()).throw(AssertionError(str(args[-1])))
    QMessageBox.information=lambda *args:QMessageBox.Ok
    try:
        window.timer.stop();window.open_module('shap');tool=window.modules['shap'];pump()
        check('只实例化第四模块',set(window.modules)=={'shap'})
        check('两组边界和处理方式均可编辑',window.data_table.columnCount()==11)
        edit(window.boards[4].controls['sample-size'],320)
        edit(window.boards[4].controls['positive-rate'],.25)
        window.data_table.item(2,7).setText('23')
        window.data_table.item(2,8).setText('77')
        check('阴性边界不覆盖阳性边界',tool.data_editor.data['features'][2]['negative']['min']==23 and tool.data_editor.data['features'][2]['positive']['min']==18)
        window.data_table.item(0,10).setText('3');window.data_table.item(0,9).setText('round')
        dialog_edit(window.boards[4].controls['data-parameters'],lambda:set_field(tool.data_editor.general.fields['id_prefix'],'VERIFY-'))
        window.show_board(5);edit(window.boards[5].controls['background-size'],70);edit(window.boards[5].controls['sample-index'],2)
        def model_edit():
            set_field(tool.model_form.fields['tol'],1e-8)
            set_field(tool.model_form.fields['max_iter'],1500)
        dialog_edit(window.boards[5].controls['model-parameters'],model_edit)
        window.binary_table.item(0,1).setText('.8')
        window.show_board(6)
        for index,key in enumerate(['summary','bar','force','waterfall','dependence_protective','dependence_risk']):
            window.select_style(key)
            editor=window.style_editor()
            check(key+' 完整字段可编辑',set(tool.config['plots']['common'])<=set(editor.fields))
            window.set_style('font_size',11.5+index*.25)
            window.set_style('axis_width',1.3+index*.1)
            window.set_style('edge_width',1.2+index*.1)
            window.set_style('line_width',1.4+index*.1)
            window.set_style('positive_color','#BA4B55')
            window.set_style('negative_color','#316DAB')
            window.set_style('bar_color','#24765B')
            window.set_style('point_color','#5B69AF')
            window.set_style('point_alpha',.9)
            window.set_style('title_size',15.5)
            window.set_style('label_size',10.5)
            window.set_style('tick_size',9.5)
            window.set_style('baseline_width',1.7)
            window.set_style('separator_width',2.3)
            if key=='dependence_protective':window.set_style('interaction_feature','年龄')
            editor.commit()
        window.select_style('force');window.set_style('figsize',[8.,3.]);window.restore_style()
        check('恢复力图保留原始专用尺寸字号',window.style_field('figsize').value()==[14.,4.] and window.style_field('font_size').value()==10.)
        window.set_style('font_size',11.5)
        def export_edit():
            set_field(tool.export_form.fields['dpi'],100)
            for box in tool.export_form.fields['formats'].format_boxes.values():box.setChecked(True)
        dialog_edit(window.boards[6].controls['style-parameters'],export_edit)
        expected=tool.collect_config();check('容差1e-8未被输入控件吞掉',expected['model']['tol']==1e-8)
        path=root/'ui-parameters.json';QFileDialog.getSaveFileName=lambda *a,**kw:(str(path),'JSON')
        tool.export_config();saved=json.loads(path.read_text(encoding="utf-8"));check('配置保存与完整界面一致',saved==expected)
        QFileDialog.getOpenFileName=lambda *a,**kw:(str(path),'JSON')
        tool.import_config();check('配置重新载入保持所有参数',tool.collect_config()==expected)
        window.refresh(force=True)
        check('载入配置后简化控件仍绑定所选图',window.style_editor().selector.currentData()==window.style_key and window.style_field('font_size').value()==expected['plots']['plots']['force']['font_size'])
        window.show_board(4);shot('complete-data-parameters');window.show_board(6);shot('data-and-styles-before-run')
        window.generate('shap');deadline=time.monotonic()+120
        while tool.worker and tool.worker.isRunning() and time.monotonic()<deadline:
            pump();time.sleep(.01)
        pump();check('后台UI任务完成',tool.result is not None and not tool.worker.isRunning())
        result=tool.result;window.refresh(force=True);shot('actual-results')
        check('实际生成320行和80阳性',len(result.data)==320 and result.data[result.config['data']['label_name']].sum()==80)
        check('数据采用新ID字段',result.data.iloc[0,0]=='VERIFY-0001')
        check('六图三格式共18文件',len(result.images)==18 and all(p.stat().st_size>100 for p in result.images))
        check('六图颜色字体线宽对象检查全部通过',len(result.audit)==6 and all(a['passed'] for a in result.audit.values()))
        check('运行参数与UI完全一致',json.loads((result.folder/'parameters.json').read_text(encoding="utf-8"))==expected)
        import pandas as pd
        pd.testing.assert_frame_equal(pd.read_excel(result.folder/'clinical_prediction_dataset_with_protective.xlsx'),result.data)
        check('Excel逐单元格与实际数据一致',True)
        export=root/'saved-results';export.mkdir(exist_ok=True);QFileDialog.getExistingDirectory=lambda *a,**kw:str(export)
        window.boards[7].controls['save-results'].click()
        target=window.last_saved_results
        check('结果另存全部文件逐字节一致',all((target/p.relative_to(result.folder)).read_bytes()==p.read_bytes() for p in result.folder.rglob('*') if p.is_file()))
        image=root/'saved-image.png';QFileDialog.getSaveFileName=lambda *a,**kw:(str(image),'PNG')
        window.boards[7].controls['save-image'].click()
        check('当前图另存成功且内容一致',image.read_bytes()==Path(window.plot_image.path).read_bytes())
        window.show_board(6);window.select_style('summary');window.refresh(force=True);shot('real-style-preview')
        check('样式预览来自实际图表',window.style_preview.path==str(next(p for p in result.images if p.name=='shap_summary_plot.png')))
        check('其他模块保持未实例化',set(window.modules)=={'shap'})
        report=dict(passed=True,checks=checks,folder=str(result.folder),runtime='bundled' if getattr(sys,'frozen',False) else 'source')
        (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");return True
    except Exception:
        import traceback
        (root/'verification.json').write_text(json.dumps(dict(passed=False,checks=checks,traceback=traceback.format_exc()),ensure_ascii=False,indent=2),encoding="utf-8");return False
    finally:
        QMessageBox.warning=original_warning;QMessageBox.information=original_info
        QFileDialog.getSaveFileName=original_save;QFileDialog.getExistingDirectory=original_dir;QFileDialog.getOpenFileName=original_open
