"""Collect labelled downloads, retaining aliases for pre-3.2 update clients."""
from pathlib import Path
import json,os,shutil,subprocess,sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'python'))
from release_assets import versioned_name

version=json.loads((root/'package.json').read_text(encoding='utf8'))['version']
target=os.environ['TAURI_ENV_TARGET_TRIPLE']
build=root/'src-tauri/target'/target/'release'
release=root/'release';release.mkdir(exist_ok=True)

def destination(legacy):return release/versioned_name(legacy,version)
def compatibility_alias(legacy,primary):
    # v3.1 and earlier select these exact names in releases/latest.
    # New clients always choose the version-labelled primary download.
    shutil.copy2(primary,release/legacy)

if sys.platform=='win32':
    setups=list((build/'bundle/nsis').glob('*-setup.exe'))
    if len(setups)!=1:raise RuntimeError('Expected exactly one Windows installer')
    legacy='ResearchDataTools-Setup-Windows-x64.exe'
    setup=destination(legacy);shutil.copy2(setups[0],setup)
    compatibility_alias(legacy,setup)
    portable=root/'portable'/('ResearchDataTools-v'+version)
    portable.mkdir(parents=True,exist_ok=True)
    shutil.copy2(build/'research-studio-v3.exe',portable/'research-studio-v3.exe')
    shutil.copy2(root/'src-tauri/binaries'/('research-python-'+target+'.exe'),portable/'research-python.exe')
    archive=destination('ResearchDataTools-Portable-Windows-x64.zip')
    shutil.make_archive(str(archive.with_suffix('')),'zip',portable.parent)
elif sys.platform=='darwin':
    arch={'aarch64-apple-darwin':'arm64','x86_64-apple-darwin':'x86_64'}[target]
    legacy='ResearchDataTools-macOS-'+arch+'.zip'
    archive=destination(legacy)
    subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(build/'bundle/macos/科研数据工具集 V3.app'),str(archive)],check=True)
    compatibility_alias(legacy,archive)
else:raise RuntimeError('Release packaging supports Windows and macOS only')

for path in sorted(release.iterdir()):
    if path.stat().st_size<=0:raise RuntimeError('Empty release asset: '+path.name)
    print(path.name, path.stat().st_size)
