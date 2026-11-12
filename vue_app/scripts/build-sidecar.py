"""Build the embedded Python executable with the active, fully installed Python."""
from pathlib import Path
import os,platform,subprocess,sys,shutil
root=Path(__file__).resolve().parents[1];repo=root.parent
os.environ.setdefault('PYINSTALLER_CONFIG_DIR',str(root/'.v3-data/pyinstaller-cache'))
subprocess.run([sys.executable,str(root/'scripts/prepare-python.py')],check=True)
# Only scientific fonts/licences belong in the Python backend. The Vue/Tauri
# host owns icons and UI assets; the historical Qt layout is not shipped here.
assets=root/'.v3-data/sidecar-assets'
if assets.exists():shutil.rmtree(assets)
assets.mkdir(parents=True)
for source in (repo/'desktop_app/clinical_studio/assets').iterdir():
 if source.is_file() and (source.suffix.lower() in ('.otf','.ttf','.ttc') or 'license' in source.name.lower()):shutil.copy2(source,assets/source.name)

machine=platform.machine().lower()
target=os.environ.get('TAURI_ENV_TARGET_TRIPLE') or ('aarch64-apple-darwin' if sys.platform=='darwin' and machine=='arm64' else 'x86_64-apple-darwin' if sys.platform=='darwin' else 'x86_64-pc-windows-msvc' if sys.platform=='win32' else 'x86_64-unknown-linux-gnu')
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--name','research-python','--paths',str(repo/'desktop_app'),'--distpath',str(root/'.v3-data/sidecar-dist'),'--workpath',str(root/'.v3-data/sidecar-build'),'--specpath',str(root/'.v3-data'),'--add-data',str(repo/'desktop_app/clinical_studio/defaults.json')+os.pathsep+'clinical_studio','--add-data',str(assets)+os.pathsep+'clinical_studio/assets','--add-data',str(root/'python/prediction_plot_defaults.json')+os.pathsep+'.','--collect-all','xgboost','--collect-data','shap','--collect-data','matplotlib','--hidden-import','matplotlib.backends.backend_pdf','--hidden-import','matplotlib.backends.backend_svg','--exclude-module','PySide6','--exclude-module','tkinter',str(root/'python/bridge.py')]
# A clean scientific build must not pick up a Qt binding from a developer's
# Python environment or optional Matplotlib/Pillow adapters.
for module in ('PySide2','PyQt5','PyQt6','shiboken2','shiboken6','PIL.ImageQt'):
 args[-1:-1]=['--exclude-module',module]
metadata=[]
for package in ('numpy','pandas','scikit-learn','shap','matplotlib','Pillow','openpyxl','scipy','xgboost'):
 metadata.extend(['--copy-metadata',package])
args=args[:-1]+metadata+args[-1:]
subprocess.run(args,check=True)
suffix='.exe' if sys.platform=='win32' else ''
subprocess.run([sys.executable,str(root/'scripts/audit-sidecar.py'),str(root/'.v3-data/sidecar-dist'/('research-python'+suffix)),'--strict-resources'],check=True)
target_path=root/'src-tauri/binaries'/('research-python-'+target+suffix);target_path.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'.v3-data/sidecar-dist'/('research-python'+suffix),target_path)
print(target_path)
