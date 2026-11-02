"""Optional training-only LASSO diagnostics and additive explanations of fitted models."""
import math,warnings
import numpy as np
import pandas as pd

DEFAULTS=dict(lasso=dict(enabled=False,lambda_min=.0001,lambda_max=1.,lambda_count=24,rule='min',max_features=10,max_iter=10000,tol=.0001),shap=dict(enabled=False,model='XGB',dataset='validation',max_samples=500,case_id=''))

def options(value,models):
    from copy import deepcopy
    config=deepcopy(DEFAULTS)
    if not isinstance(value,dict):raise ValueError('可选分析参数无效。')
    for name,part in value.items():
        if name not in config or not isinstance(part,dict) or any(k not in config[name] for k in part):raise ValueError('可选分析包含未知参数。')
        config[name].update(part)
    for name,part in config.items():
        if type(part['enabled']) is not bool:raise ValueError('可选分析开关无效。')
    for name in config:
        if not config[name]['enabled']:config[name]=deepcopy(DEFAULTS[name])
    l=config['lasso'];s=config['shap']
    def number(v,lo,hi,label,integer=False):
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi or (integer and int(v)!=v):raise ValueError(label+' 超出允许范围。')
    number(l['lambda_min'],1e-7,10,'λ 下限');number(l['lambda_max'],1e-6,100,'λ 上限')
    if l['lambda_min']>=l['lambda_max']:raise ValueError('λ 下限需小于上限。')
    number(l['lambda_count'],8,260,'λ 网格数量',True);number(l['max_features'],1,60,'最多保留指标数',True);number(l['max_iter'],100,50000,'LASSO 最大迭代数',True);number(l['tol'],1e-7,.01,'LASSO 收敛容差')
    if l['rule'] not in ('min','1se','count'):raise ValueError('LASSO 选择规则无效。')
    if s['model'] not in ('LR','RF','XGB'):raise ValueError('SHAP 目前支持 LR、RF、XGB。')
    if s['enabled'] and s['model'] not in models:raise ValueError('SHAP 所选模型未启用，请勾选该模型或调整 SHAP 设置。')
    if s['dataset'] not in ('train','validation','all'):raise ValueError('SHAP 样本范围无效。')
    number(s['max_samples'],10,500,'SHAP 最大样本数',True)
    if not isinstance(s['case_id'],str) or len(s['case_id'])>300:raise ValueError('SHAP 病例编号无效。')
    return config

def preprocessor(numeric,categorical):
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import OneHotEncoder,StandardScaler
    transformers=[]
    if numeric:transformers.append(('num',SimpleImputer(strategy='median'),numeric))
    if categorical:transformers.append(('cat',Pipeline([('fill',SimpleImputer(strategy='most_frequent')),('encode',OneHotEncoder(handle_unknown='ignore',drop='first',sparse_output=False))]),categorical))
    return Pipeline([('prepare',ColumnTransformer(transformers)),('scale',StandardScaler())])

def encoded_columns(prepare,numeric,categorical):
    names=list(numeric);groups=list(numeric)
    if categorical:
        enc=prepare.named_transformers_['cat'].named_steps['encode']
        for i,name in enumerate(categorical):
            for j,value in enumerate(enc.categories_[i]):
                if enc.drop_idx_ is not None and j==enc.drop_idx_[i]:continue
                names.append(name+'='+str(value));groups.append(name)
    return names,groups

def lasso(X,y,train,numeric,categorical,config,seed,progress):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import log_loss
    from sklearn.exceptions import ConvergenceWarning
    progress('LASSO：准备训练集内分层五折交叉验证…')
    Xtr=X.iloc[train];yt=y[train];prepare=preprocessor(numeric,categorical);matrix=prepare.fit_transform(Xtr)
    encoded,groups=encoded_columns(prepare.named_steps['prepare'],numeric,categorical)
    if matrix.shape[1]>300:raise ValueError('LASSO 编码后超过 300 列，请减少高水平分类指标。')
    lambdas=np.geomspace(config['lambda_min'],config['lambda_max'],int(config['lambda_count']));folds=[];convergence=0
    def estimator(n):
        kw=dict(solver='saga',warm_start=True,max_iter=int(config['max_iter']),tol=config['tol'],random_state=seed)
        if LogisticRegression().get_params().get('penalty')=='deprecated':kw['l1_ratio']=1.
        else:kw['penalty']='l1'
        return LogisticRegression(C=1/(n*lambdas[0]),**kw)
    coefficients=[];fitted=estimator(len(train))
    for i,lam in enumerate(lambdas):
        progress(f'LASSO：完整训练集系数路径 {i+1}/{len(lambdas)}…');fitted.set_params(C=1/(len(train)*lam))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',ConvergenceWarning);fitted.fit(matrix,yt)
            convergence+=sum(issubclass(w.category,ConvergenceWarning) for w in caught)
        coefficients.append(fitted.coef_[0].copy())
    for fold,(fit,test) in enumerate(StratifiedKFold(5,shuffle=True,random_state=seed+1).split(Xtr,yt)):
        prep=preprocessor(numeric,categorical);a=prep.fit_transform(Xtr.iloc[fit]);b=prep.transform(Xtr.iloc[test]);model=estimator(len(fit));scores=[]
        for i,lam in enumerate(lambdas):
            progress(f'LASSO：第 {fold+1}/5 折，λ {i+1}/{len(lambdas)}…');model.set_params(C=1/(len(fit)*lam))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always',ConvergenceWarning);model.fit(a,yt[fit]);convergence+=sum(issubclass(w.category,ConvergenceWarning) for w in caught)
            scores.append(float(2*log_loss(yt[test],model.predict_proba(b)[:,1],labels=[0,1])))
        folds.append(scores)
    coef=np.array(coefficients);scores=np.array(folds);mean=scores.mean(axis=0);se=scores.std(axis=0,ddof=1)/np.sqrt(5)
    original=list(X.columns);active=np.array([[any(abs(row[j])>1e-7 for j,g in enumerate(groups) if g==name) for name in original] for row in coef]);counts=active.sum(axis=1)
    imin=int(np.argmin(mean));ione=int(np.flatnonzero(mean<=mean[imin]+se[imin])[-1]);eligible=np.flatnonzero(counts<=config['max_features']);icount=int(eligible[np.argmin(mean[eligible])]) if len(eligible) else None
    chosen={'min':imin,'1se':ione,'count':icount}[config['rule']]
    if chosen is None:raise ValueError('当前 λ 网格未达到指标数量约束，请增大 λ 上限或放宽数量限制。')
    selected=[name for name,keep in zip(original,active[chosen]) if keep]
    return dict(lambdas=lambdas.tolist(),coefficients=coef.tolist(),encoded_names=encoded,groups=groups,original_names=original,nonzero_counts=counts.astype(int).tolist(),cv_mean=mean.tolist(),cv_se=se.tolist(),fold_deviance=scores.tolist(),index_min=imin,index_1se=ione,index_count=icount,index_selected=chosen,selected_features=selected,rule=config['rule'],train_n=len(train),train_indices=list(map(int,train)),convergence_warnings=convergence,lambda_definition='平均负对数似然 + λ·L1；C=1/(训练折例数·λ)',settings=config)

def explain(model_name,pipeline,X,y,train,validation,ids,numeric,categorical,config,seed,progress):
    import shap
    from scipy.special import expit
    progress('SHAP：准备同一次拟合模型及病例…')
    ix=np.array(train if config['dataset']=='train' else validation if config['dataset']=='validation' else np.arange(len(X)))
    if len(ix)>config['max_samples']:ix=np.sort(np.random.default_rng(seed).choice(ix,int(config['max_samples']),replace=False))
    if config['case_id']:
        candidates=np.flatnonzero(ids.astype(str).to_numpy()==config['case_id'])
        if not len(candidates):raise ValueError('SHAP 病例编号不存在，请核对编号列。')
        case=int(candidates[0])
    else:case=int(validation[0])
    joint=np.array(list(dict.fromkeys([*map(int,ix),case])));prep=pipeline.named_steps['prepare'];matrix=np.asarray(prep.transform(X.iloc[joint]),dtype=float);model=pipeline.named_steps['model']
    encoded,groups=encoded_columns(prep,numeric,categorical)
    if matrix.shape[1]>300:raise ValueError('SHAP 编码后超过 300 列，请减少高水平分类指标。')
    progress(f'SHAP：计算 {len(joint)} 例、{matrix.shape[1]} 个编码指标…')
    if model_name=='LR':
        background=np.asarray(prep.transform(X.iloc[train]),dtype=float)
        if len(background)>100:background=background[np.random.default_rng(seed).choice(len(background),100,replace=False)]
        explainer=shap.LinearExplainer(model,background);result=explainer(matrix);values=np.asarray(result.values);base=np.asarray(result.base_values);raw=np.asarray(model.decision_function(matrix));unit='log_odds'
    else:
        result=shap.TreeExplainer(model,model_output='raw')(matrix);values=np.asarray(result.values);base=np.asarray(result.base_values)
        if model_name=='RF':values=values[:,:,1];base=base[:,1];raw=model.predict_proba(matrix)[:,1];unit='probability'
        else:
            import xgboost as xgb
            raw=model.get_booster().predict(xgb.DMatrix(matrix),output_margin=True);unit='log_odds'
    if base.ndim==0:base=np.repeat(base,len(joint))
    base=base.reshape(-1)
    if not np.allclose(base+values.sum(axis=1),raw,rtol=1e-4,atol=1e-5):raise ValueError('SHAP 加和校验失败，未输出解释图。')
    probability=pipeline.predict_proba(X.iloc[joint])[:,1]
    if unit=='log_odds' and not np.allclose(expit(raw),probability,rtol=1e-4,atol=1e-5):raise ValueError('SHAP 原始输出与模型预测概率不一致。')
    original=list(X.columns);grouped=np.column_stack([values[:,[i for i,g in enumerate(groups) if g==name]].sum(axis=1) for name in original])
    if not np.allclose(grouped.sum(axis=1),values.sum(axis=1)):raise ValueError('SHAP 分类指标聚合校验失败。')
    locations={int(row):i for i,row in enumerate(joint)};sample_positions=[locations[int(row)] for row in ix];local=locations[case];display=[];color_values=[]
    for name in original:
        column=X.iloc[ix][name]
        if name in numeric:colors=pd.to_numeric(column,errors='coerce').to_numpy(dtype=float,copy=True)
        else:
            levels=sorted(X[name].dropna().astype(str).unique());mapping={v:i for i,v in enumerate(levels)};colors=column.map(mapping).to_numpy(dtype=float,copy=True)
        finite=np.isfinite(colors)
        if finite.any():
            lo,hi=np.min(colors[finite]),np.max(colors[finite]);colors[finite]=(colors[finite]-lo)/(hi-lo) if hi>lo else .5
        color_values.append([float(v) if np.isfinite(v) else None for v in colors])
        value=X.iloc[case][name];display.append('缺失（按训练集规则处理）' if pd.isna(value) else (f'{float(value):g}' if isinstance(value,(int,float,np.number)) else str(value)))
    return dict(model=model_name,unit=unit,feature_names=original,sample_indices=list(map(int,ix)),sample_ids=ids.iloc[ix].astype(str).tolist(),sample_shap=grouped[sample_positions].tolist(),sample_color=np.array(color_values,dtype=object).T.tolist(),sample_base=base[sample_positions].tolist(),sample_output=np.asarray(raw)[sample_positions].astype(float).tolist(),sample_probability=probability[sample_positions].tolist(),importance=np.abs(grouped[sample_positions]).mean(axis=0).tolist(),dataset=config['dataset'],dataset_total=len(train) if config['dataset']=='train' else len(validation) if config['dataset']=='validation' else len(X),case=dict(id=str(ids.iloc[case]),index=case,dataset='训练集' if case in train else '验证集',truth=int(y[case]),base=float(base[local]),output=float(raw[local]),probability=float(probability[local]),shap=grouped[local].tolist(),values=display),max_additivity_error=float(np.max(abs(base+values.sum(axis=1)-raw))))

def tables(writer,data):
    if data.get('lasso'):
        r=data['lasso'];rows=[]
        for i,lam in enumerate(r['lambdas']):rows.append(dict(lambda_=lam,ln_lambda=float(np.log(lam)),mean_deviance=r['cv_mean'][i],standard_error=r['cv_se'][i],nonzero_original=r['nonzero_counts'][i],**{'fold_'+str(j+1):v[i] for j,v in enumerate(r['fold_deviance'])}))
        pd.DataFrame(rows).to_excel(writer,sheet_name='LASSO交叉验证',index=False)
        coef=pd.DataFrame(r['coefficients'],columns=r['encoded_names']);coef.insert(0,'lambda',r['lambdas']);coef.to_excel(writer,sheet_name='LASSO编码系数路径',index=False)
        pd.DataFrame({'保留指标':r['selected_features']}).to_excel(writer,sheet_name='LASSO建议指标',index=False)
        pd.DataFrame([dict(rule=k,lambda_=r['lambdas'][r['index_'+k]],nonzero_original=r['nonzero_counts'][r['index_'+k]]) for k in ('min','1se','count') if r['index_'+k] is not None]).to_excel(writer,sheet_name='LASSO规则汇总',index=False)
    if data.get('shap'):
        r=data['shap'];table=pd.DataFrame(r['sample_shap'],columns=r['feature_names']);table.insert(0,'编号',r['sample_ids']);table['基线输出']=r['sample_base'];table['模型输出']=r['sample_output'];table['预测概率']=r['sample_probability'];table.to_excel(writer,sheet_name='SHAP逐例贡献',index=False)
        pd.DataFrame({'指标':r['feature_names'],'平均绝对SHAP值':r['importance']}).sort_values('平均绝对SHAP值',ascending=False).to_excel(writer,sheet_name='SHAP重要性',index=False)
        c=r['case'];pd.DataFrame({'指标':r['feature_names'],'原始取值':c['values'],'SHAP贡献':c['shap']}).to_excel(writer,sheet_name='SHAP单病例',index=False)
