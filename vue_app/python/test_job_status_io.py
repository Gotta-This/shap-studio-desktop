"""Transient Windows status-file sharing failures must not fail a task."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import jobs

class StatusIoTests(unittest.TestCase):
    def test_transient_read_lock_returns_real_completed_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile=Path(temporary);folder=profile/'jobs'/('a'*32);folder.mkdir(parents=True)
            (folder/'status.json').write_text(json.dumps(dict(status='done',result={'value':42})))
            original=Path.read_text;calls=[]
            def read(path,*args,**kwargs):
                calls.append(1)
                if len(calls)<3:raise PermissionError('simulated Windows sharing violation')
                return original(path,*args,**kwargs)
            with patch.object(Path,'read_text',read),patch.object(jobs.time,'sleep'):
                self.assertEqual(jobs.status(profile,'a'*32)['result']['value'],42)
            self.assertEqual(len(calls),3)
    def test_transient_replace_lock_keeps_atomic_status_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'status.json';jobs.write(path,dict(status='running'))
            original=jobs.os.replace;calls=[]
            def replace(source,target):
                calls.append(1)
                if len(calls)<3:
                    self.assertEqual(json.loads(path.read_text())['status'],'running')
                    raise PermissionError('simulated Windows sharing violation')
                return original(source,target)
            with patch.object(jobs.os,'replace',replace),patch.object(jobs.time,'sleep'):
                jobs.write(path,dict(status='done'))
            self.assertEqual(json.loads(path.read_text())['status'],'done')
            self.assertEqual(list(path.parent.glob('.status-*')),[])
    def test_permanent_denial_still_fails_and_preserves_previous_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'status.json';jobs.write(path,dict(status='running'))
            with patch.object(jobs.os,'replace',side_effect=PermissionError('permanent')),patch.object(jobs.time,'sleep'):
                with self.assertRaises(PermissionError):jobs.write(path,dict(status='done'))
            self.assertEqual(json.loads(path.read_text())['status'],'running')
            self.assertEqual(list(path.parent.glob('.status-*')),[])
    def test_other_errors_are_not_retried_or_hidden(self):
        with patch.object(jobs.time,'sleep') as sleep:
            with self.assertRaises(FileNotFoundError):jobs._retry_status_io(lambda:(_ for _ in ()).throw(FileNotFoundError()))
            sleep.assert_not_called()
