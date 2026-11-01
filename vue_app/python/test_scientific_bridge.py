from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import base64, tempfile, unittest
import bridge
class ScientificTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.old=bridge.PROFILE;bridge.PROFILE=Path(self.tmp.name)
    def tearDown(self):bridge.PROFILE=self.old;self.tmp.cleanup()
    def test_word_import_keeps_recognized_fields_and_exports_complete_xlsx(self):
        w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        node=ET.Element(w+'document');body=ET.SubElement(node,w+'body');table=ET.SubElement(body,w+'tbl')
        for row in [['项目','对照组(n=10)','中药组(n=12)'],['年龄','58.2±4.1','57.9±3.5']]:
            tr=ET.SubElement(table,w+'tr')
            for text in row:ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(tr,w+'tc'),w+'p'),w+'r'),w+'t').text=text
        path=Path(self.tmp.name)/'统计表.docx'
        with ZipFile(path,'w') as z:z.writestr('word/document.xml',ET.tostring(node))
        imported=bridge.dispatch('tool.word.read',{'paths':[str(path)]})
        self.assertTrue(imported['config']['typed_fields'] or imported['config']['indicators'])
        result=bridge.dispatch('tool.word.generate',{'config':imported['config']})
        self.assertIn('年龄',result['columns']);self.assertEqual(result['total'],22)
        with ZipFile(__import__('io').BytesIO(base64.b64decode(result['base64']))) as z:self.assertIn('xl/workbook.xml',z.namelist())
    def test_shap_data_only_generates_real_files_and_all_feature_columns(self):
        config=bridge.dispatch('tool.shap.defaults',{});config['data']['n_samples']=40
        result=bridge.dispatch('tool.shap.run',{'config':config,'data_only':True})
        self.assertEqual(len(result['rows']),40)
        self.assertIn(config['data']['features'][0]['name'],result['columns'])
        self.assertTrue((Path(result['folder'])/'clinical_prediction_dataset_with_protective.xlsx').is_file())
if __name__=='__main__':unittest.main()
