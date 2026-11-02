"""Keep the installer, frontend and update checker on the same release version."""
import json, re, unittest
from pathlib import Path
from releases import VERSION

class VersionTests(unittest.TestCase):
    def test_release_versions_match(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('package.json','package-lock.json','src-tauri/tauri.conf.json'):
            content=json.loads((root/name).read_text(encoding='utf8'))
            self.assertEqual(content['version'],VERSION,name)
            if name=='package-lock.json':self.assertEqual(content['packages']['']['version'],VERSION)
        cargo=(root/'src-tauri/Cargo.toml').read_text(encoding='utf8')
        self.assertEqual(re.search(r'^version = "([^"]+)"',cargo,re.M)[1],VERSION)
        lock=(root/'src-tauri/Cargo.lock').read_text(encoding='utf8')
        self.assertIn(f'name = "research-studio-v3"\nversion = "{VERSION}"',lock)
