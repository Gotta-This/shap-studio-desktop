"""Collect only version-labelled public downloads."""
from pathlib import Path
import json,os,shutil,subprocess,sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'python'))
from release_assets import versioned_name


def collect(root,target,system):
    version=json.loads((root/'package.json').read_text(encoding='utf8'))['version']
    build=root/'src-tauri/target'/target/'release'
    release=root/'release';release.mkdir(exist_ok=True)
    # A local rebuild must not publish old aliases or another version's files.
    for path in release.glob('ResearchDataTools-*'):
        if path.is_file() and path.suffix in ('.exe','.zip'):path.unlink()
    def destination(legacy):return release/versioned_name(legacy,version)
    if system=='win32':
        setups=list((build/'bundle/nsis').glob('*-setup.exe'))
        if len(setups)!=1:raise RuntimeError('Expected exactly one Windows installer')
        shutil.copy2(setups[0],destination('ResearchDataTools-Setup-Windows-x64.exe'))
        portable=root/'portable'/('ResearchDataTools-v'+version)
        portable.mkdir(parents=True,exist_ok=True)
        shutil.copy2(build/'research-studio-v3.exe',portable/'research-studio-v3.exe')
        shutil.copy2(root/'src-tauri/binaries'/('research-python-'+target+'.exe'),portable/'research-python.exe')
        archive=destination('ResearchDataTools-Portable-Windows-x64.zip')
        shutil.make_archive(str(archive.with_suffix('')),'zip',portable.parent,portable.name)
    elif system=='darwin':
        arch={'aarch64-apple-darwin':'arm64','x86_64-apple-darwin':'x86_64'}[target]
        archive=destination('ResearchDataTools-macOS-'+arch+'.zip')
        subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(build/'bundle/macos/科研数据工具集 V3.app'),str(archive)],check=True)
    else:raise RuntimeError('Release packaging supports Windows and macOS only')
    for path in sorted(release.iterdir()):
        if path.stat().st_size<=0:raise RuntimeError('Empty release asset: '+path.name)
        print(path.name,path.stat().st_size)


if __name__=='__main__':collect(root,os.environ['TAURI_ENV_TARGET_TRIPLE'],sys.platform)
