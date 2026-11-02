"""Release contract: fifth tool must work through the packaged IPC bridge."""
import base64, io
from pathlib import Path
from zipfile import ZipFile

def verify_prediction(call, job, folder):
    folder=Path(folder)
    source=folder/'临床二分类打包测试.csv'
    source.write_text('编号,分组,年龄,性别\n'+'\n'.join(
        f'P{i:03},{i%2},{25+(i*13)%49},{"女" if i%3 else "男"}' for i in range(100)),encoding='utf-8-sig')
    inspected=call('tool.prediction.inspect',dict(paths=[str(source)]))
    assert inspected['rows']==100
    config=call('tool.prediction.plot.defaults')['factory']
    config['common'].update(dpi=72,preview_dpi=72,formats=['png','pdf','svg'])
    config['plots']['lasso']['enabled']=True
    config['plots']['shap']['enabled']=True
    parameters=dict(dataset=inspected['id'],id_column='编号',target='分组',positive='1',
        features=[dict(name='年龄',kind='continuous'),dict(name='性别',kind='categorical')],
        models=['LR','RF','XGB','SVM'],seed=42,train_ratio=.7,threshold=.5,
        grids={model:{key:[values[0]] for key,values in grid.items()} for model,grid in inspected['grids'].items()},
        plot_config=config,optional=dict(lasso=dict(enabled=True,lambda_count=8),shap=dict(enabled=True,model='XGB',max_samples=10)))
    result=job('prediction',parameters)
    assert len(result['metrics'])==8 and len(result['images'])==5,result.keys()
    assert result['optional']['shap']['max_additivity_error']<1e-4
    assert result['optional']['lasso']['train_n']==70
    exported=call('tool.prediction.export',dict(id=result['id'],format='zip'))
    with ZipFile(io.BytesIO(base64.b64decode(exported['content']))) as archive:
        names=archive.namelist()
        assert 'plot-data.json' in names and '模型分析结果.xlsx' in names
        assert len([n for n in names if n.endswith('.png')])==5,names
        assert len([n for n in names if n.endswith('.pdf')])==5,names
        assert len([n for n in names if n.endswith('.svg')])==5,names
    config['common']['dpi']=90
    redrawn=job('prediction_plot',dict(id=result['id'],plot_config=config))
    assert redrawn['metrics']==result['metrics'] and len(redrawn['images'])==5
    print('Packaged fifth tool: four models, LASSO, SHAP, PNG/PDF/SVG/Excel archive and style redraw passed',flush=True)
