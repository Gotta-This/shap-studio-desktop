"""Verify Word UI layout with a live category-cell editor and custom group names."""
import json,traceback
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit
from .word_batch_engine import default_batch_config
from .group_verify import verify_groups


def verify_layout(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);checks=[];app=QApplication.instance()
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    def pump():app.processEvents()
    def shot(name):pump();window.grab().save(str(root/(name+'.png')))
    try:
        check('自定义组别与导出完整流程仍通过',verify_groups(window,root/'groups'))
        tool=window.open_module('word');c=default_batch_config(['常规护理组','综合干预组'])
        for g in c['groups']:
            g.update(n=25,extent_mode='category',extent=[dict(label='E1',percent=30),dict(label='E2',percent=40),dict(label='E3',percent=30)])
        tool.set_groups(c['groups']);tool.set_indicators([dict(table=1,name='治疗前评分',group=g['name'],mean=10,sd=2,digits=2,lower=None,upper=None,parity='any',raw='10±2') for g in c['groups']]);tool.source_label.setText('当前组别：常规护理组、综合干预组（合成验证）')
        tool.same_size.setChecked(False);tool.pages.setCurrentIndex(0);tool.group_selector.setCurrentIndex(0);editor=tool.group_editors[0];editor.sections.setCurrentIndex(3);pump()
        check('仅保留一层主流程页签',not tool.group_tabs.tabBar().isVisible())
        check('组别切换使用当前自定义组名','常规护理组' in tool.group_selector.itemText(0) and '综合干预组' in tool.group_selector.itemText(1))
        check('共用规则提示使用实际第一组名称','常规护理组' in tool.shared_basics.text())
        check('不同例数模式隐藏统一例数输入框',not tool.common_n.isVisible() and editor.fields['n'].isVisible())
        check('各组总人数汇总正确','合计50例' in tool.total_label.text())
        check('旧背景样式选择器与真实名称一致',tool.objectName()=='word-workflow' and 'QWidget#word-workflow' in tool.styleSheet())
        check('资料类型采用侧栏选择',editor.sections.nav.isVisible() and editor.sections.nav.currentRow()==3)
        table=editor.extent.table;field=table.item(0,1);table.editItem(field);pump();active=table.findChild(QLineEdit)
        check('比例单元格实际进入编辑',active is not None)
        rect=table.visualItemRect(field);check('编辑框完全在本行内部',rect.contains(active.geometry()) and active.height()<=table.rowHeight(0))
        check('小表格无需内部垂直滚动',table.verticalScrollBar().maximum()==0)
        shot('01-extent-editing')
        active.setText('30');QTest.keyClick(active,Qt.Key_Return);pump()
        check('编辑后的比例值正确提交',editor.extent.values()[0][1]=='30')
        tool.group_selector.setCurrentIndex(1);pump();check('切换组别显示正确配置',tool.group_tabs.currentWidget() is tool.group_editors[1])
        check('第二组提示明确共用哪个组','常规护理组' in tool.group_editors[1].shared_note.text())
        shot('02-shared-settings')
        tool.shared_basics.setChecked(False);tool.group_editors[1].sections.setCurrentIndex(1);pump();shot('03-independent-age')
        check('独立资料模式可编辑第二组规则',tool.group_editors[1].age.isEnabled())
        tool.common_n.setValue(25);tool.same_size.setChecked(True);pump();check('统一例数模式显示输入框并同步各组',tool.common_n.isVisible() and all(e.fields['n'].text()=='25' for e in tool.group_editors))
        check('调整布局不改变组别和生成配置',[g['name'] for g in tool.get_config()['groups']]==['常规护理组','综合干预组'])
        report=dict(passed=True,checks=checks)
    except Exception:report=dict(passed=False,checks=checks,traceback=traceback.format_exc())
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['passed']
