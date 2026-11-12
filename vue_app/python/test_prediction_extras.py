import unittest,tempfile,json
from pathlib import Path
import numpy as np,pandas as pd
from scipy.special import expit
from prediction import inspect,run,location
from prediction_extras import options,explain
from prediction_plots import redraw

class OptionalValidationTests(unittest.TestCase):
    def test_default_analyses_disabled(self):
        c=options({},['LR','RF','XGB','SVM']);self.assertFalse(c['lasso']['enabled']);self.assertFalse(c['shap']['enabled'])
    def test_disabled_diagnostics_ignore_unused_inputs(self):
        c=options({'lasso':{'enabled':False,'lambda_count':None},'shap':{'enabled':False,'model':'SVM'}},['LR'])
        self.assertFalse(c['lasso']['enabled']);self.assertEqual(c['lasso']['lambda_count'],24)
    def test_invalid_optional_inputs(self):
        for c in [dict(lasso=dict(enabled=True,lambda_count=3)),dict(lasso=dict(enabled=True,lambda_min=1,lambda_max=.1)),dict(shap=dict(enabled=True,model='RF')),dict(shap=dict(enabled=True,model='SVM')),dict(shap=dict(enabled=True,max_samples=999)),dict(lasso=dict(enabled=True,rule='bad'))]:
            with self.subTest(c=c),self.assertRaises(ValueError):options(c,['LR','XGB'])

class OptionalAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);rng=np.random.default_rng(47);n=120;age=rng.normal(50,10,n);group=rng.choice(['A','B','C'],n);y=rng.binomial(1,expit((age-50)/10+(group=='C')*.4))
        cls.X=pd.DataFrame({'年龄':age,'治疗类型':group});cls.y=y;cls.ids=pd.Series([f'P{i}' for i in range(n)])
        frame=cls.X.copy();frame.insert(0,'分组',y);frame.insert(0,'编号',cls.ids);path=cls.root/'病例.csv';frame.to_csv(path,index=False);data=inspect(cls.root,[path]);p=dict(dataset=data['id'],features=[dict(name='年龄',kind='continuous'),dict(name='治疗类型',kind='categorical')],models=['LR','RF','XGB','SVM'],grids={'LR':{'model__C':[1]},'RF':{'model__max_depth':[3],'model__min_samples_leaf':[2]},'XGB':{'model__max_depth':[2],'model__learning_rate':[.1]},'SVM':{'model__C':[1],'model__gamma':['scale']}},plot_config={'common':{'dpi':80,'formats':['svg']}})
        cls.base=run(cls.root,p,lambda _:None)
        cls.result=run(cls.root,dict(p,optional={'lasso':{'enabled':True,'lambda_count':8,'rule':'count','max_features':1},'shap':{'enabled':True,'model':'XGB','max_samples':30,'case_id':'P12'}}),lambda _:None)
        cls.data=json.loads((location(cls.root,cls.result['id'])/'plot-data.json').read_text())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_four_models_unaffected_by_diagnostics(self):
        self.assertEqual(self.base['metrics'],self.result['metrics']);self.assertEqual(self.base['best'],self.result['best']);self.assertEqual(len(self.base['images']),3);self.assertEqual(len(self.result['images']),5)
    def test_lasso_fold_standard_errors_counts_and_training_only(self):
        r=self.data['lasso'];fold=np.array(r['fold_deviance']);np.testing.assert_allclose(fold.mean(axis=0),r['cv_mean']);np.testing.assert_allclose(fold.std(axis=0,ddof=1)/np.sqrt(5),r['cv_se'])
        patients=pd.read_excel(location(self.root,self.result['id'])/'模型分析结果.xlsx',sheet_name='病例划分与预测');train=set(int(v[1:]) for v in patients[patients['数据集']=='训练集']['编号']);self.assertEqual(train,set(r['train_indices']))
        coef=np.asarray(r['coefficients']);expected=[sum(any(abs(row[j])>1e-7 for j,g in enumerate(r['groups']) if g==name) for name in r['original_names']) for row in coef];self.assertEqual(expected,r['nonzero_counts']);self.assertLessEqual(len(r['selected_features']),1)
        self.assertEqual(len(r['encoded_names']),3);self.assertEqual(len(r['original_names']),2)
    def test_shap_additivity_and_original_feature_grouping(self):
        r=self.data['shap'];self.assertEqual(len(r['feature_names']),2);self.assertEqual(r['unit'],'log_odds');self.assertEqual(r['case']['id'],'P12')
        np.testing.assert_allclose(np.array(r['sample_base'])+np.array(r['sample_shap']).sum(axis=1),r['sample_output'],atol=1e-5);np.testing.assert_allclose(expit(r['sample_output']),r['sample_probability'],atol=1e-5);self.assertLess(r['max_additivity_error'],1e-4)
        case=r['case'];self.assertAlmostEqual(case['base']+sum(case['shap']),case['output'],places=5)
    def test_optional_tables_and_snapshots_survive_style_only_redraw(self):
        out=location(self.root,self.result['id']);book=pd.ExcelFile(out/'模型分析结果.xlsx');self.assertIn('LASSO交叉验证',book.sheet_names);self.assertIn('SHAP逐例贡献',book.sheet_names);book.close()
        cv=pd.read_excel(out/'模型分析结果.xlsx',sheet_name='LASSO交叉验证');self.assertTrue(all('fold_'+str(i) in cv for i in range(1,6)))
        from unittest.mock import patch
        with patch('prediction_extras.lasso',side_effect=AssertionError('recomputed')),patch('prediction_extras.explain',side_effect=AssertionError('recomputed')):
            r=redraw(self.root,dict(id=self.result['id'],plot_config=self.result['plot_config']),lambda _:None)
        self.assertEqual(r['metrics'],self.result['metrics']);self.assertEqual(len(r['images']),5)
    def test_force_positive_and_negative_stacks_do_not_overlap(self):
        import matplotlib.pyplot as plt
        from unittest.mock import patch
        from copy import deepcopy
        from prediction_plots import render
        data=deepcopy(self.data);case=data['shap']['case'];case.update(base=.1,shap=[.3,-.2],output=.2,probability=float(expit(.2)))
        c=deepcopy(self.result['plot_config'])
        for name,p in c['plots'].items():p['enabled']=name=='shap'
        with tempfile.TemporaryDirectory() as temp:
            with patch('matplotlib.pyplot.close'):
                render(Path(temp),data,c);force=plt.gcf().axes[3];polygons=force.patches
                self.assertEqual(len(polygons),2)
                self.assertLessEqual(float(polygons[0].get_xy()[:,0].max()),.2+1e-10)
                self.assertGreaterEqual(float(polygons[1].get_xy()[:,0].min()),.2-1e-10)
            plt.close('all')
    def test_lr_and_rf_explanations_use_correct_output_units(self):
        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler,OneHotEncoder
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import RandomForestClassifier
        tr=np.arange(90);va=np.arange(90,120)
        for name,model in [('LR',LogisticRegression()),('RF',RandomForestClassifier(n_estimators=20,max_depth=3,random_state=1))]:
            prep=ColumnTransformer([('num',Pipeline([('fill',SimpleImputer()),('scale',StandardScaler())]),['年龄']),('cat',Pipeline([('fill',SimpleImputer(strategy='most_frequent')),('encode',OneHotEncoder(drop='first',sparse_output=False))]),['治疗类型'])]);pipe=Pipeline([('prepare',prep),('model',model)]).fit(self.X.iloc[tr],self.y[tr])
            result=explain(name,pipe,self.X,self.y,tr,va,self.ids,['年龄'],['治疗类型'],dict(model=name,dataset='validation',max_samples=20,case_id=''),4,lambda _:None)
            self.assertEqual(result['unit'],'log_odds' if name=='LR' else 'probability');np.testing.assert_allclose(np.array(result['sample_base'])+np.array(result['sample_shap']).sum(axis=1),result['sample_output'],atol=1e-5)
class ShapLayoutTests(unittest.TestCase):
    def test_twenty_long_labels_fit_without_overlaps(self):
        import matplotlib.pyplot as plt
        from prediction_plots import validated
        from prediction_extra_plots import draw_optional
        names=['预测时点前累计糖皮质激素剂量'+str(i) for i in range(20)]
        rng=np.random.default_rng(4);values=rng.normal(size=(24,20))
        r=dict(model='XGB',unit='log_odds',feature_names=names,importance=np.abs(values).mean(axis=0).tolist(),sample_shap=values.tolist(),sample_color=rng.uniform(size=(24,20)).tolist(),sample_ids=list(range(24)),dataset='validation',case=dict(id='P1',base=.1,output=float(.1+values[0].sum()),probability=.6,shap=values[0].tolist(),values=['12']*20))
        c=validated();c['plots']['shap']['enabled']=True
        def inspect(fig,*args):
            fig.canvas.draw();renderer=fig.canvas.get_renderer();a,b,w,f,cb=fig.axes
            self.assertEqual(fig._suptitle.get_fontweight(),'bold')
            for axis in (a,b,w,f):
                self.assertEqual(next(t for t in axis.texts if (t.get_gid() or '').startswith('shap-title-')).get_fontweight(),'bold')
                self.assertEqual(axis.xaxis.label.get_fontweight(),'normal')
                self.assertTrue(all(t.get_fontweight()=='normal' for t in axis.get_xticklabels()))
            for axis in (a,b,w):self.assertTrue(all(t.get_fontweight()=='normal' for t in axis.get_yticklabels()))
            self.assertEqual(len(a.get_yticklabels()),20)
            for axis in (a,b,w):
                boxes=[t.get_window_extent(renderer) for t in axis.get_yticklabels()]
                self.assertTrue(all(box.x0>=0 for box in boxes))
                self.assertTrue(all(not x.overlaps(y) for i,x in enumerate(boxes) for y in boxes[i+1:]))
            self.assertGreater(min(t.get_window_extent(renderer).x0 for t in b.get_yticklabels()),cb.get_tightbbox(renderer).x1)
            self.assertFalse(fig._suptitle.get_window_extent(renderer).overlaps(next(t for t in a.texts if t.get_gid()=='shap-title-A').get_window_extent(renderer)))
            for upper,lower in ((a,w),(w,f)):
                self.assertFalse(upper.xaxis.label.get_window_extent(renderer).overlaps(next(t for t in lower.texts if (t.get_gid() or '').startswith('shap-title-')).get_window_extent(renderer)))
            self.assertFalse(f.xaxis.label.get_window_extent(renderer).overlaps(fig.texts[-1].get_window_extent(renderer)))
            plt.close(fig)
        draw_optional(Path('.'),{'shap':r},c,inspect,[])

class ShapReferenceTests(unittest.TestCase):
    @staticmethod
    def snapshot():
        rng=np.random.default_rng(91);sv=rng.normal(size=(119,6));cs=[2.226,.761,.330,-.304,.255,0.]
        return dict(model='XGB',unit='log_odds',feature_names=['指标'+str(i) for i in range(6)],
            importance=np.abs(sv).mean(0).tolist(),sample_shap=sv.tolist(),sample_color=rng.random((119,6)).tolist(),
            sample_ids=[str(i) for i in range(119)],dataset='validation',
            case=dict(id='002',base=-.721,output=-.721+sum(cs),probability=.9,shap=cs,values=['1']*6))

    def test_reference_geometry_points_and_all_force_labels(self):
        import matplotlib.pyplot as plt
        from prediction_plots import validated
        from prediction_extra_plots import draw_optional
        from copy import deepcopy
        r=self.snapshot();before=deepcopy(r);config=validated();config['plots']['shap']['enabled']=True
        def inspect(fig,*args):
            fig.canvas.draw();a,b,c,d,cb=fig.axes
            np.testing.assert_allclose(fig.get_size_inches(),[12,10.4])
            reference=plt.figure(figsize=(12,10.4));grid=reference.add_gridspec(3,2,left=.19,right=.97,bottom=.16,top=.91,height_ratios=[1.1,.9,.59],wspace=.62,hspace=.60)
            for actual,cell in ((b,grid[0,1]),(c,grid[1,:]),(d,grid[2,:])):
                expected=reference.add_subplot(cell).get_position()
                np.testing.assert_allclose(actual.get_position().bounds,expected.bounds,atol=1e-10)
            plt.close(reference)
            self.assertAlmostEqual(a.get_position().y0,b.get_position().y0)
            self.assertAlmostEqual(a.get_position().height,b.get_position().height)
            self.assertEqual(fig._suptitle.get_fontsize(),17)
            self.assertEqual(a.get_yticklabels()[0].get_fontsize(),10)
            self.assertEqual(a.collections[0].get_sizes().tolist(),[2.5])
            self.assertAlmostEqual(a.collections[0].get_alpha(),.72)
            np.testing.assert_allclose(a.collections[0].cmap(0.)[:3],(68/255,121/255,201/255))
            self.assertEqual(len([t for t in d.texts if t.get_gid()=='shap-force-label']),6)
            self.assertEqual(len([line for line in d.lines if line.get_gid()=='shap-force-leader']),6)
            self.assertEqual(len([line for line in c.lines if line.get_gid()=='shap-waterfall-connector']),5)
            self.assertTrue(all(spine.get_visible() for spine in a.spines.values()))
            for patch in d.patches:
                x=patch.get_xy()[:,0]
                if patch.get_gid()=='shap-force-positive':self.assertLessEqual(float(x.max()),r['case']['output']+1e-10)
                else:self.assertGreaterEqual(float(x.min()),r['case']['output']-1e-10)
            plt.close(fig)
        draw_optional(Path('.'),{'shap':r},config,inspect,[])
        self.assertEqual(r,before)

    def test_old_factory_style_upgrades_but_custom_choices_survive(self):
        from prediction_plots import validated
        old={'plots':{'shap':dict(width=14,height=11.8,point_size=9,style={},bar_color='#123456',max_display=9,feature_order=['A'])}}
        p=validated(old)['plots']['shap']
        self.assertEqual((p['width'],p['height'],p['point_size']),(12,10.4,2.5))
        self.assertEqual(p['style']['title_size'],17)
        self.assertEqual(p['bar_color'],'#123456');self.assertEqual(p['max_display'],9);self.assertEqual(p['feature_order'],['A'])
        p['point_size']=7
        self.assertEqual(validated({'plots':{'shap':p}})['plots']['shap']['point_size'],7)

if __name__=='__main__':unittest.main()
