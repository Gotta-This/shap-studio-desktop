# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
is_macos = sys.platform == "darwin"
exe_name = "科研数据工具集" if is_macos else "SHAPStudio"
datas = [(str(root / "clinical_studio" / "defaults.json"), "clinical_studio"),
         (str(root / "clinical_studio" / "assets"), "clinical_studio/assets")]
datas += collect_data_files("shap", include_py_files=True)
for package in ["numpy", "pandas", "matplotlib", "scikit-learn", "shap", "Pillow", "openpyxl"]:
    datas += copy_metadata(package)

a = Analysis([str(root / "main.py")], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=collect_submodules("shap") + ["openpyxl", "PIL.Image", "PIL.PngImagePlugin",
        "matplotlib.backends.backend_svg", "matplotlib.backends.backend_pdf"],
    hookspath=[], hooksconfig={"matplotlib": {"backends": ["Agg", "SVG", "PDF"]}}, runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "IPython", "pytest", "notebook", "jupyter",
              "pandas.tests", "numpy.tests", "scipy.tests", "sklearn.tests", "matplotlib.tests"],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=exe_name, debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
    icon=str(root / "clinical_studio" / "assets" / "icon.ico") if not is_macos else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=exe_name)
if is_macos:
    app = BUNDLE(coll, name="科研数据工具集.app", icon=str(root / "clinical_studio" / "assets" / "icon.icns"),
        bundle_identifier="local.clinicalstudio.shap", version="1.0.37",
        info_plist={"NSAppleEventsUsageDescription": "用于将旧版 Word 文档的临时副本转换为可识别的表格格式。", "NSHighResolutionCapable": True, "NSRequiresAquaSystemAppearance": True,
                    "NSHumanReadableCopyright": "SHAP 分析工作台 1.0.37",
                    "CFBundleDisplayName": "科研数据工具集"})
