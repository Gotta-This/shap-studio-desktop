"""Recognition precision defaults cover both table directions and prose."""
import os,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QFileDialog
from clinical_studio.app import create_application
from clinical_studio.word_batch import WordBatchTool
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.merged_table_verify import save_fixture
from clinical_studio.word_batch_engine import generate_batch
from clinical_studio.todos import TodoStore
APP=create_application([])
PROSE='对照组25例，男15例、女10例；BMI（22.80±3.10）kg/m²。试验组25例，男14例、女11例；BMI（23.10±3.40）kg/m²。'

class PrecisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.tool=WordBatchTool();self.tool.show();APP.processEvents()
 def tearDown(self):
  self.tool.close();self.tool.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.tmp.cleanup()
 def fixture(self,vertical=False):
  return save_fixture(Path(self.tmp.name)/'source.docx',[[['项目','对照组（25例）','试验组（25例）'],['时间','22.44±4.02','16.73±3.63']]] if vertical else [[['组别','例数','时间'],['对照组','25','22.44±4.02'],['试验组','25','16.73±3.63']]])
 def fields(self):
  c=self.tool.get_config();return c['indicators']+c['typed_fields']
 def test_default_zero_for_horizontal_and_vertical_means(self):
  for vertical in (False,True):
   self.tool.import_word(self.fixture(vertical));self.tool.confirm_groups()
   fields=self.fields();self.assertEqual(len(fields),2);self.assertTrue(all(f['digits']==0 for f in fields))
   result=generate_batch(self.tool.get_config());index=result['columns'].index('时间');self.assertTrue(all(float(row[index]).is_integer() for row in result['rows']))
 def test_follow_source_restores_before_confirmation(self):
  t=self.tool;t.import_word(self.fixture(True));t.decimal_mode.setCurrentIndex(t.decimal_mode.findData('source'));t.confirm_groups()
  self.assertTrue(all(f['digits']==2 for f in self.fields()))
 def test_preview_manual_precision_is_never_overwritten(self):
  t=self.tool;t.import_word(self.fixture(True));t.preview_draft['fields'][0]['digits']=3
  t.decimal_mode.setCurrentIndex(t.decimal_mode.findData('source'));t.confirm_groups()
  self.assertEqual([f['digits'] for f in self.fields()],[3,2])
 def test_prose_new_recognition_zero_and_follow_source(self):
  editor=self.tool.prose_table_editor;editor.source.setPlainText(PROSE);editor.convert()
  cells=editor.study()['variables'][1]['cells']
  self.assertEqual({c['digits'] for c in cells.values()},{0})
  self.tool.decimal_mode.setCurrentIndex(self.tool.decimal_mode.findData('source'));editor.convert()
  self.assertEqual({c['digits'] for c in editor.study()['variables'][1]['cells'].values()},{2})
 def test_config_reload_keeps_mode_and_manual_digits(self):
  t=self.tool;t.import_word(self.fixture());t.confirm_groups();t.metrics.item(0,5).setText('3');c=t.get_config();path=Path(self.tmp.name)/'config.json';path.write_text(json.dumps(c))
  with patch.object(QFileDialog,'getOpenFileName',return_value=(str(path),'JSON')):t.load_config()
  self.assertEqual(t.decimal_mode.currentData(),'zero');self.assertEqual(self.fields()[0]['digits'],3)
  t.refresh_rule_review();self.assertEqual(self.fields()[0]['digits'],3)
 def test_ungrouped_means_default_zero(self):
  p=save_fixture(Path(self.tmp.name)/'one.docx',[[['项目','数值（n=25）'],['时间','22.44±4.02']]])
  t=self.tool;t.import_word(p);t.ungrouped_option.setChecked(True);t.ungrouped_n.setValue(25);t.confirm_groups()
  self.assertTrue(t.groups_confirmed,t.message.text());self.assertEqual(self.fields()[0]['digits'],0)

class SidebarTests(unittest.TestCase):
 def test_hierarchy_badge_and_cross_page_state(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'CLINICAL_STUDIO_TODO_PATH':str(Path(tmp)/'todos.json')}):
   store=TodoStore();task=store.add('甲老师');store.add('乙老师');w=DesktopWindow();w.timer.stop();w.show();APP.processEvents()
   try:
    for key in ('category','numeric','word','shap'):
     w.open_module(key);w.refresh(force=True);b=w.boards[w.board_index];self.assertEqual(b.controls['nav-todo'].count,2);self.assertEqual(b.controls['sidebar-space'].text(),'我的空间');self.assertEqual(b.controls['sidebar-tools'].text(),'科研工具');self.assertGreater(b.controls['nav-category'].y(),b.controls['sidebar-tools'].y())
    store.update(task['id'],completed=True);w.refresh(force=True)
    self.assertTrue(all(b.controls['nav-todo'].count==1 for b in w.boards.values()))
   finally:w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

if __name__=='__main__':unittest.main()
