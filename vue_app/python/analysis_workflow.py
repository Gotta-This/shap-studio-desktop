"""Persist owned analysis snapshots for full tables, redraw and selective export."""
from pathlib import Path
import base64,json,re,uuid,zipfile,io,os
from clinical_studio.config import default_config


def folder(profile,rid):
    if not re.fullmatch('[a-f0-9]{32}',rid or ''):raise ValueError('结果标识无效，请重新生成。')
    ref=profile/'analysis'/rid/'reference.json'
    if not ref.is_file():raise ValueError('结果已不可用，请重新生成。')
    return Path(json.loads(ref.read_text())['folder'])


def run(profile,p,progress):
    # Matplotlib 3.11 limits even addfont() entries when this flag is set.
    # Analysis uses bundled CJK fonts plus the normal installed-font fallback.
    os.environ.pop("MPL_IGNORE_SYSTEM_FONTS",None)
    from clinical_studio.engine import run_analysis
    import joblib
    previous=None
    if p.get('previous'):
        folder(profile,p['previous'])
        previous=joblib.load(profile/'analysis'/p['previous']/'model.joblib')
    result=run_analysis(p['config'],p.get('output') or profile/'exports',progress=progress,previous=previous,data_only=p.get('data_only',False))
    rid=uuid.uuid4().hex;store=profile/'analysis'/rid;store.mkdir(parents=True)
    (store/'reference.json').write_text(json.dumps({'folder':str(result.folder)}));joblib.dump(result,store/'model.joblib')
    return dict(id=rid,folder=str(result.folder),metrics=result.metrics,audit=result.audit,messages=result.messages,config=result.config,has_model=result.model is not None,columns=list(result.data.columns),rows=json.loads(result.data.head(200).to_json(orient='values')),total=len(result.data),images=[dict(name=f.name,url='data:image/png;base64,'+base64.b64encode(f.read_bytes()).decode()) for f in (result.folder/'figures').glob('*.png')])


def table(profile,p):
    import pandas as pd
    root=folder(profile,p['id']);kind=p.get('kind','data');name={'data':'data.csv','coefficients':'coefficients.csv','predictions':'test_predictions.csv','shap':'shap_values.csv'}.get(kind)
    if not name:raise ValueError('未知结果表。')
    path=root/name
    if not path.exists():return dict(columns=[],rows=[],total=0)
    df=pd.read_csv(path);start=max(0,int(p.get('page',0)))*200
    return dict(columns=list(df.columns),rows=json.loads(df.iloc[start:start+200].to_json(orient='values')),total=len(df))


def export(profile,p):
    root=folder(profile,p['id']);kinds=p.get('kinds',['data','figures','config','reports'])
    if not kinds:raise ValueError('请至少选择一项保存内容。')
    def selected(f):
        rel=f.relative_to(root)
        key='figures' if rel.parts[0]=='figures' else 'config' if f.name=='parameters.json' else 'data' if f.suffix in ('.csv','.xlsx') else 'reports'
        return key in kinds
    if p.get('destination'):
        import shutil
        target=Path(p['destination']).expanduser()/root.name
        if target.resolve()==root.resolve() or root.resolve() in target.resolve().parents:raise ValueError('不能把结果复制到自身目录内。')
        if target.exists():target=target.with_name(target.name+'_'+uuid.uuid4().hex[:6])
        for f in root.rglob('*'):
            if f.is_file() and selected(f):dest=target/f.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
        return dict(folder=str(target))
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for f in root.rglob('*'):
            if f.is_file() and selected(f):z.write(f,root.name+'/'+str(f.relative_to(root)))
    return dict(name=root.name+'.zip',base64=base64.b64encode(out.getvalue()).decode())
