"""Shared field conversion rules, independent of GUI frameworks."""
from copy import deepcopy

TYPES=[('unknown','待选择类型'),('mean_sd','数值：均数±标准差'),('quantile','数值：中位数（Q1，Q3）'),('binary','二分类：确认类别'),('gender','分类：男 / 女'),('yesno','分类：有 / 无'),('binary01','分类编码：1 / 0'),('category','自定义多分类'),('derived','由其他分类派生')]
TYPES.append(('excluded','仅保留来源，不生成'))


def convert(field,kind):
    result=deepcopy(field);old=result.get('kind');result['kind']=kind
    if kind=='excluded':result['confirmed']=True
    elif kind in ('gender','yesno','binary01'):
        result['labels']={'gender':['男','女'],'yesno':['有','无'],'binary01':[1,0]}[kind]
        if len(result.get('weights',[]))!=2:result['weights']=[None,None]
        result['confirmed']=all(v is not None for v in result['weights']) and (old!=kind or result.get('confirmed',True))
    elif kind in ('binary','category'):
        result.setdefault('labels',['类别1','类别2']);result.setdefault('weights',[None,None]);result['confirmed']=False if old!=kind else result.get('confirmed',False)
    elif old!=kind:result['confirmed']=False
    if kind=='quantile' and all(result.get(k) is not None for k in ('q1','q3')):
        span=result['q3']-result['q1']
        if result.get('lower') is None:result['lower']=max(0,result['q1']-span) if result['q1']>=0 else result['q1']-span
        if result.get('upper') is None:result['upper']=result['q3']+span
    if result.get('aggregate_pending') and kind!='excluded':result['confirmed']=False
    return result
