"""Source tables share a schema while retaining independent per-row parameters."""
import os,tempfile,unittest,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from PySide6.QtCore import Qt,QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QFileDialog,QPushButton
from PySide6.QtTest import QTest
from clinical_studio.app import create_application
from clinical_studio.strict_ui import DesktopWindow
from clinical_studio.word_batch_engine import generate_batch
from clinical_studio.resizable_fields import resize_field
from test_word_table_types import save
APP=create_application([])

def pending(name,group,table=1):return dict(name=name,group=group,table=table,kind='mean_sd',mean=None,sd=None,digits=2,lower=None,upper=None,raw='22.444.02',confirmed=False)
class SourceTablesTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.window=DesktopWindow();self.window.timer.stop();self.window.show();self.tool=self.window.open_module('word');self.pump()
 def pump(self):
  for _ in range(4):APP.processEvents()
 def tearDown(self):
  self.window.close();self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.temp.cleanup()
 def load(self):
  p=Path(self.temp.name)/'mixed.docx';save(p,[[['项目','对照组（25例）','试验组（25例）'],['年龄','50±4','51±5'],['感染','4（16.00）','1（4.00）']],[['组别','例数','时间'],['对照组','25','10±2'],['试验组','25','11±2']]])
  t=self.tool;t.import_word(p);t.confirm_groups();t.table_titles={'1':'表1.一般资料','2':'表2.恢复指标比较（x̄±s）'};t.source_tables.schedule();self.pump()
 def test_confirming_one_row_never_confirms_empty_peer_or_other_table(self):
  t=self.tool;fields=[pending('时间','对照组'),pending('时间','试验组'),pending('时间','对照组',2),pending('其他','对照组')];fields[1]['confirmed']=True;t.set_typed_fields(fields)
  def fill():
   d=t.field_dialog;d.inputs['mean'].setText('22.44');d.inputs['sd'].setText('4.02');d.sync.setChecked(True);d.apply()
  QTimer.singleShot(50,fill);t.edit_typed_field(0);self.pump()
  self.assertTrue(t.typed_specs[0]['confirmed']);self.assertEqual(t.typed_specs[0]['mean'],22.44)
  self.assertTrue(all(not f['confirmed'] and f['mean'] is None and f['sd'] is None for f in t.typed_specs[1:]))
 def test_confirmation_never_erases_existing_peer_values(self):
  t=self.tool;a=pending('时间','对照组');b=pending('时间','试验组');b.update(mean=7.5,sd=1.2,confirmed=True);t.set_typed_fields([a,b])
  def fill():
   d=t.field_dialog;d.inputs['mean'].setText('8.1');d.inputs['sd'].setText('2.3');d.apply()
  QTimer.singleShot(50,fill);t.edit_typed_field(0);self.pump();self.assertEqual({key:t.typed_specs[1][key] for key in b},b)
 def test_separate_source_tables_have_five_columns_and_full_titles(self):
  self.load();t=self.tool;panel=t.source_tables;self.assertEqual(set(panel.tables),{1,2})
  for source,table in panel.tables.items():
   self.assertEqual([table.horizontalHeaderItem(i).text() for i in range(5)],['输出列名','组别','数据类型','生成规则','Word原文']);self.assertTrue(table.isVisible());self.assertIn(t.table_titles[str(source)],[label.text() for label in panel.blocks[source].findChildren(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel)])
  self.assertFalse(t.metrics.isVisible());self.assertFalse(t.typed_table.isVisible());self.assertFalse(t.typed_label.isVisible())
 def test_inline_numeric_edits_only_change_target_row_and_survive_config(self):
  self.load();t=self.tool;panel=t.source_tables
  entry=panel.numeric_inputs[(1,0)]['mean'];entry.selectAll();QTest.keyClicks(entry,'52.75');self.pump()
  self.assertEqual(t.typed_specs[0]['mean'],52.75);self.assertEqual(t.typed_specs[1]['mean'],51.)
  entry=panel.numeric_inputs[(2,0)]['mean'];entry.selectAll();QTest.keyClicks(entry,'12.25');self.pump()
  c=t.get_config();self.assertEqual(c['indicators'][0]['mean'],12.25);self.assertEqual(c['indicators'][1]['mean'],11.)
  p=Path(self.temp.name)/'config.json';p.write_text(json.dumps(c))
  with patch.object(QFileDialog,'getOpenFileName',return_value=(str(p),'')):t.load_config()
  self.pump();self.assertEqual(t.get_config(),c);self.assertEqual(t.source_tables.numeric_inputs[(2,0)]['mean'].text(),'12.25')
 def test_inline_missing_values_require_each_row_and_preserve_other_rows(self):
  t=self.tool;t.set_typed_fields([pending('时间','对照组'),pending('时间','中药组')]);self.pump();panel=t.source_tables
  for key,value in [('mean','10'),('sd','2')]:QTest.keyClicks(panel.numeric_inputs[(1,0)][key],value)
  self.pump();self.assertTrue(t.typed_specs[0]['confirmed']);self.assertFalse(t.typed_specs[1]['confirmed'])
  with self.assertRaises(ValueError):t.get_config()
 def test_manual_indicators_form_a_separate_source_and_deletion_is_scoped(self):
  self.load();t=self.tool;t.add_indicator();self.pump();self.assertIn(0,t.source_tables.tables)
  table=t.source_tables.tables[2];table.setCurrentCell(0,0);table.selectRow(0);t.remove_indicator();self.pump()
  self.assertEqual(t.metrics.rowCount(),2);self.assertIn(0,t.source_tables.tables);self.assertNotIn(2,t.source_tables.tables)
 def test_resizing_one_table_retains_others_and_edits(self):
  self.load();p=self.tool.source_tables;before=p.tables[2].height();resize_field(p.tables[1],600,800);self.pump();self.assertEqual(p.tables[2].height(),before)
  p.schedule();self.pump();self.assertEqual(p.tables[1].height(),800)

 def test_mean_parameters_are_flat_without_completion_caption(self):
  from PySide6.QtWidgets import QLabel
  self.load();table=self.tool.source_tables.tables[1];panel=table.cellWidget(0,3);self.pump()
  entries=list(self.tool.source_tables.numeric_inputs[(1,0)].values());self.assertEqual(len({entry.mapTo(panel,entry.rect().topLeft()).y() for entry in entries}),1)
  self.assertFalse(any('参数已填写' in label.text() or '仅应用于本行' in label.text() for label in panel.findChildren(QLabel)))
  self.assertLess(table.rowHeight(0),100)
  self.assertGreaterEqual(table.columnWidth(3),panel.minimumSizeHint().width())
 def test_column_widths_follow_content_and_viewport(self):
  from PySide6.QtWidgets import QTableWidgetItem,QWidget,QComboBox,QHBoxLayout
  from clinical_studio.word_source_tables import SourceTable,HEADERS
  table=SourceTable(1,5);table.setHorizontalHeaderLabels(HEADERS)
  for col,text in [(0,'性别'),(1,'对照组'),(4,'9/6')]:table.setItem(0,col,QTableWidgetItem(text))
  cell=QWidget();line=QHBoxLayout(cell);combo=QComboBox();combo.addItem('分类：男 / 女');line.addWidget(combo);table.setCellWidget(0,2,cell)
  rule=QWidget();rule.setProperty('ruleMinimumWidth',524);table.setCellWidget(0,3,rule);table.resize(1500,220);table.show();self.pump();table.fit_columns()
  try:
   narrow=table.columnWidth(0);table.item(0,0).setText('干预后每日痉挛次数');table.fit_columns();self.assertGreater(table.columnWidth(0),narrow)
   self.assertLessEqual(sum(table.columnWidth(i) for i in range(5)),table.viewport().width())
   before=table.columnWidth(3);table.resize(1800,220);self.pump();self.assertGreaterEqual(table.columnWidth(3),before);self.assertLess(table.width(),1500)
   capped=table.columnWidth(3);table.resize(2000,220);self.pump();self.assertEqual(table.columnWidth(3),capped)
   table.resize(700,220);self.pump();self.assertGreaterEqual(table.columnWidth(3),524);self.assertGreater(table.horizontalScrollBar().maximum(),0)
  finally:table.close();table.deleteLater();self.pump()

 def test_compact_summaries_and_content_width_cap(self):
  from PySide6.QtWidgets import QLabel
  self.load();table=self.tool.source_tables.tables[1];table.fit_columns();self.pump()
  self.assertLess(table.maximumWidth(),1400)
  self.assertLessEqual(table.rowHeight(0),74)
  field=dict(kind='category',labels=['男','女'],weights=[53.333333,46.666667],source_n=15,confirmed=True)
  rule=self.tool.source_tables.other_rule(1,0,field)
  try:
   summary=rule.findChild(QLabel,'rule-summary').text()
   self.assertIn('53.33%',summary);self.assertNotIn('333333',summary)
   self.assertIn('约8例',summary)
  finally:rule.deleteLater()
