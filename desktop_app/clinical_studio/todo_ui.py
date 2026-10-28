"""Compact document todos: one name, one priority, one optional due date."""
from datetime import date,timedelta
from PySide6.QtCore import Qt,QDate,Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QComboBox,QFrame,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMenu,QCalendarWidget,QWidgetAction,QDialog)
from .todos import TodoStore,PRIORITIES
from .resizable_fields import keep_user_height
from .editor_dialogs import EditorDialog,native_owner


def date_text(value):
    if not value:return '未设日期'
    d=date.fromisoformat(value);today=date.today()
    prefix='今天 · ' if d==today else '明天 · ' if d==today+timedelta(days=1) else ''
    return prefix+(f'{d.year}年' if d.year!=today.year else '')+f'{d.month}月{d.day}日'


class DateButton(QPushButton):
    changed=Signal(object)
    def __init__(self,value=None,parent=None):
        super().__init__(parent);self.value=value;self.setObjectName('todoDate');self.setMinimumHeight(34);self.update_text();self.clicked.connect(self.pick)
    def update_text(self):self.setText(date_text(self.value)+'  ⌄');self.setToolTip(self.value or '可不设置截止日期')
    def set_date(self,value):
        self.value=value;self.update_text();self.changed.emit(value)
    def pick(self):
        menu=QMenu(native_owner(self))
        menu.addAction('今天',lambda:self.set_date(date.today().isoformat()))
        menu.addAction('明天',lambda:self.set_date((date.today()+timedelta(days=1)).isoformat()))
        calendar=QCalendarWidget();calendar.setGridVisible(False)
        d=date.fromisoformat(self.value) if self.value else date.today();calendar.setSelectedDate(QDate(d.year,d.month,d.day))
        action=QWidgetAction(menu);action.setDefaultWidget(calendar);menu.addAction(action)
        calendar.clicked.connect(lambda d:(self.set_date(d.toString('yyyy-MM-dd')),menu.close()))
        menu.addSeparator();menu.addAction('不设日期',lambda:self.set_date(None));self.date_menu=menu
        try:menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
        finally:self.date_menu=None;menu.deleteLater()


def priority_combo(value='normal'):
    combo=QComboBox();combo.setObjectName('todoPriority');combo.setMinimumHeight(34)
    for key,label in PRIORITIES.items():combo.addItem(label,key)
    combo.setCurrentIndex(combo.findData(value));return combo


class TodoDialog(EditorDialog):
    def __init__(self,parent,task=None):
        super().__init__(parent,'修改待办' if task else '新增待办',size=(580,390));task=task or {};self.result_task=None
        self.name=QLineEdit(task.get('name',''));self.name.setPlaceholderText('姓名 / 文档名称');self.name.setMaxLength(300);self.name.setMinimumHeight(38)
        self.body_layout.addWidget(QLabel('谁的文档 *'));self.body_layout.addWidget(self.name)
        row=QHBoxLayout();self.body_layout.addLayout(row)
        self.priority=priority_combo(task.get('priority','normal'));self.due=DateButton(task.get('due_date'))
        for title,control in [('优先级',self.priority),('截止日期',self.due)]:
            box=QVBoxLayout();box.addWidget(QLabel(title));box.addWidget(control);row.addLayout(box,1)
        self.error=QLabel();self.error.setStyleSheet('color:#A76639;');self.body_layout.addWidget(self.error)
        self.add_buttons('保存修改' if task else '添加待办','取消');self.name.setFocus()
    def accept(self):
        data=dict(name=self.name.text().strip(),priority=self.priority.currentData(),due_date=self.due.value)
        try:TodoStore.validate(data)
        except ValueError as exc:self.error.setText(str(exc));self.name.setFocus();return
        self.result_task=data;super().accept()


class TodoTable(QTableWidget):
    def __init__(self):
        super().__init__(0,5);self.setHorizontalHeaderLabels(['完成','谁的文档','优先级','截止日期','操作'])
        self.verticalHeader().hide();self.setShowGrid(False);self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows);self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        self.horizontalHeader().setFixedHeight(42);self.verticalHeader().setDefaultSectionSize(58)
        for col,width in [(0,56),(2,132),(3,184),(4,108)]:self.setColumnWidth(col,width)
        self.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.horizontalHeader().setMinimumSectionSize(46)
        self.empty=QLabel(self.viewport());self.empty.setTextFormat(Qt.PlainText);self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet('color:#789187;font-size:14px;background:white;');self.empty.setAttribute(Qt.WA_TransparentForMouseEvents)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        if hasattr(self,'empty'):self.empty.setGeometry(self.viewport().rect().adjusted(12,8,-12,-8))


class TodoPage(QWidget):
    changed=Signal()
    def __init__(self,parent=None,store=None):
        super().__init__(parent);self.store=store or TodoStore();self.completed=False;self.editing=False;self.signature=None;self.last_deleted=None;self.dialog=None
        self.setObjectName('todoPage');self.setStyleSheet('''
            QWidget#todoPage{background:#F5F9F6;color:#153F35;}
            QLabel#todoHeading{font-size:30px;font-weight:700;color:#153F35;}
            QLabel#todoMuted{font-size:12px;color:#789187;}
            QFrame#todoCard{background:white;border:1px solid #DFEAE3;border-radius:11px;}
            QPushButton{border:1px solid #DFEAE3;background:white;border-radius:8px;padding:6px 12px;color:#335F4B;font-size:13px;}
            QPushButton#todoPrimary{background:#087B59;color:white;border-color:#087B59;font-weight:600;}
            QPushButton#todoFilter{background:transparent;border:0;color:#789187;}
            QPushButton#todoFilter:checked{background:white;color:#153F35;font-weight:600;}
            QPushButton#todoDate{background:white;padding:4px 8px;text-align:left;}
            QLineEdit{background:white;border:1px solid #DFEAE3;border-radius:7px;padding:6px 10px;font-size:13px;min-height:20px;}
            QTableWidget{border:0;background:white;alternate-background-color:#FBFDFC;font-size:13px;}
            QTableWidget::item{padding:8px;border-bottom:1px solid #EDF2EE;color:#153F35;}
            QHeaderView::section{background:#EFF6F1;border:0;padding:8px;color:#789187;font-size:12px;}
            QComboBox#todoPriority{border:1px solid #DFEAE3;background:white;border-radius:7px;padding:4px 10px;color:#507963;font-size:12px;}
        ''')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(18)
        head=QHBoxLayout();titles=QVBoxLayout();heading=QLabel('待办事项');heading.setObjectName('todoHeading');titles.addWidget(heading)
        subtitle=QLabel('记下谁的文档、优先级和截止日期。');subtitle.setObjectName('todoMuted');titles.addWidget(subtitle);head.addLayout(titles,1)
        self.new_button=QPushButton('＋ 新增待办');self.new_button.setObjectName('todoPrimary');self.new_button.setFixedHeight(42);self.new_button.clicked.connect(lambda:self.open_editor());head.addWidget(self.new_button);layout.addLayout(head)
        tools=QHBoxLayout();self.pending_button=QPushButton();self.done_button=QPushButton()
        for button,done in [(self.pending_button,False),(self.done_button,True)]:
            button.setObjectName('todoFilter');button.setCheckable(True);button.setFixedHeight(36);button.clicked.connect(lambda _,d=done:self.set_filter(d));tools.addWidget(button)
        tools.addStretch();self.search=QLineEdit();self.search.setPlaceholderText('搜索姓名或文档名称');self.search.setClearButtonEnabled(True);self.search.setMaximumWidth(300);self.search.textChanged.connect(lambda:self.refresh());tools.addWidget(self.search);layout.addLayout(tools)
        quick=QFrame();quick.setObjectName('todoCard');line=QHBoxLayout(quick);line.setContentsMargins(16,10,16,12);line.setSpacing(14)
        self.name=QLineEdit();self.name.setMaxLength(300);self.name.setPlaceholderText('姓名 / 文档名称');self.name.returnPressed.connect(self.add_inline)
        self.priority=priority_combo();self.due=DateButton();self.priority.setFixedWidth(110);self.due.setMinimumWidth(160)
        for title,control,stretch in [('谁的文档',self.name,1),('优先级',self.priority,0),('截止日期',self.due,0)]:
            box=QVBoxLayout();box.setSpacing(5);label=QLabel(title);label.setObjectName('todoMuted');box.addWidget(label);box.addWidget(control);line.addLayout(box,stretch)
        self.add_button=QPushButton('＋ 添加');self.add_button.setObjectName('todoPrimary');self.add_button.setMinimumHeight(34);self.add_button.clicked.connect(self.add_inline);line.addWidget(self.add_button,0,Qt.AlignBottom);layout.addWidget(quick)
        card=QFrame();card.setObjectName('todoCard');card_box=QVBoxLayout(card);card_box.setContentsMargins(1,1,1,1);card_box.setSpacing(0)
        self.table=TodoTable();self.table.itemChanged.connect(self.item_changed);card_box.addWidget(self.table)
        foot=QHBoxLayout();foot.setContentsMargins(14,6,14,6);self.count=QLabel();self.count.setObjectName('todoMuted');foot.addWidget(self.count);foot.addStretch();hint=QLabel('勾选方框即可标记完成');hint.setObjectName('todoMuted');foot.addWidget(hint);card_box.addLayout(foot);layout.addWidget(card)
        status=QHBoxLayout();self.message=QLabel();self.message.setWordWrap(True);self.message.setObjectName('todoMuted');status.addWidget(self.message,1);self.undo=QPushButton('撤销删除');self.undo.clicked.connect(self.undo_delete);self.undo.hide();status.addWidget(self.undo);layout.addLayout(status);layout.addStretch()
        self.refresh()
    def file_signature(self):
        try:s=self.store.path.stat();return (s.st_mtime_ns,s.st_size)
        except FileNotFoundError:return None
    def refresh_from_disk(self):
        if self.file_signature()!=self.signature:self.refresh()
    def set_filter(self,completed):self.completed=completed;self.refresh()
    def action(self,operation,message=''):
        try:result=operation()
        except (ValueError,OSError) as exc:self.message.setText('保存失败：'+str(exc));return False
        self.message.setText(message);self.refresh();self.changed.emit();return True
    def add_inline(self):
        if self.action(lambda:self.store.add(self.name.text(),self.priority.currentData(),self.due.value),'已添加待办。'):
            self.name.clear();self.set_filter(False);self.name.setFocus()
    def open_editor(self,task=None):
        dialog=TodoDialog(self,task);self.dialog=dialog
        try:
            if dialog.exec()==QDialog.Accepted:
                data=dialog.result_task
                self.action(lambda:self.store.update(task['id'],**data) if task else self.store.add(**data),'已保存待办。')
        finally:self.dialog=None;dialog.deleteLater()
    def item_changed(self,item):
        if self.editing:return
        task_id=item.data(Qt.UserRole)
        if item.column()==0:self.action(lambda:self.store.update(task_id,completed=item.checkState()==Qt.Checked),'已更新完成状态。')
        elif item.column()==1:
            if not self.action(lambda:self.store.update(task_id,name=item.text()),'已修改文档名称。'):self.refresh()
    def delete(self,task_id):
        if self.action(lambda:self.store.delete(task_id),'已删除待办。可以撤销。'):self.last_deleted=task_id;self.undo.show()
    def undo_delete(self):
        if self.last_deleted and self.action(lambda:self.store.restore(self.last_deleted),'已恢复待办。'):self.last_deleted=None;self.undo.hide()
    def refresh(self):
        self.editing=True;self.table.blockSignals(True)
        try:
            all_tasks=[t for t in self.store.read() if not t.get('deleted')];tasks=self.store.visible(self.completed,self.search.text().strip());self.signature=self.file_signature()
            self.pending_button.setText(f'未完成  {sum(not t["completed"] for t in all_tasks)}');self.done_button.setText(f'已完成  {sum(t["completed"] for t in all_tasks)}')
            self.pending_button.setChecked(not self.completed);self.done_button.setChecked(self.completed)
            for row in range(self.table.rowCount()):
                for col in (2,3,4):
                    old=self.table.cellWidget(row,col)
                    if old:old.hide()
            self.table.clearContents();self.table.setRowCount(len(tasks))
            for row,task in enumerate(tasks):
                check=QTableWidgetItem();check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable);check.setCheckState(Qt.Checked if task['completed'] else Qt.Unchecked);check.setData(Qt.UserRole,task['id']);self.table.setItem(row,0,check)
                name=QTableWidgetItem(task['name']);name.setData(Qt.UserRole,task['id']);name.setToolTip(task['name']);self.table.setItem(row,1,name)
                combo=priority_combo(task['priority']);combo.setMaximumWidth(100);combo.currentIndexChanged.connect(lambda _,i=task['id'],c=combo:self.action(lambda:self.store.update(i,priority=c.currentData())))
                colors={'high':('#FBEEE7','#B36A42'),'normal':('#ECF5EF','#507963'),'low':('#F0F3F1','#8A9B90')};bg,fg=colors[task['priority']];combo.setStyleSheet(f'QComboBox{{background:{bg};color:{fg};}}')
                cell=QWidget();box=QHBoxLayout(cell);box.setContentsMargins(8,0,8,0);box.addWidget(combo);box.addStretch();self.table.setCellWidget(row,2,cell)
                due=DateButton(task['due_date']);due.setStyleSheet('border:0;background:transparent;'+('color:#A16A35;' if task['due_date'] and task['due_date']<=date.today().isoformat() and not task['completed'] else ''))
                due.changed.connect(lambda value,i=task['id']:self.action(lambda:self.store.update(i,due_date=value)))
                self.table.setCellWidget(row,3,due)
                actions=QWidget();buttons=QHBoxLayout(actions);buttons.setContentsMargins(2,0,2,0);buttons.setSpacing(3)
                edit=QPushButton('修改');edit.setToolTip('修改这条待办');edit.setStyleSheet('border:0;padding:4px;color:#507963;');edit.clicked.connect(lambda _,data=task:self.open_editor(data));buttons.addWidget(edit)
                remove=QPushButton('删除');remove.setToolTip('删除后可撤销');remove.setStyleSheet('border:0;padding:4px;color:#879D8D;');remove.clicked.connect(lambda _,i=task['id']:self.delete(i));buttons.addWidget(remove);self.table.setCellWidget(row,4,actions)
            self.table.setFixedHeight(keep_user_height(self.table,min(540,42+max(220,len(tasks)*58)+4)));self.count.setText(f'{len(tasks)} 项'+('已完成' if self.completed else '待办'))
            self.table.empty.setText('没有找到匹配的文档' if self.search.text().strip() else '还没有已完成的文档' if self.completed else '还没有待办文档\n\n在上方填写文档名称，即可添加。');self.table.empty.setVisible(not tasks);self.table.empty.raise_()
        except (ValueError,OSError) as exc:self.message.setText(str(exc));self.table.setRowCount(0);self.table.empty.setText('待办暂时无法读取，原文件已保留。');self.table.empty.show()
        finally:self.table.blockSignals(False);self.editing=False
