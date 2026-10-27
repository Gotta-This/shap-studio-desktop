"""Describe every generated column using the same configuration as the generator."""
from .word_batch_engine import BASE_COLUMNS,END_COLUMNS,PAIR,default_batch_config,output_columns


def number(value):return '待补全' if value is None else f'{value:g}' if isinstance(value,(int,float)) else str(value)


def basic_rules(group,unit='月'):
    def ranges(values):return '；'.join(f"{number(r['lower'])}～{number(r['upper'])}（{number(r['percent'])}%）" for r in values)
    age=ranges(group['age'])+' 岁'
    if group.get('age_stats'):age+='；均数±SD '+number(group['age_stats']['mean'])+'±'+number(group['age_stats']['sd'])
    mode=group.get('extent_mode','category')
    extent='保留空列，不生成' if mode=='blank' else ranges(group['extent_ranges']) if mode=='range' else '；'.join(f"{r['label']} {number(r['percent'])}%" for r in group['extent'])
    return {
      '性别':(group['male'],f"男 {number(group['male'])}%，女 {number(100-group['male'])}%"),
      '年龄':((group['age'],{k:group['age_stats'][k] for k in ('mean','sd')} if group.get('age_stats') else None),age),
      '病程':((group['course'],group['course_digits'],unit),ranges(group['course'])+' '+unit),
      '病情程度':(group['severity'],'；'.join(label+' '+number(value)+'%' for label,value in zip(('轻度','中度','重度'),group['severity']))),
      '病变范围':((mode,group.get('extent_ranges') if mode=='range' else group.get('extent') if mode=='category' else None,group.get('extent_digits',0)),extent),
      '总有效率':(group['effective'],f"有效 {number(group['effective'])}%，无效 {number(100-group['effective'])}%"),
      '复发率':((group['recurrence'],group.get('recurrence_scope','all')),f"复发 {number(group['recurrence'])}%，未复发 {number(100-group['recurrence'])}%；分母："+('有效者' if group.get('recurrence_scope')=='effective' else '全组')),
    }


def field_rule_rows(config):
    rows=[];start=1;unit=config.get('course_unit','月')
    names=list(dict.fromkeys(s['name'].strip() for s in config.get('indicators',[])))
    category_names=list(dict.fromkeys(s['name'].strip() for s in config.get('categoricals',[])))
    columns=output_columns(config)
    for group in config['groups']:
        name=group['name'];actual=basic_rules(group,unit)
        defaults=basic_rules(default_batch_config([name])['groups'][0])
        imported=config.get('imported_basics',{}).get(name)
        original=basic_rules(imported,unit) if imported else {}
        detected=config.get('detected_basics',{}).get(name,[])
        for column in columns:
            source='';raw='';rule=''
            if column=='编号':source='程序编号';rule=f"{start}～{start+group['n']-1}，连续自增"
            elif column=='分组':source='当前分组配置';rule=f"{name}，{group['n']}例"
            elif any(f['name'].strip()==column and f['group']==name for f in config.get('typed_fields',[])):
                f=next(f for f in config['typed_fields'] if f['name'].strip()==column and f['group']==name);kind=f['kind'];raw=f.get('raw','');kind_label={'mean_sd':'均数/标准差','quantile':'中位数/四分位数','binary':'二分类','gender':'男/女','yesno':'有/无','binary01':'1/0编码','category':'分类','derived':'分类派生'}.get(kind,'待选择类型');source=('Word正文' if f.get('source_kind')=='prose' else f"Word表{f['table']}" if f.get('table') else '手工配置')+' / '+kind_label
                if not f.get('confirmed',True):source+='（待确认）'
                if f.get('classification'):source+=' / '+f['classification']
                if f.get('header_path'):raw='原表头：'+' → '.join(f['header_path'])+'；原值：'+raw
                if kind=='mean_sd':rule=f"{number(f.get('mean'))}±{number(f.get('sd'))}；小数位{f.get('digits',2)}"
                elif kind=='quantile':rule=f"中位数{number(f.get('median'))}，Q1 {number(f.get('q1'))}，Q3 {number(f.get('q3'))}；模拟尾部{number(f.get('lower'))}～{number(f.get('upper'))}"
                elif kind=='derived':rule='由'+f.get('from_field','')+'派生：'+ '、'.join(f.get('positive_labels',[]))+'计为有效'
                elif f.get('aggregate_pending'):rule=f.get('review_note','汇总项待确认联合规则，不能独立生成')
                else:rule='；'.join(str(label)+' '+number(weight)+'%' for label,weight in zip(f.get('labels',[]),f.get('weights',[])))
            elif column in actual:
                value,rule=actual[column]
                if column in detected and column in original:
                    source=('Word正文' if column in ('性别','年龄') else 'Word表格') if value==original[column][0] else '手工修改（原Word）'
                    raw=config.get('prose_sources',{}).get(name,{}).get('raw','') if column in ('性别','年龄') else original[column][1]
                else:
                    source='程序默认参数' if value==defaults[column][0] else '手工配置'
                    raw='基础资料规则，不是Word数值指标；可在第1步修改。'
                if column in group.get('blank_fields',[]):source='已选择留空';rule='保留空列，不生成'
            elif column in category_names:
                spec=next((s for s in config['categoricals'] if s['name'].strip()==column and s['group']==name),None)
                if spec:
                    source='正文分类资料' if spec.get('raw','').startswith('正文') else '手工分类配置'
                    rule='；'.join(label+' '+number(weight)+'%' for label,weight in zip(spec['labels'],spec['weights']));raw=spec.get('raw','')
                else:source='待补全';rule='本组缺少分类配置'
            else:
                spec=next((s for s in config['indicators'] if s['name'].strip()==column and s['group']==name),None)
                if spec:
                    raw=spec.get('raw','');source='Word正文' if raw.startswith('正文') else f"Word表{spec['table']}" if spec.get('table') else '手工配置'
                    pair=PAIR.search(raw)
                    if pair and (spec['mean'],spec['sd'])!=(float(pair[1]),float(pair[2])):source+='（已修改）'
                    lower='不限' if spec.get('lower') is None else number(spec['lower']);upper='不限' if spec.get('upper') is None else number(spec['upper'])
                    rule=f"{number(spec['mean'])}±{number(spec['sd'])}；小数位 {spec['digits']}；下限 {lower}，上限 {upper}"
                else:source='待补全';rule='本组缺少数值配置'
            rows.append(dict(column=column,group=name,source=source,rule=rule,original=raw))
        start+=group['n']
    for f in config.get('typed_fields',[]):
        if f['kind']=='excluded':
            rows.append(dict(column=f['name']+'（不生成）',group=f['group'],source=f"Word表{f.get('table',0)} / 仅保留来源",rule='已选择不生成病例列；'+f.get('review_note',''),original='原表头：'+' → '.join(f.get('header_path',[]))+'；原值：'+f.get('raw','')))
    return rows
