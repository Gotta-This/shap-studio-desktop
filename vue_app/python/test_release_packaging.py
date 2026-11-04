"""Publish one version-labelled file per download, with verified alias cleanup."""
import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'scripts'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

collector=load('collect_release','collect-release.py')
cleanup=load('cleanup_release','cleanup-release-assets.py')

class PackagingTests(unittest.TestCase):
    def prepare(self,root,target):
        (root/'package.json').write_text(json.dumps(dict(version='3.2.2')))
        build=root/'src-tauri/target'/target/'release';build.mkdir(parents=True)
        release=root/'release';release.mkdir()
        for name in cleanup.ALIASES+( 'ResearchDataTools-Setup-Windows-x64-v3.2.1.exe',):
            (release/name).write_bytes(b'stale')
        return build,release
    def test_windows_outputs_only_current_version_and_portable_has_one_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);target='x86_64-pc-windows-msvc';build,release=self.prepare(root,target)
            setup=build/'bundle/nsis';setup.mkdir(parents=True);(setup/'app-setup.exe').write_bytes(b'installer')
            (build/'research-studio-v3.exe').write_bytes(b'host')
            binaries=root/'src-tauri/binaries';binaries.mkdir();(binaries/('research-python-'+target+'.exe')).write_bytes(b'engine')
            old=root/'portable/ResearchDataTools-v3.2.1';old.mkdir(parents=True);(old/'old.exe').write_bytes(b'old')
            collector.collect(root,target,'win32')
            self.assertEqual({p.name for p in release.iterdir()},{'ResearchDataTools-Setup-Windows-x64-v3.2.2.exe','ResearchDataTools-Portable-Windows-x64-v3.2.2.zip'})
            with zipfile.ZipFile(release/'ResearchDataTools-Portable-Windows-x64-v3.2.2.zip') as archive:
                self.assertEqual({n for n in archive.namelist() if not n.endswith('/')},{'ResearchDataTools-v3.2.2/research-studio-v3.exe','ResearchDataTools-v3.2.2/research-python.exe'})
    def test_each_mac_architecture_produces_one_labelled_archive(self):
        for target,arch in [('aarch64-apple-darwin','arm64'),('x86_64-apple-darwin','x86_64')]:
            with self.subTest(arch=arch),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);_,release=self.prepare(root,target)
                def ditto(args,check):Path(args[-1]).write_bytes(b'archive')
                with patch.object(collector.subprocess,'run',side_effect=ditto):collector.collect(root,target,'darwin')
                self.assertEqual([p.name for p in release.iterdir()],['ResearchDataTools-macOS-'+arch+'-v3.2.2.zip'])
    def payload(self):
        assets=[]
        for old in cleanup.ALIASES:
            suffix=Path(old).suffix;new=old[:-len(suffix)]+'-v3.2.2'+suffix
            assets.extend([dict(name=name,digest='sha256:'+'a'*64,size=12) for name in (old,new)])
        assets.append(dict(name='ResearchDataTools-Portable-Windows-x64-v3.2.2.zip',digest='sha256:'+'b'*64,size=20))
        return dict(tag_name='v3.2.2',assets=assets)
    def test_cleanup_only_removes_identical_aliases_and_updates_checksum_names(self):
        release=self.payload();remove,checksums=cleanup.plan(release)
        self.assertEqual(set(remove),set(cleanup.ALIASES))
        names={line.split()[1] for line in checksums.splitlines()}
        self.assertEqual(len(names),4);self.assertTrue(all('-v3.2.2.' in n for n in names))
        release['assets']=[a for a in release['assets'] if a['name'] not in remove]
        self.assertEqual(cleanup.plan(release)[0],[])
    def test_cleanup_refuses_missing_or_different_primary_downloads(self):
        for change in ('digest','size','missing'):
            release=self.payload()
            if change=='missing':release['assets'].pop(1)
            elif change=='digest':release['assets'][1]['digest']='sha256:'+'c'*64
            else:release['assets'][1]['size']=13
            with self.subTest(change=change),self.assertRaises(ValueError):cleanup.plan(release)
