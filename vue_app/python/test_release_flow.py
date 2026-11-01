import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import releases
import migration
from clinical_studio.manuscripts import WorkspaceStore

class ReleaseFlowTests(unittest.TestCase):
    def payload(self, data=b'installer'):
        name='ResearchDataTools-Setup-Windows-x64.exe'
        return dict(tag_name='v3.0.3', assets=[dict(name=name, size=len(data), digest='sha256:'+hashlib.sha256(data).hexdigest(), browser_download_url=releases.PREFIX+'v3.0.3/'+name)])
    def test_platform_and_versions(self):
        self.assertEqual(releases.asset_name('win32','AMD64'),'ResearchDataTools-Setup-Windows-x64.exe')
        self.assertEqual(releases.asset_name('darwin','arm64'),'ResearchDataTools-macOS-arm64.zip')
        self.assertEqual(releases.asset_name('darwin','x86_64'),'ResearchDataTools-macOS-x86_64.zip')
        self.assertTrue(releases.select(self.payload(),releases.asset_name('win32','AMD64'))['newer'])
        with self.assertRaises(ValueError):releases.select(dict(tag_name='v1.1.2'))
        with self.assertRaises(ValueError):releases.select(dict(tag_name='v3.0.3',prerelease=True))
    def test_download_verifies_checksum_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as tmp, patch('releases.asset_name',return_value='ResearchDataTools-Setup-Windows-x64.exe'):
            payload=self.payload()
            with patch('releases.check',return_value=releases.select(payload)), patch('releases.read_url',return_value=io.BytesIO(b'installer')):
                result=releases.download(Path(tmp))
                self.assertEqual(Path(result['path']).read_bytes(),b'installer')
            with patch('releases.check',return_value=releases.select(payload)), patch('releases.read_url',return_value=io.BytesIO(b'corrupted')):
                with self.assertRaises(ValueError):releases.download(Path(tmp))
            self.assertFalse(list(Path(tmp).rglob('*.part')))
            self.assertEqual(Path(result['path']).read_bytes(),b'installer')
    def test_checksum_file_fallback_and_url_rejection(self):
        with tempfile.TemporaryDirectory() as tmp, patch('releases.asset_name',return_value='ResearchDataTools-Setup-Windows-x64.exe'):
            payload=self.payload();asset=payload['assets'][0];digest=asset.pop('digest')[7:]
            payload['assets'].append(dict(name='SHA256SUMS.txt', browser_download_url=releases.PREFIX+'v3.0.3/SHA256SUMS.txt'))
            with patch('releases.check',return_value=releases.select(payload)), patch('releases.read_url',side_effect=[io.BytesIO((digest+'  '+asset['name']).encode()),io.BytesIO(b'installer')]):
                self.assertTrue(Path(releases.download(Path(tmp))['path']).is_file())
            asset['browser_download_url']='https://example.com/installer.exe'
            asset['digest']='sha256:'+digest
            with patch('releases.check',return_value=releases.select(payload)):
                with self.assertRaises(ValueError):releases.download(Path(tmp))

class MigrationTests(unittest.TestCase):
    def test_repeat_import_preserves_v3_changes_and_qt_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);qt=root/'qt';qt.mkdir();v3=root/'v3';v3.mkdir();workspace=WorkspaceStore(root/'稿件')
            tasks=dict(version=1,tasks=[dict(id='old-1',name='中文待办😀',priority='high',due_date='2028-02-29',completed=True,deleted=False)])
            todo=qt/'todos.json';todo.write_text(json.dumps(tasks,ensure_ascii=False),encoding='utf-8');original=todo.read_bytes()
            (qt/'manuscript-workspace.json').write_text(json.dumps(dict(version=1,root=str(workspace.root))),encoding='utf-8')
            result=migration.migrate(v3,str(qt));self.assertEqual(result['imported'],1);self.assertEqual(result['workspace'],str(workspace.root))
            with sqlite3.connect(v3/'personal.sqlite3') as db:db.execute("UPDATE todos SET text='V3 edited'")
            self.assertEqual(migration.migrate(v3,str(qt))['imported'],0)
            with sqlite3.connect(v3/'personal.sqlite3') as db:self.assertEqual(db.execute('SELECT text,completed FROM todos').fetchone(),('V3 edited',1))
            self.assertEqual(todo.read_bytes(),original)
            self.assertEqual((Path(result['backup'])/'todos.json').read_bytes(),original)
    def test_invalid_source_has_no_partial_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            qt=Path(tmp)/'qt';qt.mkdir();v3=Path(tmp)/'v3';v3.mkdir()
            (qt/'todos.json').write_text(json.dumps(dict(version=1,tasks=[dict(id='1',name='x',priority='wrong',completed=False)])))
            with self.assertRaises(ValueError):migration.migrate(v3,str(qt))
            self.assertFalse((v3/'personal.sqlite3').exists())

if __name__=='__main__':unittest.main()
