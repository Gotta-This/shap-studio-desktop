import ctypes,json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import desktop_layout as layout
from desktop_layout_win32 import Guid,Point,Variant

def icon(key,x,y):return dict(key=key,name=key.rsplit('\\',1)[-1],x=x,y=y)
def screen(items):return dict(icons=items,auto_arrange=False,display=dict(width=600,height=400,dpi=96,spacing=[100,100],workareas=[dict(left=0,top=0,right=600,bottom=400)]))
class FakeDesktop:
    def __init__(self,current):self.current=deepcopy(current);self.calls=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def capture(self):return deepcopy(self.current)
    def position(self,items):
        self.calls.append(deepcopy(items));self.current['icons']=deepcopy(items)

class PlanningTests(unittest.TestCase):
    def test_existing_positions_win_and_new_icons_get_empty_cells(self):
        old=screen([icon('原稿.lnk',0,0),icon('数据',0,100),icon('已删除',200,200)])
        current=screen([icon('原稿.lnk',300,0),icon('数据',400,200),icon('新增一',0,0),icon('新增二',0,100)])
        p=layout.plan(old,current);positions={i['key']:(i['x'],i['y']) for i in p['items']}
        self.assertEqual(positions['原稿.lnk'],(0,0));self.assertEqual(positions['数据'],(0,100))
        self.assertEqual((p['restored_count'],p['new_count'],p['missing_count']),(2,2,1))
        self.assertEqual(len(set(positions.values())),4)
        self.assertTrue(all(positions[n][0]>=100 for n in ['新增一','新增二']))
    def test_monitor_gaps_and_taskbar_are_not_used(self):
        old=screen([icon('a',0,0)]);current=screen([icon('a',0,0)]+[icon(str(i),0,0) for i in range(3)])
        current['display']['workareas']=[dict(left=0,top=0,right=100,bottom=200),dict(left=300,top=0,right=500,bottom=100)]
        p=layout.plan(old,current)
        self.assertEqual({(i['x'],i['y']) for i in p['items']},{(0,0),(0,100),(300,0),(400,0)})
    def test_no_space_and_offscreen_backup_fail_before_moving(self):
        old=screen([icon('a',0,0)]);now=screen([icon('a',0,0),icon('b',0,0)]);now['display']['workareas']=[dict(left=0,top=0,right=100,bottom=100)]
        with self.assertRaisesRegex(ValueError,'没有足够'):layout.plan(old,now)
        old['icons'][0]['x']=1000
        with self.assertRaisesRegex(ValueError,'无法容纳'):layout.plan(old,now)
    def test_auto_arrange_and_empty_matches_are_rejected(self):
        old=screen([icon('a',0,0)]);now=screen([icon('a',0,0)]);now['auto_arrange']=True
        with self.assertRaisesRegex(ValueError,'自动排列'):layout.plan(old,now)
        with self.assertRaisesRegex(ValueError,'没有与此备份匹配'):layout.plan(old,screen([icon('new',0,0)]))
    def test_native_abi_layout(self):
        self.assertEqual(ctypes.sizeof(Guid),16);self.assertEqual(ctypes.sizeof(Point),8)
        self.assertEqual(ctypes.sizeof(Variant),24 if ctypes.sizeof(ctypes.c_void_p)==8 else 16)
        self.assertEqual(bytes(Guid.of('000214E2-0000-0000-C000-000000000046'))[:4],b'\xe2\x14\x02\x00')

class DesktopFixture:
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.fake=FakeDesktop(screen([icon('C:\\桌面\\原稿.lnk',0,0)]))
        self.windows=patch.object(layout.sys,'platform','win32');self.windows.start()
        self.native=patch.object(layout,'_native',return_value=self.fake);self.native.start()
    def tearDown(self):self.native.stop();self.windows.stop();self.tmp.cleanup()

class StorageTests(DesktopFixture,unittest.TestCase):
    def test_diagnostics_distinguish_no_op_from_real_restore_and_hide_paths(self):
        saved=layout.backup(self.root,dict(label='私人备份名称'))
        preview=layout.preview(self.root,dict(id=saved['id']))
        self.assertEqual(preview['needs_move_count'],0)
        value=layout.restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual(value['needs_move_count'],0)
        report=layout.diagnostics(self.root)
        self.assertNotIn('私人备份名称',report['content']);self.assertNotIn('原稿.lnk',report['content']);self.assertNotIn('C:\\\\',report['content'])
        events=json.loads(report['content'])['events']
        complete=next(e for e in events if e['event']=='restore.complete')
        self.assertEqual(complete['operation'],value['diagnostic_id'])
        self.assertEqual((complete['needs_move_count'],complete['moved_count'],complete['unmatched_positions']),(0,0,0))
    def test_ignored_shell_movement_is_logged_as_failed_verification(self):
        saved=layout.backup(self.root,{})
        self.fake.current['icons'][0].update(x=400,y=200)
        preview=layout.preview(self.root,dict(id=saved['id']))
        self.assertEqual(preview['needs_move_count'],1)
        def ignored(items):self.fake.trace('native.position.result',hresult='0x00000000',succeeded=True)
        with patch.object(self.fake,'position',side_effect=ignored),patch.object(layout.time,'sleep'):
            value=layout.restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual(value['unmatched_positions'],1)
        events=json.loads(layout.diagnostics(self.root)['content'])['events']
        verify=[e for e in events if e['event']=='restore.verify'][-1]
        self.assertEqual((verify['moved_count'],verify['unmatched_positions']),(0,1))
        self.assertEqual(verify['sample'][0]['actual'],[400,200]);self.assertEqual(verify['sample'][0]['target'],[0,0])
        self.assertTrue(any(e.get('hresult')=='0x00000000' for e in events))
    def test_native_failure_is_logged_and_safety_backup_is_preserved(self):
        saved=layout.backup(self.root,{})
        preview=layout.preview(self.root,dict(id=saved['id']))
        with patch.object(self.fake,'position',side_effect=OSError('Windows 桌面接口调用失败（0x80004005）。')):
            with self.assertRaises(OSError):layout.restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        events=json.loads(layout.diagnostics(self.root)['content'])['events']
        self.assertEqual(events[-1]['event'],'restore.error')
        self.assertIn('0x80004005',events[-1]['error']['message'])
        self.assertEqual(len(layout.info(self.root)['backups']),2)
    def test_unwritable_diagnostic_log_does_not_break_restore(self):
        saved=layout.backup(self.root,{})
        preview=layout.preview(self.root,dict(id=saved['id']))
        with patch.object(layout.diagnostic,'record',return_value=False):
            value=layout.restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertFalse(value['diagnostic_saved']);self.assertEqual(value['unmatched_positions'],0)
    def test_diagnostic_rotation_keeps_three_files(self):
        with patch.object(layout.diagnostic,'MAX_BYTES',10):
            for i in range(5):layout.diagnostic.record(self.root,'event',str(i))
        files=list(self.root.glob('desktop-layout-diagnostics.jsonl*'))
        self.assertEqual(len(files),3)
        self.assertEqual(layout.diagnostics(self.root)['event_count'],3)
    def test_pinned_backups_never_expire_and_cannot_be_deleted(self):
        with patch.object(layout,'KEEP_RECENT',2):
            pinned=layout.backup(self.root,dict(label='永久排列',protected=True))
            ordinary=[layout.backup(self.root,dict(label=str(i))) for i in range(5)]
            saved=layout.info(self.root)['backups']
            self.assertEqual(len(saved),3);self.assertIn(pinned['id'],[v['id'] for v in saved])
            with self.assertRaisesRegex(ValueError,'永久保留'):layout.delete(self.root,dict(id=pinned['id']))
            layout.protect(self.root,dict(id=pinned['id'],protected=False));layout.delete(self.root,dict(id=pinned['id']))
            self.assertFalse(layout._path(self.root,ordinary[0]['id']).exists())
    def test_restore_merges_new_icons_and_saves_current_positions_first(self):
        original=layout.backup(self.root,dict(label='常用桌面',protected=True))
        self.fake.current['icons']=[icon('C:\\桌面\\原稿.lnk',400,200),icon('新增图标',0,0)]
        preview=layout.preview(self.root,dict(id=original['id']))
        result=layout.restore(self.root,dict(id=original['id'],fingerprint=preview['fingerprint']))
        self.assertEqual(result['unmatched_positions'],0);self.assertEqual(len(self.fake.calls),1)
        safety=layout._read(layout._path(self.root,result['safety_backup']['id']))
        self.assertEqual(safety['icons'][0]['x'],400);self.assertTrue(layout._read(layout._path(self.root,original['id']))['protected'])
        self.assertEqual(self.fake.current['icons'][0]['x'],0)
    def test_changed_desktop_requires_new_confirmation(self):
        old=layout.backup(self.root,{});preview=layout.preview(self.root,dict(id=old['id']))
        self.fake.current['icons'].append(icon('新文件',200,200))
        with self.assertRaisesRegex(ValueError,'桌面已发生变化'):layout.restore(self.root,dict(id=old['id'],fingerprint=preview['fingerprint']))
        self.assertEqual(self.fake.calls,[]);self.assertEqual(len(layout.info(self.root)['backups']),1)
    def test_corrupt_backup_and_traversal_do_not_delete_files(self):
        bad=layout._folder(self.root)/'corrupt.json';bad.write_text('broken',encoding='utf8')
        self.assertEqual(layout.info(self.root)['unreadable'],1);self.assertTrue(bad.exists())
        with self.assertRaisesRegex(ValueError,'标识无效'):layout.delete(self.root,dict(id='../other'))
    def test_non_windows_message_and_backend_guards(self):
        with patch.object(layout.sys,'platform','darwin'),patch.object(layout,'_native',side_effect=ValueError(layout.UNSUPPORTED)):
            self.assertEqual(layout.info(self.root)['message'],'非windows电脑无法使用')
            with self.assertRaisesRegex(ValueError,layout.UNSUPPORTED):layout.backup(self.root,{})
            with self.assertRaisesRegex(ValueError,layout.UNSUPPORTED):layout.protect(self.root,dict(id='x',protected=True))

class ScheduleTests(DesktopFixture,unittest.TestCase):
    def test_factory_defaults_use_ten_minutes_and_144_snapshots(self):
        config=layout.info(self.root)['settings']
        self.assertTrue(config['enabled'])
        self.assertEqual((config['interval_minutes'],config['keep_recent']),(10,144))
        with patch.object(layout.time,'time',return_value=1000):
            self.assertEqual(layout.tick(self.root)['next_due_at'],1600)
        with patch.object(layout.time,'time',return_value=1599):self.assertFalse(layout.tick(self.root)['created'])
        with patch.object(layout.time,'time',return_value=1600):self.assertTrue(layout.tick(self.root)['created'])
    def test_saved_settings_are_preserved_after_default_change(self):
        path=self.root/'desktop-layout-settings.json'
        path.write_text(json.dumps(dict(enabled=False,interval_minutes=15,keep_recent=20)),encoding='utf8')
        config=layout.info(self.root)['settings']
        self.assertEqual((config['enabled'],config['interval_minutes'],config['keep_recent']),(False,15,20))
        self.assertFalse(layout.tick(self.root)['created'])
    def test_frequency_survives_restart_and_automatic_expiry_skips_pinned(self):
        pinned=layout.backup(self.root,dict(label='固定桌面',protected=True))
        with patch.object(layout.time,'time',return_value=1000):
            first=layout.tick(self.root);self.assertTrue(first['created'])
            self.assertFalse(layout.tick(self.root)['created'])
            layout.settings(self.root,dict(enabled=True,interval_minutes=1,keep_recent=2))
        with patch.object(layout.time,'time',return_value=1059):self.assertFalse(layout.tick(self.root)['created'])
        with patch.object(layout.time,'time',return_value=1060):self.assertTrue(layout.tick(self.root)['created'])
        with patch.object(layout.time,'time',return_value=2000):self.assertTrue(layout.tick(self.root)['created'])
        records=layout.info(self.root)['backups'];self.assertEqual(len(records),3)
        self.assertTrue(any(r['id']==pinned['id'] and r['protected'] for r in records))
    def test_disable_and_invalid_settings_preserve_backups(self):
        old=layout.backup(self.root,{})
        with self.assertRaises(ValueError):layout.settings(self.root,dict(enabled=True,interval_minutes=0,keep_recent=2))
        layout.settings(self.root,dict(enabled=False,interval_minutes=1,keep_recent=2))
        self.assertFalse(layout.tick(self.root)['created']);self.assertTrue(layout._path(self.root,old['id']).exists())
    def test_automatic_failure_is_retried_without_overwriting_history(self):
        with patch.object(layout,'_native',side_effect=OSError('Explorer unavailable')),patch.object(layout.time,'time',return_value=1000):
            state=layout.tick(self.root);self.assertIn('Explorer',state['last_error']);self.assertEqual(state['next_due_at'],1060)
        self.assertEqual(layout.info(self.root)['backups'],[])
        with patch.object(layout.time,'time',return_value=1060):self.assertTrue(layout.tick(self.root)['created'])
        self.assertEqual(layout.info(self.root)['settings']['last_error'],'')
