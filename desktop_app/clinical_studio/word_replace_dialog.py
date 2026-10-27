"""Explicit widget dialog: never invokes a Cocoa native message-box helper."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton


class WordReplaceDialog(QDialog):
    def __init__(self,parent,path):
        super().__init__(parent,Qt.Dialog|Qt.WindowTitleHint|Qt.WindowCloseButtonHint)
        self.setObjectName('wordReplaceDialog');self.setWindowTitle('替换 Word')
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(460);self.resize(520,245)
        self.setStyleSheet('''
            QDialog#wordReplaceDialog { background:#F5F8F5; }
            QDialog#wordReplaceDialog QLabel { color:#193C2C; background:transparent; font-size:14px; }
            QDialog#wordReplaceDialog QLabel#replaceHeading { font-size:19px; font-weight:600; }
            QDialog#wordReplaceDialog QPushButton { background:white; color:#193C2C; border:1px solid #C6DEC9; border-radius:7px; padding:9px 18px; min-width:88px; }
            QDialog#wordReplaceDialog QPushButton#confirmReplace { background:#277453; color:white; border-color:#277453; }
            QDialog#wordReplaceDialog QPushButton:focus { border:2px solid #277453; }
        ''')
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(14)
        heading=QLabel('清除当前数据并导入新 Word？');heading.setObjectName('replaceHeading');layout.addWidget(heading)
        filename=QLabel('新文件：'+Path(path).name);filename.setTextFormat(Qt.PlainText);filename.setWordWrap(True);layout.addWidget(filename)
        self.message=QLabel('将清除当前 Word、已识别的表格、编辑内容及生成数据。\n选择“保留当前内容”或关闭弹窗，将不会替换。')
        self.message.setTextFormat(Qt.PlainText);self.message.setWordWrap(True);layout.addWidget(self.message)
        layout.addStretch();actions=QHBoxLayout();actions.addStretch();layout.addLayout(actions)
        self.cancel_button=QPushButton('保留当前内容');self.cancel_button.setObjectName('cancelReplace')
        self.confirm_button=QPushButton('清除并导入');self.confirm_button.setObjectName('confirmReplace')
        self.confirm_button.setAutoDefault(False);self.cancel_button.setAutoDefault(True);self.cancel_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject);self.confirm_button.clicked.connect(self.accept)
        actions.addWidget(self.cancel_button);actions.addWidget(self.confirm_button);self.cancel_button.setFocus()
