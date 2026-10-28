"""Inline Word workflow integration. Generation always reads the live edited table."""
from copy import deepcopy
import re
from .prose_table_engine import (SCHEMA,normalized,parse_document,read_docx_text,
    to_simulation_config,canonical,PAIR,QUANTILE,RANGE)
from .prose_table_ui import ProseTableEditor
from .widgets import scroll


def metric_key(name):
    name=normalized(name)[0]
    name=re.sub(r'\((?:岁|月|分|kg/m2|mmHg)\)$','',name)
    return canonical(name)


def matching_document(path,names):
    text=read_docx_text(path)
    # Keep source paragraphs with group data, excluding methods/results elsewhere in Word.
    # Every selected paragraph is retained in full; unresolved content is shown for review.
    paragraphs=[]
    for paragraph in text.splitlines():
        clean=normalized(paragraph)[0]
        if any(g in clean for g in names) and (PAIR.search(clean) or QUANTILE.search(clean) or RANGE.search(clean) or re.search(r'(?:男|女)(?:性)?\d+例',clean) or re.search(r'(?:'+ '|'.join(re.escape(n) for n in names)+r')(?:共|纳入|为)?\d+例',clean)):
            paragraphs.append(paragraph)
    if not paragraphs:return None
    document=parse_document('\n'.join(paragraphs),names)
    if not document['studies'] or not document['studies'][0]['variables']:return None
    return document


class ProseTableWorkflow:
    def setup_prose_table(self):
        self.prose_table_editor=ProseTableEditor(embedded=True)
        self.prose_table_editor.precision_mode=lambda:self.decimal_mode.currentData()
        self.prose_table_tab=self.pages.insertTab(self.PROSE_PAGE,scroll(self.prose_table_editor),'3 · 文字匹配')
        self.prose_table_editor.status.setPlainText('导入 Word 并确认组别后，匹配到的文字会在此转成可编辑竖表；也可直接粘贴文字识别。')
        self.inline_prose_active=False;self.matched_prose_document=None

    def reset_prose_table(self):
        self.inline_prose_active=False;self.matched_prose_document=None
        editor=self.prose_table_editor;editor.document=None;editor.source.clear();editor.selector.clear();editor.render();editor.evidence.clear()
        editor.status.setPlainText('当前尚未匹配正文。导入 Word 并确认组别后，匹配的文字将在此展示。')

    def match_prose_table(self,names,imported):
        self.matched_prose_document=matching_document(self.pending_source,names) if names and self.use_word_prose.isChecked() else None
        from .word_precision import prose_precision
        prose_precision(self.matched_prose_document,self.decimal_mode.currentData())
        if self.matched_prose_document:
            s=self.matched_prose_document['studies'][0]
            for g in s['groups']:
                if g['name'] not in normalized(s['source_text'])[0]:continue
                imported.text_group_matches[g['name']]=max(1,imported.text_group_matches.get(g['name'],0))

    def activate_prose_table(self,document,imported=None):
        if not document:self.reset_prose_table();return
        editor=self.prose_table_editor;editor.document=None
        editor.groups_override=[g['name'] for g in document['studies'][0]['groups']]
        editor.source.setPlainText(document['source_text']);editor.document=deepcopy(document);editor.stale=False
        if imported:
            s=editor.study() or editor.document['studies'][0]
            existing=imported.indicators+imported.typed_fields
            for v in s['variables']:
                for group,cell in v['cells'].items():
                    old=next((f for f in existing if metric_key(f['name'])==metric_key(v['name']) and f['group']==group),None)
                    if old:
                        same=v['kind']=='mean_sd' and old.get('mean')==cell.get('mean') and old.get('sd')==cell.get('sd')
                        if not same:
                            cell.setdefault('issues',[]).append('正文与已有Word表格参数冲突，请核对后确认当前值。')
                            cell['table_conflict']=deepcopy(old)
            for g in s['groups']:
                if imported.group_sizes.get(g['name']) and g['n'] is not None and imported.group_sizes[g['name']]!=g['n']:
                    g['issues'].append('正文与Word表格例数冲突，请编辑竖表例数确认。')
        editor.refresh_selector();self.inline_prose_active=True
        self.pages.setTabVisible(self.prose_table_tab,True)
        self.pages.setCurrentIndex(self.prose_table_tab)
        self.column_hint.setText('正文已转成可编辑竖表；生成时自动合并Word表格和竖表字段，例数以竖表为准。')

    def merge_prose_table(self,config,validate=True):
        # Keep the editable table state separate from the merged generation config.
        # Saving/reloading must never feed prose fields back into the table editor.
        table_state=deepcopy(config.get('table_match') or {key:config.get(key,[]) for key in ('indicators','categoricals','typed_fields')})
        config['table_match']=table_state
        for key in ('indicators','categoricals','typed_fields'):config[key]=deepcopy(table_state.get(key,[]))
        editor=self.prose_table_editor
        if not self.inline_prose_active and not editor.document:return config
        study=editor.study()
        if study:config['prose_table']=deepcopy(study)
        if editor.document:config['prose_document']=deepcopy(editor.document)
        try:
            editor.check_export()
            if set(g['name'] for g in study['groups'])!=set(g['name'] for g in config['groups']):
                raise ValueError('正文竖表的组别与当前组别不一致，请重新确认组别。')
            self.check_table_prose_conflicts(config,study)
            prose=to_simulation_config(study)
        except ValueError as exc:
            if validate:raise
            # A draft/invalid prose edit must not blank the independent table review.
            config['prose_preview_issues']=[str(exc)]
            config['prose_pending_rows']=[]
            for variable in (study or {}).get('variables',[]):
                for group in (study or {}).get('groups',[]):
                    cell=variable['cells'].get(group['name'],{})
                    config['prose_pending_rows'].append(dict(column=variable['name'],group=group['name'],source='Word正文（待核对）',rule='文字已修改或参数待补全；表格匹配保持不变',original='；'.join(e['raw'] for e in cell.get('evidence',[]))))
            return config
        keys={(metric_key(f['name']),f['group']) for f in prose['typed_fields']}
        for key in ('indicators','categoricals','typed_fields'):
            config[key]=[f for f in config.get(key,[]) if (metric_key(f['name']),f['group']) not in keys]
        config['typed_fields']+=deepcopy(prose['typed_fields'])
        sizes={g['name']:g['n'] for g in study['groups']}
        for g in config['groups']:g['n']=sizes[g['name']]
        config['prose_table']=deepcopy(study);config['prose_document']=deepcopy(editor.document)
        return config

    def check_table_prose_conflicts(self,config,study):
        message='正文与已有Word表格参数冲突，请核对后确认当前值。'
        def signature(field,n):
            kind=field.get('kind','category' if 'labels' in field else 'mean_sd')
            if kind=='mean_sd':return (kind,field.get('mean'),field.get('sd'))
            if kind=='quantile':return (kind,field.get('q1'),field.get('median'),field.get('q3'))
            if kind in ('category','gender','yesno','binary','binary01'):
                counts=field.get('counts')
                values=counts.items() if isinstance(counts,dict) else zip(field.get('labels',[]),counts) if counts else [(k,w*n/100) for k,w in zip(field.get('labels',[]),field.get('weights',[])) if w is not None]
                return ('category',tuple(sorted((str(k),round(v,6)) for k,v in values)))
            return (kind,)
        fields=config.get('indicators',[])+config.get('categoricals',[])+config.get('typed_fields',[])
        groups={g['name']:g for g in study['groups']}
        for variable in study['variables']:
            for group,cell in variable['cells'].items():
                old=next((f for f in fields if metric_key(f['name'])==metric_key(variable['name']) and f['group']==group),None)
                if old is None:continue
                n=groups[group]['n'] or 1
                current=dict(cell,kind=variable['kind'],labels=variable['labels'])
                same=signature(old,n)==signature(current,n)
                reviewed=cell.get('reviewed') and signature(old,n)==signature(cell.get('table_conflict',{}),n)
                if same or reviewed:
                    cell['issues']=[i for i in cell.get('issues',[]) if i!=message]
                else:
                    if message not in cell.setdefault('issues',[]):cell['issues'].append(message)
                    cell['table_conflict']=deepcopy(old);cell['reviewed']=False
        editor=self.prose_table_editor;editor.report()

    def open_prose_table(self):
        self.pages.setTabVisible(self.prose_table_tab,True)
        self.pages.setCurrentIndex(self.prose_table_tab)
        # Opening this page alone does not activate an empty prose source.
