from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as E
from zipfile import ZipFile
import unittest
import bridge
from word_workflow import scan,apply
from analysis_workflow import run
from clinical_studio.config import default_config

class IntentRepairTests(unittest.TestCase):
    def test_range_ignores_inactive_targets_and_blank_seed_is_none(self):
        params=dict(n=20,mode='range',mean='',sd=-99,digits=0,lower=1,upper=100,seed='')
        original=deepcopy(params)
        normalized=bridge.numeric_parameters(params)
        self.assertEqual((normalized['mean'],normalized['sd'],normalized['seed']),(0.,0.,None))
        result=bridge.dispatch('tool.numeric',params)
        self.assertEqual(len(result['values']),20)
        self.assertTrue(all(1<=v<=100 for v in result['values']))
        self.assertEqual(params,original)
        with self.assertRaises(ValueError):bridge.dispatch('tool.numeric',dict(params,lower=None))
        with self.assertRaises(ValueError):bridge.dispatch('tool.numeric',dict(params,lower=101,upper=100))

    def test_target_and_fixed_seeds_are_unchanged(self):
        params=dict(n=10,mode='target',mean=50,sd=5,digits=1,seed=12)
        self.assertEqual(bridge.numeric_parameters(params),params)
        self.assertEqual(bridge.dispatch('tool.numeric',params)['values'],bridge.dispatch('tool.numeric',params)['values'])
        with self.assertRaises(ValueError):bridge.dispatch('tool.numeric',dict(params,sd=-1))

    def fixture(self,root):
        w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        doc=E.Element(w+'document');body=E.SubElement(doc,w+'body');table=E.SubElement(body,w+'tbl')
        for row in [['项目','对照组(n=10)','中药组(n=12)'],['评分','50.00±5.00','60.00±5.00']]:
            tr=E.SubElement(table,w+'tr')
            for text in row:E.SubElement(E.SubElement(E.SubElement(E.SubElement(tr,w+'tc'),w+'p'),w+'r'),w+'t').text=text
        path=root/'precision.docx'
        with ZipFile(path,'w') as z:z.writestr('word/document.xml',E.tostring(doc))
        return path

    def test_precision_mode_switch_preserves_explicit_edits_and_original_draft(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);scanned=scan(root,self.fixture(root),'zero');draft=scanned['draft']
            original=deepcopy(draft)
            request=dict(session=scanned['session'],draft=draft,groups=scanned['scan']['candidates'],options=dict(decimal_mode='source'))
            result=apply(root,request)
            fields=lambda c:c.get('indicators',[])+c.get('typed_fields',[])
            self.assertTrue(fields(result['config']))
            self.assertEqual({f['digits'] for f in fields(result['config'])},{2})
            self.assertEqual({f['digits'] for f in result['draft']['fields']},{2})
            self.assertEqual(draft,original)
            previous=deepcopy(result['config'])
            fields(previous)[0]['digits']=4
            applied=apply(root,dict(request,previous=previous))
            self.assertEqual(sorted(f['digits'] for f in fields(applied['config'])),[2,4])
            draft['fields'][0]['digits']=3
            result=apply(root,dict(request,previous=previous))
            self.assertEqual(sorted(f['digits'] for f in fields(result['config'])),[2,3])
            request['draft']=result['draft'];request['options']['decimal_mode']='zero'
            result=apply(root,request)
            self.assertEqual(sorted(f['digits'] for f in fields(result['config'])),[0,3])

    def test_configured_output_is_used_and_explicit_output_takes_precedence(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);profile=root/'profile';profile.mkdir()
            config=default_config();config['data']['n_samples']=20;config['plots']['output_dir']=str(root/'configured')
            result=run(profile,dict(config=config,data_only=True,output=''),lambda _:None)
            self.assertTrue(Path(result['folder']).is_relative_to(root/'configured'))
            self.assertEqual(result['config']['plots']['output_dir'],str(root/'configured'))
            self.assertTrue((Path(result['folder'])/'data.csv').is_file())
            result=run(profile,dict(config=config,data_only=True,output=str(root/'explicit')),lambda _:None)
            self.assertTrue(Path(result['folder']).is_relative_to(root/'explicit'))
            self.assertEqual(result['config']['plots']['output_dir'],str(root/'explicit'))
            self.assertEqual(config['plots']['output_dir'],str(root/'configured'))
