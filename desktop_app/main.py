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
    parser.add_argument("--shap-verify",metavar="OUTPUT_DIR",help="后台核对第四模块完整参数、生成和导出")
    parser.add_argument("--word-verify",metavar="OUTPUT_DIR",help="后台核对Word病例生成完整流程")
    parser.add_argument("--word-groups-verify",metavar="OUTPUT_DIR",help="核对自定义组别导入、指标改名与Excel导出")
    parser.add_argument("--word-layout-verify",metavar="OUTPUT_DIR",help="核对Word基础资料布局和单元格编辑框")
    parser.add_argument("--input-verify",metavar="OUTPUT_DIR",help="核对整个App的下拉框滚轮保护")
    parser.add_argument("--shell-verify",metavar="OUTPUT_DIR",help="核对自适应高度、精简顶部栏与左下页脚")
    parser.add_argument("--prose-verify",metavar="OUTPUT_DIR",help="核对正文一般资料识别、冲突检查和导出")
    parser.add_argument("--table-types-verify",metavar="OUTPUT_DIR",help="核对三类表格及字段类型修改")
    parser.add_argument("--word-drop-verify",metavar="OUTPUT_DIR",help="核对拖入Word、确认弹窗与取消保留数据")
    parser.add_argument("--ungrouped-verify",metavar="OUTPUT_DIR",help="核对无分组竖表识别、例数补充、编辑及不含分组列的导出")
    parser.add_argument("--unified-preview-verify",metavar="OUTPUT_DIR",help="核对统一编辑弹窗与Word确认组别前的预览和草稿编辑")
    parser.add_argument("--merged-tables-verify",metavar="OUTPUT_DIR",help="核对同文档竖表、横表、多层合并表头及汇总率确认")
    parser.add_argument("--resize-verify",metavar="OUTPUT_DIR",help="核对四个工具文本框和表格拉伸及外层滚动")
    parser.add_argument("--todo-verify",metavar="OUTPUT_DIR",help="核对待办的本地保存、编辑、完成、重启和默认勾选项")
    parser.add_argument("--word-source",help="Word流程验证的docx来源")
    parser.add_argument("--open-tool",choices=["category","numeric","word","shap"],help="启动时打开指定工具")
    args=parser.parse_args()
    if args.todo_verify:
        todo_root=Path(args.todo_verify).resolve();todo_root.mkdir(parents=True,exist_ok=True)
        os.environ["CLINICAL_STUDIO_TODO_PATH"]=str(todo_root/"todos.json")
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
    if args.ui_verify or args.shap_verify or args.word_verify or args.word_groups_verify or args.word_layout_verify or args.input_verify or args.shell_verify or args.prose_verify or args.table_types_verify:
        from PySide6.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_DontUseNativeDialogs,True)
    from clinical_studio.app import create_application
    from clinical_studio.hub import DesktopWindow
    app=create_application(sys.argv); window=DesktopWindow(config,args.output); window.show()
    if args.open_tool:window.open_module(args.open_tool)
    if args.todo_verify:
        from clinical_studio.todo_verify import verify_todos
        def verify_todo_flow():
            window.verification_passed=verify_todos(window,args.todo_verify)
            app.quit()
        QTimer.singleShot(250,verify_todo_flow)
    if args.ui_verify:
        from clinical_studio.strict_verify import StrictVerifier
        verifier=StrictVerifier(window,args.ui_verify,app)
        QTimer.singleShot(900,verifier.start)
    if args.shap_verify:
        from clinical_studio.repair_verify import verify
        def verify_shap():
            window.verification_passed=verify(window,args.shap_verify)
            app.quit()
        QTimer.singleShot(100,verify_shap)
    if args.word_verify:
        if not args.word_source:raise ValueError("--word-verify 需要 --word-source DOCX")
        from clinical_studio.word_verify import verify_word
        def verify_word_flow():
            window.verification_passed=verify_word(window,args.word_verify,args.word_source)
            app.quit()
        QTimer.singleShot(100,verify_word_flow)
    if args.word_groups_verify:
        from clinical_studio.group_verify import verify_groups
        def verify_group_flow():
            window.verification_passed=verify_groups(window,args.word_groups_verify)
            app.quit()
        QTimer.singleShot(100,verify_group_flow)
    if args.word_layout_verify:
        from clinical_studio.layout_verify import verify_layout
        def verify_layout_flow():
            window.verification_passed=verify_layout(window,args.word_layout_verify)
            app.quit()
        QTimer.singleShot(100,verify_layout_flow)
    if args.input_verify:
        from clinical_studio.input_verify import verify_inputs
        def verify_input_flow():
            window.verification_passed=verify_inputs(window,args.input_verify)
            app.quit()
        QTimer.singleShot(100,verify_input_flow)
    if args.shell_verify:
        from clinical_studio.shell_verify import verify_shell
        def verify_shell_flow():
            window.verification_passed=verify_shell(window,args.shell_verify)
            app.quit()
        QTimer.singleShot(100,verify_shell_flow)
    if args.prose_verify:
        from clinical_studio.prose_verify import verify_prose
        def verify_prose_flow():
            window.verification_passed=verify_prose(window,args.prose_verify)
            app.quit()
        QTimer.singleShot(100,verify_prose_flow)
    if args.table_types_verify:
        from clinical_studio.table_types_verify import verify_table_types
        def verify_table_types_flow():
            window.verification_passed=verify_table_types(window,args.table_types_verify)
            app.quit()
        QTimer.singleShot(100,verify_table_types_flow)
    if args.word_drop_verify:
        from clinical_studio.word_drop_verify import verify_word_drop
        def verify_drop_flow():
            window.verification_passed=verify_word_drop(window,args.word_drop_verify)
            app.quit()
        QTimer.singleShot(250,verify_drop_flow)
    if args.ungrouped_verify:
        from clinical_studio.ungrouped_verify import verify_ungrouped
        def verify_ungrouped_flow():
            window.verification_passed=verify_ungrouped(window,args.ungrouped_verify)
            app.quit()
        QTimer.singleShot(250,verify_ungrouped_flow)
    if args.unified_preview_verify:
        from clinical_studio.unified_preview_verify import verify_unified_preview
        def verify_unified_preview_flow():
            window.verification_passed=verify_unified_preview(window,args.unified_preview_verify)
            app.quit()
        QTimer.singleShot(250,verify_unified_preview_flow)
    if args.merged_tables_verify:
        from clinical_studio.merged_table_verify import verify_merged_tables
        def verify_merged_tables_flow():
            window.verification_passed=verify_merged_tables(window,args.merged_tables_verify)
            app.quit()
        QTimer.singleShot(250,verify_merged_tables_flow)
    if args.resize_verify:
        from clinical_studio.resize_verify import verify_resize
        def verify_resize_flow():
            window.verification_passed=verify_resize(window,args.resize_verify)
            app.quit()
        QTimer.singleShot(250,verify_resize_flow)
    if args.screenshot:
        def capture():
            window.grab().save(args.screenshot); app.quit()
        QTimer.singleShot(1200,capture)
    code=app.exec()
    # Destroy the widget tree while QApplication is alive; frozen PySide cleanup
    # may otherwise visit signal-connected buttons after their Qt parent is gone.
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    if args.todo_verify or args.shap_verify or args.word_verify or args.word_groups_verify or args.word_layout_verify or args.input_verify or args.shell_verify or args.prose_verify or args.table_types_verify or args.word_drop_verify or args.resize_verify or args.merged_tables_verify or args.unified_preview_verify or args.ungrouped_verify:
        return 0 if window.verification_passed else 1
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
        flag=next((f for f in ("--todo-verify","--self-test","--ui-verify","--shap-verify","--word-verify","--word-groups-verify","--word-layout-verify","--input-verify","--shell-verify","--prose-verify","--table-types-verify","--word-drop-verify","--resize-verify","--merged-tables-verify","--unified-preview-verify","--ungrouped-verify") if f in sys.argv),None)
        if flag and sys.argv.index(flag)+1<len(sys.argv):
            target=Path(sys.argv[sys.argv.index(flag)+1]);target.mkdir(parents=True,exist_ok=True)
            (target/"fatal_error.json").write_text(json.dumps({"passed":False,"traceback":traceback.format_exc()},ensure_ascii=False,indent=2),encoding="utf-8")
            code=1
        else:
            raise
    raise SystemExit(code)
