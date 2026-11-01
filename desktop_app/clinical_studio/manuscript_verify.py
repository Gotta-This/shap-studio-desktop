"""Exercise the real Qt dialogs, filesystem and linked global todos in packages."""
from pathlib import Path
import json
import time
import traceback
from unittest.mock import patch
import zipfile

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton, QTableWidget
from .manuscripts import enable_workspace, WorkspaceStore
from .manuscript_ui import TaskDialog, ReceiveDialog, WorkDialog
from .todos import TodoStore


def verify_manuscripts(window, directory):
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    checks, callback_errors = [], []
    app = QApplication.instance()

    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
        if not value:
            raise AssertionError(name)

    def pump():
        for _ in range(4):
            app.processEvents()

    def shot(name):
        pump()
        window.grab().save(str(root/(name+'.png')))

    def save(dialog):
        box = dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(box.button(QDialogButtonBox.Ok), Qt.LeftButton)

    def modal(action):
        def run():
            dialog = app.activeModalWidget()
            try:
                if dialog is None:
                    raise AssertionError('Expected a native Qt dialog')
                action(dialog)
            except Exception:
                callback_errors.append(traceback.format_exc())
                if dialog:
                    dialog.reject()
        QTimer.singleShot(80, run)

    def wait_files():
        until = time.monotonic()+20
        while page.worker is not None and time.monotonic() < until:
            pump()
            QTest.qWait(10)
        check('材料后台处理完成且界面恢复可用', page.worker is None and page.pages.isEnabled())
        check('Qt回调未发生异常', not callback_errors)

    try:
        window.timer.stop()
        folder = root/'科研工作空间'
        folder.mkdir(exist_ok=True)
        historical = folder/'历史文稿.txt'
        historical.write_text('历史资料保留', encoding='utf-8')
        store = enable_workspace(folder)
        standalone = TodoStore().add('独立待办保留')
        window.show_board(10)
        page = window.manuscript_page
        pump()
        check('原Qt侧栏提供稿件入口', window.nav_buttons['manuscript'].isChecked())
        check('启用不扫描历史文件', store.tasks() == [] and store.files() == [] and historical.read_text(encoding='utf-8') == '历史资料保留')
        shot('01-empty-workspace')

        def fill_task(dialog):
            check('新建入口打开真实Qt表单', isinstance(dialog, TaskDialog))
            dialog.client.setText('张老师')
            dialog.name.setText('冠心病降脂论文')
            dialog.tags.setText('预测模型，心血管')
            dialog.due.set_date('2026-11-07')
            dialog.todo.setText('核对审稿意见')
            dialog.todo_due.set_date('2026-11-03')
            save(dialog)
        modal(fill_task)
        QTest.mouseClick(page.new_button, Qt.LeftButton)
        pump()
        check('新建表单成功保存', not callback_errors and page.task_id is not None)
        task_id = page.task_id
        original = store.task(task_id)
        old_dir = store.inside(original['directory'])
        check('真实目录和第一项待办已建立', old_dir.is_dir() and len(store.todos(task_id)) == 1)

        incoming = root/'incoming'
        incoming.mkdir(exist_ok=True)
        doc = incoming/'逐条回复.docx'
        with zipfile.ZipFile(doc, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第二轮修改意见</w:t></w:r></w:p></w:body></w:document>')
        image = incoming/'校准曲线.png'
        bitmap = QImage(160, 100, QImage.Format_RGB32)
        bitmap.fill(QColor('#277453'))
        bitmap.save(str(image))

        def fill_receive(dialog):
            check('接收入口打开分类确认表单', isinstance(dialog, ReceiveDialog))
            dialog.categories[0].setCurrentText('修改稿')
            dialog.categories[1].setCurrentText('图表')
            dialog.make_todo.setChecked(True)
            dialog.todo.setText('修改正文与图表')
            save(dialog)
        for repeat in range(2):
            with patch('clinical_studio.manuscript_ui.QFileDialog.getOpenFileNames', return_value=([str(doc),str(image)],'')):
                modal(fill_receive)
                QTest.mouseClick(page.import_button, Qt.LeftButton)
                wait_files()
            check('重复接收不重复建文件或待办', len(store.files(task_id)) == 2 and len(store.todos(task_id)) == 2)
        check('外部源材料保留', doc.exists() and image.exists())
        check('文件分类为真实目录', {f['category'] for f in store.files(task_id)} == {'修改稿','图表'})
        shot('02-task-files')

        # Native table model edits go through the same itemChanged handler as clicking the checkbox.
        page.work_table.item(0,0).setCheckState(Qt.Checked)
        pump()
        check('稿件页可完成待办', sum(t['completed'] for t in store.todos(task_id)) == 1)

        def rename(dialog):
            dialog.name.setText('冠心病论文_第二轮返修')
            dialog.client.setText('李老师')
            dialog.status.setCurrentText('返修中')
            save(dialog)
        modal(rename)
        page.edit_task()
        pump()
        changed = store.task(task_id)
        check('编辑同步重命名实际任务目录', not old_dir.exists() and store.inside(changed['directory']).is_dir())
        check('建立日期和文件关联保持不变', original['created_date'] == changed['created_date'] and all(store.file_path(f['id']).is_file() for f in store.files(task_id)))
        check('改名保留待办完成状态', sum(t['completed'] for t in store.todos(task_id)) == 1)

        page.show_overview()
        page.search.setText('逐条回复')
        pump()
        check('可由材料文件名检索所属任务', page.tasks_table.rowCount() == 1)
        page.tag_filter.setText('预测模型，心血管')
        page.status_filter.setCurrentText('返修中')
        page.pending.setChecked(True)
        pump()
        check('标签状态待办可组合筛选', page.tasks_table.rowCount() == 1)
        page.search.setText('不存在的任务')
        pump()
        check('无搜索结果时不显示旧任务', page.tasks_table.rowCount() == 0)
        page.clear_filters()
        shot('03-searchable-workspace')

        window.show_board(9)
        window.todo_page.refresh()
        pump()
        linked = [t for t in TodoStore().read() if t.get('workspace_task_id') == task_id]
        check('稿件待办进入已有待办页且客户信息更新', len(linked) == 2 and all(t['client'] == '李老师' for t in linked))
        check('已有独立待办未被覆盖', any(t['id'] == standalone['id'] for t in TodoStore().read()))
        actions = [b for b in window.todo_page.table.findChildren(QPushButton) if b.text() == '稿件' and b.isVisible()]
        check('全局待办提供返回稿件入口', bool(actions))
        QTest.mouseClick(actions[0], Qt.LeftButton)
        pump()
        check('全局待办返回相同稿件任务', window.board_index == 10 and page.task_id == task_id)

        source = incoming/'待分配数据.csv'
        source.write_text('a,b\n1,2', encoding='utf-8')
        page.show_overview()
        def inbox_receive(dialog):
            dialog.target.setCurrentIndex(dialog.target.findData(None))
            save(dialog)
        with patch('clinical_studio.manuscript_ui.QFileDialog.getOpenFileNames', return_value=([str(source)],'')):
            modal(inbox_receive)
            QTest.mouseClick(page.import_button, Qt.LeftButton)
            wait_files()
        page.set_mode('inbox')
        pump()
        check('未分类收件箱独立保存新材料', page.inbox_table.rowCount() == 1 and len(store.files()) == 1)
        fid = store.files()[0]['id']
        old_path = store.file_path(fid)
        page.inbox_table.selectRow(0)
        def classify(dialog):
            dialog.target.setCurrentIndex(dialog.target.findData(task_id))
            dialog.categories[0].setCurrentText('原始数据')
            save(dialog)
        modal(classify)
        QTest.mouseClick(page.archive_button, Qt.LeftButton)
        wait_files()
        check('归档实际移动受管副本且保留外部原件', not old_path.exists() and store.file_path(fid).parent.name == '原始数据' and source.exists())

        def undo(dialog):
            listing = dialog.findChild(QTableWidget)
            row = next(i for i in range(listing.rowCount()) if listing.item(i,0).text() == '归档材料')
            listing.selectRow(row)
            target = next(b for b in dialog.findChildren(QPushButton) if b.text() == '撤销所选归档')
            QTest.mouseClick(target, Qt.LeftButton)
        modal(undo)
        page.show_log()
        pump()
        check('操作记录可撤销未关联待办的归档', len(store.files()) == 1 and old_path.exists())

        page.open_task(task_id)
        f = next(f for f in store.files(task_id) if f['original_name'] == doc.name)
        store.file_path(f['id']).unlink()
        page.refresh_detail()
        check('文件丢失在界面明确显示', any(page.file_table.item(i,3).text() == '已丢失' for i in range(page.file_table.rowCount())))
        with patch('clinical_studio.manuscript_ui.QFileDialog.getOpenFileName', return_value=(str(doc),'')):
            page.open_file(f['id'])
        check('选择原文件后校验并重新关联', store.file_path(f['id']).read_bytes() == doc.read_bytes())

        for width,height in [(1100,760),(1440,960),(1728,1050)]:
            window.resize(width,height)
            pump()
            check(f'{width}宽度保持原生字体与可滚动布局', window.views[10].transform().m11() == 1 and window.manuscript_area.width() == window.boards[10].width()-296 and page.width() >= window.manuscript_area.viewport().width())
        window.resize(1440,960)
        page.show_overview()
        shot('04-final-workspace')
        reopened = WorkspaceStore(store.root, create=False)
        check('重新打开索引保留全部数据', len(reopened.tasks()) == 1 and len(reopened.files(task_id)) == 2 and len(reopened.todos(task_id)) == 2)
        report = dict(passed=True, checks=checks)
    except Exception:
        report = dict(passed=False, checks=checks, traceback=traceback.format_exc(), callback_errors=callback_errors)
    (root/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report['passed']
