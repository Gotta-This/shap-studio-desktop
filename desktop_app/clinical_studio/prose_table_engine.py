"""Offline prose -> editable summary model. No synthetic values or statistics inferred."""
from copy import deepcopy
from pathlib import Path
import json
import math
import re
import unicodedata
from zipfile import ZipFile
from xml.etree import ElementTree as ET

SCHEMA = 'clinical-prose-table/v1'
NUM = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
PAIR = re.compile(r'(' + NUM + r')±(' + NUM + r')')
RANGE = re.compile(r'(' + NUM + r')[～~—–至-](' + NUM + r')')
QUANTILE = re.compile(r'(' + NUM + r')\((' + NUM + r')[,，](' + NUM + r')\)')
KNOWN_GROUPS = ('对照组','试验组','实验组','观察组','干预组','治疗组','研究组','安慰剂组','训练集','验证集','测试集')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def normalized(text):
    """Keep an offset map back to the unchanged original, including NFKC expansions."""
    chars, offsets = [], []
    for i, char in enumerate(text):
        for c in unicodedata.normalize('NFKC', char):
            if not c.isspace():
                chars.append(c.replace('−', '-')); offsets.append(i)
    return ''.join(chars), offsets


def canonical(name):
    name = name.strip('：:，,；;。()（） ')
    name = re.sub(r'^(?:其中|患者的?|其)', '', name)
    name = re.sub(r'(?:平均年龄|均龄)$', '年龄', name)
    name = re.sub(r'(?:为|平均|均值|均数)$', '', name)
    name = name.replace('APACHEII', 'APACHEⅡ').replace('APACHE2', 'APACHEⅡ')
    name = name.replace('PaO2/FiO2', '氧合指数').replace('PaO₂/FiO₂', '氧合指数')
    return name.strip('：:()（） ')


def read_docx_text(path):
    """Read body prose only. A table is not mistaken for prose."""
    with ZipFile(path) as archive:
        body = ET.fromstring(archive.read('word/document.xml')).find(W+'body')
    paragraphs = []
    def walk(node):
        for child in node:
            if child.tag == W+'tbl':
                continue
            if child.tag == W+'p':
                text = ''.join(n.text or '' for n in child.iter(W+'t'))
                paragraphs.append(text)
            else:
                walk(child)
    if body is not None: walk(body)
    return '\n'.join(paragraphs)


def parse_document(text, group_names=None):
    blocks = [b for b in re.split(r'\n\s*\n', text.strip()) if b.strip()]
    return {'schema': SCHEMA, 'source_text': text,
            'studies': [parse_study(block, group_names) for block in blocks]}


def clauses(segment):
    """Split outer punctuation; preserve quartiles, category lists and range+mean."""
    pieces=[]; start=0; depth=0
    for i,char in enumerate(segment):
        if char in '(（': depth+=1
        elif char in ')）': depth=max(0,depth-1)
        elif depth==0 and char in ';；。,,，':
            current=segment[start:i]
            if char in ',，' and (re.match(r'(?:平均|均龄)',segment[i+1:]) or (':' in current and '例' in current)):
                continue
            if current: pieces.append((start,current))
            start=i+1
    if start<len(segment):pieces.append((start,segment[start:]))
    return pieces


def parse_study(source, group_names=None):
    text, offsets = normalized(source)
    def evidence(start, end):
        if start >= end: return {'raw': '', 'start': 0, 'end': 0}
        a, b = offsets[start], offsets[end-1]+1
        return {'raw': source[a:b], 'start': a, 'end': b}
    names = list(dict.fromkeys(group_names or [g for g in KNOWN_GROUPS if g in text]))
    study = {'source_text': source, 'groups': [], 'variables': [], 'notes': [], 'issues': [], 'unparsed': []}
    if not names:
        study['issues'].append('未识别组别，请填写原文中的组名后重新识别。')
        study['unparsed'].append({'raw': source, 'reason': '组别未识别'})
        return study
    pattern = re.compile('|'.join(re.escape(g) for g in sorted(names,key=len,reverse=True)))
    markers = list(pattern.finditer(text))
    names = list(dict.fromkeys(group_names or [m[0] for m in markers]))
    study['groups'] = [{'name': n, 'n': None, 'n_origin': 'missing', 'evidence': [], 'issues': []} for n in names]
    groups = {g['name']: g for g in study['groups']}
    variables = {}
    def variable(name, kind, unit=''):
        name = canonical(name)
        if name not in variables:
            variables[name] = {'name': name, 'kind': kind, 'unit': unit, 'labels': [], 'cells': {}}
            study['variables'].append(variables[name])
        v = variables[name]
        if v['kind'] != kind: study['issues'].append(name+'存在不同统计类型，请核对。')
        if unit and v['unit'] and unit != v['unit']: study['issues'].append(name+'单位不一致，请核对。')
        if unit and not v['unit']: v['unit'] = unit
        return v
    def put(v, group, cell):
        old = v['cells'].get(group)
        if old is not None:
            if {k:w for k,w in old.items() if k not in ('evidence','issues')} != {k:w for k,w in cell.items() if k not in ('evidence','issues')}:
                old.setdefault('issues', []).append('同一组指标出现多个不同值；请拆分研究或核对。')
                old.setdefault('alternatives', []).append(cell)
            else: old['evidence'].extend(cell['evidence'])
        else: v['cells'][group] = cell
    # A concluding comparison may mention group names again; exclude it from data segments.
    conclusion = re.search(r'两组(?:患者|在|上述|一般资料|比较|的)', text)
    stop = conclusion.start() if conclusion else len(text)
    for i, marker in enumerate(markers):
        if marker.start() >= stop: continue
        end = min(markers[i+1].start() if i+1 < len(markers) else len(text), stop)
        a, b = marker.end(), end
        segment = text[a:b]; group = marker[0]; g = groups[group]
        count = re.match(r'(?:共|纳入|为|各)?(\d+)例', segment)
        if count:
            n = int(count[1]); g['evidence'].append(evidence(a, a+count.end()))
            if g['n'] is not None and g['n'] != n: g['issues'].append('原文组例数冲突')
            else: g.update(n=n, n_origin='reported')
            a += count.end(); segment = text[a:b]
        # Gender is a single categorical variable, even though the UI expands its levels.
        sex = list(re.finditer(r'(男|女)(?:性)?(\d+)例', segment))
        if sex:
            v = variable('性别', 'category', '例'); counts = {}
            for m in sex:
                counts[m[1]] = int(m[2])
                if m[1] not in v['labels']: v['labels'].append(m[1])
            # Explicit binary semantics; a missing count is not filled with zero.
            for label in ('男','女'):
                if label not in v['labels']: v['labels'].append(label)
            put(v, group, {'counts': counts, 'evidence': [evidence(a+m.start(),a+m.end()) for m in sex], 'issues': []})
        # Semicolon clauses have stable ownership. Commas within mean/range descriptions stay together.
        for local, clause in clauses(segment):
            start = a+local
            ev = evidence(start, start+len(clause))
            if not clause: continue
            if re.fullmatch(r'[,，、]*(?:(?:男|女)(?:性)?\d+例[,，、]*)+', clause): continue
            if re.fullmatch(r'[,，]*\d+例[,，]*', clause): continue
            # Named categorical section, e.g. 部位:双侧24例、单侧6例.
            cat = re.match(r'([^:：]+)[:：](.+)', clause) or re.match(r'(呼吸衰竭类型|机械通气方式)(.+)',clause)
            if cat and re.search(r'\d+例', cat[2]):
                entries = list(re.finditer(r'([^、,，:：]+?)(\d+)例',cat[2]))
                if entries:
                    v = variable(cat[1], 'category', '例'); counts = {}
                    for m in entries:
                        label = m[1].strip()
                        if label in counts: study['issues'].append(v['name']+'类别重复，请核对。')
                        counts[label] = int(m[2])
                        if label not in v['labels']: v['labels'].append(label)
                    put(v,group,{'counts':counts,'evidence':[ev],'issues':[]})
                    residue = cat[2]
                    for m in reversed(entries): residue=residue[:m.start()]+residue[m.end():]
                    if residue.strip('、,，'): study['unparsed'].append(dict(ev,reason='分类描述中仍有未识别内容'))
                    continue
            pair = PAIR.search(clause); quant = QUANTILE.search(clause)
            range_match = RANGE.search(clause)
            value = pair or quant or range_match
            if value:
                prefix = clause[:value.start()].rstrip('(（:：')
                # Range followed by a mean shares the original indicator name.
                if pair and range_match and range_match.start() < pair.start(): prefix=clause[:range_match.start()]
                prefix = re.split('[,，]', prefix)[-1]
                if prefix in ('平均','均龄','平均年龄'): prefix='年龄'
                name = canonical(prefix)
                if not name:
                    study['unparsed'].append(dict(ev,reason='数值缺少明确指标名称')); continue
                suffix = clause[value.end():].lstrip(')）')
                unit = re.match(r'(kg/m[²2]|mmHg|岁|月|分|h|天|小时|%|mg/L|mmol/L)', suffix, re.I)
                unit = unit[1].replace('kg/m2','kg/m²') if unit else ''
                kind = 'mean_sd' if pair else 'quantile' if quant else 'range'
                v = variable(name,kind,unit)
                cell = {'evidence':[ev], 'issues':[]}
                if pair: cell.update(mean=float(pair[1]),sd=float(pair[2]),digits=max(decimal_digits(pair[1]),decimal_digits(pair[2])))
                elif quant: cell.update(median=float(quant[1]),q1=float(quant[2]),q3=float(quant[3]),digits=max(decimal_digits(quant[j]) for j in (1,2,3)))
                if range_match: cell.update(lower=float(range_match[1]),upper=float(range_match[2]))
                if name=='年龄' and unit=='岁' and pair and cell['mean'].is_integer() and cell['sd'].is_integer():cell['digits']=0
                put(v,group,cell)
                # Any additional numeric summary in one clause needs review, not silent omission.
                if len(list(PAIR.finditer(clause))) > 1:
                    cell['issues'].append('同一分句有多个统计值，请拆成分号分隔的指标后重新识别。')
                continue
            if clause.strip('，,'):
                study['unparsed'].append(dict(ev,reason='未支持或未识别的描述，请核对'))
    if conclusion:
        note = evidence(conclusion.start(),len(text)); study['notes'].append(note)
        intro = text[conclusion.start():]
        compare = re.search(r'(?:性别|年龄|BMI|APACHE)', intro)
        if compare and '比较' in intro:
            listed = intro[compare.start():intro.index('比较')]
            listed = re.sub(r'(?:等方面|等|分布)$','',listed)
            for label in re.split(r'[、,，]|以及|及',listed):
                label = canonical(re.sub(r'构成$|分布$','',label))
                if label and label not in variables:
                    matches=[name for name in variables if name.endswith(label)]
                    if len(matches)!=1: variable(label,'unknown')
    # Infer N only from complete explicit categorical partitions, requiring agreement.
    for g in study['groups']:
        totals=[]
        for v in study['variables']:
            cell=v['cells'].get(g['name'])
            if v['kind']=='category' and cell and len(v['labels'])>=2 and set(cell['counts'])==set(v['labels']):
                totals.append(sum(cell['counts'].values()))
        if g['n'] is None and totals:
            if len(set(totals))==1: g.update(n=totals[0],n_origin='inferred')
            else: g['issues'].append('分类人数合计不一致，不能推算组例数')
    # Overall total is corroborating evidence, never allocated across groups.
    total = re.search(r'(?:共纳入|共计|共)(?:[^。;；]*?患者)?(\d+)例',text[:markers[0].start()] if markers else '')
    if total:
        study['reported_total']=int(total[1])
    return study


def decimal_digits(value): return len(value.split('.')[1]) if '.' in value else 0


def validate_study(study):
    errors=list(study.get('issues',[])); warnings=[]
    if len(study['groups'])<2: errors.append('至少需要两个组别。')
    group_names=[g['name'] for g in study['groups']]
    if len(set(group_names))!=len(group_names): errors.append('组名重复。')
    for g in study['groups']:
        errors.extend(g.get('issues',[]))
        if isinstance(g['n'],bool) or not isinstance(g['n'],int) or not 2<=g['n']<=5000: errors.append(g['name']+'：请补全2～5000的组例数。')
        if g.get('n_origin')=='inferred': warnings.append(g['name']+'例数由分类人数推算，请核对。')
    if study.get('reported_total') is not None and all(isinstance(g['n'],int) for g in study['groups']):
        if sum(g['n'] for g in study['groups'])!=study['reported_total']: errors.append('各组例数合计与原文总例数不一致。')
    seen=set()
    if not study['variables']: errors.append('尚未识别到可用指标。')
    for v in study['variables']:
        name=v['name']
        if not name.strip() or name in seen or name in ('编号','分组') or name.startswith('='): errors.append('指标名称为空、重复或不可用：'+name)
        seen.add(name)
        if v['kind'] not in ('mean_sd','category','quantile','range','unknown'): errors.append(name+'：不支持的数据类型。')
        for g in study['groups']:
            label=name+' / '+g['name']; cell=v['cells'].get(g['name'])
            if not cell: errors.append(label+'：原文未报告数值，请补全或删除该指标。'); continue
            errors.extend(label+'：'+issue for issue in cell.get('issues',[]))
            def finite(key):
                value=cell.get(key)
                return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value)
            if v['kind']=='mean_sd':
                if not finite('mean') or not finite('sd') or cell['sd']<0: errors.append(label+'：均数或标准差无效。')
                if cell.get('digits',2) not in range(5): errors.append(label+'：最多支持4位小数。')
            elif v['kind']=='category':
                counts=cell.get('counts',{}); labels=v['labels']
                if len(labels)<2 or len(set(labels))!=len(labels) or any(not str(x).strip() for x in labels): errors.append(label+'：请补全至少两个不同类别。')
                if set(counts)!=set(labels) or any(type(x) is not int or x<0 for x in counts.values()): errors.append(label+'：类别人数缺失或无效。')
                elif sum(counts.values())!=g['n']: errors.append(label+('：男女例数之和与本组例数不一致。' if name=='性别' else '：分类人数合计与本组例数不一致。'))
            elif v['kind']=='quantile':
                if not all(finite(k) for k in ('q1','median','q3')) or not cell['q1']<=cell['median']<=cell['q3']: errors.append(label+'：四分位数顺序或数值无效。')
                if not all(finite(k) for k in ('lower','upper')): errors.append(label+'：模拟所需尾部上下限未报告，请补全。')
                elif all(finite(k) for k in ('q1','q3')) and not cell['lower']<=cell['q1']<=cell['q3']<=cell['upper']: errors.append(label+'：尾部范围须包含四分位数。')
            else: errors.append(label+'：当前信息不足以确定模拟参数，请选择类型并补全。')
            for key in ('lower','upper'):
                if cell.get(key) is not None and not finite(key): errors.append(label+'：上下限无效。')
            if all(finite(k) for k in ('lower','upper')):
                if cell['lower']>cell['upper']: errors.append(label+'：下限大于上限。')
                if finite('mean') and not cell['lower']<=cell['mean']<=cell['upper']: errors.append(label+'：均数不在范围内。')
                elif v['kind']=='mean_sd' and finite('mean') and finite('sd') and isinstance(g['n'],int) and g['n']>1:
                    max_sd=math.sqrt(max(0,(cell['mean']-cell['lower'])*(cell['upper']-cell['mean'])*g['n']/(g['n']-1)))
                    if cell['sd']>max_sd+1e-9:errors.append(label+'：范围、均数和标准差无法同时满足。')
    warnings.extend('未识别内容：'+x['raw'] for x in study.get('unparsed',[]))
    # Unrecognized clauses must be explicitly reviewed before simulation handoff.
    if study.get('unparsed') and not study.get('unparsed_reviewed'): errors.append('存在未识别原文，请核对并勾选已核对未识别内容。')
    return {'errors':list(dict.fromkeys(errors)), 'warnings':list(dict.fromkeys(warnings))}


def to_simulation_config(study):
    report=validate_study(study)
    if report['errors']: raise ValueError('\n'.join(report['errors']))
    from .word_batch_engine import default_batch_config, validate_batch
    config=default_batch_config([g['name'] for g in study['groups']])
    config.update(include_basics=False, indicators=[], categoricals=[], typed_fields=[], source='正文转表', prose_table=deepcopy(study))
    for target,g in zip(config['groups'],study['groups']): target['n']=g['n']
    for v in study['variables']:
        for g in study['groups']:
            cell=v['cells'][g['name']]
            field=dict(name=v['name'],group=g['name'],kind=v['kind'],table=0,source_kind='prose',source_n=g['n'],unit=v['unit'],confirmed=True,
                       raw='；'.join(e['raw'] for e in cell.get('evidence',[])),digits=cell.get('digits',2),lower=cell.get('lower'),upper=cell.get('upper'))
            if v['kind']=='category':
                field.update(labels=list(v['labels']),counts=[cell['counts'][k] for k in v['labels']],weights=[cell['counts'][k]/g['n']*100 for k in v['labels']])
            else:
                for k in ('mean','sd','median','q1','q3'):
                    if k in cell: field[k]=cell[k]
            config['typed_fields'].append(field)
    validate_batch(config)
    return config


def save_document(document,path):
    if document.get('schema')!=SCHEMA: raise ValueError('不支持的正文表格版本。')
    payload=deepcopy(document)
    payload['validation']=[validate_study(study) for study in document['studies']]
    payload['ready_for_simulation']=[not report['errors'] for report in payload['validation']]
    Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def load_document(path):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('schema')!=SCHEMA or not isinstance(doc.get('studies'),list): raise ValueError('不是受支持的正文表格JSON。')
    return doc
