"""Single-dataset vertical summaries; no source group labels are invented."""
import re
from copy import deepcopy
from .word_table_types import clean,summary,MEAN,QUARTILES,COUNT,header_n

DATASET='未分组数据'
VALUE_HEADERS={'数值','数据','结果','统计描述','描述统计','统计值','统计量','描述','总体','总计','全部','全体','合计','总样本','样本','总人群','整体','n(%)','n/%','例(%)','例数(%)','均数±标准差','均值±标准差','均数±s','mean±sd','均数±sd','均值±sd','人数(%)','人数','例数','n','value'}
NAME_HEADERS={'项目','指标','变量','特征','基本资料','一般资料','名称','parameter','variable'}
NAMES_N={'例数','样本量','总例数','总人数','人数','n','样本数'}
STAT_HEADERS={'p','p值','t','z','χ2','χ²','统计值','检验值'}


def value_header(value):
    text=re.sub(r'\(?[nN]=\d+\)?','',clean(value)).lower().strip(':：')
    return text in VALUE_HEADERS or (not text and header_n(value) is not None)


def parse_ungrouped(rows,table,n_override=None):
    result=dict(handled=False,fields=[],n=None,issues=[])
    if not rows:return result
    width=max(map(len,rows),default=0)
    if width<2:return result
    first=[clean(v).lower() for v in rows[0]]
    if first[0] in ('组别','分组','group'):return result
    category_col=None;start=0
    if first[0] in NAME_HEADERS or any(value_header(value) for value in rows[0][1:]):
        columns=[i for i,value in enumerate(rows[0]) if i and value_header(value)]
        measurements=[i for i in columns if first[i] not in NAMES_N]
        columns=measurements or columns
        if len(columns)!=1:return result
        value_col=columns[0];start=1
        if value_col==2 and first[1] in ('类别','分类','水平','category'):category_col=1
        elif any(i not in (0,value_col) and label not in STAT_HEADERS|NAMES_N for i,label in enumerate(first)):return result
    elif width==2 and any(MEAN.search(clean(row[1])) or QUARTILES.search(clean(row[1])) or COUNT.search(clean(row[1])) for row in rows if len(row)>1):
        value_col=1
    else:return result
    n_values={header_n(value) for value in rows[0] if header_n(value)} if start else set()
    n_columns=[i for i,label in enumerate(first) if i!=value_col and label in NAMES_N] if start else []
    for row in rows[start:]:
        for col in n_columns:
            if col<len(row) and clean(row[col]).isdigit():n_values.add(int(clean(row[col])))
        if row and clean(row[0]).lower() in NAMES_N and len(row)>value_col and clean(row[value_col]).isdigit():n_values.add(int(clean(row[value_col])))
    if len(n_values)==1:result['n']=next(iter(n_values))
    elif len(n_values)>1:result['issues'].append(f'表{table}例数有多个不同值，请核对。')
    n=result['n'] if result['n'] is not None else n_override
    records=[];blocks={};parent=''
    for index,row in enumerate(rows[start:],start):
        name=row[0].strip() if row else '';raw=row[value_col].strip() if len(row)>value_col else ''
        if clean(name).lower() in NAMES_N|STAT_HEADERS|{'编号','序号'} or name.startswith(('注:','注：')):continue
        if category_col is not None:
            if name:parent=name
            label=row[category_col].strip() if len(row)>category_col else ''
            if parent and label:blocks.setdefault(parent,[]).append((label,raw,index))
        elif name and not raw:parent=name
        elif parent and name and (COUNT.match(clean(raw)) or clean(raw).isdigit()) and not MEAN.search(clean(raw)):
            blocks.setdefault(parent,[]).append((name,raw,index))
        elif name:
            parent='';records.append(summary(name,DATASET,raw,n,table,row=index+1,column=value_col+1))
    for name,items in blocks.items():
        # Complications/comorbidities can overlap within the same person. Their
        # counts must not be summed into a sample size or a one-choice category.
        if any(hint in clean(name) for hint in ('并发症','合并症','合并疾病','基础疾病','既往史','病史')):
            for label,raw,index in items:
                field=summary(label,DATASET,raw,n,table,header_path=[name,label],row=index+1,column=value_col+1)
                match=COUNT.match(clean(raw));count=int(match[1]) if match else int(clean(raw)) if clean(raw).isdigit() else None
                if count is not None:
                    percent=float(match[2]) if match else None;weight=count/n*100 if n else percent
                    field.update(kind='yesno',labels=['有','无'],count=count,reported_percent=percent,weights=[weight,100-weight] if weight is not None else [None,None],confirmed=bool(n and 0<=count<=n))
                records.append(field)
            continue
        counts=[]
        for label,raw,index in items:
            match=COUNT.match(clean(raw));counts.append(int(match[1]) if match else int(clean(raw)) if clean(raw).isdigit() else None)
        total=sum(counts) if all(value is not None for value in counts) else None
        denominator=n or total
        valid=bool(len(items)>=2 and denominator and total==denominator and len({item[0] for item in items})==len(items))
        field=summary(name,DATASET,'；'.join(label+' '+raw for label,raw,_ in items),denominator,table,row=items[0][2]+1,column=value_col+1)
        field.update(kind='category',labels=[label for label,_,_ in items],counts=counts,source_n=denominator,weights=[c/denominator*100 if c is not None and denominator else None for c in counts],confirmed=valid)
        if not valid:field['review_note']='分类人数不完整或合计与例数不一致，请人工核对。'
        records.append(field)
    inferred={f.get('source_n') for f in records if f.get('counts') and f.get('source_n')}
    if not n_values and len(inferred)==1:result['n']=next(iter(inferred))
    elif len(inferred)>1:result['issues'].append(f'表{table}各分类项目的人数合计不同，请核对例数。')
    if not records:return result
    for field in records:
        field['source_n_origin']='Word人数' if result['n'] is not None else '手工补充的例数' if n_override is not None else '未报告'
        if result['n'] is None and n_override and field.get('count') is not None and field.get('reported_percent') is not None and abs(field['count']/n_override*100-field['reported_percent'])>.05:
            field['confirmed']=False;field['review_note']='补充的例数与原文人数、百分比不一致，请核对源表例数或手动确认比例。'
    result.update(handled=True,fields=records)
    return result


def scan_ungrouped(inventory,n_override=None):
    fields=[];sizes=[];issues=[]
    for table in inventory:
        if table['groups']:continue
        parsed=parse_ungrouped(table['rows'],table['table'])
        source_n=parsed['n'] or n_override
        if source_n and any(field.get('source_n') is None for field in parsed['fields']):
            parsed=parse_ungrouped(table['rows'],table['table'],source_n)
        if not parsed['handled']:continue
        table['orientation']='竖表：无分组'
        if parsed['n'] is not None:sizes.append(parsed['n'])
        issues+=parsed['issues']
        for field in parsed['fields']:
            field['source_kind']='ungrouped_table';field['table_title']=table['title'];fields.append(field)
    size=next(iter(set(sizes))) if len(set(sizes))==1 and not issues else None
    if len(set(sizes))>1:issues.append('无分组竖表之间的例数不同，不能默认视为同一批病例，请核对后填写生成例数。')
    return fields,size,issues
