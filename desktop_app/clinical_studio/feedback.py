"""Visible, non-modal feedback shared by clipboard actions in every tool."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QLabel


def notify(owner,message,success=True):
    host=owner.window()
    # Controllers may be hidden while their controls are represented on the board.
    if not host.isVisible():
        host=QApplication.activeModalWidget() or QApplication.activeWindow() or host
    toast=getattr(host,'copy_feedback',None)
    if toast is None:
        toast=QLabel(host);toast.setObjectName('copyFeedback')
        toast.setAttribute(Qt.WA_TransparentForMouseEvents)
        toast.timer=QTimer(toast);toast.timer.setSingleShot(True);toast.timer.timeout.connect(toast.hide)
        host.copy_feedback=toast
    toast.setText(('✓ ' if success else '')+message)
    toast.setAccessibleName(message)
    toast.setStyleSheet('QLabel{background:#ECF6EF;color:#193C2C;border:1px solid #A8D4B8;border-radius:10px;padding:12px 18px;font-size:14px;}')
    toast.adjustSize();toast.move(max(12,(host.width()-toast.width())//2),max(12,host.height()-toast.height()-26))
    toast.show();toast.raise_();toast.timer.start(2600)
    return toast


def copy_text(owner,text,message='复制成功，可直接粘贴到 Excel。'):
    QApplication.clipboard().setText(text)
    return notify(owner,message)
