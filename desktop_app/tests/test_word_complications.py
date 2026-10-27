"""Caption context identifies consistent complication counts as yes/no."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from clinical_studio.word_batch_engine import W,read_word,default_batch_config,generate_batch,export_batch
from clinical_studio.word_scan import scan_word
from clinical_studio.word_table_types import summary
from clinical_studio.typed_field_ui import convert
from test_word_table_types import save
ROWS=[['组别','例数','切口感染','恶心呕吐','总发生率'],['对照组','25','2（8.00）','4（16.00）','6（24.00）'],['试验组','25','0（0.00）','1（4.00）','1（4.00）']]
def caption(path,title):
 with ZipFile(path) as z:root=ET.fromstring(z.read('word/document.xml'))
 body=root.find(W+'body')
 for previous in list(body.findall(W+'p')):body.remove(previous)
 p=ET.Element(W+'p');ET.SubElement(ET.SubElement(p,W+'r'),W+'t').text=title;body.insert(0,p)
 with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(root))
class ComplicationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'counts.docx';save(self.path,[ROWS]);caption(self.path,'表4.两组并发症率比较 n，%')
 def tearDown(self):self.temp.cleanup()
 def test_scan_and_import_auto_confirm_only_component_fields(self):
  for fields in [read_word(self.path,['对照组','试验组']).typed_fields,scan_word(self.path)['fields']]:
   individual=[f for f in fields if not f.get('aggregate_pending')];aggregate=[f for f in fields if f.get('aggregate_pending')]
   self.assertEqual(len(individual),4);self.assertTrue(all(f['kind']=='yesno' and f['confirmed'] and f['labels']==['有','无'] for f in individual))
   self.assertEqual(len(aggregate),2);self.assertTrue(all(not f['confirmed'] for f in aggregate))
   f=next(f for f in individual if f['name']=='恶心呕吐' and f['group']=='对照组');self.assertEqual(f['weights'],[16,84]);self.assertEqual(f['source_n'],25)
 def test_generates_exact_four_yes_twenty_one_no_and_exports(self):
  r=read_word(self.path,['对照组','试验组']);c=default_batch_config(['对照组','试验组']);c['include_basics']=False;c['typed_fields']=r.typed_fields
  for g in c['groups']:g['n']=25
  with self.assertRaises(ValueError):generate_batch(c)
  c['typed_fields']=[convert(f,'excluded') if f.get('aggregate_pending') else f for f in r.typed_fields]
  result=generate_batch(c);i=result['columns'].index('恶心呕吐');v=[row[i] for row in result['rows'] if row[1]=='对照组'];self.assertEqual(v.count('有'),4);self.assertEqual(v.count('无'),21)
  export_batch(result,Path(self.temp.name)/'result.xlsx')
 def test_inconsistent_percentage_remains_pending_even_in_preview(self):
  for raw,n in [('4（20.00）',25),('26（104.00）',25),('4（16.00）',None)]:
   f=summary('恶心呕吐','对照组',raw,n,1,table_title='表4 并发症比较');self.assertFalse(f['confirmed']);self.assertFalse(convert(f,'yesno')['confirmed']);self.assertIn('核对',f['review_note'])
 def test_reported_percentage_rounding_is_respected(self):
  f=summary('恶心呕吐','对照组','1（6.67）',15,1,table_title='表4 并发症比较');self.assertTrue(f['confirmed'])
 def test_generic_consistent_counts_use_neutral_binary_encoding(self):
  caption(self.path,'表4 一般指标比较');f=read_word(self.path,['对照组','试验组']).typed_fields
  self.assertTrue(all(v['kind']=='binary01' and v['confirmed'] and v['labels']==[1,0] for v in f if not v.get('aggregate_pending')))
 def test_vertical_complications_caption_also_applies(self):
  save(self.path,[[['项目','对照组（25例）','试验组（25例）'],['恶心呕吐','4（16.00）','1（4.00）'],['总发生率','4（16.00）','1（4.00）']]]);caption(self.path,'表4 并发症发生情况')
  f=read_word(self.path,['对照组','试验组']).typed_fields;self.assertTrue(all(v['confirmed'] for v in f if v['name']=='恶心呕吐'));self.assertTrue(all(not v['confirmed'] for v in f if v['name']=='总发生率'))
