"""Run regressions and dispose Qt objects before interpreter teardown."""
import gc
import sys
import unittest


def main():
    suite=unittest.defaultTestLoader.discover('tests')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    from PySide6.QtCore import QCoreApplication,QEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete,isValid
    app=QApplication.instance()
    if app:
        for widget in QApplication.topLevelWidgets():
            if isValid(widget):
                widget.close();widget.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        app.processEvents();gc.collect()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        app.quit();delete(app)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
