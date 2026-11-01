"""Build the embedded Python executable with the active, fully installed Python."""
from pathlib import Path
import os,platform,subprocess,sys,shutil
root=Path(__file__).resolve().parents[1];repo=root.parent
os.environ.setdefault('PYINSTALLER_CONFIG_DIR',str(root/'.v3-data/pyinstaller-cache'))
machine=platform.machine().lower()
target=os.environ.get('TAURI_ENV_TARGET_TRIPLE') or ('aarch64-apple-darwin' if sys.platform=='darwin' and machine=='arm64' else 'x86_64-apple-darwin' if sys.platform=='darwin' else 'x86_64-pc-windows-msvc' if sys.platform=='win32' else 'x86_64-unknown-linux-gnu')
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--name','research-python','--paths',str(repo/'desktop_app'),'--distpath',str(root/'.v3-data/sidecar-dist'),'--workpath',str(root/'.v3-data/sidecar-build'),'--specpath',str(root/'.v3-data'),'--add-data',str(repo/'desktop_app/clinical_studio/defaults.json')+os.pathsep+'clinical_studio','--add-data',str(repo/'desktop_app/clinical_studio/assets')+os.pathsep+'clinical_studio/assets','--collect-data','shap','--collect-data','matplotlib','--exclude-module','PySide6','--exclude-module','tkinter',str(root/'python/bridge.py')]
metadata=[]
for package in ('numpy','pandas','scikit-learn','shap','matplotlib','Pillow','openpyxl'):
 metadata.extend(['--copy-metadata',package])
args=args[:-1]+metadata+args[-1:]
subprocess.run(args,check=True)
suffix='.exe' if sys.platform=='win32' else ''
target_path=root/'src-tauri/binaries'/('research-python-'+target+suffix);target_path.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'.v3-data/sidecar-dist'/('research-python'+suffix),target_path)
print(target_path)
