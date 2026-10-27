"""Noncommittal DOCX inventory: titles, orientations, candidate groups and drafts."""
from copy import deepcopy
import json,re
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from .word_batch_engine import W,_grid,read_word,table_titles
from .word_table_types import clean,MEAN,QUARTILES,COUNT,header_n,group_label
from .prose_table_engine import read_docx_text,parse_document,normalized,KNOWN_GROUPS
from .typed_field_ui import convert



def candidate(value,explicit=False):
    text=clean(value)
    text=group_label(text).strip(':：()（）')
    if text.lower() in ('组别','分组','group','n','例数','统计值','p','p值','t','z','χ2','χ²','合计','总计','总体','全部','全体','总样本','整体','样本','数值','结果','数据'):return None
    if not text or len(text)>100 or re.search(r'[±%<>＝=;；。]',text) or re.fullmatch(r'[\d.]+',text):return None
    if explicit or text in KNOWN_GROUPS:return text
    return None


def fields_for_groups(path,names,titles):
    imported=read_word(path,names) if names else None
    fields=[]
    for origin,items in (('indicators',imported.indicators if imported else []),('typed_fields',imported.typed_fields if imported else [])):
        for field in items:
            value=deepcopy(field);value.setdefault('kind','mean_sd');value.setdefault('confirmed',value.get('mean') is not None and value.get('sd') is not None)
            value=convert(value,value['kind']);value['table_title']=titles.get(value.get('table'),titles.get(str(value.get('table')),''))
            value['_preview_key']=json.dumps([value.get('table'),value['group'],value['name']],ensure_ascii=False);value['_preview_origin']=origin
            fields.append(value)
    return fields


def scan_word(path):
    # Use the same validity and size checks as a normal import.
    read_word(path,[],parse_indicators=False)
    with ZipFile(path) as archive:body=ET.fromstring(archive.read('word/document.xml')).find(W+'body')
    tables=list(body.iter(W+'tbl'));titles=table_titles(body,tables);inventory=[];names=[]
    for index,table in enumerate(tables,1):
        rows,origins=_grid(table,True);found=[];group_columns=set()
        for row in rows[:5]:
            for col,value in enumerate(row):
                if clean(value).lower() in ('组别','分组','group'):group_columns.add(col)
                if header_n(value):
                    name=candidate(value,True)
                    if name and name not in found:found.append(name)
        for row in rows:
            has_data=any(MEAN.search(clean(v)) or QUARTILES.search(clean(v)) or COUNT.search(clean(v)) or clean(v).isdigit() for v in row)
            for col,value in enumerate(row):
                name=candidate(value,explicit=has_data and col in group_columns)
                if name and name not in found:found.append(name)
        if group_columns:orientation='横表：组别在行'
        elif found:orientation='竖表：组别在列'
        else:orientation='方向待核对'
        for name in found:
            if name not in names:names.append(name)
        inventory.append(dict(table=index,title=titles.get(index,f'表{index}'),orientation=orientation,groups=found,rows=rows,columns=max(map(len,rows),default=0)))
    text=read_docx_text(path);text_normal=normalized(text)[0]
    for name in KNOWN_GROUPS:
        if name in text_normal and name not in names:names.append(name)
    notes=[]
    if len(names)>20:notes.append('候选组别超过20个，预览暂不合并字段；请填写本次组别后匹配。')
    chosen=names if len(names)<=20 else []
    fields=fields_for_groups(path,chosen,titles)
    from .ungrouped_tables import scan_ungrouped
    ungrouped_fields,ungrouped_n,ungrouped_issues=scan_ungrouped(inventory)
    for value in ungrouped_fields:
        value=convert(value,value['kind']);value['_preview_key']=json.dumps([value['table'],value['group'],value['name']],ensure_ascii=False);value['_preview_origin']='typed_fields';fields.append(value)
    notes+=ungrouped_issues
    prose_names=[name for name in chosen if name in text_normal]
    # The overview retains the whole prose, while parsing only paragraphs with
    # group summaries avoids treating every heading as an unresolved statistic.
    from .prose_table_integration import matching_document
    prose=matching_document(path,prose_names) if prose_names else None
    prose=prose or parse_document(text,prose_names or None)
    return dict(source=str(path),tables=inventory,candidates=names,fields=fields,prose_document=prose,prose_text=text,issues=notes,ungrouped_n=ungrouped_n,has_ungrouped=bool(ungrouped_fields))


def scan_report(scan):
    lines=['导入预览（尚未应用识别结果，不会生成数据）','候选组别：'+('、'.join(scan['candidates']) or ('无分组竖表，不需要填写组名' if scan.get('has_ungrouped') else '暂未识别，可手动填写')),'']
    for table in scan['tables']:
        count=len({f['_preview_key'] for f in scan['fields'] if f.get('table')==table['table']})
        lines.append(f"{table['title']} · {table['orientation']} · {len(table['rows'])}行/{table['columns']}列 · 识别{count}个字段")
        lines.append('  '+('无分组数据：无需填写组名' if '无分组' in table['orientation'] else '候选组别：'+('、'.join(table['groups']) or '待填写')))
    studies=scan['prose_document']['studies'];lines+=['',f"正文：{len(scan['prose_text'])}字，识别{sum(len(s['variables']) for s in studies)}个指标；原文及未识别提示可在预览中查看。"]
    lines+=scan['issues'];return '\n'.join(lines)


def apply_preview_fields(imported,scan,draft,names):
    if not scan or not draft:return
    original={f['_preview_key']:f for f in scan['fields']};edited={f['_preview_key']:f for f in draft['fields'] if f['_preview_key'] in original and f!=original[f['_preview_key']]}
    numerics=[];typed=[]
    for origin,items in (('indicators',imported.indicators),('typed_fields',imported.typed_fields)):
        for field in items:
            key=json.dumps([field.get('table'),field['group'],field['name']],ensure_ascii=False)
            if key in edited and field['group'] in names:
                baseline=original[key];fresh=deepcopy(field)
                fresh.update({k:deepcopy(v) for k,v in edited[key].items() if not k.startswith('_preview_') and baseline.get(k)!=v})
                field=fresh;field.setdefault('kind','mean_sd')
                if origin=='indicators' and field['kind']=='mean_sd':field.setdefault('parity','any');numerics.append(field)
                else:typed.append(field)
            elif origin=='indicators':numerics.append(field)
            else:typed.append(field)
    imported.indicators=numerics;imported.typed_fields=typed


def preview_prose(scan,draft,names):
    if not scan or not draft or draft['prose_document']==scan['prose_document']:return None
    if draft.get('prose_stale'):raise ValueError('预览中的正文已修改，请先在预览中重新识别后再确认组别。')
    document=deepcopy(draft['prose_document'])
    matches=[s for s in document['studies'] if {g['name'] for g in s['groups']}==set(names) and s['variables']]
    if len(matches)!=1:raise ValueError('预览中修改的正文与当前组别不一致，或含多项研究；请核对预览和组别后确认。')
    document['studies']=matches;return document
