import unittest,tempfile,zipfile,warnings
from unittest.mock import patch
from pathlib import Path
import numpy as np
import pandas as pd
from prediction import inspect,prepared,run,hl,export,GRIDS

class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        rng=np.random.default_rng(22);n=120;age=rng.normal(50,10,n);sex=rng.choice(['女','男'],n)
        y=(rng.random(n)<1/(1+np.exp(-((age-50)/12+(sex=='男')*.5)))).astype(int)
        self.df=pd.DataFrame({'编号':[f'P{i:03}' for i in range(n)],'分组':y,'年龄':age,'性别':sex,'指标':rng.normal(size=n)})
        self.file=self.root/'输入.xlsx';self.df.to_excel(self.file,index=False)
        self.data=inspect(self.root,[self.file]);self.p=dict(dataset=self.data['id'],id_column='编号',target='分组',positive='1',features=[dict(name='年龄',kind='continuous'),dict(name='性别',kind='categorical')],seed=20261102,train_ratio=.7,split_mode='ratio',threshold=.5,models=['LR'],grids=GRIDS)
    def tearDown(self):self.tmp.cleanup()
    def test_import_sheet_and_preview(self):
        self.assertEqual(self.data['rows'],120);self.assertEqual(len(self.data['preview']),8);self.assertEqual(self.data['columns'][3]['kind'],'categorical')
    def test_split_reproducible_and_count(self):
        a=prepared(self.root,self.p);b=prepared(self.root,self.p)
        self.assertEqual(len(a[4]),84);np.testing.assert_array_equal(a[4],b[4]);self.assertFalse(set(a[4]) & set(a[5]))
        self.assertEqual(len(prepared(self.root,dict(self.p,split_mode='count',train_count=80))[4]),80)
    def test_invalid_inputs(self):
        for extra in [dict(positive='missing'),dict(features=[]),dict(seed=-1),dict(threshold=1),dict(models=[]),dict(id_column='分组')]:
            with self.subTest(extra=extra),self.assertRaises(ValueError):prepared(self.root,dict(self.p,**extra))
    def test_duplicate_id(self):
        self.df.loc[1,'编号']=self.df.loc[0,'编号'];self.df.to_excel(self.file,index=False);d=inspect(self.root,[self.file])
        with self.assertRaisesRegex(ValueError,'重复'):prepared(self.root,dict(self.p,dataset=d['id']))
    def test_invalid_numeric_and_missing_outcome(self):
        self.df['年龄']=self.df['年龄'].astype(object);self.df.loc[0,'年龄']='abc';self.df.to_excel(self.file,index=False);d=inspect(self.root,[self.file])
        with self.assertRaisesRegex(ValueError,'非数值'):prepared(self.root,dict(self.p,dataset=d['id']))
        self.df.loc[0,'分组']=np.nan;self.df.to_excel(self.file,index=False);d=inspect(self.root,[self.file])
        with self.assertRaisesRegex(ValueError,'缺失'):prepared(self.root,dict(self.p,dataset=d['id']))
    def test_missing_predictors_allowed(self):
        self.df.loc[0,'年龄']=np.nan;self.df.loc[1,'性别']=np.nan;self.df.to_excel(self.file,index=False);d=inspect(self.root,[self.file]);prepared(self.root,dict(self.p,dataset=d['id']))
    def test_degenerate_hl(self):
        r=hl(np.array([0,1]*10),np.full(20,.5));self.assertIsNone(r['p']);self.assertIsNone(r['chi2'])
    def test_end_to_end_four_models_and_export(self):
        p=dict(self.p,models=['LR','RF','XGB','SVM'],grids={k:{a:[b[0]] for a,b in g.items()} for k,g in GRIDS.items()})
        with patch.dict('os.environ',{'MPL_IGNORE_SYSTEM_FONTS':'1'}),warnings.catch_warnings():
            warnings.filterwarnings('error',message=r'Glyph .* missing')
            r=run(self.root,p,lambda _:None)
        self.assertEqual(len(r['metrics']),8);self.assertEqual(len(r['images']),3)
        out=self.root/'prediction'/r['id'];patients=pd.read_excel(out/'模型分析结果.xlsx',sheet_name='病例划分与预测');self.assertEqual(len(patients),120)
        from sklearn.metrics import roc_auc_score,brier_score_loss
        for row in r['metrics']:
            subset=patients[patients['数据集']==row['dataset']];prob=subset[row['model']+'预测概率'];truth=subset['阳性编码']
            self.assertAlmostEqual(row['auc'],roc_auc_score(truth,prob));self.assertAlmostEqual(row['brier'],brier_score_loss(truth,prob))
        from PIL import Image
        with Image.open(out/'ROC_训练与验证.png') as im:self.assertEqual(im.size,(8580,4680));self.assertAlmostEqual(im.info['dpi'][0],650,delta=.1)
        with zipfile.ZipFile(out/'完整分析结果.zip') as z:self.assertIn('analysis.json',z.namelist());self.assertEqual(len([x for x in z.namelist() if x.endswith('.pdf')]),3)
        self.assertGreater(len(export(self.root,dict(id=r['id'],format='zip'))['content']),10000)
    def test_path_and_headers(self):
        with self.assertRaises(ValueError):inspect(self.root,token='../../')
        f=self.root/'重复.csv';f.write_text('编号,分组,年龄,年龄\na,0,1,2\nb,1,3,4')
        with self.assertRaisesRegex(ValueError,'重复'):inspect(self.root,[f])
    def test_cancel(self):
        def cancel(_):raise InterruptedError('cancel')
        with self.assertRaises(InterruptedError):run(self.root,self.p,cancel)
if __name__=='__main__':unittest.main()
