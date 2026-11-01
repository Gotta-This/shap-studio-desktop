"""Real directories, indexed files and cross-page todos survive failures/restarts."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from clinical_studio.manuscripts import WorkspaceStore, CATEGORIES, component, enable_workspace
from clinical_studio.todos import TodoStore


class ManuscriptStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.store = WorkspaceStore(self.base/'工作空间')
        self.task = self.store.create_task('冠心病论文', '张老师', tags=['预测模型','心血管'],
                                          deadline='2026-11-07', first_todo='核对审稿意见')

    def tearDown(self):
        self.temp.cleanup()

    def source(self, name='审稿意见.txt', content=b'first review'):
        path = self.base/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_real_hierarchy_and_existing_material_never_scanned(self):
        historical = self.store.root/'历史文稿.docx'
        historical.write_bytes(b'old')
        self.assertEqual(self.store.files(), [])
        self.assertEqual(self.store.files(self.task), [])
        task = self.store.task(self.task)
        folder = self.store.inside(task['directory'])
        self.assertEqual(set(p.name for p in folder.iterdir()), set(CATEGORIES))
        self.assertEqual(historical.read_bytes(), b'old')
        second = self.store.create_task('另一项任务', '张老师')
        self.assertEqual(self.store.task(second)['created_date'], task['created_date'])
        with self.assertRaises(ValueError):
            self.store.create_task('冠心病论文', '张老师')

    def test_windows_names_and_path_escape_are_rejected(self):
        for name in ['../危险', 'A/B', 'A\\B', 'NUL.txt', 'COM1', '名字.', 'x:y', '..']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                component(name)
        with self.assertRaises(ValueError):
            self.store.inside('../outside')
        outside = self.base/'outside'
        outside.mkdir()
        try:
            (self.store.root/'跳转').symlink_to(outside, target_is_directory=True)
        except OSError:
            return  # Windows may disable symlink creation for unprivileged users.
        with self.assertRaises(ValueError):
            self.store.inside('跳转/test')

    def test_copy_dedup_links_completion_and_restart(self):
        source = self.source()
        a = self.store.receive_files([source], self.task, ['原稿'], '核对审稿意见')
        path = self.store.file_path(a['file_ids'][0])
        self.assertEqual(path.read_bytes(), source.read_bytes())
        self.assertTrue(source.exists())
        todo = self.store.todos(self.task)[0]
        self.store.update_todo(todo['id'], completed=True)
        b = self.store.receive_files([source], self.task, ['原稿'], '核对审稿意见')
        self.assertEqual(b['received'], 0)
        self.assertEqual(a['file_ids'], b['file_ids'])
        reopened = WorkspaceStore(self.store.root, create=False)
        self.assertEqual(len(reopened.files(self.task)), 1)
        self.assertTrue(reopened.todos(self.task)[0]['completed'])
        self.assertEqual(reopened.todos(self.task)[0]['file_ids'], a['file_ids'])
        self.assertEqual(reopened.tasks()[0]['pending_count'], 0)

    def test_same_filename_different_content_is_preserved(self):
        first = self.source('one/data.csv', b'one')
        second = self.source('two/data.csv', b'two')
        self.store.receive_files([first, second], self.task, ['原始数据']*2)
        files = self.store.files(self.task)
        self.assertEqual(len(files), 2)
        self.assertEqual({self.store.file_path(f['id']).read_bytes() for f in files}, {b'one', b'two'})
        self.assertEqual(len({f['path'] for f in files}), 2)

    def test_rename_syncs_files_preserves_ids_dates_and_completed_todos(self):
        ids = self.store.receive_files([self.source()], self.task)['file_ids']
        task = self.store.task(self.task)
        todo = self.store.todos(self.task)[0]
        self.store.update_todo(todo['id'], completed=True, file_ids=ids)
        self.store.update_task(self.task, name='第二轮返修', client='李老师', tags=['修回'], status='返修中')
        changed = self.store.task(self.task)
        self.assertEqual(changed['created_date'], task['created_date'])
        self.assertFalse(self.store.inside(task['directory']).exists())
        self.assertTrue(self.store.file_path(ids[0]).is_file())
        self.assertIn('李老师', str(self.store.file_path(ids[0])))
        self.assertTrue(self.store.todos(self.task)[0]['completed'])
        self.assertEqual(self.store.todos(self.task)[0]['file_ids'], ids)

    def test_rename_collision_and_database_failure_leave_old_files_intact(self):
        task = self.store.task(self.task)
        original = self.store.inside(task['directory'])
        other = self.store.create_task('已有任务', '张老师')
        with self.assertRaises(ValueError):
            self.store.update_task(self.task, name='已有任务', client='张老师')
        with patch.object(self.store, 'event', side_effect=OSError('failed write')):
            with self.assertRaises(OSError):
                self.store.update_task(self.task, name='应回滚', client='张老师')
        self.assertEqual(self.store.task(self.task)['name'], task['name'])
        self.assertTrue(original.is_dir())
        self.assertFalse(self.store.inside((Path(task['directory']).parent/'应回滚').as_posix()).exists())
        self.assertTrue(self.store.inside(self.store.task(other)['directory']).exists())

    def test_failed_import_is_all_or_nothing_and_keeps_sources(self):
        source = self.source()
        with patch.object(self.store, 'event', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.receive_files([source], self.task)
        self.assertEqual(self.store.files(self.task), [])
        self.assertEqual(source.read_bytes(), b'first review')
        self.assertEqual(list(self.store.root.rglob('审稿意见.txt')), [])
        self.assertEqual(list(self.store.root.glob('.manuscript-import-*')), [])

    def test_inbox_archive_undo_and_conflicting_undo(self):
        fid = self.store.receive_files([self.source()])['file_ids'][0]
        original = self.store.file_path(fid)
        self.store.archive_files([fid], self.task, ['修改稿'])
        event = next(e for e in self.store.events() if e['kind'] == '归档材料')
        self.assertFalse(original.exists())
        self.assertEqual(self.store.files(self.task)[0]['category'], '修改稿')
        original.write_bytes(b'new user file')
        with self.assertRaises(ValueError):
            self.store.undo_archive(event['id'])
        self.assertEqual(original.read_bytes(), b'new user file')
        original.unlink()
        self.store.undo_archive(event['id'])
        self.assertEqual(len(self.store.files()), 1)
        self.assertTrue(original.exists())
        with self.assertRaises(ValueError):
            self.store.undo_archive(event['id'])

    def test_archive_rollback_and_linked_undo_require_explicit_unlink(self):
        fid = self.store.receive_files([self.source()])['file_ids'][0]
        original = self.store.file_path(fid)
        with patch.object(self.store, 'event', side_effect=OSError('failed save')):
            with self.assertRaises(OSError):
                self.store.archive_files([fid], self.task, ['图表'])
        self.assertTrue(original.is_file())
        self.assertEqual(len(self.store.files()), 1)
        self.store.archive_files([fid], self.task, ['原稿'], '核对审稿意见')
        event = self.store.events()[0]
        with self.assertRaises(ValueError):
            self.store.undo_archive(event['id'])
        todo = self.store.todos(self.task)[0]
        self.store.update_todo(todo['id'], file_ids=[])
        self.store.undo_archive(event['id'])
        self.assertEqual(self.store.todos(self.task)[0]['text'], '核对审稿意见')

    def test_missing_file_relocation_checks_content_and_keeps_state(self):
        source = self.source()
        fid = self.store.receive_files([source], self.task)['file_ids'][0]
        target = self.store.file_path(fid)
        target.unlink()
        with self.assertRaises(FileNotFoundError):
            self.store.file_path(fid)
        wrong = self.source('wrong.txt', b'wrong')
        with self.assertRaises(ValueError):
            self.store.relocate_file(fid, wrong)
        self.assertFalse(target.exists())
        self.store.relocate_file(fid, source)
        self.assertEqual(self.store.file_path(fid).read_bytes(), source.read_bytes())

    def test_search_tag_client_status_date_and_todo_filters(self):
        self.store.receive_files([self.source('图表说明.csv')], self.task)
        self.assertEqual(len(self.store.tasks(query='图表说明')), 1)
        self.assertEqual(len(self.store.tasks(query='审稿', client='张老师', tag='心血管', status='进行中', due_after='2026-11-01', due_before='2026-11-10', pending_only=True)), 1)
        self.assertEqual(self.store.tasks(tag='护理'), [])
        self.assertEqual(self.store.tasks(due_before='2026-11-06'), [])

    def test_existing_global_todos_link_without_migration_or_duplication(self):
        env = {'CLINICAL_STUDIO_WORKSPACE_CONFIG': str(self.base/'config.json'),
               'CLINICAL_STUDIO_TODO_PATH': str(self.base/'todos.json')}
        with patch.dict(os.environ, env):
            enable_workspace(self.store.root)
            todos = TodoStore()
            local = todos.add('独立待办')
            linked = next(t for t in todos.read() if t['id'].startswith('workspace:'))
            todos.update(linked['id'], completed=True, priority='high')
            todos.update(local['id'], name='独立待办修改')
            raw = json.loads(todos.path.read_text(encoding='utf-8'))['tasks']
            self.assertEqual(len(raw), 1)
            self.assertEqual(raw[0]['name'], '独立待办修改')
            self.assertTrue(self.store.todos(self.task)[0]['completed'])
            self.assertEqual(len(todos.read()), 2)
            self.assertEqual(len(todos.visible(True, query='张老师')), 1)
            with patch.object(WorkspaceStore, 'update_todo', side_effect=sqlite3.OperationalError('locked')):
                with self.assertRaisesRegex(ValueError, '未能保存'):
                    todos.update(linked['id'], completed=False)
            self.assertTrue(self.store.todos(self.task)[0]['completed'])

    def test_unavailable_workspace_preserves_independent_todos(self):
        env = {'CLINICAL_STUDIO_WORKSPACE_CONFIG': str(self.base/'config.json'),
               'CLINICAL_STUDIO_TODO_PATH': str(self.base/'todos.json')}
        with patch.dict(os.environ, env):
            enable_workspace(self.store.root)
            store = TodoStore()
            store.add('独立待办')
            self.store.path.rename(self.store.path.with_suffix('.backup'))
            self.assertEqual([t['name'] for t in store.read()], ['独立待办'])
            self.assertIn('暂不可用', store.workspace_error)


if __name__ == '__main__':
    unittest.main()
