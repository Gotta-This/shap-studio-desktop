import unittest,tempfile,json,hashlib,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np,pandas as pd
from prediction import inspect,run,location
from prediction_plots import defaults,validated,redraw,render

class PlotValidationTests(unittest.TestCase):
    def test_defaults_and_partial_inheritance(self):
        c=validated({'common':{'dpi':150},'plots':{'roc':{'style':{'dpi':200}}}})
        self.assertEqual(c['common']['dpi'],150);self.assertEqual(c['plots']['roc']['style']['dpi'],200);self.assertEqual(c['models']['RF']['color'],'#E68A2E')
    def test_bad_styles_are_rejected(self):
        bad=[{'common':{'dpi':0}},{'common':{'formats':[]}},{'common':{'background':'bad-color'}},{'model_order':['LR']},{'common':{'dpi':float('nan')}},{'plots':{'roc':{'left':.9,'right':.2}}},{'plots':{'roc':{'filename':'../escape'}}},{'plots':{'roc':{'legend_template':'{label.__class__}'}}},{'plots':{'roc':{'x_ticks':[1,0]}}},{'plots':{'nomogram':{'feature_order':['年龄','年龄']}}},{'plots':{'nomogram':{'features':{'年龄':{'ticks':['bad']}}}}},{'unknown':1}]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):validated(value)
    def test_feature_label_mapping(self):
        c=validated({'plots':{'nomogram':{'features':{'性别':{'category_labels':{'0':'女','1':'男'},'color':'#ff0000'}}}}})
        self.assertEqual(c['plots']['nomogram']['features']['性别']['category_labels']['0'],'女')

class PlotRedrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);r=np.random.default_rng(44);n=100
        age=r.normal(50,10,n);gender=r.choice(['女','男'],n);y=r.binomial(1,1/(1+np.exp(-(age-50)/10)))
        df=pd.DataFrame({'编号':[f'P{i}' for i in range(n)],'分组':y,'年龄':age,'性别':gender});path=cls.root/'数据.xlsx';df.to_excel(path,index=False);data=inspect(cls.root,[path]);cls.base=run(cls.root,dict(dataset=data['id'],features=[dict(name='年龄',kind='continuous'),dict(name='性别',kind='categorical')],models=['LR','RF'],grids={'LR':{'model__C':[1]},'RF':{'model__max_depth':[3],'model__min_samples_leaf':[2]}},plot_config={'common':{'dpi':80,'formats':['svg']}}),lambda _:None)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_redraw_no_refit_and_styles_reach_real_export(self):
        source=location(self.root,self.base['id']);hash_before=hashlib.sha256((source/'模型分析结果.xlsx').read_bytes()).hexdigest()
        config=defaults();config['common'].update(dpi=150,formats=['png','svg'],background='#fff8f0',title_size=23)
        config['model_order']=['RF','LR','XGB','SVM'];config['models']['RF'].update(label='Forest custom',color='#123abc',line_style='--')
        config['models']['LR'].update(label='Logistic custom',color='#a12345')
        config['plots']['roc'].update(title='Custom ROC title',width=8,height=6,filename='custom_roc',legend_template='{label}: {auc}',x_label='Custom X',legend_frame=True)
        config['plots']['nomogram'].update(feature_order=['性别','年龄'],points_label='Score custom')
        config['plots']['nomogram']['features']={'性别':{'label':'Gender custom','color':'#ee1122','category_labels':{'男':'Male','女':'Female'}},'年龄':{'label':'Age custom','color':'#11aa22'}}
        with patch('sklearn.model_selection.GridSearchCV.fit',side_effect=AssertionError('redraw refit')):
            result=redraw(self.root,dict(id=self.base['id'],plot_config=config),lambda _:None)
        out=location(self.root,result['id']);self.assertEqual(result['metrics'],self.base['metrics']);self.assertEqual(result['best'],self.base['best'])
        self.assertEqual(hashlib.sha256((out/'模型分析结果.xlsx').read_bytes()).hexdigest(),hash_before);self.assertEqual(hashlib.sha256((source/'模型分析结果.xlsx').read_bytes()).hexdigest(),hash_before)
        from PIL import Image
        with Image.open(out/'custom_roc.png') as im:self.assertEqual(im.size,(1200,900));self.assertAlmostEqual(im.info['dpi'][0],150,delta=.1)
        svg=(out/'custom_roc.svg').read_text();self.assertIn('Custom ROC title',svg);self.assertIn('#123abc',svg);self.assertIn('Custom X',svg);self.assertLess(svg.index('Forest custom'),svg.index('Logistic custom'))
        nom=(out/'LR列线图.svg').read_text();self.assertIn('#ee1122',nom);self.assertIn('#11aa22',nom);self.assertIn('Score custom',nom);self.assertLess(nom.index('Gender custom'),nom.index('Age custom'))
        with zipfile.ZipFile(out/'完整分析结果.zip') as z:self.assertIn('custom_roc.svg',z.namelist());self.assertIn('图表设置.json',z.namelist());self.assertNotIn('ROC_训练与验证.svg',z.namelist())
    def test_separate_panels_and_per_plot_override(self):
        c=defaults();c['common'].update(dpi=80,formats=['svg']);c['plots']['roc'].update(layout='separate',style={'dpi':100,'formats':['png']});c['plots']['calibration']['enabled']=False;c['plots']['nomogram']['enabled']=False
        result=redraw(self.root,dict(id=self.base['id'],plot_config=c),lambda _:None);out=location(self.root,result['id'])
        self.assertEqual(len(result['images']),2);self.assertTrue((out/'ROC_训练与验证_训练集.png').exists());self.assertFalse(list(out.glob('*.svg')))
        from PIL import Image
        with Image.open(out/'ROC_训练与验证_训练集.png') as im:self.assertEqual(im.size,(1320,720))
    def test_redraw_clears_obsolete_automatic_dpi_messages(self):
        c=defaults();c['common'].update(dpi=650,formats=['png','pdf'])
        with patch('prediction_plots.MAX_RASTER_PIXELS',1000000):
            first=redraw(self.root,dict(id=self.base['id'],plot_config=c),lambda _:None)
            self.assertTrue(any('PNG 已由' in w for w in first['warnings']))
            c['common']['dpi']=50
            second=redraw(self.root,dict(id=first['id'],plot_config=c),lambda _:None)
            self.assertFalse(any('PNG 已由' in w for w in second['warnings']))
            self.assertNotIn('PNG 已由',(location(self.root,second['id'])/'说明.txt').read_text())
    def test_invalid_tick_range_does_not_change_source(self):
        c=defaults();c['common'].update(dpi=80,formats=['svg']);c['plots']['nomogram']['features']={'年龄':{'ticks':[-999]}}
        with self.assertRaisesRegex(ValueError,'训练集范围'):redraw(self.root,dict(id=self.base['id'],plot_config=c),lambda _:None)
        self.assertTrue((location(self.root,self.base['id'])/'result.json').exists())
    def test_all_disabled_reports_error(self):
        c=defaults();c['common']['dpi']=80
        for p in c['plots'].values():p['enabled']=False
        with self.assertRaisesRegex(ValueError,'没有可生成'):redraw(self.root,dict(id=self.base['id'],plot_config=c),lambda _:None)
if __name__=='__main__':unittest.main()

class ReferenceNomogramTests(unittest.TestCase):
    def test_reference_axes_use_correct_independent_scales_and_risk_alignment(self):
        import matplotlib.pyplot as plt
        from scipy.special import expit
        raw=[dict(name='NRS-2002总分',kind='continuous',beta=.8,minimum=1.,maximum=5.),dict(name='能量摄入达标',kind='categorical',values=['0','1'],weights=[0.,1.4]),dict(name='CFS总分',kind='continuous',beta=.43,minimum=3.,maximum=6.),dict(name='RCSQ睡眠评分',kind='continuous',beta=-.1,minimum=42.,maximum=88.),dict(name='基线SPPB总分',kind='continuous',beta=-.1667,minimum=4.,maximum=10.),dict(name='规范功能锻炼',kind='categorical',values=['0','1'],weights=[0.,-2.1])]
        data=dict(panels=[],nomogram=dict(intercept=1.2,axes=raw));c=defaults();c['common'].update(dpi=80,formats=['svg']);c['plots']['roc']['enabled']=False;c['plots']['calibration']['enabled']=False;c['plots']['nomogram']['auto_risk_ticks']=False
        with tempfile.TemporaryDirectory() as temp:
            with patch('matplotlib.pyplot.close'):
                render(Path(temp),data,c);fig=plt.gcf();ax=fig.axes[0]
                segments={a.get_gid():a.get_segments()[0] for a in ax.collections if a.get_gid()}
                np.testing.assert_allclose(segments['nomogram-points'][:,0],[0,1]);np.testing.assert_allclose(segments['nomogram-total'][:,0],[0,1]);np.testing.assert_allclose(segments['nomogram-feature-3'][:,0],[0,1])
                self.assertLess(segments['nomogram-feature-0'][1,0],1)
                contributions=[(min(a['minimum']*a['beta'],a['maximum']*a['beta']),max(a['minimum']*a['beta'],a['maximum']*a['beta'])) if a['kind']=='continuous' else (min(a['weights']),max(a['weights'])) for a in raw]
                base=1.2+sum(v[0] for v in contributions);span=sum(hi-lo for lo,hi in contributions)
                risk=segments['nomogram-risk'][:,0];self.assertGreater(risk[0],0);self.assertLess(risk[1],1)
                expected=np.array([.01,.1,.5,.9,.99]);x=(np.log(expected/(1-expected))-base)/span;inside=(x>=0)&(x<=1)
                np.testing.assert_allclose(risk,[x[inside].min(),x[inside].max()]);np.testing.assert_allclose(expit(base+x[inside]*span),expected[inside])
                ticks=[t for t in ax.texts if np.isclose(t.get_position()[1],4.5-c['plots']['nomogram']['tick_offset'])]
                ordered=[t.get_text() for t in sorted(ticks,key=lambda t:t.get_position()[0])];self.assertEqual(ordered,['88','80','70','60','50','42'])
            plt.close('all')
    def test_nice_integral_ticks_match_reference_conventions(self):
        from prediction_plots import nice_ticks
        np.testing.assert_allclose(nice_ticks(0,296.9,6),[0,50,100,150,200,250,296.9])
        np.testing.assert_allclose(nice_ticks(1,5,5),[1,2,3,4,5])

class RasterBudgetTests(unittest.TestCase):
    def test_default_style_accepts_sixty_indicators_without_preflight_pixel_failure(self):
        c=validated({},['指标'+str(i) for i in range(60)])
        self.assertEqual(c['common']['dpi'],650)
    def test_large_png_adapts_actual_dpi_and_preserves_vector_output(self):
        import matplotlib.pyplot as plt
        data=dict(panels=[],nomogram=dict(intercept=-5,axes=[dict(name='指标',kind='continuous',beta=1.,minimum=0.,maximum=10.)]))
        c=defaults()
        for name,p in c['plots'].items():p['enabled']=name=='nomogram'
        with tempfile.TemporaryDirectory() as folder,patch('prediction_plots.MAX_RASTER_PIXELS',200000):
            images,notes,config=render(Path(folder),data,c)
            self.assertLess(images[0]['dpi'],650);self.assertEqual(images[0]['requested_dpi'],650);self.assertEqual(config['common']['dpi'],650)
            from PIL import Image
            with Image.open(Path(folder)/'LR列线图.png') as im:
                self.assertLessEqual(im.width*im.height,200000);self.assertAlmostEqual(im.info['dpi'][0],images[0]['dpi'],delta=.1)
            self.assertTrue((Path(folder)/'LR列线图.pdf').read_bytes().startswith(b'%PDF'));self.assertTrue(any('自动调整' in s for s in notes))
    def test_vector_only_and_regular_sized_dpi(self):
        from prediction_plots import bounded_dpi,MAX_RASTER_PIXELS
        self.assertEqual(bounded_dpi(11.8,8.2,650,MAX_RASTER_PIXELS),650)
        self.assertLessEqual(11.8*40.6*bounded_dpi(11.8,40.6,650,MAX_RASTER_PIXELS)**2,MAX_RASTER_PIXELS)
