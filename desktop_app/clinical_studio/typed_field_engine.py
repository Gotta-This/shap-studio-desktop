"""Validation and synthesis for explicit mean/SD, quartile and categorical fields."""
import math


def validate_fields(config):
    groups={g['name']:g for g in config['groups']};seen={};existing={s['name'].strip() for s in config.get('indicators',[])+config.get('categoricals',[])}
    if len(config.get('typed_fields',[]))>250*len(groups):raise ValueError('最多支持250个表格字段。')
    for f in config.get('typed_fields',[]):
        name=f['name'].strip();group=f['group'];kind=f['kind']
        if not name or name in ('编号','分组') or name.startswith('=') or name in existing:raise ValueError('表格字段名为空、重复或与已有指标冲突，请修改列名。')
        if group not in groups or group in seen.setdefault(name,set()):raise ValueError(name+'的组别无效或重复。')
        seen[name].add(group)
        if kind=='excluded':continue
        if f.get('aggregate_pending'):raise ValueError(name+'：汇总项须确认联合生成规则，不能独立生成；可先选“仅保留来源，不生成”。')
        if not f.get('confirmed',True):raise ValueError(name+'：请在“编辑参数”确认数据类型及类别含义后生成。')
        if kind not in ('mean_sd','quantile','binary','gender','yesno','binary01','category','derived'):raise ValueError(name+'：请选择数据类型并补全参数。')
        def finite(key):
            v=f.get(key)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError(name+'：请补全有效的'+key+'参数。')
            return v
        if kind in ('mean_sd','quantile'):
            digits=f.get('digits',2)
            if not isinstance(digits,int) or digits not in range(5):raise ValueError(name+'小数位须为0～4。')
            for key in ('lower','upper'):
                if f.get(key) is not None:finite(key)
            if f.get('lower') is not None and f.get('upper') is not None and f['lower']>f['upper']:raise ValueError(name+'下限大于上限。')
            if kind=='mean_sd':
                if f.get('parity','any') not in ('any','odd','even') or f.get('parity','any')!='any' and digits!=0:raise ValueError(name+'奇数或偶数须使用0位小数。')
                finite('mean')
                if finite('sd')<0:raise ValueError(name+'标准差不能为负。')
            else:
                q1,median,q3=finite('q1'),finite('median'),finite('q3')
                if not q1<=median<=q3:raise ValueError(name+'须满足Q1≤中位数≤Q3。')
                if f.get('lower') is None or f.get('upper') is None or not f['lower']<=q1<=q3<=f['upper']:raise ValueError(name+'须设置包含四分位数的模拟尾部上下限。')
                if groups[group]['n']<7:raise ValueError(name+'四分位数模拟至少需要7例。')
        elif kind=='derived':
            parent=next((s for s in config.get('typed_fields',[]) if s['name']==f.get('from_field') and s['group']==group),None)
            if not parent or parent['kind'] not in ('category','binary','gender','yesno','binary01') or not set(f.get('positive_labels',[])).issubset(parent['labels']):raise ValueError(name+'的来源字段或有效类别已更改，请编辑派生规则。')
        else:
            labels=f.get('labels',[]);weights=f.get('weights',[])
            if len(labels)<2 or len(labels)!=len(weights) or len(set(labels))!=len(labels) or any(not str(v).strip() for v in labels):raise ValueError(name+'须配置至少两个不同类别及各自比例。')
            if kind in ('gender','yesno','binary','binary01') and len(labels)!=2:raise ValueError(name+'二分类须配置两个类别。')
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in weights) or abs(sum(weights)-100)>1e-6:raise ValueError(name+'的类别比例须为非负数且合计100%。')
    if any(names!=set(groups) for names in seen.values()):raise ValueError('每个表格字段须配置全部所选组别；缺失行请补全。')


def quantile(values,p):
    ordered=sorted(values);position=(len(values)-1)*p;lo=math.floor(position);hi=math.ceil(position)
    return ordered[lo]*(hi-position)+ordered[hi]*(position-lo) if lo!=hi else ordered[lo]


def quartile_values(field,n,rng):
    anchors={0:field['lower'],n-1:field['upper']}
    for p,key in ((.25,'q1'),(.5,'median'),(.75,'q3')):
        position=(n-1)*p;anchors[math.floor(position)]=field[key];anchors[math.ceil(position)]=field[key]
    points=sorted(anchors.items());values=[0.]*n
    for (start,low),(end,high) in zip(points,points[1:]):
        for i in range(start,end+1):values[i]=round(low+(high-low)*(i-start)/(end-start),field['digits'])
    rng.shuffle(values);return values


def apply_fields(config,group,n,data,checks,rng,cancelled,numeric,categorical,statistics):
    fields=[s for s in config.get('typed_fields',[]) if s['group']==group and s['kind']!='excluded']
    overrides={s['name'].strip() for s in fields}
    checks[:]=[c for c in checks if c['group']!=group or c['field'] not in overrides]
    for field in sorted(fields,key=lambda f:f['kind']=='derived'):
        if cancelled():raise InterruptedError('已取消生成。')
        name=field['name'].strip();kind=field['kind']
        if kind=='mean_sd':
            values=numeric(dict(field,parity=field.get('parity','any')),n,rng,cancelled);mean,sd=statistics(values)
            checks.append(dict(group=group,field=name,n=n,target_mean=field['mean'],actual_mean=mean,mean_error=mean-field['mean'],target_sd=field['sd'],actual_sd=sd,sd_error=sd-field['sd'],minimum=min(values),maximum=max(values)))
        elif kind=='quantile':
            values=quartile_values(field,n,rng)
            checks.append(dict(group=group,field=name,n=n,target_q1=field['q1'],actual_q1=quantile(values,.25),target_median=field['median'],actual_median=quantile(values,.5),target_q3=field['q3'],actual_q3=quantile(values,.75),minimum=min(values),maximum=max(values)))
        elif kind=='derived':
            values=[field['labels'][0] if value in field['positive_labels'] else field['labels'][1] for value in data[field['from_field']]]
            for label in field['labels']:checks.append(dict(group=group,field=name,category=label,actual_count=values.count(label),actual_percent=values.count(label)/n*100))
        else:values=categorical(name,field['labels'],field['weights'])
        data[name]=values
    return overrides
