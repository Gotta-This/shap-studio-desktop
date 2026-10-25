"""开发启动与安装包入口。"""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    # 缓存写到用户可写目录，不写入签名后的 App 包。
    cache=Path(os.environ.get("SHAP_STUDIO_CACHE",str(Path.home()/"Library"/"Caches"/"SHAPStudio") if sys.platform=="darwin" else str(Path.home()/".cache"/"SHAPStudio")))
    cache.mkdir(parents=True,exist_ok=True)
    if getattr(sys,"frozen",False):
        # 覆盖打包器为单次进程创建的临时目录，避免每次分析重建字体缓存。
        os.environ["MPLCONFIGDIR"]=str(cache/"matplotlib")
    else:
        os.environ.setdefault("MPLCONFIGDIR",str(cache/"matplotlib"))
    os.environ.setdefault("NUMBA_CACHE_DIR",str(cache/"numba"))
    os.environ.setdefault("MPLBACKEND","Agg")
    parser=argparse.ArgumentParser(description="离线 SHAP 分析工作台")
    parser.add_argument("--self-test",metavar="OUTPUT_DIR",help="用默认参数完整分析并核对打包后的环境")
    parser.add_argument("--config",help="启动时载入配置 JSON")
    parser.add_argument("--output",help="结果保存目录")
    parser.add_argument("--screenshot",help="将初始界面保存为 PNG 后退出")
    parser.add_argument("--ui-verify",metavar="OUTPUT_DIR",help="显示应用窗口，通过控件操作完成修改、生成、保存和独立核对")
    args=parser.parse_args()
    from clinical_studio.config import default_config,load_config
    config=load_config(args.config) if args.config else default_config()
    if args.self_test:
        from clinical_studio.engine import run_analysis
        result=run_analysis(config,args.self_test,print)
        if not all(item["passed"] for item in result.audit.values()):
            raise RuntimeError("打包环境的颜色核对未全部通过。")
        (Path(args.self_test)/"self_test_passed.json").write_text(json.dumps({"passed":True,"folder":str(result.folder),"images":len(result.images)},ensure_ascii=False,indent=2),encoding="utf-8")
        return 0
    from PySide6.QtCore import QTimer, Qt, QCoreApplication, QEvent
    if args.ui_verify:
        from PySide6.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_DontUseNativeDialogs,True)
    from clinical_studio.app import create_application,MainWindow
    app=create_application(sys.argv); window=MainWindow(config,args.output); window.show()
    if args.ui_verify:
        from clinical_studio.ui_verify import UiVerifier
        verifier=UiVerifier(window,args.ui_verify,app)
        QTimer.singleShot(900,verifier.start)
    if args.screenshot:
        def capture():
            window.grab().save(args.screenshot); app.quit()
        QTimer.singleShot(1200,capture)
    code=app.exec()
    # Destroy the widget tree while QApplication is alive; frozen PySide cleanup
    # may otherwise visit signal-connected buttons after their Qt parent is gone.
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    if args.ui_verify:
        return 0 if verifier.passed else 1
    return code


if __name__=="__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        code=main()
    except Exception:
        import traceback
        flag=next((f for f in ("--self-test","--ui-verify") if f in sys.argv),None)
        if flag and sys.argv.index(flag)+1<len(sys.argv):
            target=Path(sys.argv[sys.argv.index(flag)+1]);target.mkdir(parents=True,exist_ok=True)
            (target/"fatal_error.json").write_text(json.dumps({"passed":False,"traceback":traceback.format_exc()},ensure_ascii=False,indent=2),encoding="utf-8")
            code=1
        else:
            raise
    raise SystemExit(code)
