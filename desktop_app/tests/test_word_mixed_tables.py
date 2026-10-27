"""Mixed orientations and real OOXML merged headers preserve editable semantics."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from copy import deepcopy
from collections import Counter
from clinical_studio.merged_table_verify import save_fixture,BASELINE,COMPLICATIONS
from clinical_studio.word_batch_engine import read_word,default_batch_config,generate_batch,output_columns,validate_batch
from clinical_studio.word_table_types import summary,parse_table
from clinical_studio.typed_field_ui import convert,FieldDialog
from clinical_studio.app import create_application
APP=create_application([])

class MixedTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=save_fixture(Path(self.tmp.name)/'mixed.docx')
        self.result=read_word(self.path,['对照组','试验组'])
    def tearDown(self):self.tmp.cleanup()
    def config(self):
        config=default_batch_config(['对照组','试验组']);config.update(include_basics=False,indicators=deepcopy(self.result.indicators),typed_fields=deepcopy(self.result.typed_fields))
        for group in config['groups']:group['n']=20
        return config
    def test_four_tables_all_match_without_changing_flat_numeric_names(self):
        r=self.result
        self.assertEqual(r.table_count,4);self.assertEqual(r.group_sizes,{'对照组':20,'试验组':20})
        self.assertTrue(all(set(m['groups'])=={'对照组','试验组'} for m in r.table_matches))
        self.assertEqual(len(r.indicators),12)
        self.assertEqual({f['name'] for f in r.indicators},{'术后6h','术后24h','术后48h','首次下床活动时间','首次肛门排气时间','住院时间'})
        self.assertEqual(len(r.typed_fields),32)
    def test_vertical_categories_counts_units_and_statistics(self):
        fields={f['name']:f for f in self.result.typed_fields if f['table']==1 and f['group']=='对照组'}
        self.assertEqual(len(fields),8)
        self.assertEqual(fields['性别']['labels'],['男','女']);self.assertEqual(fields['性别']['weights'],[90,10])
        self.assertEqual(fields['疝侧别']['labels'],['左','右']);self.assertEqual(fields['ASA分级']['counts'],[8,10,2])
        self.assertEqual(fields['体重指数（kg/m²）']['mean'],23.85)
        self.assertEqual(fields['合并高血压']['kind'],'yesno');self.assertEqual(fields['合并高血压']['weights'],[35,65])
        self.assertTrue(all(f['confirmed'] for f in fields.values()))
        self.assertNotIn('P值',fields);self.assertNotIn('统计值',fields)
    def test_merged_headers_use_leaf_name_and_keep_source_and_parent(self):
        fields={f['name']:f for f in self.result.typed_fields if f['table']==4 and f['group']=='对照组'}
        self.assertEqual(len(fields),8)
        self.assertEqual(fields['尿潴留']['classification'],'并发症');self.assertEqual(fields['尿潴留']['count'],2)
        self.assertEqual(fields['尿潴留']['source_cell'],{'row':3,'column':3})
        self.assertEqual(fields['护理前（分）']['header_path'],['SAS','护理前（分）'])
        self.assertEqual(fields['护理前（分）']['mean'],52.45)
        self.assertEqual(fields['总发生率']['classification'],'并发症')
        self.assertTrue(fields['总发生率']['aggregate_pending']);self.assertFalse(fields['总发生率']['confirmed'])
    def test_pending_aggregate_cannot_be_silently_confirmed_by_type_combo(self):
        config=self.config()
        with self.assertRaisesRegex(ValueError,'总发生率'):validate_batch(config)
        config['typed_fields']=[convert(f,'yesno') if f.get('aggregate_pending') else f for f in config['typed_fields']]
        with self.assertRaisesRegex(ValueError,'汇总项'):validate_batch(config)
        field=next(f for f in config['typed_fields'] if f.get('aggregate_pending'))
        dialog=FieldDialog(field);dialog.apply();self.assertIsNone(dialog.result_field)
        self.assertIn('总发生率',dialog.error.text());dialog.kind.setCurrentIndex(dialog.kind.findData('excluded'));dialog.apply()
        self.assertEqual(dialog.result_field['kind'],'excluded');dialog.deleteLater();APP.processEvents()
    def test_excluding_total_generates_all_other_columns_and_correct_counts(self):
        config=self.config();config['typed_fields']=[convert(f,'excluded') if f.get('aggregate_pending') else f for f in config['typed_fields']]
        result=generate_batch(config);cols=result['columns'];self.assertNotIn('总发生率',cols);self.assertEqual(len(result['rows']),40)
        for group,male,counts in [('对照组',18,[8,10,2]),('试验组',17,[9,9,2])]:
            rows=[r for r in result['rows'] if r[1]==group]
            self.assertEqual(sum(r[cols.index('性别')]=='男' for r in rows),male)
            self.assertEqual([sum(r[cols.index('ASA分级')]==label for r in rows) for label in ['I','II','III']],counts)
        from clinical_studio.word_rule_review import field_rule_rows
        review=field_rule_rows(config);self.assertEqual(sum(r['column']=='总发生率（不生成）' for r in review),2)
    def test_missing_group_and_mismatched_category_counts_stay_pending(self):
        invalid=summary('ASA分级（I/II/III）','对照组','8(40)/9(45)/2(10)',20,1)
        self.assertFalse(invalid['confirmed'])
        missing=deepcopy(COMPLICATIONS);missing.pop(3)
        imported=read_word(save_fixture(self.path,[missing]),['对照组','试验组'])
        missing_fields=[f for f in imported.typed_fields if f['group']=='试验组']
        self.assertEqual(len(missing_fields),8);self.assertTrue(all(not f['confirmed'] for f in missing_fields))
    def test_original_count_footnotes_are_still_accepted(self):
        field=summary('基础疾病','A','7（35.00）*',20,1)
        self.assertEqual(field['count'],7);self.assertEqual(field['weights'],[35,65]);self.assertEqual(field['kind'],'binary01');self.assertTrue(field['confirmed'])
    def test_duplicate_leaf_names_keep_both_parent_names(self):
        rows=[["组别","例数",("SAS",2),("VAS",2)],["组别","例数","护理前","出院前","护理前","出院前"],["对照组","20","52±5","40±4","6±1","3±1"],["试验组","20","51±5","39±4","5±1","2±1"]]
        imported=read_word(save_fixture(self.path,[rows]),['对照组','试验组'])
        self.assertEqual({f['name'] for f in imported.typed_fields},{'SAS / 护理前','SAS / 出院前','VAS / 护理前','VAS / 出院前'})
    def test_percentage_only_aggregate_stays_pending(self):
        field=summary('总发生率','对照组','35%',20,4)
        self.assertTrue(field['aggregate_pending']);self.assertFalse(field['confirmed']);self.assertEqual(field['reported_percent'],35)
    def test_mixed_categorical_columns_preserve_existing_outcome_rates(self):
        rows=[['组别','例数','感染','总有效率','复发率','评分'],['对照组','20','2(10)','18(90)','1(5)','10±2'],['试验组','20','1(5)','19(95)','0(0)','9±2']]
        imported=read_word(save_fixture(self.path,[rows]),['对照组','试验组'])
        self.assertEqual(imported.outcome_rates['对照组'],{'总有效率':90.,'复发率':5.})
        self.assertNotIn('总有效率',{f['name'] for f in imported.typed_fields})
    def test_plain_vertical_counts_with_explicit_binary_hint(self):
        table=[['项目','对照组(n=20)','试验组(n=20)'],['合并高血压','7','6']]
        result=parse_table(table,[],['对照组','试验组'],1)
        self.assertTrue(result['handled']);self.assertEqual(result['fields'][0]['weights'],[35,65])
        self.assertEqual(result['fields'][0]['labels'],['有','无'])

if __name__=='__main__':unittest.main()
