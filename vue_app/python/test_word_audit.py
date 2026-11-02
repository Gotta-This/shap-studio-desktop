from copy import deepcopy
import unittest
from clinical_studio.word_batch_engine import default_batch_config
from word_workflow import audit

class WordAuditTests(unittest.TestCase):
    def test_reports_all_pending_rules_without_changing_confirmation_or_precision(self):
        config=default_batch_config();group=config['groups'][0]['name']
        config['typed_fields']=[
            dict(table=1,name='性别',group=group,kind='gender',labels=['男','女'],weights=[56.75675675675676,43.24324324324324],confirmed=True),
            dict(table=1,name='需确认性别',group=group,kind='gender',labels=['男','女'],weights=[50,50],confirmed=False),
            dict(table=1,name='未识别',group=group,kind='unknown',confirmed=False),
            dict(table=1,name='错误数值',group=group,kind='mean_sd',mean=10,sd=-1,digits=0,confirmed=True),
        ]
        original=deepcopy(config)
        result=audit(dict(config=config))
        self.assertEqual(result['total'],4)
        self.assertEqual({i['name'] for i in result['issues']},{'需确认性别','未识别','错误数值'})
        self.assertFalse(result['valid'])
        self.assertEqual(config,original)
        config['typed_fields']=config['typed_fields'][:1]
        self.assertEqual(audit(dict(config=config))['pending'],0)
    def test_group_parameter_errors_are_not_reported_as_passed(self):
        config=default_batch_config();config['groups'][0]['n']=0
        result=audit(dict(config=config))
        self.assertFalse(result['valid'])
        self.assertTrue(result['global_error'])
