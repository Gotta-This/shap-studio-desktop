"""Resize the actual desktop shell and verify its compact, adaptive layout."""
import json,traceback
from pathlib import Path
from PySide6.QtWidgets import QApplication,QComboBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from .layout_verify import verify_layout
from .version import APP_VERSION


def verify_shell(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);checks=[];app=QApplication.instance()
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    def pump():
        for _ in range(3):app.processEvents()
    def shot(name):pump();window.grab().save(str(root/(name+'.png')))
    try:
        window.timer.stop();check('Word配置布局和生成导出仍正常',verify_layout(window,root/'word-layout'))
        tool=window.open_module('word');tool.pages.setCurrentIndex(0);tool.group_selector.setCurrentIndex(0);pump();short=None
        for width,height,label in [(1440,960,'standard'),(1440,1320,'tall'),(1280,760,'short'),(1728,800,'wide')]:
            window.resize(width,height);pump();view=window.views[3];view.verticalScrollBar().setValue(0);pump();board=window.boards[3]
            check(label+'顶部无整体居中留白',abs(view.mapFromScene(0,0).y())<=1)
            check(label+'内容区随画板高度延伸',abs(tool.geometry().bottom()-(board.height()-25))<=2)
            footer=board.controls['sidebar-footer'];check(label+'页脚在左侧菜单底部',footer.parentWidget() is view.viewport() and footer.x()<224*view.transform().m11() and abs(footer.geometry().bottom()-(view.viewport().height()-round(20*view.transform().m11())-1))<=2)
            if label=='standard':short=tool.height()
            if label=='tall':check('加高窗口增加Word可用高度',tool.height()>short+250)
            shot(label)
        window.resize(1440,1100);pump()
        for key,index in [('category',1),('numeric',2),('word',3),('shap',4)]:
            window.open_module(key);pump();board=window.boards[index]
            footer=board.controls['sidebar-footer']
            check(key+'菜单页脚含当前版本',footer.version.text()=='当前版本 V'+APP_VERSION)
            check(key+'菜单页脚共享更新状态',footer.status.text()==window.updates.message and footer.button.text()==window.updates.action)
            removed=[s for s in board.spec['shapes'] if (s['x']>=1230 and 12<=s['y']<60) or (s['x']<224 and s['y']>=767)]
            check(key+'本地模式和本机运行卡片已移除',bool(removed) and all(s['id'] in board.hidden_shapes for s in removed))
            header=next(s for s in board.spec['shapes'] if s['x']==224 and s['y']==0 and s['height']==76)
            check(key+'顶部栏为44逻辑像素',board.shape_rect(header).height()==44)
            title=next(s for s in board.spec['shapes'] if s['type']=='text' and s['x']==260 and s['y']==111)
            subtitle=next(s for s in board.spec['shapes'] if s['type']=='text' and s['x']==260 and s['y']==156)
            check(key+'主副标题恢复上下排列',board.shape_rect(title).top()==52 and board.shape_rect(title).height()==42 and board.shape_rect(subtitle).top()==96 and board.shape_rect(subtitle).left()==board.shape_rect(title).left())
            footer_shapes=[s for s in board.spec['shapes'] if s['x']>=224 and s['y']>=890]
            check(key+'主内容底部不再绘制宽页脚',all(s['id'] in board.hidden_shapes for s in footer_shapes))
        for target in ('home','category','numeric','word','shap','word'):
            current=window.boards[window.board_index];button=current.controls['nav-'+target];QTest.mouseClick(button,Qt.LeftButton);pump()
            check('切换到'+target+'后不留虚线焦点框',all(not b.hasFocus() and 'dotted' not in b.styleSheet() for b in window.nav_buttons.values()))
            check('切换到'+target+'仅当前菜单选中',sum(b.isChecked() for b in window.nav_buttons.values())==1)
        for index in (4,5,6,7):
            window.show_board(index);pump();board=window.boards[index]
            for step in range(1,5):
                button=board.controls[f'step-{step}'];button.setFocus();pump()
                check(f'第四工具页面{index}步骤{step}不绘制虚线焦点框','dotted' not in button.styleSheet() and 'outline:none' in button.styleSheet())
        window.show_home();pump();board=window.boards[0]
        check('首页欢迎语含宝宝和表情','欢迎回来宝宝 🥰' in board.overrides.values())
        check('左上角使用App图标',not board.controls['brand-icon'].pixmap.isNull())
        shot('home')
        window.open_module('word');pump();check('Word操作区紧接双行标题',tool.y()==130);shot('final-word')
        report=dict(passed=True,checks=checks)
    except Exception:report=dict(passed=False,checks=checks,traceback=traceback.format_exc())
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['passed']
