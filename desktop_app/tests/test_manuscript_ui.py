import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.manuscript_verify import verify_manuscripts
from PySide6.QtCore import QCoreApplication,QEvent
APP=create_application([])


class ManuscriptUiTests(unittest.TestCase):
    def test_real_qt_workflow_and_existing_todo_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict(os.environ,{'CLINICAL_STUDIO_TODO_PATH':str(root/'todos.json'),
                                      'CLINICAL_STUDIO_WORKSPACE_CONFIG':str(root/'workspace.json')}):
                window=DesktopWindow(auto_check_updates=False)
                window.show()
                try:
                    passed=verify_manuscripts(window,root/'evidence')
                    self.assertTrue(passed,(root/'evidence/verification.json').read_text(encoding='utf-8'))
                finally:
                    if hasattr(window,'manuscript_page') and window.manuscript_page.worker:
                        window.manuscript_page.worker.wait(20000)
                        APP.processEvents()
                    window.close();window.deleteLater()
                    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
