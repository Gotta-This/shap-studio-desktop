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


def peer_schema(field, result):
    """Apply the Qt dialog's schema sync without copying per-group values."""
    import math
    other=convert(field,result['kind'])
    other['confirmed']=bool(field.get('confirmed',False) and field.get('kind','mean_sd')==result['kind'])
    other['classification']=result.get('classification','')
    if other.get('aggregate_pending') and result['kind']!='excluded':other['confirmed']=False
    if result['kind'] in ('category','binary','gender','yesno','binary01'):
        if len(other.get('weights',[]))!=len(result['labels']):other['weights']=[None]*len(result['labels']);other['confirmed']=False
        other['labels']=deepcopy(result['labels'])
    required=('mean','sd') if other['kind']=='mean_sd' else ('q1','median','q3','lower','upper') if other['kind']=='quantile' else ()
    if any(not isinstance(other.get(key),(int,float)) or isinstance(other[key],bool) or not math.isfinite(other[key]) for key in required):other['confirmed']=False
    if other['kind'] in ('category','binary','gender','yesno','binary01') and any(value is None for value in other.get('weights',[])):other['confirmed']=False
    return other


def validate_edit(field):
    """Validate an individual editable rule before closing the V3 dialog."""
    import math
    f=deepcopy(field);kind=f.get('kind','mean_sd')
    def finite(x):return type(x) in (int,float) and math.isfinite(x)
    if f.get('aggregate_pending') and kind!='excluded':raise ValueError('总发生率的联合规则尚未确认，请选择“仅保留来源，不生成”，或删除此项。')
    if kind not in dict(TYPES) or kind=='unknown':raise ValueError('请先选择数据类型。')
    if kind in ('mean_sd','quantile'):
        required=('mean','sd') if kind=='mean_sd' else ('q1','median','q3','lower','upper')
        if any(not finite(f.get(k)) for k in required):raise ValueError('请补全有效的数值参数。')
        if type(f.get('digits')) is not int or not 0<=f['digits']<=4:raise ValueError('小数位须为 0～4 的整数。')
        for k in ('lower','upper'):
            if f.get(k) is not None and not finite(f[k]):raise ValueError('上下限须为有效数字。')
        if f.get('lower') is not None and f.get('upper') is not None and f['lower']>f['upper']:raise ValueError('下限不能大于上限。')
        if kind=='mean_sd':
            if f['sd']<0:raise ValueError('标准差不能为负数。')
            if f.get('parity','any')!='any' and f['digits']!=0:raise ValueError('奇数／偶数规则须使用 0 位小数。')
        elif not f['lower']<=f['q1']<=f['median']<=f['q3']<=f['upper']:raise ValueError('上下限和四分位数必须按顺序递增。')
    elif kind in ('binary','gender','yesno','binary01','category'):
        labels,weights=f.get('labels',[]),f.get('weights',[])
        if len(labels)<2 or len(set(map(str,labels)))!=len(labels) or any(not str(x).strip() for x in labels):raise ValueError('请补全至少两个不同的类别。')
        if len(weights)!=len(labels) or any(not finite(x) or x<0 for x in weights) or abs(sum(weights)-100)>1e-6:raise ValueError('类别比例需为非负数，补全并合计 100%。')
        if kind=='binary01' and any(type(x) is not int for x in labels):raise ValueError('分类编码须为整数。')
    elif kind=='derived':
        if not f.get('from_field','').strip() or not f.get('positive_labels'):raise ValueError('请填写来源字段和计为有效的类别。')
        f['labels']=['有效','无效']
    f['confirmed']=True
    return f
