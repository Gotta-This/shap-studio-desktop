"""Import Word summary tables and create explicitly labelled synthetic case data.

DOCX parsing uses the OOXML grid (including horizontal/vertical merges), not
positional guesses based on the number of physical cells. No source files change.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from .data_tools_engine import numeric_numbers, statistics

GROUPS = ('对照组', '中药组')
BASE_COLUMNS = ['编号', '分组', '性别', '年龄', '病程', '病情程度', '病变范围']
END_COLUMNS = ['总有效率', '复发率']
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NUM = r'[+−-]?(?:\d+(?:\.\d*)?|\.\d+)'
PAIR = re.compile(r'('+NUM+r')\s*±\s*('+NUM+r')')


@dataclass
class ImportResult:
    indicators: list
    group_sizes: dict
    outcome_rates: dict
    messages: list
    source: str
    table_count: int


def _grid(table, with_origins=False):
    rows = []
    origins = []
    above = []
    for row_index,tr in enumerate(table.findall(W+'tr')):
        row = []
        origin = []
        before = tr.find(W+'trPr/'+W+'gridBefore')
        if before is not None:
            row.extend(['']*int(before.get(W+'val', '0')))
            origin.extend([None]*len(row))
        for cell_index,cell in enumerate(tr.findall(W+'tc')):
            text = ''.join(t.text or '' for t in cell.iter(W+'t')).strip()
            span = cell.find(W+'tcPr/'+W+'gridSpan')
            width = int(span.get(W+'val', '1')) if span is not None else 1
            merge = cell.find(W+'tcPr/'+W+'vMerge')
            if merge is not None and merge.get(W+'val') != 'restart' and not text:
                text = above[len(row)] if len(row) < len(above) else ''
            row.extend([text]*width)
            origin.extend([(row_index,cell_index)]*width)
        rows.append(row)
        origins.append(origin)
        above = row
    return (rows,origins) if with_origins else rows


def _clean(value):
    return re.sub(r'\s+', '', value).replace('−', '-')


def _header(headers, col):
    labels = []
    for row in headers:
        value = row[col].strip() if col < len(row) else ''
        if value and value not in labels:
            labels.append(value)
    phase = next(('前' if '前' in x else '后' for x in reversed(labels)
                  if x in ('治疗前', '治疗后', '干预前', '干预后', '前', '后')), '')
    metric = next((x for x in labels if x not in ('治疗前', '治疗后', '干预前', '干预后', '前', '后')), '')
    metric = re.sub(r'[（(].*?[）)]', '', metric).strip()
    return (phase+'-' if phase else '')+metric


def read_word(path):
    path = Path(path)
    if path.suffix.lower() != '.docx':
        raise ValueError('请选择 .docx 文件；旧版 .doc 请先另存为 .docx。')
    try:
        with ZipFile(path) as archive:
            info = archive.getinfo('word/document.xml')
            if info.file_size > 25_000_000:
                raise ValueError('Word 正文过大（上限 25 MB），请精简文件后导入。')
            root = ET.fromstring(archive.read(info))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError('无法读取 Word 正文，请确认文件为有效的 .docx。') from exc
    body = root.find(W+'body')
    if body is None:
        raise ValueError('Word 中没有正文。')
    tables = body.findall(W+'tbl')
    indicators, sizes, rates, messages = [], {}, {}, []
    used_names = set(BASE_COLUMNS+END_COLUMNS)
    for index, table in enumerate(tables, 1):
        rows,origins = _grid(table,True)
        group_rows = {g: [row for row in rows if row and _clean(row[0]) == g] for g in GROUPS}
        if not any(group_rows.values()):
            messages.append(f'表 {index}：未找到对照组／中药组数据行，未导入。')
            continue
        if any(len(v)>1 for v in group_rows.values()):
            messages.append(f'表 {index}：同组存在多行，无法自动确定，整表未导入；请人工补录。')
            continue
        first = min(i for i, row in enumerate(rows) if row and _clean(row[0]) in GROUPS)
        headers = rows[:first]
        for group, candidates in group_rows.items():
            if not candidates:
                messages.append(f'表 {index}：缺少{group}行；相关指标会标记为待补全。')
                continue
            row = candidates[0]
            if len(row)>1 and _clean(row[1]).isdigit():
                n = int(_clean(row[1]))
                if group in sizes and sizes[group]!=n:
                    messages.append(f'表 {index}：{group}例数 {n} 与此前 {sizes[group]} 不同，请核对配置。')
                else:
                    sizes[group] = n
        width = max(map(len, rows), default=0)
        found = 0
        relevant=[i for i,row in enumerate(rows) if i<first or (row and _clean(row[0]) in GROUPS)]
        for col in range(2, width):
            # Word sometimes splits one physical data cell across several grid columns.
            # Import it once when the headers AND both data rows share that same span.
            if col>2 and all(col<len(origins[i]) and origins[i][col] is not None and origins[i][col]==origins[i][col-1] for i in relevant):
                continue
            raw = {g: (rs[0][col] if rs and col<len(rs[0]) else '') for g, rs in group_rows.items()}
            matches = {g: PAIR.search(_clean(v)) for g, v in raw.items()}
            name = _header(headers, col)
            if any(matches.values()):
                if not name:
                    name = f'表{index}-指标{col-1}'
                    messages.append(f'表 {index}第 {col+1} 列：无可识别表头，已使用临时名称。')
                if name in used_names:
                    name += f'（表{index}列{col+1}）'
                used_names.add(name)
                for group in GROUPS:
                    match = matches[group]
                    if not match:
                        messages.append(f'表 {index} {name} {group}：未识别均数±标准差，生成前请补全或移除该指标的两组行。')
                    indicators.append(dict(table=index, name=name, group=group,
                                           mean=float(match[1]) if match else None,
                                           sd=float(match[2]) if match else None,
                                           digits=2, lower=None, upper=None, parity='any', raw=raw[group]))
                found += 1
            elif name in END_COLUMNS:
                for group, value in raw.items():
                    value = _clean(value).replace('（','(').replace('）',')')
                    match = re.match(r'(\d+)\((\d+(?:\.\d+)?)%?\)', value)
                    if match and sizes.get(group):
                        rates.setdefault(group, {})[name] = int(match[1])/sizes[group]*100
                    else:
                        pct = re.fullmatch(r'(\d+(?:\.\d+)?)%', value)
                        if pct:
                            rates.setdefault(group, {})[name] = float(pct[1])
                        else:
                            messages.append(f'表 {index} {group} {name}：比例未识别，请手动设置。')
        messages.append(f'表 {index}：识别 {found} 个数值指标。')
    if not indicators:
        messages.append('未识别到均数±标准差指标，可在指标配置中手动添加。')
    messages.append('基本资料的区间及比例为可编辑初始值，未从 Word 正文推断；请逐项核对。')
    messages.append('各指标按列独立模拟，不还原病例配对、相关性或原文检验结果。')
    return ImportResult(indicators, sizes, rates, messages, str(path.resolve()), len(tables))


def default_batch_config():
    return dict(version=1, seed=12, source='', course_unit='月', groups=[dict(
        name=g, n=70, male=50., severity=[50.,50.,0.], effective=80., recurrence=10.,
        age=[dict(lower=18, upper=74, percent=100.)],
        course=[dict(lower=1, upper=60, percent=100.)], course_digits=0,
        extent=[dict(label='E1',percent=33.),dict(label='E2',percent=34.),dict(label='E3',percent=33.)])
        for g in GROUPS], indicators=[])


def allocation(n, weights):
    if not weights or any(not math.isfinite(w) or w<0 for w in weights) or abs(math.fsum(weights)-100)>1e-6:
        raise ValueError('每组比例须为非负数，且合计为 100%。')
    expected = [n*w/100 for w in weights]
    counts = [math.floor(v) for v in expected]
    for i in sorted(range(len(weights)),key=lambda i: (-(expected[i]-counts[i]),i))[:n-sum(counts)]:
        counts[i] += 1
    return counts


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(f'{label}须为有效数字。')
    return value


def validate_batch(config):
    if config.get('version') != 1:
        raise ValueError('不支持此配置版本。')
    seed = config.get('seed')
    if not isinstance(seed,int) or isinstance(seed,bool) or not 0<=seed<=4294967295:
        raise ValueError('随机种子须为 0～4294967295 的整数。')
    groups = config.get('groups',[])
    if [g.get('name') for g in groups] != list(GROUPS):
        raise ValueError('分组须依次为对照组、中药组。')
    for g in groups:
        n=g.get('n')
        if not isinstance(n,int) or isinstance(n,bool) or not 2<=n<=5000:
            raise ValueError(f"{g['name']}例数须为 2～5000 的整数。")
        for name in ('male','effective','recurrence'):
            if not 0<=_finite(g[name],name)<=100:
                raise ValueError(f'{name}须在 0～100% 之间。')
        if len(g['severity'])!=3:
            raise ValueError('病情程度须包含轻度、中度、重度三个比例。')
        allocation(n,[_finite(x,'病情比例') for x in g['severity']])
        for key in ('age','course'):
            ranges=g[key]
            allocation(n,[_finite(r['percent'],'区间比例') for r in ranges])
            d=0 if key=='age' else g['course_digits']
            if not isinstance(d,int) or d not in range(5):
                raise ValueError('病程小数位须为 0～4。')
            for r in ranges:
                low,high=_finite(r['lower'],'区间下限'),_finite(r['upper'],'区间上限')
                if low<0 or low>high or high>1e6 or math.ceil(low*10**d)>math.floor(high*10**d):
                    raise ValueError('年龄／病程区间须非负、有可用数值，且上限不超过 100 万。')
            active=sorted(ranges,key=lambda r:r['lower'])
            if any(a['upper']>=b['lower'] for a,b in zip(active,active[1:])):
                raise ValueError('年龄／病程区间包含端点，请设置互不重叠的区间（例如 10～19、20～29）。')
        extent=g['extent']
        allocation(n,[_finite(r['percent'],'病变范围比例') for r in extent])
        labels=[r['label'].strip() for r in extent]
        if any(not s for s in labels) or len(labels)!=len(set(labels)):
            raise ValueError('病变范围名称不能为空或重复。')
    specs=config.get('indicators',[])
    if not specs:
        raise ValueError('请导入 Word 或添加至少一个数值指标。')
    if len(specs)>500:
        raise ValueError('最多支持 250 个指标（每个指标两组配置）。')
    names={}
    for spec in specs:
        name=spec['name'].strip()
        if not name or name in BASE_COLUMNS+END_COLUMNS or name.startswith('='):
            raise ValueError('指标名不能为空、与固定列重名或以等号开头。')
        group=spec['group']
        if group not in GROUPS or group in names.setdefault(name,set()):
            raise ValueError(f'{name} 的分组无效或重复。')
        names[name].add(group)
        _finite(spec['mean'],name+'均数')
        if _finite(spec['sd'],name+'标准差')<0:
            raise ValueError(f'{name} 的标准差须非负。')
        digits=spec['digits']
        if not isinstance(digits,int) or digits not in range(5) or spec['parity'] not in ('any','odd','even'):
            raise ValueError('指标小数位须为 0～4，数值类型须有效。')
        if spec['parity']!='any' and digits!=0:
            raise ValueError('奇偶数指标的小数位须为 0。')
        for key in ('lower','upper'):
            if spec.get(key) is not None:
                _finite(spec[key],name+'边界')
        if spec.get('lower') is not None and spec.get('upper') is not None and spec['lower']>spec['upper']:
            raise ValueError(f'{name} 下限不能超过上限。')
    if any(gs!=set(GROUPS) for gs in names.values()):
        raise ValueError('每个指标都须配置对照组和中药组；请补全缺失行。')


def _categorical(n, labels, weights, rng):
    a=[label for label,count in zip(labels,allocation(n,weights)) for _ in range(count)]
    rng.shuffle(a)
    return a


def _ranges(n, ranges, digits, rng):
    factor=10**digits
    a=[]
    for r,count in zip(ranges,allocation(n,[r['percent'] for r in ranges])):
        a.extend(rng.randint(math.ceil(r['lower']*factor),math.floor(r['upper']*factor))/factor for _ in range(count))
    rng.shuffle(a)
    return a


def _indicator(spec,n,rng):
    options=dict(n=n,mean=spec['mean'],sd=spec['sd'],digits=spec['digits'],
                 lower=spec.get('lower'),upper=spec.get('upper'),seed=rng.getrandbits(32))
    if spec['parity']=='any':
        return numeric_numbers(**options)
    parity=1 if spec['parity']=='odd' else 0
    options.update(mean=(spec['mean']-parity)/2,sd=spec['sd']/2,digits=0,
                   lower=math.ceil((spec['lower']-parity)/2) if spec.get('lower') is not None else None,
                   upper=math.floor((spec['upper']-parity)/2) if spec.get('upper') is not None else None)
    return [2*x+parity for x in numeric_numbers(**options)]


def generate_batch(config, progress=lambda _:None, cancelled=lambda:False):
    config=deepcopy(config)
    validate_batch(config)
    rng=random.Random(config['seed'])
    names=list(dict.fromkeys(s['name'].strip() for s in config['indicators']))
    columns=BASE_COLUMNS+names+END_COLUMNS
    rows,checks=[],[]
    for g in config['groups']:
        n=g['n'];group=g['name']
        def categories(field,labels,weights):
            values=_categorical(n,labels,weights,rng)
            counts=Counter(values)
            for label,pct in zip(labels,weights):
                checks.append(dict(group=group,field=field,category=label,target_percent=pct,actual_count=counts[label],actual_percent=counts[label]/n*100))
            return values
        data={'分组':[group]*n,
              '性别':categories('性别',['男','女'],[g['male'],100-g['male']]),
              '年龄':_ranges(n,g['age'],0,rng),
              '病程':_ranges(n,g['course'],g['course_digits'],rng),
              '病情程度':categories('病情程度',['轻度','中度','重度'],g['severity']),
              '病变范围':categories('病变范围',[r['label'] for r in g['extent']],[r['percent'] for r in g['extent']]),
              '总有效率':categories('总有效率',['有效','无效'],[g['effective'],100-g['effective']]),
              '复发率':categories('复发率',['复发','未复发'],[g['recurrence'],100-g['recurrence']])}
        for field,key in [('年龄','age'),('病程','course')]:
            for r,count in zip(g[key],allocation(n,[r['percent'] for r in g[key]])):
                actual=sum(r['lower']<=v<=r['upper'] for v in data[field])
                checks.append(dict(group=group,field=field,category=f"{r['lower']:g}～{r['upper']:g}",target_percent=r['percent'],actual_count=actual,actual_percent=actual/n*100))
        for spec in (s for s in config['indicators'] if s['group']==group):
            if cancelled():
                raise InterruptedError('已取消生成，未保存新的结果。')
            progress(f"{group} · {spec['name']}")
            try:
                values=_indicator(spec,n,rng)
            except ValueError as exc:
                raise ValueError(f"{group} / {spec['name']}：{exc}") from exc
            if cancelled():
                raise InterruptedError('已取消生成，未保存新的结果。')
            data[spec['name'].strip()]=values
            mean,sd=statistics(values)
            checks.append(dict(group=group,field=spec['name'],n=n,target_mean=spec['mean'],actual_mean=mean,mean_error=mean-spec['mean'],target_sd=spec['sd'],actual_sd=sd,sd_error=sd-spec['sd'],minimum=min(values),maximum=max(values)))
        start=len(rows)+1
        rows.extend([[start+i]+[data[c][i] for c in columns[1:]] for i in range(n)])
    return dict(columns=columns,rows=rows,checks=checks,config=config)


def export_batch(result,path):
    """Write atomically: original files survive failed/cancelled saves."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    path=Path(path)
    book=Workbook();sheet=book.active;sheet.title='模拟病例数据'
    sheet.append(result['columns'])
    for row in result['rows']:
        sheet.append(row)
    audit=book.create_sheet('统计核对')
    fields=[('group','分组'),('field','字段'),('category','类别或区间'),('n','例数'),('target_mean','目标均数'),('actual_mean','实际均数'),('mean_error','均数偏差'),('target_sd','目标标准差'),('actual_sd','实际标准差'),('sd_error','标准差偏差'),('minimum','最小值'),('maximum','最大值'),('target_percent','目标比例%'),('actual_count','实际人数'),('actual_percent','实际比例%')]
    audit.append([v for k,v in fields])
    for check in result['checks']:
        audit.append([check.get(k) for k,v in fields])
    settings=book.create_sheet('生成配置');settings.append(['设置','值'])
    settings.append(['数据性质','模拟数据，非原始病例；各指标独立生成，不还原配对或检验结果。'])
    settings.append(['比例处理','最大余数法分配整数人数后随机打乱；复发率以该组全部病例为分母。'])
    settings.append(['病程单位',result['config'].get('course_unit','月')])
    for key,value in result['config'].items():
        # One indicator per row avoids Excel's 32,767 character cell limit.
        if key in ('indicators','groups'):
            for i,item in enumerate(value,1):
                settings.append([f'{key}[{i}]',json.dumps(item,ensure_ascii=False,allow_nan=False)])
        else:
            settings.append([key,json.dumps(value,ensure_ascii=False,allow_nan=False)])
    for ws in book:
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.font=Font(color='FFFFFF',bold=True);cell.fill=PatternFill('solid',fgColor='0D7668')
        for i in range(1,ws.max_column+1):
            ws.column_dimensions[get_column_letter(i)].width=20 if ws is not settings else (28 if i==1 else 100)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value,str):
                    cell.data_type='s'  # user-entered labels are text, never formulas
    fd,tmp=tempfile.mkstemp(suffix='.xlsx',dir=path.parent);os.close(fd)
    try:
        book.save(tmp);os.replace(tmp,path)
    finally:
        book.close()
        if os.path.exists(tmp):os.unlink(tmp)
    return path
