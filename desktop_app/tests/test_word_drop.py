"""Finder drag/drop rejects non-Word files and never replaces data without consent."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QMimeData,QUrl,QPoint,QPointF,Qt
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QFileDialog
from clinical_studio.word_batch import WordBatchTool
from test_prose_table_workflow import make_docx,SECOND
APP=QApplication.instance() or QApplication([])

class WordDropTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.first=self.root/'first.docx';self.second=self.root/'second.DOCX'
        make_docx(self.first,SECOND);make_docx(self.second,SECOND.replace('58.6','59.6'))
        self.t=WordBatchTool();self.t.show();APP.processEvents()
    def tearDown(self):self.t.close();self.t.deleteLater();APP.processEvents();self.tmp.cleanup()
    def mime(self,*paths):
        data=QMimeData();data.setUrls([p if isinstance(p,QUrl) else QUrl.fromLocalFile(str(p)) for p in paths]);return data
    def enter(self,mime,widget=None):
        event=QDragEnterEvent(QPoint(8,8),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        APP.sendEvent(widget or self.t,event);return event
    def drop(self,mime,widget=None):
        target=widget or self.t
        self.assertTrue(self.enter(mime,target).isAccepted())
        event=QDropEvent(QPointF(8,8),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        APP.sendEvent(target,event);APP.processEvents();return event
    def current(self):
        t=self.t;t.use_word_prose.setChecked(True);t.import_word(self.first);t.show_group_selection(['对照组','试验组']);t.confirm_groups()
        row=next(i for i,(vi,p,_) in enumerate(t.prose_table_editor.rows) if vi is not None and t.prose_table_editor.study()['variables'][vi]['name']=='BMI' and p=='summary')
        t.prose_table_editor.table.item(row,4).setText('24.5±3.1');t.result={'test':'generated data'}
    def test_first_drop_on_import_button_without_confirmation(self):
        with patch.object(self.t,'confirm_word_replacement') as confirm:
            event=self.drop(self.mime(self.first),self.t.import_button)
        self.assertTrue(event.isAccepted());confirm.assert_not_called()
        self.assertEqual(self.t.pending_source,str(self.first.resolve()))
    def test_rejects_other_types_multi_files_directories_remote_and_text(self):
        for name in ('test.pdf','test.xlsx','test.png'):(self.root/name).write_text('test')
        for mime in [self.mime(self.root/'test.pdf'),self.mime(self.root/'test.xlsx'),self.mime(self.root/'test.png'),self.mime(self.first,self.second),self.mime(self.root),self.mime(QUrl('https://example.com/test.docx')),self.mime(self.root/'missing.docx')]:
            self.assertFalse(self.enter(mime).isAccepted())
        text=QMimeData();text.setText('text');self.assertFalse(self.enter(text).isAccepted())
        self.assertFalse(self.t.prose_table_editor.source.acceptDrops())
    def test_doc_extension_uses_same_import_and_confirmation(self):
        self.t.use_word_prose.setChecked(True)
        doc=self.root/'legacy.doc';doc.write_bytes(self.first.read_bytes())
        self.assertTrue(self.enter(self.mime(doc)).isAccepted())
        self.assertTrue(self.t.import_word(doc));self.assertEqual(self.t.pending_source,str(doc.resolve()))
        self.t.show_group_selection(['对照组','试验组']);self.t.confirm_groups();APP.processEvents()
        self.assertTrue(self.t.inline_prose_active)
        self.assertEqual([g['n'] for g in self.t.get_config()['groups']],[25,25])
        before=self.t.get_config()
        corrupt=self.root/'corrupt.doc';corrupt.write_bytes(b'bad doc')
        with patch('clinical_studio.word_formats.ensure_docx',side_effect=ValueError('转换失败')),patch.object(self.t,'confirm_word_replacement') as confirm:
            self.assertFalse(self.t.import_word(corrupt,confirm_replace=True))
        confirm.assert_not_called();self.assertEqual(self.t.get_config(),before)

    def test_cancel_preserves_current_word_edits_and_results(self):
        self.current();before=self.t.get_config();document=self.t.prose_table_editor.document;result=self.t.result
        with patch.object(self.t,'confirm_word_replacement',return_value=False) as confirm:
            event=self.drop(self.mime(self.second))
        confirm.assert_called_once();self.assertTrue(event.isAccepted())
        self.assertEqual(self.t.get_config(),before);self.assertIs(self.t.result,result);self.assertIs(self.t.prose_table_editor.document,document)
    def test_accept_clears_previous_data_and_stages_new_word(self):
        self.current()
        with patch.object(self.t,'confirm_word_replacement',return_value=True):event=self.drop(self.mime(self.second))
        self.assertTrue(event.isAccepted());self.assertEqual(self.t.pending_source,str(self.second.resolve()))
        self.assertEqual(self.t.source,'');self.assertIsNone(self.t.result);self.assertIsNone(self.t.prose_table_editor.document)
        self.assertFalse(self.t.groups_confirmed);self.assertEqual(self.t.metrics.rowCount(),0)
    def test_pending_word_also_requires_confirmation(self):
        self.t.import_word(self.first)
        with patch.object(self.t,'confirm_word_replacement',return_value=False) as confirm:self.drop(self.mime(self.second))
        confirm.assert_called_once();self.assertEqual(self.t.pending_source,str(self.first.resolve()))
    def test_corrupt_word_never_clears_existing_data_or_asks_to_replace(self):
        self.current();bad=self.root/'corrupt.docx';bad.write_bytes(b'not a docx');before=self.t.get_config()
        with patch.object(self.t,'confirm_word_replacement') as confirm:event=self.drop(self.mime(bad))
        self.assertTrue(event.isAccepted());confirm.assert_not_called();self.assertEqual(self.t.get_config(),before)
    def test_file_picker_uses_same_replacement_confirmation(self):
        self.t.import_word(self.first)
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(self.second),'')),patch.object(self.t,'confirm_word_replacement',return_value=False) as confirm:self.t.pick_word()
        confirm.assert_called_once();self.assertEqual(self.t.pending_source,str(self.first.resolve()))
    def test_confirmation_runs_only_after_drop_event_returns(self):
        self.t.import_word(self.first);mime=self.mime(self.second)
        self.assertTrue(self.enter(mime).isAccepted())
        event=QDropEvent(QPointF(8,8),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        with patch.object(self.t,'confirm_word_replacement',return_value=False) as confirm:
            APP.sendEvent(self.t,event);confirm.assert_not_called()
            self.assertEqual(self.t.pending_source,str(self.first.resolve()))
            APP.processEvents();confirm.assert_called_once()
        self.assertEqual(self.t.pending_source,str(self.first.resolve()))

    def test_five_workflow_tabs_are_in_requested_order(self):
        self.assertEqual([self.t.pages.tabText(i) for i in range(self.t.pages.count())],['1 · 基础资料','2 · 表格匹配','3 · 文字匹配','4 · 全部字段以及来源','5 · 生成与导出'])
        self.assertTrue(all(self.t.pages.isTabVisible(i) for i in range(5)))

    def test_busy_workflow_does_not_accept_drop(self):
        with patch.object(self.t,'is_running',return_value=True):self.assertFalse(self.enter(self.mime(self.second)).isAccepted())

if __name__=='__main__':unittest.main()
