"""真实点击运行按钮，验证后台任务、结果页和数据表。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.setdefault("MPLCONFIGDIR","/private/tmp/dbq-matplotlib-check")
os.environ.setdefault("NUMBA_CACHE_DIR","/private/tmp/dbq-numba")
import json
import sys
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from clinical_studio.app import create_application,MainWindow

app=create_application([])
root=Path(__file__).resolve().parents[1]
window=MainWindow(output=str(root/"verification"/"gui"));window.show()
failures=[]

def fail(title,message):
    failures.append(message);app.quit()
QMessageBox.warning=lambda parent,title,message:fail(title,message)

def finish():
    if window.result is None or window.worker.isRunning():
        QTimer.singleShot(100,finish);return
    result=window.result
    try:
        assert window.nav.currentRow()==4
        assert window.data_table.model().rowCount()==800
        assert window.coefficient_table.model().rowCount()==7
        assert window.prediction_table.model().rowCount()==240
        assert len(result.images)==6
        assert all(item["passed"] for item in result.audit.values())
        window.grab().save(str(root/"结果界面预览.png"))
        for index,file in [(1,"数据参数界面.png"),(3,"图表设置界面.png")]:
            window.nav.setCurrentRow(index);app.processEvents()
            if index==3:window.style_editor.selector.setCurrentIndex(3);app.processEvents()
            window.grab().save(str(root/file))
        (root/"verification"/"gui_flow_passed.json").write_text(json.dumps({"passed":True,"result":str(result.folder),"gallery_images":6,"data_rows":800,"test_rows":240},ensure_ascii=False,indent=2))
    except Exception as exc:failures.append(str(exc))
    app.quit()

def start():
    QTest.mouseClick(window.run_button,Qt.LeftButton)
    QTimer.singleShot(100,finish)
QTimer.singleShot(500,start)
QTimer.singleShot(120000,lambda:fail("timeout","GUI run exceeded 120 seconds"))
app.exec()
if window.worker:window.worker.wait(5000)
window.close()
if failures:raise RuntimeError("; ".join(failures))
print("GUI click → worker → six images → tables → saved result: PASSED")
