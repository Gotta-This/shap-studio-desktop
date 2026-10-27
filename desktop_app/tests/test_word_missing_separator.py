"""Grouped vertical subcategories and malformed mean/SD must stay reviewable."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from clinical_studio.app import create_application
from clinical_studio.word_batch import WordBatchTool
from clinical_studio.word_batch_engine import read_word
from clinical_studio.word_scan import scan_word
from clinical_studio.word_table_types import header_group,header_n
from test_word_table_types import save
APP=create_application([])
BASE=[['项目','对照组（25例）','试验组（25例）','统计值','P值'],['年龄（岁）','44.84±9.75','46.40±10.18','0.554','0.582'],['性别','','','0.325','0.569'],['男','15（60.00）','13（52.00）','',''],['女','10（40.00）','12（48.00）','',''],['手术方式','','','',''],['腹腔镜','19（76.00）','17（68.00）','',''],['开腹','6（24.00）','8（32.00）','',''],['基础疾病','','','',''],['有','9（36.00）','11（44.00）','',''],['无','16（64.00）','14（56.00）','','']]
BROKEN=[['组别','例数','肠鸣音恢复时间（h）','首次排气时间（h）'],['对照组','25','22.444.02','35.846.20'],['试验组','25','16.763.63','27.565.42'],['t','','5.241','5.024'],['P','','＜0.001','＜0.001']]
class MissingSeparatorTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'tables.docx';save(self.path,[BASE,BROKEN])
 def tearDown(self):self.temp.cleanup()
 def test_group_headers_support_example_counts(self):
  for text in ['对照组（25例）','对照组 (n = 25)','对照组（N=25）']:
   self.assertEqual(header_group(text,['对照组']),'对照组');self.assertEqual(header_n(text),25)
  self.assertIsNone(header_n('术后25小时'));self.assertIsNone(header_group('对照组（术后25小时）',['对照组']))
 def test_vertical_categories_stay_one_variable(self):
  s=scan_word(self.path);self.assertEqual(s['candidates'],['对照组','试验组']);self.assertEqual(s['tables'][0]['orientation'],'竖表：组别在列')
  r=read_word(self.path,s['candidates']);self.assertEqual(r.group_sizes,dict.fromkeys(s['candidates'],25));self.assertEqual(r.group_matches,dict.fromkeys(s['candidates'],2))
  f=next(f for f in r.typed_fields if f['name']=='性别' and f['group']=='对照组')
  self.assertEqual(f['labels'],['男','女']);self.assertEqual(f['weights'],[60,40]);self.assertTrue(f['confirmed']);self.assertIn('15（60.00）',f['raw'])
  self.assertFalse(any(f['name'] in ['男','女','有','无','腹腔镜','开腹'] for f in r.typed_fields))
  self.assertEqual(next(f['kind'] for f in r.typed_fields if f['name']=='基础疾病'),'yesno')
 def test_malformed_statistics_remain_blank_and_pending(self):
  r=read_word(self.path,['对照组','试验组']);fields=[f for f in r.typed_fields if f['table']==2]
  self.assertEqual(len(fields),4)
  for f in fields:
   self.assertEqual(f['kind'],'mean_sd');self.assertIsNone(f['mean']);self.assertIsNone(f['sd']);self.assertFalse(f['confirmed']);self.assertIn('分隔符',f['review_note'])
  self.assertEqual(fields[0]['raw'],'22.444.02')
 def test_ui_import_confirm_and_generation_guard(self):
  t=WordBatchTool()
  try:
   self.assertTrue(t.import_word(self.path));t.confirm_groups();self.assertTrue(t.groups_confirmed,t.message.text());self.assertEqual(len(t.typed_specs),12)
   with self.assertRaises(ValueError):t.get_config()
  finally:t.close();t.deleteLater();APP.processEvents()
 def test_standard_flat_numeric_still_uses_legacy_route(self):
  save(self.path,[[['组别','例数','术后6 h'],['对照组','25','5.32±0.99'],['试验组','25','4.76±0.88']]])
  r=read_word(self.path,['对照组','试验组']);self.assertEqual(len(r.indicators),2);self.assertEqual(r.typed_fields,[])
