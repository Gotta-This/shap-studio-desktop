import ctypes,json,tempfile,unittest,zipfile
import desktop_layout_assistant as assistant
import desktop_layout_assistant_control as control
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
        self.assistant=patch.object(assistant,'probe',return_value=dict(checked=True,running=False,installed=False,data_found=False,message=''));self.assistant_mock=self.assistant.start()
        self.windows=patch.object(layout.sys,'platform','win32');self.windows.start()
        self.native=patch.object(layout,'_native',return_value=self.fake);self.native.start()
    def tearDown(self):self.native.stop();self.windows.stop();self.assistant.stop();self.tmp.cleanup()

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


class AssistantTests(DesktopFixture,unittest.TestCase):
    def start_assistant(self):
        root=self.root/'vendor';root.mkdir();(root/'layout.ini').write_text('synthetic layout 1')
        self.assistant_mock.return_value.update(running=True,installed=True,data_found=True)
        mock=patch.object(assistant,'data_root',return_value=root);mock.start();self.addCleanup(mock.stop)
        return root
    def test_dual_backup_deduplicates_and_reads_back_vendor_bytes(self):
        root=self.start_assistant()
        one=layout.backup(self.root,{})
        two=layout.backup(self.root,{})
        self.assertEqual(one['assistant']['status'],'saved')
        self.assertEqual(one['assistant']['archive'],two['assistant']['archive'])
        archives=list((layout._folder(self.root)/'360-data').glob('*.zip'));self.assertEqual(len(archives),1)
        with zipfile.ZipFile(archives[0]) as archive:self.assertEqual(archive.read('layout.ini'),(root/'layout.ini').read_bytes())
        self.assertEqual(layout._read(layout._path(self.root,one['id']))['icons'],self.fake.current['icons'])
    def test_pin_and_delete_keep_shared_archive_until_last_reference(self):
        self.start_assistant()
        one=layout.backup(self.root,dict(protected=True));two=layout.backup(self.root,{})
        archive=layout._folder(self.root)/'360-data'/one['assistant']['archive']
        layout.delete(self.root,dict(id=two['id']));self.assertTrue(archive.exists())
        with self.assertRaises(ValueError):layout.delete(self.root,dict(id=one['id']))
        layout.protect(self.root,dict(id=one['id'],protected=False));layout.delete(self.root,dict(id=one['id']))
        self.assertFalse(archive.exists())
    def test_vendor_failure_preserves_windows_and_warns_scheduler(self):
        self.start_assistant()
        with patch.object(assistant,'MAX_BYTES',1):
            value=layout.backup(self.root,{})
            state=layout.tick(self.root)
        self.assertEqual(value['assistant']['status'],'failed');self.assertTrue(state['created']);self.assertTrue(state['last_error'])
        self.assertEqual(len(layout.history(self.root)[0]),2)
    def test_changed_vendor_file_is_not_recorded_as_success(self):
        self.start_assistant()
        original=assistant._inventory
        calls=[]
        def changing(root):
            value=original(root);calls.append(1)
            return value if len(calls)==1 else value+ [('new',0,0)]
        with patch.object(assistant,'_inventory',side_effect=changing):value=layout.backup(self.root,{})
        self.assertEqual(value['assistant']['status'],'failed')
        self.assertEqual(list((layout._folder(self.root)/'360-data').iterdir()),[])
    def test_running_assistant_allows_native_restore_with_scope_warning(self):
        saved=layout.backup(self.root,{})
        self.fake.current['icons'][0].update(x=400,y=200)
        self.start_assistant()
        preview=layout.preview(self.root,dict(id=saved['id']))
        self.assertIn('仅恢复 Windows',preview['assistant_warning'])
        with patch.object(control,'ProcessCycle',side_effect=AssertionError('must not close 360 for native restore')):
            result=layout.restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual(result['unmatched_positions'],0);self.assertEqual(len(self.fake.calls),1)
        self.assertIn('360',result['assistant_warning'])
    def test_feature_switch_survives_reload_and_stops_all_layout_operations(self):
        saved=layout.backup(self.root,{})
        layout.settings(self.root,dict(feature_enabled=False,enabled=True,interval_minutes=10,keep_recent=144))
        self.assertFalse(layout.info(self.root)['settings']['feature_enabled'])
        self.assertIsNone(layout.tick(self.root)['created'])
        with self.assertRaisesRegex(ValueError,'工具已关闭'):layout.backup(self.root,{})
        with self.assertRaisesRegex(ValueError,'工具已关闭'):layout.preview(self.root,dict(id=saved['id']))
        with self.assertRaisesRegex(ValueError,'工具已关闭'):layout.restore(self.root,dict(id=saved['id']))
        layout.settings(self.root,dict(feature_enabled=True,enabled=False,interval_minutes=10,keep_recent=144))
        self.assertEqual(layout.backup(self.root,{})['assistant']['status'],'not_running')
    def test_missing_directory_is_partial_failure(self):
        self.assistant_mock.return_value.update(running=True)
        with patch.object(assistant,'data_root',return_value=self.root/'missing'):
            self.assertEqual(layout.backup(self.root,{})['assistant']['status'],'failed')
    def test_process_names_are_specific_to_desktop_ui(self):
        self.assertTrue(assistant.is_desktop_assistant('360DesktopLite64.exe'))
        for name in ('360tray.exe','360DesktopService.exe','DesktopMgr.exe'):
            self.assertFalse(assistant.is_desktop_assistant(name))
    def test_real_probe_distinguishes_data_from_running_state(self):
        self.assistant.stop()
        with patch.object(assistant,'_windows_processes',return_value=[]),patch.object(assistant,'_registered',return_value=True),patch.object(assistant,'data_root',return_value=None):
            state=assistant.probe()
        self.assertTrue(state['checked']);self.assertTrue(state['installed']);self.assertFalse(state['running']);self.assertFalse(state['data_found'])
        self.assistant.start()

    def test_pruning_keeps_protected_vendor_archive_and_removes_expired_one(self):
        root=self.start_assistant()
        layout.settings(self.root,dict(enabled=False,interval_minutes=10,keep_recent=1))
        pinned=layout.backup(self.root,dict(protected=True))
        (root/'layout.ini').write_text('synthetic layout 2');old=layout.backup(self.root,{})
        (root/'layout.ini').write_text('synthetic layout 3');new=layout.backup(self.root,{})
        archives={p.name for p in (layout._folder(self.root)/'360-data').glob('*.zip')}
        self.assertEqual(archives,{pinned['assistant']['archive'],new['assistant']['archive']})
        self.assertNotIn(old['assistant']['archive'],archives)
    def test_symlinked_vendor_content_is_rejected(self):
        root=self.start_assistant()
        (root/'link').symlink_to(root/'layout.ini')
        self.assertEqual(layout.backup(self.root,{})['assistant']['status'],'failed')

class AssistantRestoreTests(DesktopFixture,unittest.TestCase):
    start_assistant=AssistantTests.start_assistant
    def setup_backup(self):
        root=self.start_assistant();saved=layout.backup(self.root,{})
        (root/'layout.ini').write_text('current layout before restore')
        self.assistant_mock.return_value['running']=False
        return root,saved
    def test_restores_exact_files_and_preserves_entire_original_directory(self):
        root,saved=self.setup_backup();(root/'new-only.dat').write_bytes(b'current-only')
        preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        result=layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual((root/'layout.ini').read_text(),'synthetic layout 1')
        self.assertFalse((root/'new-only.dat').exists())
        rollback=Path(result['rollback_directory'])
        self.assertEqual((rollback/'layout.ini').read_text(),'current layout before restore')
        self.assertEqual((rollback/'new-only.dat').read_bytes(),b'current-only')
        self.assertEqual(self.fake.calls,[])
    def test_current_change_invalidates_confirmation(self):
        root,saved=self.setup_backup();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        (root/'layout.ini').write_text('changed after preview')
        with self.assertRaisesRegex(ValueError,'重新预览'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual((root/'layout.ini').read_text(),'changed after preview')
    def test_restarted_assistant_blocks_overwrite(self):
        root,saved=self.setup_backup();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        self.assistant_mock.return_value['running']=True
        with patch.object(control,'process_snapshot',return_value=[]),self.assertRaisesRegex(ValueError,'重新预览'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual((root/'layout.ini').read_text(),'current layout before restore')
    def test_commit_failure_rolls_back_without_losing_configuration(self):
        import desktop_layout_assistant_restore as restore
        root,saved=self.setup_backup();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        replace=restore.os.replace
        def fail_stage(source,destination):
            if Path(source).name.startswith('.360DesktopLite-restore-'):raise OSError('simulated locked directory')
            return replace(source,destination)
        with patch.object(restore.os,'replace',side_effect=fail_stage):
            with self.assertRaisesRegex(ValueError,'已保留或回退'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual((root/'layout.ini').read_text(),'current layout before restore')
    def test_corrupt_archive_never_changes_live_configuration(self):
        root,saved=self.setup_backup()
        path=layout._folder(self.root)/'360-data'/saved['assistant']['archive']
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('layout.ini','tampered')
        with self.assertRaisesRegex(ValueError,'完整性校验失败'):layout.assistant_preview(self.root,dict(id=saved['id']))
        self.assertEqual((root/'layout.ini').read_text(),'current layout before restore')
    def test_unsafe_zip_paths_are_rejected_before_modification(self):
        root,saved=self.setup_backup()
        path=layout._folder(self.root)/'360-data'/saved['assistant']['archive']
        for name in ('../outside','C:/outside','dir\\outside','file:stream','NUL.txt','dir./file','/absolute'):
            with self.subTest(name=name):
                with zipfile.ZipFile(path,'w') as archive:archive.writestr(name,'unsafe')
                with self.assertRaises(ValueError):layout.assistant_preview(self.root,dict(id=saved['id']))
                self.assertEqual((root/'layout.ini').read_text(),'current layout before restore')
    def test_missing_directory_can_be_created_and_feature_off_blocks_vendor_restore(self):
        import shutil
        root,saved=self.setup_backup();shutil.rmtree(root)
        preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        self.assertFalse(preview['current_exists'])
        result=layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual(result['rollback_directory'],'');self.assertTrue((root/'layout.ini').is_file())
        layout.settings(self.root,dict(feature_enabled=False,enabled=False,interval_minutes=10,keep_recent=144))
        with self.assertRaisesRegex(ValueError,'工具已关闭'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))

    def test_post_write_verification_failure_restores_original(self):
        import desktop_layout_assistant_restore as restore
        root,saved=self.setup_backup();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        current=restore._current;calls=[]
        def corrupt_after_commit(path):
            calls.append(1)
            if (path/'layout.ini').read_text()=='synthetic layout 1':(path/'layout.ini').write_text('simulated corruption')
            return current(path)
        with patch.object(restore,'_current',side_effect=corrupt_after_commit):
            with self.assertRaisesRegex(ValueError,'写入后内容校验失败'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual((root/'layout.ini').read_text(),'current layout before restore')
    def test_rollback_failure_keeps_original_and_logs_no_paths(self):
        import desktop_layout_assistant_restore as restore
        root,saved=self.setup_backup();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        replace=restore.os.replace
        def locked(source,destination):
            if Path(source).name.startswith(('.360DesktopLite-restore-','.360DesktopLite-before-restore-')):raise OSError('simulated lock')
            return replace(source,destination)
        with patch.object(restore.os,'replace',side_effect=locked):
            with self.assertRaisesRegex(ValueError,'自动回退失败'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        rollback=list(root.parent.glob('.360DesktopLite-before-restore-*'));self.assertEqual(len(rollback),1)
        self.assertEqual((rollback[0]/'layout.ini').read_text(),'current layout before restore')
        report=layout.diagnostics(self.root)['content'];self.assertNotIn(str(root.parent),report);self.assertNotIn('layout.ini',report)
    def test_case_aliases_and_zip_symlinks_are_rejected(self):
        root,saved=self.setup_backup();path=layout._folder(self.root)/'360-data'/saved['assistant']['archive']
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('FILE','1');archive.writestr('file','2')
        with self.assertRaisesRegex(ValueError,'重复文件'):layout.assistant_preview(self.root,dict(id=saved['id']))
        entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=0o120777<<16
        with zipfile.ZipFile(path,'w') as archive:archive.writestr(entry,'outside')
        with self.assertRaisesRegex(ValueError,'链接或特殊文件'):layout.assistant_preview(self.root,dict(id=saved['id']))


class AutomaticAssistantRestoreTests(DesktopFixture,unittest.TestCase):
    start_assistant=AssistantTests.start_assistant
    def setup_auto(self):
        root=self.start_assistant();saved=layout.backup(self.root,{})
        (root/'layout.ini').write_text('live data')
        snapshot=patch.object(control,'process_snapshot',return_value=[dict(pid=123,low=456,high=0,path='360Desktop.exe',size=1,modified=1)])
        snapshot.start();self.addCleanup(snapshot.stop)
        return root,saved
    def test_graceful_close_flush_restore_and_restart(self):
        root,saved=self.setup_auto()
        preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        self.assertTrue(preview['auto_restart'])
        with patch.object(control,'ProcessCycle') as cycle:
            def shutdown():
                (root/'layout.ini').write_text('final flushed configuration')
                self.assistant_mock.return_value['running']=False
            cycle.return_value.shutdown.side_effect=shutdown
            cycle.return_value.resume.return_value=True
            result=layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
            cycle.return_value.shutdown.assert_called_once();cycle.return_value.resume.assert_called_once();cycle.return_value.close.assert_called_once()
        self.assertTrue(result['restarted']);self.assertEqual((root/'layout.ini').read_text(),'synthetic layout 1')
        self.assertEqual((Path(result['rollback_directory'])/'layout.ini').read_text(),'final flushed configuration')
    def test_shutdown_refusal_does_not_overwrite(self):
        root,saved=self.setup_auto();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        with patch.object(control,'ProcessCycle') as cycle:
            cycle.return_value.shutdown.side_effect=ValueError('refused normal exit')
            with self.assertRaisesRegex(ValueError,'refused normal exit'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
            cycle.return_value.resume.assert_called_once();cycle.return_value.close.assert_called_once()
        self.assertEqual((root/'layout.ini').read_text(),'live data')
    def test_restart_failure_does_not_hide_successful_file_restore(self):
        root,saved=self.setup_auto();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        with patch.object(control,'ProcessCycle') as cycle:
            cycle.return_value.shutdown.side_effect=lambda:self.assistant_mock.return_value.update(running=False)
            cycle.return_value.resume.return_value=False
            result=layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertFalse(result['restarted']);self.assertIn('手动打开',result['message']);self.assertEqual((root/'layout.ini').read_text(),'synthetic layout 1')
    def test_changed_process_generation_requires_new_confirmation(self):
        root,saved=self.setup_auto();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        with patch.object(control,'process_snapshot',return_value=[dict(pid=123,low=999,high=0)]),patch.object(control,'ProcessCycle') as cycle:
            with self.assertRaisesRegex(ValueError,'重新预览'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
            cycle.assert_not_called()
        self.assertEqual((root/'layout.ini').read_text(),'live data')
    def test_write_failure_restarts_after_rollback(self):
        import desktop_layout_assistant_restore as restore
        root,saved=self.setup_auto();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        with patch.object(control,'ProcessCycle') as cycle,patch.object(restore,'_restore_stopped',side_effect=ValueError('write failed and rolled back')):
            cycle.return_value.shutdown.side_effect=lambda:self.assistant_mock.return_value.update(running=False)
            with self.assertRaisesRegex(ValueError,'write failed'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
            cycle.return_value.resume.assert_called_once()
        self.assertEqual((root/'layout.ini').read_text(),'live data')
    def test_unsafe_recovery_failure_does_not_restart_into_missing_profile(self):
        import desktop_layout_assistant_restore as restore
        root,saved=self.setup_auto();preview=layout.assistant_preview(self.root,dict(id=saved['id']))
        with patch.object(control,'ProcessCycle') as cycle,patch.object(restore,'_restore_stopped',side_effect=restore.RecoveryRequired('manual recovery needed')):
            cycle.return_value.shutdown.side_effect=lambda:self.assistant_mock.return_value.update(running=False)
            with self.assertRaisesRegex(ValueError,'manual recovery'):layout.assistant_restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
            cycle.return_value.resume.assert_not_called();cycle.return_value.close.assert_called_once()


class RestartManagerTests(unittest.TestCase):
    def test_windows_struct_layout_and_graceful_flags(self):
        from unittest.mock import MagicMock
        self.assertEqual(ctypes.sizeof(control.FileTime),8);self.assertEqual(ctypes.sizeof(control.UniqueProcess),12)
        api=MagicMock()
        def start(handle,flags,key):handle._obj.value=42;return 0
        api.RmStartSession.side_effect=start;api.RmRegisterResources.return_value=0;api.RmShutdown.return_value=0
        process=dict(pid=123,low=456,high=0,path='C:/360/360Desktop.exe')
        with patch.object(control.C,'WinDLL',return_value=api,create=True),patch.object(control,'_wait_running',return_value=True):
            cycle=control.ProcessCycle([process]);cycle.shutdown();self.assertTrue(cycle.resume());cycle.close()
        args=api.RmRegisterResources.call_args.args
        self.assertEqual((args[1],args[3],args[5]),(0,1,0));self.assertEqual(args[4][0].pid,123)
        api.RmShutdown.assert_called_once_with(42,0,None);api.RmRestart.assert_called_once_with(42,0,None);api.RmEndSession.assert_called_once_with(42)
    def test_non_desktop_process_is_never_registered_for_shutdown(self):
        from unittest.mock import MagicMock
        api=MagicMock()
        with patch.object(control.C,'WinDLL',return_value=api,create=True):
            cycle=control.ProcessCycle([dict(path='C:/Windows/explorer.exe')])
            with self.assertRaisesRegex(ValueError,'非 360'):cycle.shutdown()
        api.RmStartSession.assert_not_called()


class NativeRestoreAssistantTests(DesktopFixture,unittest.TestCase):
    def test_late_assistant_reversion_is_not_reported_as_success(self):
        saved=layout.backup(self.root,{})
        self.fake.current['icons'][0].update(x=400,y=200)
        self.assistant_mock.return_value['running']=True
        preview=layout.preview(self.root,dict(id=saved['id']))
        def revert(delay):self.fake.current['icons'][0].update(x=400,y=200)
        with patch.object(layout.time,'sleep',side_effect=revert):
            result=layout.restore(self.root,dict(id=saved['id'],fingerprint=preview['fingerprint']))
        self.assertEqual(result['unmatched_positions'],1);self.assertIn('仅恢复 Windows',result['assistant_warning'])


class AutomaticRestartFallbackTests(unittest.TestCase):
    def api(self):
        from unittest.mock import MagicMock
        return MagicMock()
    def test_fallback_launches_only_observed_executable_without_shell(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'360Desktop.exe';path.write_bytes(b'synthetic exe')
            item=dict(pid=123,low=456,high=0,path=str(path),size=path.stat().st_size,modified=path.stat().st_mtime_ns)
            api=self.api()
            with patch.object(control.C,'WinDLL',return_value=api,create=True),patch.object(control,'_wait_running',side_effect=[False,True]),patch.object(control.subprocess,'Popen') as popen:
                cycle=control.ProcessCycle([item]);cycle.session=42;cycle.attempted=True
                self.assertTrue(cycle.resume())
                self.assertEqual(popen.call_args.args[0],[str(path)])
                self.assertFalse(popen.call_args.kwargs['shell'])
    def test_changed_executable_is_not_launched(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'360Desktop.exe';path.write_bytes(b'changed exe')
            item=dict(pid=123,low=456,high=0,path=str(path),size=1,modified=0)
            with patch.object(control.C,'WinDLL',return_value=self.api(),create=True),patch.object(control,'_wait_running',return_value=False),patch.object(control.subprocess,'Popen') as popen:
                cycle=control.ProcessCycle([item]);cycle.session=42;cycle.attempted=True
                self.assertFalse(cycle.resume());popen.assert_not_called()
    def test_denied_shutdown_never_requests_force(self):
        api=self.api()
        def start(handle,flags,key):handle._obj.value=42;return 0
        api.RmStartSession.side_effect=start;api.RmRegisterResources.return_value=0;api.RmShutdown.return_value=351
        with patch.object(control.C,'WinDLL',return_value=api,create=True):
            cycle=control.ProcessCycle([dict(pid=123,low=456,high=0,path='C:/360/360Desktop.exe')])
            with self.assertRaisesRegex(ValueError,'未覆盖配置'):cycle.shutdown()
            cycle.close()
        api.RmShutdown.assert_called_once_with(42,0,None)
