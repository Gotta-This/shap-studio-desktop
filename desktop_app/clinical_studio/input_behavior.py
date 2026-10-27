"""Consistent table scrolling and safe wheel input over closed dropdowns."""
from PySide6.QtCore import QObject,QEvent,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication,QWidget,QComboBox,QAbstractItemView,QAbstractScrollArea,QTableView


class TableScrollBehavior(QObject):
    @staticmethod
    def configure(table):
        # Item scrolling jumps an entire (potentially very wide) column. Pixel
        # mode also preserves native trackpad deltas and momentum in Qt.
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.horizontalScrollBar().setSingleStep(16)
        table.verticalScrollBar().setSingleStep(16)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Show and isinstance(watched,QTableView):
            self.configure(watched)
        elif event.type()==QEvent.Wheel and isinstance(watched,QWidget):
            table=watched.parentWidget()
            if isinstance(table,QTableView) and watched is table.viewport() and not event.pixelDelta().isNull():
                # Some Qt styles/platforms fall back to angleDelta even for
                # trackpads. Apply the supplied native pixels exactly once.
                moved=False
                for bar,delta in ((table.horizontalScrollBar(),event.pixelDelta().x()),
                                  (table.verticalScrollBar(),event.pixelDelta().y())):
                    before=bar.value()
                    bar.setValue(before-delta)
                    moved=moved or bar.value()!=before
                if moved:
                    event.accept()
                    return True
        return False


class ComboWheelGuard(QObject):
    def eventFilter(self,watched,event):
        if event.type()!=QEvent.Wheel or not isinstance(watched,QWidget):
            return False
        widget=watched
        while widget is not None and not isinstance(widget,QComboBox):
            # Open popup lists handle their own scrolling and selection.
            if isinstance(widget,QAbstractItemView):return False
            widget=widget.parentWidget()
        if widget is None:return False
        # Consume wheel input even when the closed combo has keyboard focus.
        # Route it to a scrollable ancestor instead of changing its value.
        parent=widget.parentWidget()
        delta=event.pixelDelta() if not event.pixelDelta().isNull() else event.angleDelta()
        while parent is not None:
            if isinstance(parent,QAbstractScrollArea):
                bars=((parent.verticalScrollBar(),delta.y()),(parent.horizontalScrollBar(),delta.x()))
                if any((amount>0 and bar.value()>bar.minimum()) or (amount<0 and bar.value()<bar.maximum()) for bar,amount in bars):
                    viewport=parent.viewport()
                    forwarded=QWheelEvent(QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),event.globalPosition(),event.pixelDelta(),event.angleDelta(),event.buttons(),event.modifiers(),event.phase(),event.inverted(),event.source())
                    QApplication.sendEvent(viewport,forwarded)
                    break
            parent=parent.parentWidget()
        event.accept()
        return True


def install_input_behavior(app):
    # One application filter covers dynamic forms, dialogs, table cells and fonts.
    if not hasattr(app,'combo_wheel_guard'):
        app.combo_wheel_guard=ComboWheelGuard(app)
        app.installEventFilter(app.combo_wheel_guard)
    if not hasattr(app,'table_scroll_behavior'):
        app.table_scroll_behavior=TableScrollBehavior(app)
        app.installEventFilter(app.table_scroll_behavior)
        for widget in QApplication.allWidgets():
            if isinstance(widget,QTableView):
                app.table_scroll_behavior.configure(widget)
