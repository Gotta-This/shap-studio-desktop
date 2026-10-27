"""Slash count rows are data, and reporting notes are not category names."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from clinical_studio.word_batch_engine import read_word,default_batch_config,generate_batch
from clinical_studio.word_table_types import summary,slash_categories
from clinical_studio.word_scan import scan_word
from test_word_table_types import save
ROWS=[['项目','对照组（n=15）','试验组（n=15）','统计值','P值'],['性别（男/女，例，构成比）','9/6','8/7','0.136','0.713'],['年龄（岁，x±s）','45.67±10.20','47.13±11.02','0.378','0.708'],['创伤类型（锐器伤/钝器伤/动物咬伤/其他，例，构成比）','7/4/3/1','5/5/4/1','0.587','0.899'],['基础免疫史（完整/不完整/不详，例，构成比）','3/8/4','4/7/4','0.209','0.901']]
class SlashCategoriesTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'table.docx';save(self.path,[ROWS])
 def tearDown(self):self.temp.cleanup()
 def test_first_gender_row_is_data_and_keeps_source_location(self):
  r=read_word(self.path,['对照组','试验组']);fields=[f for f in r.typed_fields if f['name']=='性别']
  self.assertEqual(len(fields),2);self.assertEqual([f['counts'] for f in fields],[[9,6],[8,7]])
  for f in fields:
   self.assertEqual(f['kind'],'gender');self.assertEqual(f['labels'],['男','女']);self.assertTrue(f['confirmed']);self.assertEqual(f['source_cell']['row'],2)
   self.assertEqual(f['header_path'],['性别（男/女，例，构成比）'])
 def test_reporting_notes_removed_from_each_classification(self):
  fields=read_word(self.path,['对照组','试验组']).typed_fields
  self.assertEqual(next(f['labels'] for f in fields if f['name']=='创伤类型'),['锐器伤','钝器伤','动物咬伤','其他'])
  self.assertEqual(next(f['labels'] for f in fields if f['name']=='基础免疫史'),['完整','不完整','不详'])
  self.assertEqual(len(scan_word(self.path)['fields']),8)
 def test_generated_gender_and_category_counts_are_exact(self):
  r=read_word(self.path,['对照组','试验组']);c=default_batch_config(['对照组','试验组']);c['include_basics']=False;c['typed_fields']=r.typed_fields
  for g in c['groups']:g['n']=15
  result=generate_batch(c);index=result['columns'].index('性别')
  self.assertEqual([sum(row[index]=='男' for row in result['rows'] if row[1]==g) for g in ['对照组','试验组']],[9,8])
 def test_category_only_table_without_mean_row_is_kept(self):
  save(self.path,[ROWS[:2]]);r=read_word(self.path,['对照组','试验组']);self.assertEqual(len(r.typed_fields),2)
 def test_horizontal_slash_table_is_typed(self):
  save(self.path,[[['组别','例数','性别（男/女，例，构成比）'],['对照组','15','9/6'],['试验组','15','8/7']]])
  r=read_word(self.path,['对照组','试验组']);self.assertEqual(len(r.typed_fields),2);self.assertTrue(all(f['kind']=='gender' for f in r.typed_fields))
 def test_inconsistent_counts_require_review(self):
  f=summary('性别（男/女，例，构成比）','对照组','9/5',15,1);self.assertFalse(f['confirmed'])
  self.assertIsNone(slash_categories('性别（男/女，例，构成比）','9/5/1'))
  self.assertEqual(summary('体重指数（kg/m²）','对照组','23.1',15,1)['kind'],'unknown')
