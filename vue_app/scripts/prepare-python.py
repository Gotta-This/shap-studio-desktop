"""Prepare the private Python environment, including macOS XGBoost OpenMP.

Run with the installed project interpreter after pip install -r requirements.txt.
Reuses the libomp shipped by scikit-learn, without modifying system libraries.
"""
from pathlib import Path
import importlib.util, shutil, subprocess, sys

def prepare():
    if sys.platform!='darwin': return
    xgb=importlib.util.find_spec('xgboost');sk=importlib.util.find_spec('sklearn')
    if not xgb or not sk: return
    folder=Path(xgb.origin).parent/'lib';lib=folder/'libxgboost.dylib'
    runtime=Path(sk.origin).parent/'.dylibs/libomp.dylib'
    if not runtime.exists(): raise RuntimeError('scikit-learn 未提供 libomp，请安装 macOS libomp 后重试。')
    shutil.copy2(runtime,folder/'libomp.dylib')
    load=subprocess.check_output(['otool','-l',str(lib)],text=True)
    if 'path @loader_path (offset' not in load:
        subprocess.run(['install_name_tool','-add_rpath','@loader_path',str(lib)],check=True)
        subprocess.run(['codesign','--force','--sign','-',str(lib)],check=True)
    print('macOS XGBoost OpenMP runtime ready.')
if __name__=='__main__':prepare()
