"""Read the fixed general-information sentence patterns; numbers always come from DOCX."""
import re
import unicodedata

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NUMBER=r'\d+(?:\.\d+)?'
PAIR=rf'(?P<mean>{NUMBER})\s*±\s*(?P<sd>{NUMBER})'


def compact(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',value))


def body_paragraphs(body):
    """Exclude table paragraphs so summary tables cannot masquerade as prose."""
    result=[]
    def walk(node):
        for child in node:
            if child.tag==W+'tbl':continue
            if child.tag==W+'p':
                text=''.join(t.text or '' for t in child.iter(W+'t')).strip()
                if text:result.append(text)
            else:walk(child)
    walk(body)
    return result


def read_general_prose(body,groups):
    text='\n'.join(body_paragraphs(body));normalized=compact(text)
    if not groups:return {},{}
    lookup={compact(g):g for g in groups}
    pattern=re.compile('(?P<group>'+'|'.join(re.escape(g) for g in sorted(lookup,key=len,reverse=True))+r')(?:共|纳入|为)?(?P<n>\d+)例')
    matches=list(pattern.finditer(normalized));found={};counts={g:0 for g in groups}
    for i,marker in enumerate(matches):
        segment=normalized[marker.start():matches[i+1].start() if i+1<len(matches) else len(normalized)]
        # The concluding comparison and the following sections are not group data.
        segment=re.split(r'两组上述|两组一般资料|两组比较|(?:\d+[.、])?(?:研究方法|治疗方法|观察指标|统计学方法)',segment,maxsplit=1)[0]
        group=lookup[marker['group']];n=int(marker['n']);data=dict(n=n,raw=segment,issues=[],indicators=[],categoricals=[])
        if not 2<=n<=5000:data['issues'].append('正文组例数须在2～5000之间')
        male=re.search(r'男(?:性)?(\d+)例',segment);female=re.search(r'女(?:性)?(\d+)例',segment)
        if male or female:
            if male and female:
                data['male_count']=int(male[1]);data['female_count']=int(female[1])
                if data['male_count']+data['female_count']!=n:data['issues'].append('男女例数之和与本组例数不一致')
            else:data['issues'].append('性别人数未完整识别')
        age=re.search(r'年龄(?P<lower>'+NUMBER+r')[~～—–至-](?P<upper>'+NUMBER+r')岁?',segment)
        if age:
            data['age']=[dict(lower=float(age['lower']),upper=float(age['upper']),percent=100.)]
            average=re.match(r'[,，;；]?(?:平均|均龄|平均年龄)[(（]?'+PAIR+r'[)）]?岁?',segment[age.end():])
            if average:data['age_stats']=dict(mean=float(average['mean']),sd=float(average['sd']),raw=age[0]+average[0])
        elif re.search(r'年龄',segment):data['issues'].append('年龄范围或句式未完整识别')
        fields=[('BMI',r'BMI'),('APACHEⅡ评分',r'APACHEII评分'),('SOFA评分',r'SOFA评分'),('入组前机械通气时间（h）',r'入组前机械通气时间')]
        for name,label in fields:
            match=re.search(label+r'[:：]?[(（]?'+PAIR+r'[)）]?',segment,re.I)
            if match:
                data['indicators'].append(dict(table=0,name=name,group=group,mean=float(match['mean']),sd=float(match['sd']),digits=2,lower=0.,upper=None,parity='any',raw='正文：'+match[0]))
            elif re.search(label,segment,re.I):data['issues'].append(name+'的均数±标准差未完整识别')
        for name,label,choices in [('呼吸衰竭类型',r'呼吸衰竭类型',r'(III型|II型|I型|[123]型)'),('机械通气方式',r'机械通气方式',r'(经口气管插管|经鼻气管插管|气管切开)')]:
            start=re.search(label,segment)
            if not start:continue
            section=re.split('[;；。]',segment[start.end():],maxsplit=1)[0]
            items=re.findall(choices+r'(\d+)例',section)
            if not items or len({label for label,_ in items})!=len(items):
                data['issues'].append(name+'的类别人数未完整识别');continue
            total=sum(int(number) for _,number in items)
            if total!=n:data['issues'].append(name+'人数之和与本组例数不一致')
            data['categoricals'].append(dict(name=name,group=group,labels=[label for label,_ in items],weights=[round(int(number)/n*100,12) if n else 0 for _,number in items],counts=[int(number) for _,number in items],raw='正文：'+start[0]+section))
        if not any(key in data for key in ('male_count','age')) and not data['indicators'] and not data['categoricals']:continue
        counts[group]+=1
        if group in found:
            found[group]['issues'].append('正文出现多段本组一般资料，请核对原文，避免使用错误段落')
        else:found[group]=data
    return found,counts
