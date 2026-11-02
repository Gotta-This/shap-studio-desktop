"""General binary clinical prediction workflow. No source records are modified."""
from pathlib import Path
import base64, hashlib, io, json, math, re, uuid, zipfile
import numpy as np
import pandas as pd

MODELS = ('LR','RF','XGB','SVM')
COLORS = dict(zip(MODELS, ('#8054A2','#E68A2E','#2776B5','#239A8B')))
GRIDS = {'LR': {'model__C':[0.1,1,10]}, 'RF': {'model__max_depth':[3,6], 'model__min_samples_leaf':[2,5]}, 'XGB': {'model__max_depth':[2,3], 'model__learning_rate':[0.05,0.1]}, 'SVM': {'model__C':[0.1,1,10], 'model__gamma':['scale']}}

def location(profile, token):
    if not re.fullmatch(r'[a-f0-9]{32}',str(token)): raise ValueError('数据或结果编号无效。')
    path=profile/'prediction'/token
    if not path.is_dir(): raise ValueError('数据或结果已不可用，请重新导入。')
    return path

def frame(path, sheet=None):
    meta=json.loads((path/'source.json').read_text())
    source=path/meta['file']
    if source.suffix=='.csv':
        try: raw=pd.read_csv(source,header=None,dtype=object,encoding='utf-8-sig')
        except UnicodeDecodeError: raw=pd.read_csv(source,header=None,dtype=object,encoding='gb18030')
    else: raw=pd.read_excel(source,sheet_name=sheet or meta['sheets'][0],header=None,dtype=object)
    if raw.shape[0]<2: raise ValueError('文件需要一行列名和至少一行数据。')
    headers=[str(x).strip() if pd.notna(x) else '' for x in raw.iloc[0]]
    if any(not x for x in headers) or len(set(headers))!=len(headers): raise ValueError('列名不能留空或重复。')
    df=raw.iloc[1:].copy();df.columns=headers;df=df.reset_index(drop=True)
    df=df.replace(r'^\s*$',np.nan,regex=True)
    if len(df)>50000 or len(headers)>300: raise ValueError('第一版支持最多 50,000 行、300 列。')
    return df

def inspect(profile, paths=None, token=None, sheet=None):
    if paths is not None:
        if len(paths)!=1: raise ValueError('请选择一个 Excel 或 CSV 文件。')
        source=paths[0];ext=source.suffix.lower()
        if ext not in ('.xlsx','.csv'): raise ValueError('支持 XLSX 和 CSV，请先将 XLS 转为 XLSX。')
        if source.stat().st_size>32*1024*1024: raise ValueError('数据文件最多 32 MB。')
        token=uuid.uuid4().hex;path=profile/'prediction'/token;path.mkdir(parents=True)
        (path/('input'+ext)).write_bytes(source.read_bytes())
        sheets=[]
        if ext=='.xlsx':
            with pd.ExcelFile(source) as workbook:sheets=workbook.sheet_names
        (path/'source.json').write_text(json.dumps(dict(file='input'+ext,name=source.name,sheets=sheets,sha256=hashlib.sha256(source.read_bytes()).hexdigest()),ensure_ascii=False))
    path=location(profile,token);meta=json.loads((path/'source.json').read_text());df=frame(path,sheet)
    columns=[]
    for name in df:
        s=df[name];non=s.dropna();numeric=pd.to_numeric(non,errors='coerce').notna().all()
        distinct=non.astype(str).unique().tolist()
        columns.append(dict(name=name,kind='categorical' if not numeric or len(distinct)<=2 else 'continuous',missing=int(s.isna().sum()),unique=len(distinct),values=distinct[:100],selected=name not in ('编号','分组')))
    return dict(id=token,name=meta['name'],sheets=meta['sheets'],sheet=sheet or (meta['sheets'][0] if meta['sheets'] else ''),rows=len(df),columns=columns,preview=json.loads(df.head(8).to_json(orient='values')),grids=GRIDS)

def prepared(profile,p):
    path=location(profile,p.get('dataset'));df=frame(path,p.get('sheet'));idcol=p.get('id_column','编号');target=p.get('target','分组')
    if idcol not in df or target not in df or idcol==target: raise ValueError('请选择不同的编号列与结局列。')
    if df[idcol].isna().any() or df[idcol].astype(str).duplicated().any(): raise ValueError('病例编号不能缺失或重复；同一病例请先整理为一行。')
    if df[target].isna().any(): raise ValueError('结局列存在缺失，请先核对。')
    labels=df[target].astype(str);levels=sorted(labels.unique())
    positive=str(p.get('positive','1'))
    if len(levels)!=2 or positive not in levels: raise ValueError('结局必须恰好包含两类，并选择有效的阳性结局。')
    features=p.get('features',[]);names=[f['name'] for f in features]
    if not names or len(names)!=len(set(names)) or any(n not in df or n in (idcol,target) for n in names): raise ValueError('至少选择一个有效指标；编号和结局不能参与预测。')
    if len(names)>60: raise ValueError('第一版最多选择 60 个预测指标。')
    X=df[names].copy();numeric=[];categorical=[]
    for f in features:
        name=f['name']
        if X[name].isna().all(): raise ValueError(name+'：整列为空，请取消该指标。')
        if f['kind']=='continuous':
            converted=pd.to_numeric(X[name],errors='coerce')
            if (converted.isna() & X[name].notna()).any() or np.isinf(converted.dropna().astype(float)).any(): raise ValueError(name+'：包含非数值或无穷值，请检查变量类型。')
            X[name]=converted.astype(float);numeric.append(name)
        elif f['kind']=='categorical':
            if X[name].dropna().astype(str).nunique()>30: raise ValueError(name+'：分类水平超过 30，请核对类型或取消该指标。')
            X[name]=X[name].map(lambda v:str(v) if pd.notna(v) else np.nan);categorical.append(name)
        else: raise ValueError('变量类型无效。')
    y=(labels==positive).astype(int).to_numpy();seed=p.get('seed',20261102)
    if type(seed) is not int or not 0<=seed<=2**32-1: raise ValueError('随机种子必须为 0～4294967295 的整数。')
    if p.get('split_mode','ratio')=='count':
        train=p.get('train_count')
        if type(train) is not int or not 5<=train<len(df)-1: raise ValueError('训练例数必须是整数，并给验证集保留至少两例。')
    else:
        ratio=p.get('train_ratio',0.7)
        if not isinstance(ratio,(int,float)) or not 0.5<=ratio<=0.9: raise ValueError('训练比例应为 0.5～0.9。')
        train=int(math.floor(len(df)*ratio))
    from sklearn.model_selection import train_test_split
    try: tr,va=train_test_split(np.arange(len(df)),train_size=train,stratify=y,random_state=seed)
    except ValueError as e: raise ValueError('无法分层划分，请检查两类例数及划分比例：'+str(e))
    if min(np.bincount(y[tr],minlength=2))<5: raise ValueError('训练集中每类至少 5 例，才能进行分层 5 折交叉验证。')
    for name in names:
        if X.iloc[tr][name].isna().all():raise ValueError(name+'：训练集内整列缺失，无法填补，请取消该指标。')
    if min(np.bincount(y[va],minlength=2))<1: raise ValueError('验证集需要同时包含两个结局类别。')
    threshold=p.get('threshold',0.5)
    if not isinstance(threshold,(int,float)) or not 0<threshold<1: raise ValueError('分类阈值应在 0 和 1 之间。')
    models=p.get('models',list(MODELS))
    if not models or len(set(models))!=len(models) or any(m not in MODELS for m in models): raise ValueError('请选择有效模型。')
    return path,df,X,y,tr,va,numeric,categorical,models

def hl(y,prob):
    from scipy.stats import chi2
    table=pd.DataFrame({'p':prob,'y':y})
    table['bin']=pd.qcut(table.p,q=10,duplicates='drop')
    rows=[];stat=0.;small=0
    for _,g in table.groupby('bin',observed=True):
        n=len(g);expected=float(g.p.sum());observed=int(g.y.sum());den=expected*(1-expected/n)
        if den<=0: continue
        contribution=(observed-expected)**2/den;stat+=contribution
        small+=int(expected<5)+int(n-expected<5)
        rows.append(dict(n=n,expected=expected,observed=observed,predicted=float(g.p.mean()),actual=observed/n,contribution=contribution))
    dof=len(rows)-2
    return dict(chi2=stat if dof>0 else None,df=max(dof,0),p=float(chi2.sf(stat,dof)) if dof>0 else None,groups=len(rows),small_cells=small,rows=rows)

def evaluate(y,prob,threshold,seed):
    from sklearn.metrics import roc_auc_score,confusion_matrix,f1_score,brier_score_loss
    pred=prob>=threshold;tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    def ratio(a,b):return float(a/b) if b else None
    rng=np.random.default_rng(seed);aucs=[]
    for _ in range(300):
        ix=rng.integers(0,len(y),len(y))
        if len(np.unique(y[ix]))==2: aucs.append(roc_auc_score(y[ix],prob[ix]))
    ci=np.quantile(aucs,[.025,.975]).tolist() if aucs else [None,None]
    return dict(auc=float(roc_auc_score(y,prob)),ci_low=ci[0],ci_high=ci[1],accuracy=ratio(tp+tn,len(y)),sensitivity=ratio(tp,tp+fn),specificity=ratio(tn,tn+fp),ppv=ratio(tp,tp+fp),npv=ratio(tn,tn+fn),f1=float(f1_score(y,pred,zero_division=0)),brier=float(brier_score_loss(y,prob)),hl=hl(y,prob))

def run(profile,p,progress):
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler,OneHotEncoder
    from sklearn.model_selection import GridSearchCV,StratifiedKFold,ParameterGrid
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.svm import SVC
    progress('核对数据、结局编码与分层划分…')
    path,df,X,y,tr,va,numeric,categorical,models=prepared(profile,p)
    from prediction_plots import validated,snapshot,render,archive
    from prediction_extras import options,lasso,explain,tables
    optional=options(p.get('optional',{}),models)
    requested_plots=json.loads(json.dumps(p.get('plot_config') or {}))
    for extra in ('lasso','shap'):
        if optional[extra]['enabled'] and extra not in requested_plots.get('plots',{}):requested_plots.setdefault('plots',{})[extra]={'enabled':True}
    plot_config=validated(requested_plots,[f['name'] for f in p['features']])
    if optional['shap']['enabled'] and optional['shap']['case_id'] and optional['shap']['case_id'] not in df[p.get('id_column','编号')].astype(str).tolist():raise ValueError('SHAP 病例编号不存在，请核对编号列。')
    seed=p.get('seed',20261102);threshold=p.get('threshold',.5)
    grids=p.get('grids',GRIDS)
    estimators={'LR':LogisticRegression(max_iter=3000,random_state=seed),'RF':RandomForestClassifier(n_estimators=150,n_jobs=1,random_state=seed),'SVM':SVC(probability=True,random_state=seed)}
    if 'XGB' in models:
        try:
            from xgboost import XGBClassifier
            estimators['XGB']=XGBClassifier(n_estimators=100,n_jobs=1,random_state=seed,eval_metric='logloss',tree_method='hist')
        except ImportError: raise ValueError('当前 Python 环境缺少 XGBoost，请安装项目依赖后重试。')
    for model in models:
        grid=grids.get(model)
        if not isinstance(grid,dict) or not grid or any(k not in GRIDS[model] for k in grid): raise ValueError(model+' 网格参数无效，请使用界面列出的参数。')
        if any(not isinstance(v,list) or not v or len(v)>10 for v in grid.values()) or len(ParameterGrid(grid))>50: raise ValueError('每个参数应为非空数组，每模型最多 50 组组合。')
    rid=uuid.uuid4().hex;out=profile/'prediction'/rid;out.mkdir(parents=True)
    reports=[];predictions={};best={};lr=None;fitted_models={}
    for model in models:
        progress('正在训练 '+model+'：网格搜索 × 分层 5 折交叉验证…')
        transforms=[]
        if numeric:transforms.append(('num',Pipeline([('fill',SimpleImputer(strategy='median')),('scale',StandardScaler())]),numeric))
        if categorical:transforms.append(('cat',Pipeline([('fill',SimpleImputer(strategy='most_frequent')),('encode',OneHotEncoder(handle_unknown='ignore',drop='first',sparse_output=False))]),categorical))
        pipe=Pipeline([('prepare',ColumnTransformer(transforms)),('model',estimators[model])])
        search=GridSearchCV(pipe,grids[model],scoring='roc_auc',cv=StratifiedKFold(5,shuffle=True,random_state=seed),n_jobs=1,error_score='raise')
        search.fit(X.iloc[tr],y[tr]);fitted=search.best_estimator_
        best[model]=dict(params=search.best_params_,cv_auc=float(search.best_score_))
        fitted_models[model]=fitted
        if model=='LR':lr=fitted
        predictions[model]={}
        for label,ix in [('训练集',tr),('验证集',va)]:
            progress(model+'：计算 '+label+' 指标与 AUC 置信区间…')
            prob=fitted.predict_proba(X.iloc[ix])[:,1];predictions[model][label]=prob
            reports.append(dict(model=model,dataset=label,n=len(ix),events=int(y[ix].sum()),**evaluate(y[ix],prob,threshold,seed)))
    extras={}
    if optional['lasso']['enabled']:extras['lasso']=lasso(X,y,tr,numeric,categorical,optional['lasso'],seed,progress)
    if optional['shap']['enabled']:extras['shap']=explain(optional['shap']['model'],fitted_models[optional['shap']['model']],X,y,tr,va,df[p.get('id_column','编号')],numeric,categorical,optional['shap'],seed,progress)
    progress('正在生成图件及可选分析图…')
    plot_data=snapshot(X.iloc[tr],numeric,categorical,lr,y,tr,va,predictions,reports)
    plot_data.update(extras)
    (out/'plot-data.json').write_text(json.dumps(plot_data,ensure_ascii=False,allow_nan=False),encoding='utf8')
    images,notes,plot_config=render(out,plot_data,plot_config)
    progress('正在保存结果表、逐例概率与分析记录…')
    source=json.loads((path/'source.json').read_text());split=np.full(len(df),'验证集',dtype=object);split[tr]='训练集'
    patients=pd.DataFrame({'编号':df[p.get('id_column','编号')],'结局原值':df[p.get('target','分组')],'阳性编码':y,'数据集':split})
    for model in models:
        prob=np.empty(len(df));prob[tr]=predictions[model]['训练集'];prob[va]=predictions[model]['验证集'];patients[model+'预测概率']=prob
    metrics=[];bins=[]
    for row in reports:
        metrics.append({k:v for k,v in row.items() if k!='hl'}|{'HL_chi2':row['hl']['chi2'],'HL_df':row['hl']['df'],'HL_P':row['hl']['p'],'HL_groups':row['hl']['groups'],'HL_small_cells':row['hl']['small_cells']})
        bins.extend(dict(model=row['model'],dataset=row['dataset'],**r) for r in row['hl']['rows'])
    config=dict(p,optional=optional,plot_config=plot_config,figure_exports=[{k:v for k,v in image.items() if k!='url'} for image in images],input_sha256=source['sha256'],source_name=source['name'],actual_split=dict(train=len(tr),validation=len(va),train_ratio=len(tr)/len(df)),best=best)
    import importlib.metadata,platform
    config['environment']={k:importlib.metadata.version(k) for k in ('numpy','pandas','scikit-learn','matplotlib','scipy')}
    if 'XGB' in models:config['environment']['xgboost']=importlib.metadata.version('xgboost')
    config['python']=platform.python_version()
    (out/'analysis.json').write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    with pd.ExcelWriter(out/'模型分析结果.xlsx') as writer:
        pd.DataFrame(metrics).to_excel(writer,sheet_name='模型指标',index=False)
        patients.to_excel(writer,sheet_name='病例划分与预测',index=False)
        pd.DataFrame(bins).to_excel(writer,sheet_name='HL分组明细',index=False)
        pd.DataFrame([dict(model=k,cv_auc=v['cv_auc'],params=json.dumps(v['params'])) for k,v in best.items()]).to_excel(writer,sheet_name='最优参数',index=False)
        tables(writer,plot_data)
    warnings=notes+['训练集指标为表观性能；验证集为内部留出验证。','AUC 95%CI 使用 300 次百分位 Bootstrap；无定义的指标显示为空。','H-L 按预测概率十分位分组；重复分位点合并，少于 3 个有效组时不报告 χ²/P。','Brier 为概率整体误差；H-L P值不能单独证明模型校准良好。']
    if any(r['hl']['small_cells'] for r in reports):warnings.append('部分 H-L 分组期望频数低于 5，检验结果请谨慎解释。')
    if X.isna().any().any():warnings.append('存在指标缺失：连续变量按训练折中位数、分类变量按训练折众数填补。')
    if 'lasso' in extras:warnings.append('LASSO 仅使用训练集与折内预处理，诊断结果不自动替换四模型输入；λ 定义为平均负对数似然的 L1 系数。')
    if 'shap' in extras:warnings.append('SHAP 使用同一次拟合模型；分类编码贡献按原始指标相加，并已核对基线＋贡献＝模型输出。')
    optional_summary={}
    if 'lasso' in extras:
        r=extras['lasso'];optional_summary['lasso']=dict(selected_features=r['selected_features'],lambda_selected=r['lambdas'][r['index_selected']],rule=r['rule'],train_n=r['train_n'],convergence_warnings=r['convergence_warnings'])
    if 'shap' in extras:
        r=extras['shap'];optional_summary['shap']=dict(model=r['model'],unit=r['unit'],sample_n=len(r['sample_ids']),dataset=r['dataset'],case=r['case'],max_additivity_error=r['max_additivity_error'])
    (out/'说明.txt').write_text('\n'.join(warnings),encoding='utf8')
    (out/'图表设置.json').write_text(json.dumps(plot_config,ensure_ascii=False,indent=2),encoding='utf8')
    archive(out)
    summary=dict(id=rid,optional=optional_summary,plot_config=plot_config,plot_features=[dict(name=f['name'],kind=f['kind'],values=X[f['name']].dropna().astype(str).unique().tolist()[:30] if f['kind']=='categorical' else []) for f in p['features']],metrics=metrics,images=images,warnings=warnings,best=best,split=config['actual_split'],source=source['name'],positive=str(p.get('positive','1')),threshold=threshold)
    (out/'result.json').write_text(json.dumps(summary,ensure_ascii=False,allow_nan=False),encoding='utf8')
    return summary

def export(profile,p):
    path=location(profile,p['id']);name='模型分析结果.xlsx' if p.get('format')=='xlsx' else '完整分析结果.zip'
    target=path/name
    if not target.is_file():raise ValueError('结果文件不存在，请重新运行。')
    return dict(name=name,content=base64.b64encode(target.read_bytes()).decode())
