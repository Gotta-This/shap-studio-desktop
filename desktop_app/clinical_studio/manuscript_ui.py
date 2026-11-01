"""Native Qt manuscript workspace, using the existing mint desktop shell."""
from datetime import date, datetime
from pathlib import Path
import json
import sqlite3
import zipfile
import xml.etree.ElementTree as ET

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QStackedWidget, QFileDialog, QDialog, QFormLayout,
    QPlainTextEdit, QListWidget, QListWidgetItem, QMessageBox, QMenu,
    QScrollArea, QSplitter,
)
from .manuscripts import CATEGORIES, STATUSES, WorkspaceStore, configured_workspace, enable_workspace
from .todo_ui import DateButton, priority_combo
from .editor_dialogs import EditorDialog, native_owner


def label(text, muted=False):
    item = QLabel(text)
    item.setTextFormat(Qt.PlainText)
    item.setWordWrap(True)
    if muted:
        item.setStyleSheet('color:#637668;font-size:12px;')
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    item.setMinimumHeight(36)
    if primary:
        item.setObjectName('primary')
    item.clicked.connect(callback)
    return item


def table(headers):
    item = QTableWidget(0, len(headers))
    item.setHorizontalHeaderLabels(headers)
    item.setSelectionBehavior(QAbstractItemView.SelectRows)
    item.setEditTriggers(QAbstractItemView.NoEditTriggers)
    item.setAlternatingRowColors(True)
    item.setShowGrid(False)
    item.verticalHeader().hide()
    item.verticalHeader().setDefaultSectionSize(48)
    item.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    item.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    item.setMinimumHeight(220)
    return item


def cell(text, identifier=None):
    item = QTableWidgetItem(str(text))
    item.setToolTip(str(text))
    if identifier is not None:
        item.setData(Qt.UserRole, identifier)
    return item


class TaskDialog(EditorDialog):
    def __init__(self, parent, store, task_id=None):
        self.store, self.task_id = store, task_id
        task = store.task(task_id) if task_id else {}
        super().__init__(parent, '编辑稿件任务' if task_id else '新建稿件任务', size=(660, 720))
        form = QFormLayout()
        self.body_layout.addLayout(form)
        self.client = QLineEdit(task.get('client', ''))
        self.client.setPlaceholderText('客户 / 甲方；留空归入“未分类”')
        self.name = QLineEdit(task.get('name', ''))
        self.name.setPlaceholderText('任务名称，创建实际目录')
        self.tags = QLineEdit('，'.join(task.get('tags', [])))
        self.tags.setPlaceholderText('多个标签用逗号分隔')
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.status.setCurrentText(task.get('status', '进行中'))
        self.due = DateButton(task.get('due_date'))
        for title, field in [('客户 / 甲方', self.client), ('任务名称 *', self.name), ('标签', self.tags),
                             ('任务状态', self.status), ('任务截止日期', self.due)]:
            form.addRow(title, field)
        form.addRow('建立日期 · 固定', label(task.get('created_date', date.today().strftime('%Y%m%d'))))
        if not task_id:
            self.todo = QLineEdit()
            self.todo.setPlaceholderText('如：整理变量字典、核对审稿意见')
            self.todo_due = DateButton()
            self.priority = priority_combo()
            form.addRow('第一项待办 *', self.todo)
            form.addRow('待办截止日期', self.todo_due)
            form.addRow('待办优先级', self.priority)
        self.notes = QPlainTextEdit(task.get('notes', ''))
        self.notes.setMaximumHeight(100)
        form.addRow('备注', self.notes)
        self.body_layout.addWidget(label('目录：客户 / 建立日期 / 任务名。修改客户或名称会同步重命名实际目录；建立日期保持不变。', True))
        self.error = label('')
        self.error.setStyleSheet('color:#A76639;')
        self.body_layout.addWidget(self.error)
        self.add_buttons('保存修改' if task_id else '创建任务', '取消')
        self.name.setFocus()

    def accept(self):
        try:
            values = dict(name=self.name.text(), client=self.client.text(), tags=self.tags.text(),
                          status=self.status.currentText(), deadline=self.due.value, notes=self.notes.toPlainText())
            if self.task_id:
                self.store.update_task(self.task_id, **values)
            else:
                self.task_id = self.store.create_task(**values, first_todo=self.todo.text(),
                    todo_deadline=self.todo_due.value, priority=self.priority.currentData())
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            return
        super().accept()


class WorkDialog(EditorDialog):
    def __init__(self, parent, store, task_id, work=None):
        super().__init__(parent, '编辑下一步工作' if work else '新增下一步工作', size=(620, 620))
        self.store, self.task_id, self.work = store, task_id, work
        work = work or {}
        form = QFormLayout()
        self.body_layout.addLayout(form)
        self.name = QLineEdit(work.get('text', ''))
        self.priority = priority_combo(work.get('priority', 'normal'))
        self.due = DateButton(work.get('due_date'))
        form.addRow('下一步工作 *', self.name)
        form.addRow('优先级', self.priority)
        form.addRow('截止日期', self.due)
        self.files = QListWidget()
        for f in store.files(task_id):
            item = QListWidgetItem(f['original_name'])
            item.setData(Qt.UserRole, f['id'])
            item.setCheckState(Qt.Checked if f['id'] in work.get('file_ids', []) else Qt.Unchecked)
            self.files.addItem(item)
        self.body_layout.addWidget(label('关联文件 · 可取消关联，完成状态由你手动确认', True))
        self.body_layout.addWidget(self.files)
        self.error = label('')
        self.error.setStyleSheet('color:#A76639;')
        self.body_layout.addWidget(self.error)
        self.add_buttons('保存', '取消')

    def accept(self):
        try:
            ids = [self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())
                   if self.files.item(i).checkState() == Qt.Checked]
            if self.work:
                self.store.update_todo(self.work['id'], text=self.name.text(), priority=self.priority.currentData(),
                                       due_date=self.due.value, file_ids=ids)
            else:
                self.store.add_todo(self.task_id, self.name.text(), self.priority.currentData(), self.due.value, ids)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            return
        super().accept()


class ReceiveDialog(EditorDialog):
    def __init__(self, parent, store, filenames, task_id=None, archive=False):
        super().__init__(parent, '归档收件材料' if archive else '接收新材料', size=(760, 650))
        self.result_data = None
        self.archive = archive
        self.body_layout.addWidget(label('确认归属、文件分类和下一步工作。外部源文件保留；收件箱中的受管副本在归档时实际移动。', True))
        self.target = QComboBox()
        if not archive:
            self.target.addItem('暂存到未分类收件箱', None)
        for task in store.tasks():
            self.target.addItem(task['client'] + ' / ' + task['name'], task['id'])
        if task_id:
            self.target.setCurrentIndex(self.target.findData(task_id))
        self.body_layout.addWidget(self.target)
        self.categories = []
        listing = table(['文件', '归入分类'])
        listing.setRowCount(len(filenames))
        for i, name in enumerate(filenames):
            listing.setItem(i, 0, cell(name))
            combo = QComboBox()
            combo.addItems(CATEGORIES)
            if Path(name).suffix.lower() in ('.png', '.jpg', '.jpeg', '.svg', '.tif', '.tiff'):
                combo.setCurrentText('图表')
            elif Path(name).suffix.lower() in ('.csv', '.xlsx', '.xls'):
                combo.setCurrentText('原始数据')
            listing.setCellWidget(i, 1, combo)
            self.categories.append(combo)
        self.body_layout.addWidget(listing)
        self.make_todo = QCheckBox('同时建立下一步工作（同名待办复用，保留原完成状态）')
        self.body_layout.addWidget(self.make_todo)
        self.todo = QLineEdit()
        self.todo.setPlaceholderText('如：核对第二轮审稿意见')
        self.body_layout.addWidget(self.todo)
        row = QHBoxLayout()
        self.priority = priority_combo()
        self.due = DateButton()
        row.addWidget(self.priority)
        row.addWidget(self.due)
        self.body_layout.addLayout(row)
        self.error = label('')
        self.error.setStyleSheet('color:#A76639;')
        self.body_layout.addWidget(self.error)
        self.add_buttons('确认归档' if archive else '确认接收', '取消')

    def accept(self):
        task_id = self.target.currentData()
        if self.archive and task_id is None:
            self.error.setText('请先新建稿件任务，再归档材料。')
            return
        if self.make_todo.isChecked() and (task_id is None or not self.todo.text().strip()):
            self.error.setText('建立待办时，请选择稿件任务并填写下一步工作。')
            return
        self.result_data = dict(task_id=task_id, categories=[c.currentText() for c in self.categories],
                               todo_text=self.todo.text().strip() if self.make_todo.isChecked() else '',
                               deadline=self.due.value, priority=self.priority.currentData())
        super().accept()


class FileWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.succeeded.emit(self.operation())
        except Exception as exc:
            self.failed.emit(str(exc))


class ManuscriptPage(QWidget):
    changed = Signal()

    def __init__(self, parent=None, store=None):
        super().__init__(parent)
        self.store = store
        self.worker = None
        self.task_id = None
        self.signature = None
        self.mode = 'tasks'
        self.setObjectName('manuscriptPage')
        self.setStyleSheet('''QWidget#manuscriptPage{background:#F5F8F5;}
            QLabel#manuscriptTitle{font-size:27px;font-weight:600;color:#193C2C;}
            QPushButton:checked{background:#DDF2E4;color:#195D42;border-color:#B8DECA;font-weight:600;}
            QPushButton#primary{background:#277453;color:white;border-color:#277453;}
            QTableWidget{background:white;border:1px solid #DEE8DF;border-radius:8px;}
            QTableWidget::item{padding:7px;}
            QHeaderView::section{background:#ECF6EF;color:#637668;padding:10px;border:0;}
        ''')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)
        heading = QHBoxLayout()
        title = label('稿件工作空间')
        title.setObjectName('manuscriptTitle')
        heading.addWidget(title, 1)
        heading.addWidget(button('刷新', self.refresh))
        self.settings_button = button('工作空间设置', self.choose_root)
        heading.addWidget(self.settings_button)
        self.import_button = button('导入材料', self.receive)
        heading.addWidget(self.import_button)
        self.new_button = button('＋ 新建任务', self.new_task, True)
        heading.addWidget(self.new_button)
        outer.addLayout(heading)
        self.location = label('', True)
        outer.addWidget(self.location)
        self.message = label('')
        self.message.setStyleSheet('color:#96632C;')
        outer.addWidget(self.message)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        setup = QWidget()
        setup_box = QVBoxLayout(setup)
        setup_box.addStretch()
        setup_box.addWidget(label('选择本地工作空间，开始管理新稿件任务。'))
        setup_box.addWidget(label('只接收你新建或主动导入的材料，不扫描或整理历史文稿。', True))
        setup_box.addWidget(button('选择工作目录', self.choose_root, True))
        setup_box.addStretch()
        self.pages.addWidget(setup)
        overview = QWidget()
        box = QVBoxLayout(overview)
        box.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self.tasks_button = button('稿件任务', lambda: self.set_mode('tasks'))
        self.inbox_button = button('未分类收件箱', lambda: self.set_mode('inbox'))
        self.tasks_button.setCheckable(True)
        self.inbox_button.setCheckable(True)
        nav.addWidget(self.tasks_button)
        nav.addWidget(self.inbox_button)
        nav.addStretch()
        nav.addWidget(button('操作记录', self.show_log))
        box.addLayout(nav)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索客户、任务、标签、文件名或下一步工作')
        self.search.setClearButtonEnabled(True)
        self.client_filter = QComboBox()
        self.status_filter = QComboBox()
        self.status_filter.addItems(['全部状态', *STATUSES])
        self.tag_filter = QLineEdit()
        self.tag_filter.setPlaceholderText('标签（逗号组合）')
        for field in (self.search, self.client_filter, self.status_filter, self.tag_filter):
            filters.addWidget(field, 2 if field is self.search else 1)
        box.addLayout(filters)
        dates = QHBoxLayout()
        self.after, self.before = DateButton(), DateButton()
        dates.addWidget(label('任务截止日期'))
        dates.addWidget(self.after)
        dates.addWidget(label('至'))
        dates.addWidget(self.before)
        self.pending = QCheckBox('仅有未完成待办')
        dates.addWidget(self.pending)
        dates.addStretch()
        dates.addWidget(button('清除筛选', self.clear_filters))
        self.archive_button = button('归档选中材料', self.archive_selected, True)
        dates.addWidget(self.archive_button)
        box.addLayout(dates)
        self.tasks_table = table(['任务 / 客户', '标签', '状态', '截止日期', '待办', '文件'])
        self.tasks_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tasks_table.cellDoubleClicked.connect(lambda row, col: self.open_task(self.tasks_table.item(row, 0).data(Qt.UserRole)))
        box.addWidget(self.tasks_table)
        self.inbox_table = table(['材料文件', '接收时间', '大小', '状态'])
        self.inbox_table.cellDoubleClicked.connect(lambda row, col: self.open_file(self.inbox_table.item(row, 0).data(Qt.UserRole)))
        box.addWidget(self.inbox_table)
        self.summary = label('', True)
        box.addWidget(self.summary)
        self.pages.addWidget(overview)
        detail = QWidget()
        detail_box = QVBoxLayout(detail)
        detail_box.setContentsMargins(0, 0, 0, 0)
        tools = QHBoxLayout()
        tools.addWidget(button('← 返回任务表', self.show_overview))
        self.detail_title = label('')
        self.detail_title.setStyleSheet('font-size:20px;font-weight:600;')
        tools.addWidget(self.detail_title, 1)
        tools.addWidget(button('编辑任务', self.edit_task))
        tools.addWidget(button('打开文件夹', self.open_folder))
        detail_box.addLayout(tools)
        self.detail_meta = label('', True)
        detail_box.addWidget(self.detail_meta)
        categories = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItems(['全部文件', *CATEGORIES])
        self.file_search = QLineEdit()
        self.file_search.setPlaceholderText('搜索当前任务文件')
        categories.addWidget(self.category)
        categories.addWidget(self.file_search, 1)
        categories.addWidget(button('新增待办', self.add_work, True))
        categories.addWidget(button('操作记录', lambda: self.show_log(self.task_id)))
        detail_box.addLayout(categories)
        self.file_table = table(['文件', '分类', '接收时间', '状态'])
        self.file_table.cellDoubleClicked.connect(lambda row, col: self.preview_file(self.file_table.item(row, 0).data(Qt.UserRole)))
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.file_menu)
        detail_box.addWidget(self.file_table, 2)
        detail_box.addWidget(label('下一步工作 · 双击修改，勾选完成；新增工作不会撤回已完成的事项。', True))
        self.work_table = table(['下一步工作', '优先级', '截止日期', '关联文件'])
        self.work_table.itemChanged.connect(self.work_changed)
        self.work_table.cellDoubleClicked.connect(lambda row, col: self.edit_work(self.work_table.item(row, 0).data(Qt.UserRole)))
        detail_box.addWidget(self.work_table, 1)
        self.detail_path = label('', True)
        detail_box.addWidget(self.detail_path)
        self.pages.addWidget(detail)
        self.search.textChanged.connect(self.refresh)
        self.tag_filter.textChanged.connect(self.refresh)
        self.client_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.pending.toggled.connect(self.refresh)
        self.after.changed.connect(self.refresh)
        self.before.changed.connect(self.refresh)
        self.category.currentIndexChanged.connect(self.refresh_detail)
        self.file_search.textChanged.connect(self.refresh_detail)
        if store is None:
            try:
                self.store = configured_workspace()
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.message.setText(str(exc))
        self.refresh()

    def fail(self, exc):
        self.message.setText(str(exc))

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def run_files(self, operation):
        if self.busy():
            self.message.setText('正在整理材料，请等待当前操作完成。')
            return
        self.message.setText('正在复制、校验并整理材料…')
        self.pages.setEnabled(False)
        for control in (self.new_button, self.import_button, self.settings_button):
            control.setEnabled(False)
        worker = FileWorker(operation, self)
        self.worker = worker
        worker.succeeded.connect(self.received)
        worker.failed.connect(self.fail)
        worker.finished.connect(self.worker_finished)
        worker.start()

    def received(self, result):
        if isinstance(result, dict):
            self.message.setText(f'已接收 {result["received"]} 个新文件；复用 {len(result["duplicates"])} 个重复材料。源文件保留。')
        else:
            self.message.setText('材料已归档，文件关联和下一步工作已同步。')

    def worker_finished(self):
        worker=self.worker
        self.worker=None
        if worker:worker.deleteLater()
        self.pages.setEnabled(True)
        for control in (self.new_button, self.import_button, self.settings_button):
            control.setEnabled(True)
        self.refresh()
        if self.task_id:
            self.refresh_detail()
        self.changed.emit()

    def choose_root(self):
        if self.busy():
            return
        root = QFileDialog.getExistingDirectory(native_owner(self), '选择本地科研工作空间', str(self.store.root) if self.store else '')
        if not root:
            return
        try:
            self.store = enable_workspace(root)
            self.task_id = None
            self.show_overview()
            self.message.setText('工作空间已启用。历史文件未被扫描或移动。')
            self.changed.emit()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fail(exc)

    def clear_filters(self):
        self.search.clear()
        self.tag_filter.clear()
        self.client_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self.pending.setChecked(False)
        self.after.set_date(None)
        self.before.set_date(None)
        self.refresh()

    def set_mode(self, mode):
        self.mode = mode
        self.refresh()

    def show_overview(self):
        self.task_id = None
        self.refresh()

    def new_task(self):
        if not self.store:
            self.choose_root()
            if not self.store:
                return
        dialog = TaskDialog(self, self.store)
        try:
            if dialog.exec() == QDialog.Accepted:
                self.open_task(dialog.task_id)
                self.changed.emit()
        finally:
            dialog.deleteLater()

    def edit_task(self):
        dialog = TaskDialog(self, self.store, self.task_id)
        try:
            if dialog.exec() == QDialog.Accepted:
                self.refresh_detail()
                self.changed.emit()
        finally:
            dialog.deleteLater()

    def refresh(self, *args):
        self.new_button.setEnabled(not self.busy())
        self.import_button.setEnabled(self.store is not None and not self.busy())
        if not self.store:
            self.pages.setCurrentIndex(0)
            self.location.setText('尚未启用本地工作空间')
            return
        self.location.setText(str(self.store.root))
        if self.task_id:
            self.refresh_detail()
            return
        try:
            all_tasks = self.store.tasks()
            clients = ['全部客户', *sorted({t['client'] for t in all_tasks})]
            if [self.client_filter.itemText(i) for i in range(self.client_filter.count())] != clients:
                old = self.client_filter.currentText()
                self.client_filter.blockSignals(True)
                self.client_filter.clear()
                self.client_filter.addItems(clients)
                self.client_filter.setCurrentText(old if old in clients else clients[0])
                self.client_filter.blockSignals(False)
            tags = [s.strip() for s in self.tag_filter.text().replace('，', ',').split(',') if s.strip()]
            tasks = self.store.tasks(query=self.search.text().strip(),
                client=self.client_filter.currentText() if self.client_filter.currentIndex() > 0 else '',
                status=self.status_filter.currentText() if self.status_filter.currentIndex() > 0 else '',
                due_before=self.before.value, due_after=self.after.value, pending_only=self.pending.isChecked())
            tasks = [t for t in tasks if all(tag in t['tags'] for tag in tags)]
            self.tasks_table.setRowCount(len(tasks))
            for i, task in enumerate(tasks):
                values = [task['name'] + '\n' + task['client'], ' · '.join(task['tags']), task['status'],
                          task['due_date'] or '—', task['pending_count'], task['file_count']]
                for j, value in enumerate(values):
                    self.tasks_table.setItem(i, j, cell(value, task['id']))
            inbox = [f for f in self.store.files() if self.search.text().casefold() in f['original_name'].casefold()]
            self.populate_files(self.inbox_table, inbox, inbox=True)
            self.tasks_button.setText(f'稿件任务  {len(all_tasks)}')
            self.inbox_button.setText(f'未分类收件箱  {len(self.store.files())}')
            is_inbox = self.mode == 'inbox'
            self.tasks_button.setChecked(not is_inbox)
            self.inbox_button.setChecked(is_inbox)
            self.tasks_table.setVisible(not is_inbox)
            self.inbox_table.setVisible(is_inbox)
            self.archive_button.setVisible(is_inbox)
            self.summary.setText(f'共 {len(inbox) if is_inbox else len(tasks)} 项'+('；选中材料后点击“归档选中材料”。' if is_inbox else '；双击任务查看文件与待办。'))
            self.pages.setCurrentIndex(1)
            self.signature = self.store.signature()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fail(exc)

    def refresh_from_disk(self):
        if self.store and not self.busy():
            try:
                if self.store.signature() != self.signature:
                    self.refresh()
            except OSError as exc:
                self.fail(exc)

    def open_task(self, task_id):
        if not self.store:
            self.message.setText('请先恢复稿件工作空间。')
            return
        self.task_id = task_id
        self.category.setCurrentIndex(0)
        self.file_search.clear()
        self.refresh_detail()

    def populate_files(self, listing, files, inbox=False):
        listing.setRowCount(len(files))
        for i, f in enumerate(files):
            exists = self.store.inside(f['path']).is_file()
            values = [f['original_name'], datetime.fromisoformat(f['received_at']).astimezone().strftime('%Y-%m-%d %H:%M'), f'{f["size"]:,} B', '可用' if exists else '已丢失'] if inbox else [f['original_name'], f['category'], datetime.fromisoformat(f['received_at']).astimezone().strftime('%Y-%m-%d %H:%M'), '可用' if exists else '已丢失']
            for j, value in enumerate(values):
                listing.setItem(i, j, cell(value, f['id']))

    def refresh_detail(self, *args):
        if not self.store or not self.task_id:
            return
        try:
            task = self.store.task(self.task_id)
            self.detail_title.setText(task['name'])
            self.detail_meta.setText(' · '.join([task['client'], task['status'], '截止 '+(task['due_date'] or '未设置'), *task['tags']]))
            self.detail_path.setText(str(self.store.inside(task['directory'])))
            files = self.store.files(self.task_id, self.category.currentText() if self.category.currentIndex() > 0 else None)
            files = [f for f in files if self.file_search.text().casefold() in f['original_name'].casefold()]
            self.populate_files(self.file_table, files)
            works = [w for w in self.store.todos(self.task_id) if not w['deleted']]
            self.work_table.blockSignals(True)
            try:
                self.work_table.setRowCount(len(works))
                for i, work in enumerate(works):
                    name = cell(work['text'], work['id'])
                    name.setFlags(name.flags() | Qt.ItemIsUserCheckable)
                    name.setCheckState(Qt.Checked if work['completed'] else Qt.Unchecked)
                    self.work_table.setItem(i, 0, name)
                    for j, value in enumerate([{'high': '高', 'normal': '普通', 'low': '低'}[work['priority']], work['due_date'] or '—', len(work['file_ids'])], 1):
                        self.work_table.setItem(i, j, cell(value, work['id']))
            finally:
                self.work_table.blockSignals(False)
            self.pages.setCurrentIndex(2)
            self.signature = self.store.signature()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fail(exc)

    def add_work(self):
        self.edit_work(None)

    def edit_work(self, work_id):
        work = next((w for w in self.store.todos(self.task_id) if w['id'] == work_id), None)
        dialog = WorkDialog(self, self.store, self.task_id, work)
        try:
            if dialog.exec() == QDialog.Accepted:
                self.refresh_detail()
                self.changed.emit()
        finally:
            dialog.deleteLater()

    def work_changed(self, item):
        if item.column() != 0:
            return
        try:
            self.store.update_todo(item.data(Qt.UserRole), completed=item.checkState() == Qt.Checked)
            self.changed.emit()
            self.signature = self.store.signature()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fail(exc)
            self.refresh_detail()

    def receive(self):
        if not self.store or self.busy():
            return
        paths, _ = QFileDialog.getOpenFileNames(native_owner(self), '选择新材料；源文件会保留')
        if not paths:
            return
        dialog = ReceiveDialog(self, self.store, [Path(p).name for p in paths], self.task_id)
        try:
            if dialog.exec() == QDialog.Accepted:
                values = dialog.result_data
                self.run_files(lambda: self.store.receive_files(paths, **values))
        finally:
            dialog.deleteLater()

    def archive_selected(self):
        ids = [self.inbox_table.item(i.row(), 0).data(Qt.UserRole) for i in self.inbox_table.selectionModel().selectedRows()]
        if not ids:
            self.message.setText('请先选中收件材料。')
            return
        files = {f['id']: f for f in self.store.files()}
        dialog = ReceiveDialog(self, self.store, [files[i]['original_name'] for i in ids], archive=True)
        try:
            if dialog.exec() == QDialog.Accepted:
                values = dialog.result_data
                self.run_files(lambda: self.store.archive_files(ids, **values))
        finally:
            dialog.deleteLater()

    def open_folder(self):
        try:
            path = self.store.inside(self.store.task(self.task_id)['directory'])
            if not path.is_dir():
                raise ValueError('任务目录已被外部移动，请恢复原目录后重试。')
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise OSError('无法打开任务文件夹。')
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fail(exc)

    def open_file(self, file_id):
        try:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.file_path(file_id)))):
                raise OSError('无法使用系统默认程序打开文件。')
        except FileNotFoundError:
            self.relocate(file_id)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fail(exc)

    def relocate(self, file_id):
        source, _ = QFileDialog.getOpenFileName(native_owner(self), '文件已丢失：选择原材料，内容校验通过后重新关联')
        if source:
            try:
                self.store.relocate_file(file_id, source)
                self.refresh()
                self.changed.emit()
                self.message.setText('文件已重新关联；原任务、分类及待办状态保留。')
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.fail(exc)

    def file_menu(self, point):
        item = self.file_table.itemAt(point)
        if item is None:
            return
        fid = self.file_table.item(item.row(), 0).data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction('预览', lambda: self.preview_file(fid))
        menu.addAction('用系统默认程序打开', lambda: self.open_file(fid))
        menu.addAction('更改文件分类', lambda: self.reclassify(fid))
        menu.addAction('重新关联丢失文件', lambda: self.relocate(fid))
        menu.exec(self.file_table.viewport().mapToGlobal(point))

    def reclassify(self, file_id):
        dialog = EditorDialog(self, '更改文件分类', size=(500, 260))
        combo = QComboBox()
        combo.addItems(CATEGORIES)
        dialog.body_layout.addWidget(combo)
        dialog.body_layout.addWidget(label('文件将实际移动到当前任务的对应分类目录。', True))
        dialog.add_buttons('确认移动', '取消')
        try:
            if dialog.exec() == QDialog.Accepted:
                category=combo.currentText()
                self.run_files(lambda: self.store.archive_files([file_id], self.task_id, [category]))
        finally:
            dialog.deleteLater()

    def preview_file(self, file_id):
        try:
            path = self.store.file_path(file_id)
        except FileNotFoundError:
            self.relocate(file_id)
            return
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.fail(exc)
            return
        dialog = EditorDialog(self, path.name, size=(920, 720))
        dialog.body_layout.addWidget(button('用系统默认程序打开完整文件', lambda: self.open_file(file_id)))
        try:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                image = QLabel()
                image.setPixmap(pixmap.scaled(840, 520, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                image.setAlignment(Qt.AlignCenter)
                dialog.body_layout.addWidget(image)
            elif path.suffix.lower() in ('.txt', '.csv', '.md', '.json', '.log', '.docx'):
                if path.suffix.lower() == '.docx':
                    with zipfile.ZipFile(path) as archive:
                        info = archive.getinfo('word/document.xml')
                        if info.file_size > 20 * 1024 * 1024:
                            raise ValueError('文档较大，请使用系统程序打开。')
                        root = ET.fromstring(archive.read(info))
                        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                        content = '\n'.join(''.join(p.itertext()) for p in root.iter(ns+'p'))
                else:
                    with path.open('r', encoding='utf-8', errors='replace') as stream:
                        content = stream.read(500000)
                editor = QPlainTextEdit(content[:500000])
                editor.setReadOnly(True)
                dialog.body_layout.addWidget(editor)
                dialog.body_layout.addWidget(label('文字预览；完整格式请使用上方系统打开。', True))
            else:
                dialog.body_layout.addWidget(label('此格式使用系统默认程序打开，可保留完整排版和交互。'))
            dialog.add_buttons('关闭', '返回')
            dialog.exec()
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            self.fail(exc)
        finally:
            dialog.deleteLater()

    def show_log(self, task_id=None):
        # QPushButton.clicked supplies a bool when connected directly.
        if isinstance(task_id, bool):
            task_id = None
        if not self.store:
            return
        dialog = EditorDialog(self, '操作记录', size=(900, 650))
        listing = table(['操作', '时间（UTC）', '详情'])
        events = self.store.events(task_id)
        listing.setRowCount(len(events))
        for i, event in enumerate(events):
            for j, value in enumerate([event['kind'], event['created_at'][:19], json.dumps(event['details'], ensure_ascii=False)]):
                listing.setItem(i, j, cell(value, event['id']))
        dialog.body_layout.addWidget(listing)
        error = label('', True)
        dialog.body_layout.addWidget(error)
        def undo():
            row = listing.currentRow()
            if row < 0 or events[row]['kind'] != '归档材料':
                error.setText('请选择一次“归档材料”操作。')
                return
            try:
                self.store.undo_archive(events[row]['id'])
                self.refresh()
                self.changed.emit()
                dialog.accept()
            except (ValueError, OSError, sqlite3.Error) as exc:
                error.setText(str(exc))
        dialog.body_layout.addWidget(button('撤销所选归档', undo))
        dialog.body_layout.addWidget(label('撤销会检查文件位置和关联；存在后续移动、重名或关联待办时会保留现状并提示。', True))
        dialog.add_buttons('关闭', '返回')
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()
