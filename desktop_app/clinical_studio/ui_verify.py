"""在真实显示的 Qt 窗口内操作控件、对话框并独立核对导出文件。"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import traceback

from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit,QComboBox,QCheckBox,QScrollArea,QFileDialog,QPushButton,QMessageBox

from .config import default_config,PLOT_NAMES


SCENARIO_FEATURES=[
    ("CRP_UI",[82.5,7.25,25.,120.],[48.5,9.5,10.,95.],"round",2),
    ("CSVD_UI",[3.2,.65,0.,6.],[1.4,.45,0.,4.],"round",2),
    ("年龄_UI",[68.5,8.75,35.,90.],[73.25,9.25,32.,95.],"round",2),
    ("TG_UI",[6.4,.95,.2,15.],[3.8,.75,.1,12.],"round",3),
    ("白蛋白_UI",[34.75,2.25,15.,65.],[44.25,2.75,18.,70.],"round",2),
    ("教育年限_UI",[7.25,2.6,0.,24.],[13.5,3.1,0.,26.],"round",2),
]
SCENARIO_COLORS={
    "summary":{"low_color":"#1950A0","high_color":"#E16A31"},
    "bar":{"bar_color":"#2B8C64"},
    "force":{"positive_color":"#C75B16","negative_color":"#5E4EA3"},
    "waterfall":{"positive_color":"#B93462","negative_color":"#147D92"},
    "dependence_protective":{"point_color":"#2864B7"},
    "dependence_risk":{"point_color":"#A34C15"},
}
SCENARIO_FONTS=["Noto Sans CJK SC","DejaVu Sans","Noto Sans CJK SC","DejaVu Serif","DejaVu Sans Mono","Noto Sans CJK SC"]


class UiVerifier:
    def __init__(self,window,directory,app):
        self.window,self.app=window,app
        self.root=Path(directory).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.shots=self.root/"screenshots";self.shots.mkdir(exist_ok=True)
        self.expected=default_config();self.events=[];self.checks=[];self.passed=False
        self.window.resize(1460,980)
        # Qt 的 ControlModifier 在 macOS 映射为 Command 快捷键。
        self.modifier=Qt.ControlModifier
        self.window.worker=None
        # 无论普通运行还是安装包运行，失败都落到可供 CI 检查的 JSON。
        self.original_warning=QMessageBox.warning
        QMessageBox.warning=lambda parent,title,message:self.fail(RuntimeError(f"{title}: {message}"))

    def log(self,message,**detail):
        self.events.append({"action":message,**detail});print(message,flush=True)

    def ensure(self,widget):
        parent=widget.parentWidget()
        while parent:
            if isinstance(parent,QScrollArea):parent.ensureWidgetVisible(widget,20,20)
            parent=parent.parentWidget()
        self.app.processEvents()

    def click(self,widget):
        self.ensure(widget)
        if not widget.isEnabled():raise AssertionError(f"控件未启用：{widget.objectName() or type(widget).__name__}")
        if isinstance(widget,QCheckBox):
            QTest.mouseClick(widget,Qt.LeftButton,pos=QPoint(8,widget.height()//2))
        else:QTest.mouseClick(widget,Qt.LeftButton)
        self.app.processEvents()

    def type_text(self,widget,text):
        self.ensure(widget);widget.setFocus();QTest.mouseClick(widget,Qt.LeftButton)
        QTest.keyClick(widget,Qt.Key_A,self.modifier)
        # 离屏平台的弹出菜单不一定恢复键盘焦点，明确选择输入框内容。
        # 只操作文本选择与输入事件，不直接修改配置或 spinbox 数值。
        widget.selectAll()
        if not str(text):QTest.keyClick(widget,Qt.Key_Backspace)
        elif str(text).isascii():QTest.keyClicks(widget,str(text))
        else:
            event=QInputMethodEvent();event.setCommitString(str(text));QApplication.sendEvent(widget,event)
        QTest.keyClick(widget,Qt.Key_Tab);self.app.processEvents()

    def combo(self,combo,value):
        index=combo.findData(value)
        if index<0:index=combo.findText(str(value),Qt.MatchExactly)
        if index<0:raise AssertionError(f"下拉选项不存在：{value}")
        self.ensure(combo);combo.setFocus()
        combo.showPopup();self.app.processEvents()
        item=combo.model().index(index,combo.modelColumn(),combo.rootModelIndex())
        combo.view().scrollTo(item);self.app.processEvents()
        QTest.mouseClick(combo.view().viewport(),Qt.LeftButton,pos=combo.view().visualRect(item).center())
        self.app.processEvents()

    def field(self,field,value):
        from .widgets import ColorField,FileField
        editor=field.editor
        if isinstance(editor,(ColorField,FileField)):self.type_text(editor.text,"" if value is None else value)
        elif field.key=="font_family":self.combo(editor,value[0])
        elif field.key=="formats":
            for fmt,box in field.format_boxes.items():
                if box.isChecked()!=(fmt in value):self.click(box)
        elif hasattr(field,"pair"):
            for spin,item in zip(field.pair,value):
                self.type_text(spin.findChild(QLineEdit),format(float(item),".10f").rstrip("0").rstrip(".") or "0")
                QTest.keyClick(spin,Qt.Key_Return)
        elif isinstance(editor,QCheckBox):
            if editor.isChecked()!=value:self.click(editor)
        elif isinstance(editor,QComboBox):self.combo(editor,value)
        elif isinstance(editor,QLineEdit):self.type_text(editor,"" if value is None else value)
        else:
            number=value*100 if field.percent else value
            text=format(float(number),".10f").rstrip("0").rstrip(".") or "0"
            self.type_text(editor.findChild(QLineEdit),text)
            QTest.keyClick(editor,Qt.Key_Return)
            self.app.processEvents()
        actual=field.value()
        if field.key=="font_family":
            if editor.currentFont().family()!=value[0]:raise AssertionError(f"字体输入未生效：{actual} != {value}")
        elif actual!=value:raise AssertionError(f"控件输入未生效：{field.key}: {actual} != {value}")
        self.log("修改控件",field=field.key,value=value)

    def navigate(self,index):
        item=self.window.nav.item(index)
        QTest.mouseClick(self.window.nav.viewport(),Qt.LeftButton,pos=self.window.nav.visualItemRect(item).center())
        self.app.processEvents()

    def tab(self,tabs,index):
        QTest.mouseClick(tabs.tabBar(),Qt.LeftButton,pos=tabs.tabBar().tabRect(index).center());self.app.processEvents()

    def shot(self,name):
        self.app.processEvents();self.window.grab().save(str(self.shots/(name+".png")))

    def style_field(self,key,value):
        editor=self.window.style_editor;field=editor.fields[key]
        for index in range(editor.tabs.count()):
            if editor.tabs.widget(index).isAncestorOf(field):self.tab(editor.tabs,index);break
        override=editor.overrides.get(key)
        if override is not None and not override.isChecked():self.click(override)
        self.field(field,value)

    def check(self,label,condition,**detail):
        item=dict(item=label,passed=bool(condition),**detail);self.checks.append(item)
        if not condition:raise AssertionError(label+": "+str(detail))

    def fail(self,error):
        if getattr(self,"failed",False):return
        self.failed=True;self.log("验证失败",error=str(error),traceback=traceback.format_exc())
        self.finish_report(False);QTimer.singleShot(50,self.app.quit)

    def start(self):
        try:
            self.log("开始真实窗口控件操作",platform=sys.platform,runtime="bundled" if getattr(sys,"frozen",False) else "source",
                     qt_platform=QApplication.platformName())
            self.type_text(self.window.output_edit,str(self.root/"runs"))
            self.navigate(1);editor=self.window.data_editor
            self.tab(editor.tabs,1)
            changes=dict(n_samples=420,positive_rate=.30,random_seed=20261025,label_name="模拟不良结局",positive_name="发生事件",
                         negative_name="未发生事件",id_name="病例编号",id_prefix="CASE-",id_width=5,id_start=101)
            for key,value in changes.items():self.field(editor.general.fields[key],value)
            self.expected["data"].update(changes);self.shot("01_样本与字段设置")
            self.tab(editor.tabs,0)
            for index,(name,positive,negative,mode,digits) in enumerate(SCENARIO_FEATURES):
                item=editor.list.item(index)
                QTest.mouseClick(editor.list.viewport(),Qt.LeftButton,pos=editor.list.visualItemRect(item).center());self.app.processEvents()
                self.type_text(editor.name,name);feature=self.expected["data"]["features"][index];feature["name"]=name
                for group,values in [("positive",positive),("negative",negative)]:
                    for key,value in zip(["mean","std","min","max"],values):
                        self.field(editor.detail_forms[group].fields[key],value);feature[group][key]=value
                self.field(editor.detail_forms["processing"].fields["transform"],mode)
                self.field(editor.detail_forms["processing"].fields["digits"],digits)
                feature.update(transform=mode,digits=digits)
                self.shot(f"02_{index+1}_连续特征")
            item=editor.list.item(6)
            QTest.mouseClick(editor.list.viewport(),Qt.LeftButton,pos=editor.list.visualItemRect(item).center());self.app.processEvents()
            self.type_text(editor.name,"高血压编码_UI")
            for key,value in dict(values=[0,2],positive_p=.82,negative_p=.28).items():self.field(editor.detail_forms["binary"].fields[key],value)
            self.expected["data"]["features"][6].update(name="高血压编码_UI",values=[0,2],positive_p=.82,negative_p=.28)
            self.shot("03_分类特征")
            self.navigate(2)
            for key,value in dict(test_size=.25,split_seed=123,random_state=321,max_iter=1600,C=.8,tol=.00001,threshold=.55).items():
                self.field(self.window.model_form.fields[key],value);self.expected["model"][key]=value
            self.shot("04_模型设置")
            model_tabs=self.window.model_form.parentWidget()
            while model_tabs and not hasattr(model_tabs,"tabBar"):model_tabs=model_tabs.parentWidget()
            self.tab(model_tabs,1)
            for key,value in dict(background_max_samples=150,background_seed=123,protective_feature="白蛋白_UI").items():
                self.field(self.window.explanation_form.fields[key],value);self.expected["explanation"][key]=value
            self.navigate(3)
            for key,value in dict(dpi=180,formats=["png","svg","pdf"],random_seed=777,sample_index=3).items():
                self.field(self.window.export_form.fields[key],value);self.expected["plots"][key]=value
            for index,name in enumerate(PLOT_NAMES):
                self.combo(self.window.style_editor.selector,name)
                custom=dict(SCENARIO_COLORS[name],font_family=[SCENARIO_FONTS[index]],font_size=13+index,
                            title_size=17+index,label_size=12+index,tick_size=10+index,
                            line_width=round(1.4+.3*index,1),axis_width=round(1.2+.2*index,1),
                            baseline_width=round(1.8+.2*index,1),edge_width=round(.8+.1*index,1),
                            baseline_color=["#596A7D","#61724F","#705A64","#4F6D75","#7C5F48","#5F607D"][index])
                for key,value in custom.items():
                    self.style_field(key,value)
                    # 字体族保留控件提供的后备字体，这些后备同样记录到预期快照中。
                    self.expected["plots"]["plots"][name][key]=self.window.style_editor.fields[key].value() if key=="font_family" else value
                self.shot(f"05_{index+1}_线宽设置")
                for key in SCENARIO_COLORS[name]:
                    field=self.window.style_editor.fields[key]
                    for tab in range(self.window.style_editor.tabs.count()):
                        if self.window.style_editor.tabs.widget(tab).isAncestorOf(field):self.tab(self.window.style_editor.tabs,tab);break
                    self.ensure(field)
                self.shot(f"06_{index+1}_颜色设置")
                field=self.window.style_editor.fields["font_family"]
                for tab in range(self.window.style_editor.tabs.count()):
                    if self.window.style_editor.tabs.widget(tab).isAncestorOf(field):self.tab(self.window.style_editor.tabs,tab);break
                self.shot(f"07_{index+1}_字体设置")
                if name.startswith("dependence_"):
                    feature="白蛋白_UI" if name.endswith("protective") else "CRP_UI"
                    self.style_field("feature",feature);self.expected["plots"]["plots"][name]["feature"]=feature
            self.check("运行前：全部控件值与逐项预期一致",self.window.collect_config()==self.expected)
            (self.root/"expected_ui_settings.json").write_text(json.dumps(self.expected,ensure_ascii=False,indent=2))
            self.log("点击生成数据并分析")
            self.click(self.window.run_button)
            QTimer.singleShot(250,self.wait_result)
            QTimer.singleShot(240000,lambda:self.fail(RuntimeError("界面实测超时")) if not self.passed else None)
        except Exception as error:self.fail(error)

    def wait_result(self):
        if getattr(self,"failed",False):return
        if self.window.worker is not None and self.window.worker.isRunning():QTimer.singleShot(250,self.wait_result);return
        if self.window.result is None:self.fail(RuntimeError("界面任务未生成结果"));return
        try:
            self.shot("08_生成后结果页面")
            self.save_dialog(self.window.save_button,self.root/"从界面保存的配置.json")
            destination=self.root/"另存完整结果";destination.mkdir(exist_ok=True)
            copy_button=next(b for b in self.window.results_page.findChildren(QPushButton) if b.text().startswith("另存完整结果"))
            self.save_dialog(copy_button,destination)
            self.save_single_image()
            self.verify_exports()
            self.finish_report(True);self.passed=True
            self.log("实际窗口操作、保存和独立核对：全部通过")
            QTimer.singleShot(150,self.app.quit)
        except Exception as error:self.fail(error)

    def save_dialog(self,button,path):
        errors=[]
        def fill():
            try:
                dialog=QApplication.activeModalWidget()
                if not isinstance(dialog,QFileDialog):raise AssertionError("未打开文件保存/目录选择对话框")
                edit=dialog.findChild(QLineEdit,"fileNameEdit")
                if edit is None:raise AssertionError("对话框中未找到文件名输入框")
                self.type_text(edit,str(path));QTest.keyClick(edit,Qt.Key_Return)
            except Exception as error:
                errors.append(error)
                if QApplication.activeModalWidget():QApplication.activeModalWidget().reject()
        QTimer.singleShot(250,fill);self.click(button)
        if errors:raise errors[0]
        self.log("通过文件对话框保存",path=str(path))

    def save_single_image(self):
        errors=[]
        path=self.root/"从界面另存的摘要图.png"
        button=next(b for b in self.window.gallery.findChildren(QPushButton) if b.text().startswith("查看大图"))
        def in_preview():
            try:
                preview=QApplication.activeModalWidget()
                save=next(b for b in preview.findChildren(QPushButton) if b.text().startswith("另存此图"))
                self.save_dialog(save,path)
                self.shot("09_另存图片后的结果页面")
                QTest.keyClick(preview,Qt.Key_Escape)
            except Exception as error:
                errors.append(error)
                if QApplication.activeModalWidget():QApplication.activeModalWidget().reject()
        QTimer.singleShot(250,in_preview);self.click(button)
        if errors:raise errors[0]
        self.check("单图另存文件存在",path.is_file())

    def verify_exports(self):
        import numpy as np
        import pandas as pd
        from PIL import Image
        result=self.window.result
        self.check("输出来自打包后的运行环境",getattr(sys,"frozen",False),executable=sys.executable)
        self.check("运行实际打包 App 的 Qt 界面控件",QApplication.platformName() in ("offscreen","cocoa","windows","xcb","wayland"),platform=QApplication.platformName())
        exported=json.loads((result.folder/"parameters.json").read_text())
        saved=json.loads((self.root/"从界面保存的配置.json").read_text())
        self.check("导出参数与界面全部设置一致",exported==self.expected)
        self.check("界面保存的配置与运行快照一致",saved==exported)
        # 独立实现原始随机抽样顺序，不调用应用的 generate_dataset。
        data=self.expected["data"];n=data["n_samples"];rng=np.random.RandomState(data["random_seed"])
        count=int(n*data["positive_rate"]);labels=np.asarray([1]*count+[0]*(n-count));rng.shuffle(labels)
        values={}
        for feature in data["features"]:
            if feature["kind"]=="continuous":
                pos,neg=feature["positive"],feature["negative"]
                a=rng.normal(pos["mean"],pos["std"],n).clip(pos["min"],pos["max"])
                b=rng.normal(neg["mean"],neg["std"],n).clip(neg["min"],neg["max"])
                arr=np.where(labels==1,a,b)
                if feature["transform"]=="int":arr=arr.astype(int)
                elif feature["transform"]=="round":arr=arr.round(feature["digits"])
            else:
                p,q=feature["positive_p"],feature["negative_p"]
                arr=np.where(labels==1,rng.choice(feature["values"],n,p=[1-p,p]),rng.choice(feature["values"],n,p=[1-q,q]))
            values[feature["name"]]=arr
        reference=pd.DataFrame(values);reference[data["label_name"]]=labels
        reference.insert(0,data["id_name"],[data["id_prefix"]+str(i+data["id_start"]).zfill(data["id_width"]) for i in range(n)])
        csv=pd.read_csv(result.folder/"data.csv");excel=pd.read_excel(result.folder/"clinical_prediction_dataset_with_protective.xlsx")
        pd.testing.assert_frame_equal(reference,csv,check_exact=False,rtol=0,atol=1e-12)
        pd.testing.assert_frame_equal(reference,excel,check_exact=False,rtol=0,atol=1e-12)
        self.check("独立重算：全部数据单元与 CSV、Excel 一致",True,rows=n,columns=len(reference.columns),positive_count=count)
        self.check("界面数据表包含全部样本",self.window.data_table.model().rowCount()==n)
        self.check("模型测试集行数符合界面比例",len(result.test)==105)
        self.check("六张图各导出 PNG、SVG、PDF",len(result.images)==18 and len(result.audit)==6)
        for name,audit in result.audit.items():
            self.check(f"{name}：颜色、字体、字号、线宽、尺寸对象核对",audit["passed"],
                       color_checks=len(audit["object_checks"]),style_checks=len(audit.get("style_checks",[])))
            self.check(f"{name}：PNG 像素证据",all(c["passed"] for c in audit["png_checks"]),checks=len(audit["png_checks"]))
        for path in result.images:
            self.check("图表文件已保存",path.is_file() and path.stat().st_size>100,file=path.name)
            if path.suffix==".png":
                dpi=Image.open(path).info.get("dpi",(0,0))
                self.check("PNG 导出 DPI 与界面一致",all(abs(v-self.expected["plots"]["dpi"])<.1 for v in dpi),file=path.name,dpi=list(dpi))
        copied=self.root/"另存完整结果"/result.folder.name
        files=[p for p in result.folder.rglob("*") if p.is_file()]
        for file in files:
            dest=copied/file.relative_to(result.folder)
            self.check("另存完整结果字节一致",dest.is_file() and hashlib.sha256(file.read_bytes()).digest()==hashlib.sha256(dest.read_bytes()).digest(),file=str(file.relative_to(result.folder)))
        original=next(path for path in result.images if path.name=="shap_summary_plot.png")
        self.check("另存单张图片字节一致",hashlib.sha256(original.read_bytes()).digest()==hashlib.sha256((self.root/"从界面另存的摘要图.png").read_bytes()).digest())

    def finish_report(self,passed):
        result=self.window.result
        report=dict(passed=passed,time=datetime.now().isoformat(),runtime="bundled" if getattr(sys,"frozen",False) else "source",
                    qt_platform=QApplication.platformName(),executable=sys.executable,events=self.events,checks=self.checks,
                    settings=self.expected,result_folder=str(result.folder) if result else None)
        (self.root/"ui_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        lines=["打包 App 界面控件操作核对报告",f"整体结果：{'全部通过' if passed else '未通过'}",f"运行方式：{report['runtime']}；窗口平台：{report['qt_platform']}",
               f"输出目录：{report['result_folder']}","", "操作：修改所有数据分布参数、模型参数，以及六张图的颜色、字体、字号和线宽；点击生成；通过保存对话框保存配置、单张图片和完整结果。",""]
        for item in self.checks:lines.append(f"[{'通过' if item['passed'] else '失败'}] {item['item']}")
        if not passed:lines.append(json.dumps(self.events[-1],ensure_ascii=False))
        (self.root/"界面实测核对报告.txt").write_text("\n".join(lines),encoding="utf-8")
