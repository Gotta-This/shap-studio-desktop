"""Exercise native controls in an isolated todo file, including a second window."""
import json,time,traceback
from pathlib import Path
from datetime import date,timedelta
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from .todos import TodoStore
from .todo_ui import DateButton


def verify_todos(window,directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True);app=QApplication.instance();checks=[]
    def pump():
        for _ in range(8):app.processEvents()
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));print(name,bool(ok),flush=True)
        if not ok:raise AssertionError(name)
    try:
        window.timer.stop();pump();page=window.todo_page
        check('启动默认打开待办',window.board_index==9 and window.current_module is None)
        check('待办入口位于工作台上方',window.boards[9].controls['nav-todo'].y()<window.home_button.y())
        check('首次打开为空状态',page.table.rowCount()==0 and page.table.empty.isVisible())
        window.grab().save(str(root/'empty.png'))
        page.name.setFocus();QTest.keyClicks(page.name,'Demo document A');QTest.keyClick(page.name,Qt.Key_Return);pump()
        check('输入名称回车添加并保存',page.table.rowCount()==1 and TodoStore(page.store.path).visible()[0]['name']=='Demo document A')
        errors=[]
        def add_dialog():
            try:
                d=page.dialog;check('新增弹窗只有三个输入',d is not None and hasattr(d,'name') and hasattr(d,'priority') and hasattr(d,'due'))
                d.grab().save(str(root/'new-dialog.png'));d.name.setText('李老师 · 修改稿');d.priority.setCurrentIndex(d.priority.findData('high'));d.due.set_date(date.today().isoformat());d.accept()
            except Exception:errors.append(traceback.format_exc());page.dialog.reject() if page.dialog else None
        QTimer.singleShot(120,add_dialog);page.new_button.click();pump();check('新增弹窗保存成功',not errors and page.table.rowCount()==2)
        page.table.item(0,1).setText('李老师 · 最新修改稿');pump()
        check('直接修改名称落盘',any(t['name']=='李老师 · 最新修改稿' for t in TodoStore(page.store.path).visible()))
        due=page.table.cellWidget(0,3)
        def tomorrow():
            try:due.date_menu.actions()[1].trigger();due.date_menu.close()
            except Exception:errors.append(traceback.format_exc())
        QTimer.singleShot(100,tomorrow);due.click();pump();check('日期菜单真实操作保存明天',not errors and any(t['due_date']==(date.today()+timedelta(days=1)).isoformat() for t in page.store.visible()))
        window.grab().save(str(root/'populated.png'))
        rect=page.table.visualItemRect(page.table.item(0,0));QTest.mouseClick(page.table.viewport(),Qt.LeftButton,pos=QPoint(rect.left()+14,rect.center().y()));pump()
        check('勾选完成移出待办列表',len(page.store.visible(True))==1 and page.table.rowCount()==1)
        page.done_button.click();pump();check('已完成列表保留文档',page.table.rowCount()==1)
        task=page.store.visible(True)[0];page.delete(task['id']);pump();check('删除后可撤销',page.table.rowCount()==0 and page.undo.isVisible());page.undo.click();pump();check('撤销恢复原完成状态',page.table.rowCount()==1 and page.store.visible(True)[0]['id']==task['id'])
        page.search.setText('无匹配名称');pump();check('搜索筛选文档',page.table.rowCount()==0);page.search.clear();page.pending_button.click();pump()
        from .strict_ui import DesktopWindow
        other=DesktopWindow();other.timer.stop();other.show();pump()
        try:check('新窗口读取已保存文档及完成状态',other.board_index==9 and len(other.todo_page.store.visible())==1 and len(other.todo_page.store.visible(True))==1)
        finally:other.close();other.deleteLater();pump()
        for size in [(1100,800),(1800,1100),(1440,960)]:
            window.resize(*size);pump();board=window.boards[9]
            check(f'窗口{size[0]}保持正常字号和内容伸展',window.views[9].transform().m11()==1 and window.todo_area.width()==board.width()-296)
        for key in ('category','numeric','word','shap'):
            window.open_module(key);pump();check(key+'工具可正常切换',window.current_module==key)
        word=window.modules['word'];check('采用正文一般资料默认不勾选',not word.use_word_prose.isChecked())
        check('已核对未识别内容默认不勾选',not word.prose_table_editor.reviewed.isChecked())
        word.prose_table_editor.reviewed.setChecked(True);word.reset_prose_table();pump();check('清空正文后复核勾选重置',not word.prose_table_editor.reviewed.isChecked())
        window.open_module('word');pump();window.grab().save(str(root/'word-defaults.png'))
        window.show_board(9);pump();window.grab().save(str(root/'home-final.png'))
        report=dict(passed=True,checks=checks)
    except Exception:report=dict(passed=False,checks=checks,traceback=traceback.format_exc())
    (root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report['passed']
