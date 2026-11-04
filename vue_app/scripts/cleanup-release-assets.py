"""Remove verified duplicate aliases from one release, keeping primary packages."""
import json,os,re,subprocess,tempfile
from pathlib import Path

REPO='Gotta-This/shap-studio-desktop'
ALIASES=('ResearchDataTools-Setup-Windows-x64.exe','ResearchDataTools-macOS-arm64.zip','ResearchDataTools-macOS-x86_64.zip')


def plan(release):
    tag=release['tag_name']
    if not re.fullmatch(r'v\d+\.\d+\.\d+',tag) or release.get('draft') or release.get('prerelease'):raise ValueError('Expected a published stable release')
    assets={a['name']:a for a in release['assets']};remove=[]
    for name in ALIASES:
        if name not in assets:continue
        suffix=Path(name).suffix;primary=name[:-len(suffix)]+'-'+tag+suffix
        old=assets[name];new=assets.get(primary)
        if not new or old.get('size')!=new.get('size') or not re.fullmatch(r'sha256:[0-9a-f]{64}',old.get('digest') or '') or old.get('digest')!=new.get('digest'):
            raise ValueError('Refusing to remove an alias without an identical version-labelled package: '+name)
        remove.append(name)
    kept=[a for a in release['assets'] if a['name'] not in remove and a['name'].endswith(('.exe','.zip'))]
    for asset in kept:
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',asset.get('digest') or ''):raise ValueError('Missing checksum: '+asset['name'])
    checksums=''.join(a['digest'][7:]+'  '+a['name']+'\n' for a in sorted(kept,key=lambda a:a['name']))
    return remove,checksums


def main():
    tag=os.environ.get('RELEASE_TAG','v3.2.2')
    if not re.fullmatch(r'v\d+\.\d+\.\d+',tag):raise ValueError('Invalid release tag')
    def gh(*args):return subprocess.check_output(['gh',*args,'--repo',REPO],text=True)
    release=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/releases/tags/{tag}'],text=True))
    remove,checksums=plan(release)
    if not remove:print('No duplicate aliases remain.');return
    # All pairs are verified before the first deletion. No package is rebuilt.
    for name in remove:gh('release','delete-asset',tag,name,'--yes');print('Removed duplicate:',name)
    with tempfile.TemporaryDirectory() as temporary:
        checksum=Path(temporary)/'SHA256SUMS.txt';checksum.write_text(checksums,encoding='utf8')
        gh('release','upload',tag,str(checksum),'--clobber')
        body=(release.get('body') or '').replace('无版本号文件供旧版更新兼容。','安装包仅保留带版本号的文件。')
        notes=Path(temporary)/'notes.md';notes.write_text(body,encoding='utf8')
        gh('release','edit',tag,'--notes-file',str(notes))
    after=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/releases/tags/{tag}'],text=True))
    names={a['name'] for a in after['assets']}
    if names.intersection(ALIASES):raise RuntimeError('Duplicate aliases remain')
    print('Remaining release assets:',', '.join(sorted(names)))


if __name__=='__main__':main()
