"""Explicitly typed summaries from row-oriented and column-oriented DOCX tables."""
import re,unicodedata
from collections import Counter

NUM=r'[+−-]?(?:\d+(?:\.\d*)?|\.\d+)'
MEAN=re.compile('('+NUM+r')±('+NUM+')')
QUARTILES=re.compile('('+NUM+r')\(('+NUM+r')[,，]('+NUM+r')\)')
COUNT=re.compile(r'(\d+)\(('+NUM+r')%?\)')


def clean(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value)).replace('−','-')
def group_label(value):
    return re.sub(r'\((?:[nN]=\d+|\d+例)\)|[nN]=\d+','',clean(value))
def header_group(value,groups):
    base=group_label(value)
    return next((g for g in groups if clean(g)==base),None)
def header_n(value):
    m=re.search(r'[nN]=(\d+)|\((\d+)例\)',clean(value));return int(m[1] or m[2]) if m else None

def slash_categories(name,raw):
    """Use explicit category order; trailing reporting notation is not a label."""
    match=re.search(r'\(([^()]*/[^()]*)\)',clean(name))
    if not match:return None
    content=match[1]
    segments=re.split(r'[,;]',content)
    notation={'例','例数','人数','n','%','构成比','比例','百分比','例(%)','n(%)'}
    if len(segments)>1 and all(part.lower() in notation for part in segments[1:]):content=segments[0]
    labels=content.split('/')
    parts=clean(raw).split('/')
    counts=[re.fullmatch(r'(\d+)(?:\(('+NUM+r')%?\))?',part) for part in parts]
    if len(labels)<2 or any(not label for label in labels) or len(labels)!=len(parts) or not all(counts):return None
    return labels,[int(match[1]) for match in counts]


def row_has_data(row):
    return any(MEAN.search(clean(value)) or QUARTILES.search(clean(value)) or COUNT.search(clean(value)) or re.fullmatch(r'\d+',clean(value)) or slash_categories(row[0],value) is not None for value in row[1:]) if row else False


def summary(name,group,raw,n,table,*,header_path=None,row=None,column=None,table_title=''):
    text=clean(raw);path=header_path or [name]
    classification=' / '.join(path[:-1])
    record=dict(name=name,group=group,table=table,raw=raw,source_n=n,digits=2,lower=None,upper=None,confirmed=True,
                header_path=path,classification=classification,table_title=table_title,source_cell=dict(row=row,column=column))
    if '总发生率' in clean(name):
        count_match=COUNT.search(text);percent_match=re.fullmatch('('+NUM+r')%',text)
        count=int(count_match[1]) if count_match else None
        percent=float(count_match[2]) if count_match else float(percent_match[1]) if percent_match else None
        weight=count/n*100 if count is not None and n else percent
        return dict(record,kind='unknown',count=count,reported_percent=percent,weights=[weight,100-weight] if weight is not None else [None,None],labels=['有','无'],confirmed=False,
                    aggregate_pending=True,review_note='总发生率为汇总项，需确认统计口径及与各并发症的联合规则；不能独立随机生成。可先选择“仅保留来源，不生成”。')
    m=MEAN.search(text)
    if m:return dict(record,kind='mean_sd',mean=float(m[1]),sd=float(m[2]))
    if re.fullmatch(r'[+-]?\d+\.\d+\.\d+',text):
        return dict(record,kind='mean_sd',mean=None,sd=None,confirmed=False,review_note='原文数值缺少分隔符（如22.444.02），无法确定均数和标准差。请核对并填写；程序不自动拆分。')
    m=QUARTILES.search(text)
    if m:return dict(record,kind='quantile',median=float(m[1]),q1=float(m[2]),q3=float(m[3]),confirmed=False)
    # Explicit categories in the row label define the order of slash-separated
    # counts. A slash in a unit (kg/m²) must never be treated as categories.
    categories=slash_categories(name,raw)
    if categories:
        labels,counts=categories;denominator=n or sum(counts)
        valid=bool(denominator and sum(counts)==denominator)
        field_name=re.sub(r'[（(][^()（）]*/[^()（）]*[）)]','',name).strip()
        return dict(record,name=field_name,kind='gender' if labels==['男','女'] else 'category',labels=labels,counts=counts,
                    source_n=denominator,weights=[count/denominator*100 if denominator else None for count in counts],confirmed=valid,
                    review_note='' if valid else '分类人数合计与例数不一致，请核对。')
    m=COUNT.search(text)
    bare=re.fullmatch(r'\d+',text)
    complication_hint='并发症' in classification or '并发症' in clean(table_title)
    binary_hint='并发症' in classification or clean(name).startswith('合并') or (complication_hint and m is not None)
    if m or (bare and binary_hint):
        count=int(m[1]) if m else int(text);percent=float(m[2]) if m else None
        weight=count/n*100 if n else percent
        weights=[weight,100-weight] if weight is not None else [None,None]
        valid=bool(n and 0<=count<=n)
        if percent is not None:
            decimals=len(m[2].partition('.')[2])
            valid=valid and 0<=percent<=100 and abs(count/n*100-percent)<=0.5*10**(-decimals)+1e-9
        neutral=bool(m and valid and not binary_hint)
        note='人数、百分比与例数不一致或例数缺失，请核对。' if not valid else '默认编码：1表示原文报告的人数，0表示其余人数。可在编辑参数中修改类别名称。' if neutral else ''
        return dict(record,review_note=note,kind='yesno' if binary_hint else 'binary01' if neutral else 'binary',labels=['有','无'] if binary_hint else [1,0] if neutral else ['待确认类别1','待确认类别2'],
                    weights=weights,count=count,reported_percent=percent,confirmed=bool(valid and (binary_hint or neutral)))
    return dict(record,kind='unknown',confirmed=False,review_note='未识别数据类型或类别，请根据原文手动配置。')


def leaf_headers(headers,col):
    labels=[]
    for row in headers:
        value=row[col].strip() if col<len(row) else ''
        if value and (not labels or clean(value)!=clean(labels[-1])):labels.append(value)
    return labels


PHASES={'治疗前','治疗后','干预前','干预后','护理前','护理后','前','后'}

def parse_row_phases(rows,origins,groups,table,result,table_title):
    """A group/N may span several rows; an explicit phase owns each data row."""
    data=[];current=None
    group_columns={col for row in rows[:1] for col,value in enumerate(row) if clean(value) in ('组别','分组','组')}
    for index,row in enumerate(rows):
        group=next((header_group(value,groups) for value in row if header_group(value,groups)),None)
        if group:current=group
        elif any(col<len(row) and clean(row[col]) and clean(row[col]) not in ('组别','分组','组') for col in group_columns):current=None
        phase=next(((col,clean(value)) for col,value in enumerate(row) if clean(value) in PHASES),None)
        if phase and current and any(MEAN.search(clean(v)) or QUARTILES.search(clean(v)) for v in row):
            data.append((index,row,current,phase[0],phase[1]))
    if not data:return False
    headers=rows[:data[0][0]]
    if not headers:return False
    result['handled']=True
    seen={};phases=list(dict.fromkeys(item[4] for item in data));phase_cols={item[3] for item in data}
    for index,row,group,_,phase in data:
        if (group,phase) in seen:
            result['issues'].append(f'表{table} {group} {phase}有多行，无法确定对应关系，请核对。');return True
        seen[group,phase]=(index,row);result['matches'][group]=result['matches'].get(group,0)+1
        for col,value in enumerate(row):
            path=leaf_headers(headers,col);label=clean(path[-1]).lower() if path else ''
            if (label in ('n','样本量') or '例数' in label) and clean(value).isdigit():
                n=int(clean(value))
                if group in result['sizes'] and n!=result['sizes'][group]:result['issues'].append(f'表{table} {group}各时间点例数不一致，请核对。')
                else:result['sizes'][group]=n
    width=max(map(len,rows))
    for col in range(width):
        if col in phase_cols:continue
        path=leaf_headers(headers,col)
        if not path:continue
        name=path[-1];label=clean(name).lower()
        if label in ('组别','分组','组','n','样本量','t','p','p值','统计值') or '例数' in label:continue
        if not any(col<len(row) and (MEAN.search(clean(row[col])) or QUARTILES.search(clean(row[col]))) for _,row,_,_,_ in data):continue
        if col and all(col<len(origins[i]) and origins[i][col]==origins[i][col-1] for i,_,_,_,_ in data):continue
        for phase in phases:
            for group in groups:
                index,row=seen.get((group,phase),(None,[]))
                field=summary(name,group,row[col] if col<len(row) else '',result['sizes'].get(group),table,header_path=[phase,*path],row=index+1 if index is not None else None,column=col+1,table_title=table_title)
                field['name']=phase+'-'+name;field['timepoint']=phase
                result['fields'].append(field)
    return True


def parse_horizontal(rows,origins,groups,table,result,table_title=''):
    if parse_row_phases(rows,origins,groups,table,result,table_title):return result
    data=[(index,row,next((header_group(value,groups) for value in row if header_group(value,groups)),None)) for index,row in enumerate(rows)]
    data=[item for item in data if item[2]]
    if not data:return result
    # Unselected groups can precede the first selected group. Those are data
    # rows, never additional header levels (important for one-group imports).
    first_data=next((i for i,row in enumerate(rows) if i and row_has_data(row)),data[0][0])
    headers=rows[:min(first_data,data[0][0])]
    if not headers:return result
    # Keep the established flat numeric/outcome parser for its existing layouts.
    # The new route handles hierarchical headers and mixed categorical summaries.
    width=max(map(len,rows),default=0)
    categorical_table=any(
        (QUARTILES.search(clean(row[col])) or COUNT.fullmatch(clean(row[col])) or slash_categories((leaf_headers(headers,col) or [''])[-1],row[col]) is not None)
        and (leaf_headers(headers,col) or [''])[-1] not in ('总有效率','复发率')
        for _,row,_ in data for col in range(1,len(row)))
    legacy_phases=any(clean(value) in ('治疗前','治疗后','干预前','干预后','前','后') for row in headers for value in row)
    malformed=any(re.fullmatch(r'[+-]?\d+\.\d+\.\d+',clean(value)) for _,row,_ in data for value in row)
    complex_table=categorical_table or malformed or (len(headers)>1 and not legacy_phases)
    if not complex_table:return result
    if any(sum(item[2]==group for item in data)>1 for group in groups):
        result['issues'].append(f'表{table}同组存在多行，不能确定对应关系，请核对原表。')
        return result
    for _,row,group in data:
        result['matches'][group]=1
        for col,value in enumerate(row):
            path=leaf_headers(headers,col);label=clean(path[-1]) if path else ''
            if ('例数' in label or label.lower() in ('n','样本量')) and clean(value).isdigit():result['sizes'][group]=int(clean(value))
            n=header_n(value)
            if header_group(value,groups) and n:result['sizes'][group]=n
    result['handled']=True;used=set()
    paths={col:leaf_headers(headers,col) for col in range(width)}
    leaves=Counter(path[-1] for path in paths.values() if path)
    for col in range(width):
        path=leaf_headers(headers,col)
        if not path:continue
        name=path[-1];label=clean(name).lower()
        if label in ('组别','分组','组','n','样本量','t','p','p值','统计值','χ2','χ²','z') or '例数' in label:continue
        if any(header_group(path_part,groups) for path_part in path):continue
        if any(col<len(row) and header_group(row[col],groups) for _,row,_ in data):continue
        if label in ('总有效率','复发率'):
            # Preserve existing outcome controls even when an otherwise flat
            # table also contains a new categorical column.
            for _,row,group in data:
                raw=clean(row[col]) if col<len(row) else '';match=COUNT.search(raw);n=result['sizes'].get(group)
                percent=re.fullmatch('('+NUM+r')%',raw)
                value=int(match[1])/n*100 if match and n else float(percent[1]) if percent else None
                if value is not None:result['rates'].setdefault(group,{})[name]=value
            continue
        # Skip duplicate logical columns made by one physical merged cell.
        relevant=list(range(len(headers)))+[index for index,_,_ in data]
        if col and all(i<len(origins) and col<len(origins[i]) and origins[i][col] is not None and origins[i][col]==origins[i][col-1] for i in relevant):continue
        output_name=' / '.join(path) if leaves[name]>1 and len(path)>1 else name
        if output_name in used:output_name+=f'（列{col+1}）'
        used.add(output_name)
        for group in groups:
            found=next(((index,row) for index,row,g in data if g==group),None)
            index,row=found if found else (None,[])
            field=summary(name,group,row[col] if col<len(row) else '',result['sizes'].get(group),table,header_path=path,row=index+1 if index is not None else None,column=col+1,table_title=table_title)
            if output_name!=name:field['name']=output_name
            result['fields'].append(field)
            if field.get('aggregate_pending'):result['issues'].append(f"表{table} {group} {name}："+field['review_note'])
    for field in result['fields']:
        if field.get('review_note') and not field.get('aggregate_pending'):
            result['issues'].append(f"表{table} {field['group']} {field['name']}："+field['review_note'])
    return result


def parse_table(rows,origins,groups,table,table_title=''):
    result=dict(handled=False,fields=[],sizes={},matches={},issues=[],baseline=False,rates={})
    # Group names in column headings, optionally merged and carrying n=.
    first_data=next((i for i,row in enumerate(rows) if i and row_has_data(row)),len(rows))
    headers=rows[:first_data];columns={}
    for row in headers:
        for col,value in enumerate(row):
            group=header_group(value,groups)
            if group:
                columns[col]=group;result['matches'][group]=1
                n=header_n(value)
                if n:result['sizes'][group]=n
    if columns and first_data<len(rows):
        result['handled']=True;phases={}
        for col in columns:
            labels=[clean(row[col]) for row in headers if col<len(row)]
            phases[col]=next(('前' if '前' in v else '后' for v in reversed(labels) if v in ('治疗前','治疗后','干预前','干预后','前','后')),'')
        result['baseline']=not any(phases.values())
        category_rows=set()
        for index,row in enumerate(rows[first_data:],first_data):
            if not row or not row[0].strip() or any(col<len(row) and row[col].strip() for col in columns):continue
            children=[]
            for child_index in range(index+1,len(rows)):
                child=rows[child_index]
                if not child or not child[0].strip():break
                if not all(col<len(child) and (COUNT.fullmatch(clean(child[col])) or clean(child[col]).isdigit()) for col in columns):break
                children.append((child_index,child))
            if len(children)<2:continue
            labels=[child[0].strip() for _,child in children]
            # Disease/complication subrows can overlap; never turn them into
            # mutually exclusive categories just because the counts add up.
            if labels!=['有','无'] and any(hint in clean(row[0]) for hint in ('并发症','合并症','合并疾病','基础疾病','既往史','病史')):continue
            category_rows.update([index]+[i for i,_ in children])
            for col,group in columns.items():
                counts=[int(COUNT.fullmatch(clean(child[col]))[1]) if COUNT.fullmatch(clean(child[col])) else int(clean(child[col])) for _,child in children]
                n=result['sizes'].get(group)
                raw='；'.join(label+' '+child[col] for label,(_,child) in zip(labels,children))
                parsed=summary(row[0].strip(),group,raw,n,table,row=index+1,column=col+1,table_title=table_title)
                valid=bool(n and sum(counts)==n and len(set(labels))==len(labels))
                parsed.update(kind='gender' if labels==['男','女'] else 'yesno' if labels==['有','无'] else 'category',labels=labels,counts=counts,weights=[c/n*100 if n else None for c in counts],confirmed=valid)
                parsed['source_rows']=[i+1 for i,_ in children]
                parsed['review_note']='' if valid else '分类人数合计与例数不一致或例数缺失，请核对。'
                result['fields'].append(parsed)
                if parsed['review_note']:result['issues'].append(f'表{table} {group} {row[0]}：'+parsed['review_note'])
        for index,row in enumerate(rows[first_data:],first_data):
            if index in category_rows:continue
            if not row:continue
            name=row[0].strip()
            if not name or clean(name).lower() in ('t','p','p值','z','χ2','χ²','统计值','项目'):continue
            if name.startswith(('注：','注:')):continue
            if index<len(origins) and origins[index] and all(col<len(origins[index]) and origins[index][col]==origins[index][0] for col in columns):continue
            for col,group in columns.items():
                if col and index<len(origins) and col<len(origins[index]) and origins[index][col]==origins[index][col-1] and columns.get(col-1)==group and phases.get(col-1)==phases.get(col):continue
                raw=row[col] if col<len(row) else ''
                field=(phases[col]+'-' if phases[col] else '')+name
                parsed=summary(field,group,raw,result['sizes'].get(group),table,row=index+1,column=col+1,table_title=table_title)
                result['fields'].append(parsed)
                if parsed.get('source_n'):result['sizes'].setdefault(group,parsed['source_n'])
                if parsed.get('review_note'):result['issues'].append(f'表{table} {group} {field}：'+parsed['review_note'])
        result['fields'].sort(key=lambda f:(f['source_cell']['row'],f['source_cell']['column']))
        return result
    # Four mutually exclusive efficacy grades in columns, groups in rows.
    efficacy=('基本痊愈','显效','有效','无效')
    for hi,header in enumerate(rows):
        labels=[clean(v) for v in header]
        if not all(name in labels for name in efficacy):continue
        for row in rows[hi+1:]:
            group=next((header_group(v,groups) for v in row if header_group(v,groups)),None)
            if not group:continue
            n=None
            for col,label in enumerate(labels):
                if ('例数' in label or label.lower() in ('n','样本量')) and col<len(row) and row[col].strip().isdigit():n=int(row[col])
            counts=[]
            for label in efficacy:
                col=labels.index(label);m=COUNT.search(clean(row[col])) if col<len(row) else None
                counts.append(int(m[1]) if m else None)
            if n:result['sizes'][group]=n
            valid=n and all(c is not None for c in counts) and sum(counts)==n
            if not valid:result['issues'].append(f'表{table} {group}疗效分级人数不完整或合计不等于例数，请核对原表。')
            result['fields'].append(dict(table=table,name='疗效分级',group=group,kind='category',labels=list(efficacy),weights=[c/n*100 if valid else None for c in counts],counts=counts,source_n=n,raw='；'.join(row),confirmed=bool(valid)))
            total=COUNT.search(clean(row[labels.index('总有效率')])) if '总有效率' in labels and labels.index('总有效率')<len(row) else None
            consistent=bool(valid and (not total or (int(total[1])==sum(counts[:-1]) and abs(float(total[2])-sum(counts[:-1])/n*100)<=.02)))
            if not consistent:result['issues'].append(f'表{table} {group}总有效人数或比例与疗效分级合计不一致，请确认派生规则。')
            result['fields'].append(dict(table=table,name='总有效率',group=group,kind='derived',from_field='疗效分级',positive_labels=list(efficacy[:-1]),labels=['有效','无效'],raw='由基本痊愈、显效、有效三项合计；原表：'+(total[0] if total else '未报告'),confirmed=consistent))
        break
    return result if result['fields'] else parse_horizontal(rows,origins,groups,table,result,table_title=table_title)
