"""Validate configuration structure before Vue renders nested editors."""
from copy import deepcopy
from clinical_studio.word_batch_engine import default_batch_config,group_names


def prose_document(value):
    if not isinstance(value,dict) or not isinstance(value.get('studies'),list):raise ValueError('不是有效的文字匹配配置。')
    document=deepcopy(value);document.setdefault('source_text','')
    if not isinstance(document['source_text'],str):raise ValueError('文字原文必须是文本。')
    for study in document['studies']:
        if not isinstance(study,dict) or not isinstance(study.get('groups'),list) or not isinstance(study.get('variables'),list):raise ValueError('文字研究缺少组别或变量表。')
        names=group_names([g.get('name','') for g in study['groups'] if isinstance(g,dict)])
        if len(names)!=len(study['groups']):raise ValueError('文字组别格式无效。')
        for group in study['groups']:group.setdefault('n',None);group.setdefault('issues',[])
        for variable in study['variables']:
            if not isinstance(variable,dict) or not isinstance(variable.get('name'),str) or not isinstance(variable.get('cells'),dict):raise ValueError('文字变量缺少名称或分组数值。')
            variable.setdefault('kind','unknown');variable.setdefault('labels',[]);variable.setdefault('unit','')
            if not isinstance(variable['labels'],list):raise ValueError('文字类别标签必须为列表。')
            for cell in variable['cells'].values():
                if not isinstance(cell,dict):raise ValueError('文字数值格式无效。')
                cell.setdefault('evidence',[]);cell.setdefault('issues',[])
                if not isinstance(cell['evidence'],list) or not isinstance(cell['issues'],list):raise ValueError('文字证据或问题列表格式无效。')
                if any(not isinstance(e,dict) or not isinstance(e.get('raw'),str) for e in cell['evidence']):raise ValueError('文字证据格式无效。')
    return document


def word(value):
    if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('groups'),list):raise ValueError('不是有效的 Word 生成配置。')
    if any(not isinstance(g,dict) for g in value['groups']):raise ValueError('基础资料组别格式无效。')
    names=group_names([g.get('name','') for g in value['groups']]);result=default_batch_config(names);result.update(deepcopy(value))
    defaults=default_batch_config(names)['groups']
    result['groups']=[{**base,**group,'name':name} for base,group,name in zip(defaults,value['groups'],names)]
    for group in result['groups']:
        if not isinstance(group['severity'],list) or len(group['severity'])!=3:raise ValueError('病情程度须含轻、中、重三个比例。')
        for key in ('age','course','extent','extent_ranges'):
            if not isinstance(group[key],list) or any(not isinstance(row,dict) for row in group[key]):raise ValueError('基础资料的区间和类别须为列表。')
    for key in ('indicators','typed_fields','categoricals'):
        if key in result.get('table_match',{}):result[key]=deepcopy(result['table_match'][key])
        result.setdefault(key,[])
        if not isinstance(result[key],list) or any(not isinstance(f,dict) or not isinstance(f.get('name'),str) or f.get('group') not in names for f in result[key]):raise ValueError('表格匹配字段缺少名称或有效组别。')
    result.pop('table_match',None)
    result.setdefault('include_basics',True);result.setdefault('same_group_size',len({g['n'] for g in result['groups']})==1);result.setdefault('shared_basics',False)
    if result.get('prose_document') is not None:result['prose_document']=prose_document(result['prose_document'])
    if not isinstance(result.get('import_options',{}),dict):raise ValueError('导入选项格式无效。')
    return result


def shap(value):
    from clinical_studio.config import validate
    try:validate(value)
    except (KeyError,TypeError,AttributeError,IndexError) as exc:raise ValueError('模拟生图配置不完整或格式无效，请选择完整参数文件。') from exc
    return deepcopy(value)
