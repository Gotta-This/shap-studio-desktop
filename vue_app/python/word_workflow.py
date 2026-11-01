"""Qt Word workflow adapter; source drafts, live tables and prose stay separate."""
from copy import deepcopy
from pathlib import Path
import json,re,shutil,uuid
from dataclasses import asdict
from clinical_studio.word_batch_engine import read_word,default_batch_config,validate_batch,group_names
from clinical_studio.word_scan import scan_word,scan_report,apply_preview_fields,preview_prose
from clinical_studio.word_precision import scan_precision,fields_precision,prose_precision
from clinical_studio.prose_matching import matching_document,metric_key
from clinical_studio.prose_table_engine import parse_document,to_simulation_config,validate_study
from clinical_studio.word_rule_review import field_rule_rows


def source_path(profile,session):
    if not re.fullmatch(r'[a-f0-9]{32}',session or ''):raise ValueError('Word 导入会话无效，请重新导入。')
    folder=profile/'word-sessions'/session
    source=folder/'source.json'
    if not source.exists():raise ValueError('原文已不可用，请重新导入。')
    return Path(json.loads(source.read_text())['path'])

def scan(profile,path,mode='zero'):
    session=uuid.uuid4().hex;folder=profile/'word-sessions'/session;folder.mkdir(parents=True)
    from clinical_studio.word_formats import ensure_docx
    # A converted .doc lives in a per-process temporary directory. Persist the
    # normalized document before the bridge exits so confirmation can reopen it.
    normalized=ensure_docx(path)
    dest=folder/'source.docx';shutil.copy2(normalized,dest)
    data=scan_precision(scan_word(dest),mode);data['source_name']=path.name
    (folder/'source.json').write_text(json.dumps({'path':str(dest),'name':path.name}))
    return dict(session=session,scan=data,draft=deepcopy(data),report=scan_report(data))

def match(profile,p):
    path=source_path(profile,p['session']);names=group_names(p['groups']);imported=read_word(path,names,parse_indicators=False)
    return dict(groups=[dict(name=g,tables=imported.group_matches.get(g,0),paragraphs=imported.text_group_matches.get(g,0),n=imported.group_sizes.get(g)) for g in names],table_count=imported.table_count,messages=imported.messages)

def apply(profile,p):
    path=source_path(profile,p['session']);source_name=json.loads((profile/'word-sessions'/p['session']/'source.json').read_text()).get('name',path.name);options=p.get('options',{});mode=options.get('decimal_mode','zero')
    inventory=scan_precision(scan_word(path),mode);draft=p.get('draft') or inventory
    ungrouped=p.get('ungrouped',False)
    if ungrouped:
        n=p.get('n') or inventory.get('ungrouped_n')
        if type(n) is not int or not 2<=n<=5000:raise ValueError('请填写 2～5000 的生成例数。')
        from clinical_studio.ungrouped_tables import scan_ungrouped,DATASET
        from clinical_studio.word_batch_engine import ImportResult
        fields,_,issues=scan_ungrouped(deepcopy(inventory['tables']),n)
        obj=ImportResult([],{}, {},[],str(path),len(inventory['tables']),typed_fields=fields)
        fields_precision(obj.typed_fields,mode);apply_preview_fields(obj,inventory,draft,[DATASET]);fields=obj.typed_fields
        if not fields:raise ValueError('未发现无分组竖表。')
        config=default_batch_config(['未分组数据']);config.update(ungrouped=True,include_basics=False,typed_fields=fields,table_titles={str(t['table']):t['title'] for t in draft['tables']})
        config['groups'][0]['n']=n
        return dict(config=config,prose_document=None,imported=None,report=scan_report(inventory))
    names=group_names(p['groups']);imported=read_word(path,names)
    missing=[g for g in names if not(imported.group_matches.get(g) or imported.text_group_matches.get(g))]
    if missing:raise ValueError('以下组别未匹配到 Word 表格或正文：'+'、'.join(missing)+'。请修改或移除后重新确认。')
    fields_precision(imported.indicators,mode);fields_precision(imported.typed_fields,mode)
    # Re-scan with the chosen groups; retain the initial keys so only actual edits apply.
    from clinical_studio.word_scan import fields_for_groups
    known={f['_preview_key'] for f in inventory['fields']}
    inventory['fields'] += [f for f in fields_for_groups(path,names,{t['table']:t['title'] for t in inventory['tables']}) if f['_preview_key'] not in known]
    apply_preview_fields(imported,inventory,draft,names)
    document=None
    if options.get('prose'):
        document=preview_prose(inventory,draft,names) or matching_document(path,names)
        prose_precision(document,mode)
    previous={g['name']:g for g in p.get('previous',{}).get('groups',[])}
    config=default_batch_config(names)
    for i,g in enumerate(config['groups']):
        if g['name'] in previous:config['groups'][i]=deepcopy(previous[g['name']]);g=config['groups'][i]
        if options.get('sizes') and g['name'] in imported.group_sizes:g['n']=imported.group_sizes[g['name']]
        if document:
            found=next((x for x in document['studies'][0]['groups'] if x['name']==g['name']),None)
            if found and found['n'] is not None:g['n']=found['n']
        if options.get('rates'):
            for k,v in imported.outcome_rates.get(g['name'],{}).items():g['effective' if k=='总有效率' else 'recurrence']=v
    config.update(source=source_name,indicators=imported.indicators,typed_fields=imported.typed_fields,categoricals=[],include_basics=not imported.baseline_columns and not bool(document),same_group_size=not options.get('sizes') and not bool(document),shared_basics=not bool(document),import_options=options,table_titles={str(t['table']):t['title'] for t in draft['tables']},imported_basics={g['name']:deepcopy(g) for g in config['groups']},detected_basics={g['name']:list(imported.outcome_rates.get(g['name'],{})) if options.get('rates') else [] for g in config['groups']})
    return dict(config=config,prose_document=document,imported=asdict(imported),report=scan_report(inventory)+'\n'+'\n'.join(imported.messages))


def signature(field,n):
    kind=field.get('kind','category' if 'labels' in field else 'mean_sd')
    if kind=='mean_sd':return (kind,field.get('mean'),field.get('sd'))
    if kind=='quantile':return (kind,field.get('q1'),field.get('median'),field.get('q3'))
    if kind in ('category','gender','yesno','binary','binary01'):
        counts=field.get('counts');values=counts.items() if isinstance(counts,dict) else zip(field.get('labels',[]),counts) if counts else [(k,w*n/100) for k,w in zip(field.get('labels',[]),field.get('weights',[])) if w is not None]
        return ('category',tuple(sorted((str(k),round(v,6)) for k,v in values)))
    return (kind,)


def compose(p,validate=True):
    config=deepcopy(p['config']);groups=config['groups'];options=config.get('import_options',{})
    active_document=p.get('prose_document') if p.get('prose_active',True) else None
    if config.get('same_group_size') and not active_document:
        for g in groups[1:]:g['n']=groups[0]['n']
    if config.get('shared_basics') and len(groups)>1:
        for i in range(1,len(groups)):
            keep={k:groups[i][k] for k in ('name','n','effective','recurrence','recurrence_scope')}
            groups[i]=dict(deepcopy(groups[0]),**keep)
    if options.get('leave_unknown_blank'):
        for g in groups:g['blank_fields']=[n for n in ('性别','年龄','病程','病情程度','病变范围','总有效率','复发率') if n not in config.get('detected_basics',{}).get(g['name'],[])]
    document=active_document;study=None
    if document and p.get('prose_active',True):
        if p.get('prose_stale') and validate:raise ValueError('输入文字已变化，请先重新识别。')
        studies=document.get('studies',[]);index=p.get('study_index',0)
        if studies and 0<=index<len(studies):study=deepcopy(studies[index])
        elif validate:raise ValueError('没有可用的文字研究，请重新识别或关闭采用文字匹配。')
        else:config['prose_preview_issues']=['输入文字已变化，请先重新识别。' if p.get('prose_stale') else '没有可用的文字研究，请重新识别。']
    table_state={k:deepcopy(config.get(k,[])) for k in ('indicators','categoricals','typed_fields')};config['table_match']=table_state
    if study:
        try:
            if p.get('prose_stale'):raise ValueError('输入文字已变化，请先重新识别。')
            if set(g['name'] for g in study['groups'])!=set(g['name'] for g in groups):raise ValueError('文字匹配与当前组别不一致，请重新确认组别。')
            fields=sum((config.get(k,[]) for k in ('indicators','categoricals','typed_fields')),[])
            for v in study['variables']:
                for group,cell in v['cells'].items():
                    old=next((f for f in fields if metric_key(f['name'])==metric_key(v['name']) and f['group']==group),None)
                    if old is None:continue
                    n=next(g['n'] for g in study['groups'] if g['name']==group) or 1
                    if signature(old,n)!=signature(dict(cell,kind=v['kind'],labels=v['labels']),n):
                        reviewed=cell.get('reviewed') and signature(old,n)==signature(cell.get('table_conflict',{}),n)
                        if not reviewed:raise ValueError(v['name']+' / '+group+'：正文与 Word 表格参数冲突，请核对并确认当前值。')
            prose=to_simulation_config(study);keys={(metric_key(f['name']),f['group']) for f in prose['typed_fields']}
            for key in ('indicators','categoricals','typed_fields'):config[key]=[f for f in config.get(key,[]) if (metric_key(f['name']),f['group']) not in keys]
            config['typed_fields']+=prose['typed_fields'];sizes={g['name']:g['n'] for g in study['groups']}
            for g in groups:g['n']=sizes[g['name']]
            config.update(include_basics=False,prose_table=study,prose_document=deepcopy(document))
        except (ValueError,KeyError,TypeError) as exc:
            if validate:raise
            config['prose_preview_issues']=[str(exc)]
            config['prose_pending_rows']=[dict(column=v['name'],group=g['name'],source='Word正文（待核对）',rule='文字已修改或参数待补全；表格匹配保持不变',original='；'.join(e['raw'] for e in v['cells'].get(g['name'],{}).get('evidence',[]))) for v in study.get('variables',[]) for g in study.get('groups',[])]
    config['field_rules']=field_rule_rows(config)+config.get('prose_pending_rows',[])
    if validate:validate_batch(config)
    return config


def review(p):
    try:
        config=compose(p,False);return dict(rows=config['field_rules'],error='；'.join(config.get('prose_preview_issues',[])),columns=__import__('clinical_studio.word_batch_engine',fromlist=['output_columns']).output_columns(config))
    except (ValueError,KeyError,TypeError) as e:
        # A bad prose draft must not blank independent table sources.
        base=deepcopy(p);base['prose_active']=False;config=compose(base,False)
        return dict(rows=config['field_rules'],error=str(e),columns=[])
