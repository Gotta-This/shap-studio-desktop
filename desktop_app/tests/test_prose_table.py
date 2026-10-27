import json
import os
from pathlib import Path
import tempfile
import unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from clinical_studio.prose_table_engine import parse_document,validate_study,to_simulation_config,save_document,load_document

FIRST='对照组男17例、女13例，年龄52～78岁，平均（65.38±7.42）岁；APACHEⅡ评分（20.47±3.26）分；肺部感染部位：双侧24例、单侧6例。试验组男16例、女14例，年龄50～79岁，平均（64.85±8.03）岁；APACHEⅡ评分（21.03±3.51）分；肺部感染部位：双侧25例、单侧5例。两组患者性别、年龄、APACHEⅡ评分、入ICU时氧合指数及感染部位分布比较，差异均无统计学意义（P＞0.05），具有可比性。'
SECOND='本研究共纳入重症肺炎机械通气患者50例，对照组25例，试验组25例。对照组男14例、女11例，年龄（58.6±10.2）岁，BMI（22.8±3.1）kg/m²，APACHEⅡ评分（18.4±3.6）分，入组时PaO₂/FiO₂为（151.24±34.56）mmHg；试验组男15例、女10例，年龄（57.9±9.8）岁，BMI（22.5±2.9）kg/m²，APACHEⅡ评分（18.1±3.4）分，入组时PaO₂/FiO₂为（149.96±35.18）mmHg。两组患者在性别构成、年龄、BMI、APACHEⅡ评分及入组时氧合指数等方面比较，差异均无统计学意义（P＞0.05），具有可比性。'

class ProseTests(unittest.TestCase):
    def parse(self,text):return parse_document(text)['studies'][0]
    def test_first(self):
        s=self.parse(FIRST);vs={v['name']:v for v in s['variables']}
        self.assertEqual([g['n'] for g in s['groups']],[30,30])
        self.assertEqual(vs['年龄']['cells']['对照组']['lower'],52)
        self.assertEqual(vs['年龄']['cells']['对照组']['mean'],65.38)
        self.assertEqual(vs['性别']['cells']['试验组']['counts'],{'男':16,'女':14})
        self.assertEqual(vs['肺部感染部位']['cells']['对照组']['counts'],{'双侧':24,'单侧':6})
        self.assertIn('入ICU时氧合指数',vs)
        with self.assertRaises(ValueError):to_simulation_config(s)
        self.assertFalse(s['unparsed'])
        self.assertEqual(set(vs),{'性别','年龄','APACHEⅡ评分','肺部感染部位','入ICU时氧合指数'})
    def test_second(self):
        s=self.parse(SECOND);vs={v['name']:v for v in s['variables']}
        self.assertEqual([g['n'] for g in s['groups']],[25,25])
        self.assertEqual(set(vs),{'性别','年龄','BMI','APACHEⅡ评分','入组时氧合指数'})
        self.assertEqual(vs['BMI']['unit'],'kg/m²')
        self.assertEqual(vs['入组时氧合指数']['cells']['试验组']['mean'],149.96)
        self.assertEqual(validate_study(s)['errors'],[])
        c=to_simulation_config(s)
        self.assertFalse(c['include_basics']);self.assertEqual(len(c['typed_fields']),10)
        from clinical_studio.word_batch_engine import generate_batch
        r=generate_batch(c)
        self.assertEqual(len(r['rows']),50)
        self.assertEqual(len(r['columns']),7)
        self.assertNotIn('P',r['columns'])
    def test_separate_studies_and_original_evidence(self):
        d=parse_document(FIRST+'\n\n'+SECOND);self.assertEqual(len(d['studies']),2)
        for s in d['studies']:
            for v in s['variables']:
                for cell in v['cells'].values():
                    for e in cell['evidence']:self.assertEqual(s['source_text'][e['start']:e['end']],e['raw'])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'table.json';save_document(d,p);self.assertEqual(load_document(p)['studies'],d['studies']);self.assertEqual(load_document(p)['ready_for_simulation'],[False,True])
    def test_conflict_missing_counts_and_total(self):
        s=self.parse(SECOND.replace('男14例','男13例'))
        self.assertTrue(any('分类人数' in e or '男女例数之和' in e for e in validate_study(s)['errors']))
        s=self.parse(SECOND.replace('患者50例','患者60例'))
        self.assertTrue(any('总例数' in e for e in validate_study(s)['errors']))
        s=self.parse(SECOND.replace('男14例、女11例','男14例'))
        self.assertTrue(validate_study(s)['errors'])
    def test_duplicate_values_block_and_unparsed_block(self):
        s=self.parse(SECOND.replace('；试验组','；对照组年龄（60±10）岁；试验组'))
        self.assertTrue(any('多个不同值' in e for e in validate_study(s)['errors']))
        s=self.parse(SECOND.replace('；试验组','；病程资料不详；试验组'))
        self.assertTrue(s['unparsed'])
        with self.assertRaises(ValueError):to_simulation_config(s)
    def test_selected_group_with_missing_prose_is_retained(self):
        s=parse_document('对照组25例，年龄（58.6±10.2）岁',['对照组','试验组'])['studies'][0]
        self.assertEqual([g['name'] for g in s['groups']],['对照组','试验组'])
        self.assertTrue(any('试验组' in e for e in validate_study(s)['errors']))

    def test_unknown_groups_and_quantile(self):
        s=parse_document('A组10例，CRP为13.5(10.8,15.5)mg/L；B组10例，CRP为13(11.1,14.9)mg/L',['A组','B组'])['studies'][0]
        self.assertEqual(s['variables'][0]['kind'],'quantile')
        self.assertTrue(any('上下限' in e for e in validate_study(s)['errors']))
        self.assertTrue(self.parse('患者资料不详')['issues'])

if __name__=='__main__':unittest.main()
