"""Compare current offscreen Qt with V3 on the repository corpus; never use desktop input."""
from pathlib import Path
import hashlib,json,os,sys,tempfile,traceback
from copy import deepcopy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('MPLBACKEND','Agg')
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'desktop_app'),str(ROOT/'vue_app/python')]
from clinical_studio.app import create_application
from clinical_studio.word_batch import WordBatchTool
from clinical_studio.word_batch_engine import output_columns,validate_batch,generate_batch,read_word
from clinical_studio.word_formats import ensure_docx
from PySide6.QtWidgets import QMessageBox
from word_workflow import scan,apply,compose
APP=create_application([])
QMessageBox.warning=lambda *a,**k:QMessageBox.StandardButton.Ok
QMessageBox.information=lambda *a,**k:QMessageBox.StandardButton.Ok
QMessageBox.critical=lambda *a,**k:QMessageBox.StandardButton.Ok

def fingerprint(c):
    return dict(groups=[{k:g.get(k) for k in ('name','n','male','age','course','severity','effective','recurrence','extent_mode','recurrence_scope','blank_fields')} for g in c['groups']],
                columns=output_columns(c),include_basics=c.get('include_basics',True),
                fields=sorted([{k:f.get(k) for k in ('table','name','group','kind','mean','sd','digits','lower','upper','labels','weights','counts','confirmed','from_field','positive_labels')} for key in ('indicators','categoricals','typed_fields') for f in c.get(key,[])],key=lambda f:(str(f['table']),f['name'],f['group'])))
def validity(c):
    try:validate_batch(c);return ''
    except Exception as e:return str(e)

out=ROOT/'vue_app/.v3-data/audit-qt-corpus';out.mkdir(parents=True,exist_ok=True)
records=[]
with tempfile.TemporaryDirectory(prefix='v3-qt-corpus-') as tmp:
    os.environ['CLINICAL_STUDIO_TODO_PATH']=tmp+'/todos.json'
    for path in sorted((ROOT/'word').rglob('*')):
        if path.suffix.lower() not in ('.doc','.docx'):continue
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        print('Audit',path.name,flush=True)
        try:
            # ensure_docx uses only the available headless LibreOffice converter here.
            normalized=ensure_docx(path)
            for mode in ('defaults','source-options'):
                entry=dict(file=str(path.relative_to(ROOT/'word')),mode=mode,original_sha256=before)
                t=WordBatchTool()
                try:
                    enabled=mode=='source-options'
                    t.use_word_sizes.setChecked(enabled);t.use_word_rates.setChecked(enabled);t.use_word_prose.setChecked(enabled)
                    if not t.import_word(normalized):raise ValueError(t.message.text())
                    t.match_timer.stop()
                    candidates=[e.text() for e in t.group_inputs if e.text().strip()]
                    if candidates and not t.ungrouped_option.isChecked():
                        found=read_word(normalized,candidates,parse_indicators=False)
                        matched=[g for g in candidates if found.group_matches.get(g) or found.text_group_matches.get(g)]
                        if matched and matched!=candidates:
                            entry['manually_selected_groups']=matched;t.show_group_selection(matched)
                    t.confirm_groups();t.match_timer.stop()
                    if not t.groups_confirmed:
                        s=scan(Path(tmp),normalized)
                        try:apply(Path(tmp),dict(session=s['session'],groups=candidates,options=dict(prose=enabled)))
                        except ValueError as exc:entry.update(expected_block=True,qt_message=t.message.text(),vue_message=str(exc))
                        else:entry['audit_error']='Qt blocked group confirmation but Vue accepted'
                        records.append(entry);(out/'comparison.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,default=str));continue
                    qt=t.get_config(validate=False)
                    s=scan(Path(tmp),normalized)
                    r=apply(Path(tmp),dict(session=s['session'],draft=s['draft'],groups=[g['name'] for g in qt['groups']],options=dict(sizes=enabled,rates=enabled,prose=enabled),ungrouped=t.ungrouped,n=qt['groups'][0]['n']))
                    p=dict(config=r['config'],prose_document=r['prose_document'])
                    v3=compose(p,False)
                    try:qt_strict=t.get_config(validate=True);qt_error=''
                    except ValueError as exc:qt_error=str(exc)
                    try:vue_strict=compose(p,True);vue_error=''
                    except ValueError as exc:vue_error=str(exc)
                    entry['validation_agrees']=bool(qt_error)==bool(vue_error)
                    qf,vf=fingerprint(qt),fingerprint(v3)
                    entry.update(groups=[g['name'] for g in qt['groups']],qt_validation=qt_error,vue_validation=vue_error,differences={k:dict(qt=qf[k],vue=vf[k]) for k in qf if qf[k]!=vf[k]})
                    if not qt_error and not vue_error:
                        import time
                        deadline=time.monotonic()+20
                        cancel=lambda:time.monotonic()>deadline
                        a,b=generate_batch(qt_strict,cancelled=cancel),generate_batch(vue_strict,cancelled=cancel)
                        entry['same_generated_output']=a['columns']==b['columns'] and a['rows']==b['rows']
                        entry['generated_rows']=len(b['rows'])
                except Exception as e:entry['audit_error']=str(e)
                finally:t.match_timer.stop();t.close();t.deleteLater();APP.processEvents()
                records.append(entry)
                (out/'comparison.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,default=str))
        except Exception as e:records.append(dict(file=str(path.relative_to(ROOT/'word')),audit_error=str(e)))
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before,'Original changed!'
(out/'comparison.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,default=str))
print(json.dumps(dict(cases=len(records),differences=sum(bool(r.get('differences')) for r in records),errors=sum(bool(r.get('audit_error')) for r in records)),ensure_ascii=False),flush=True)

if any(r.get('differences') or r.get('audit_error') or r.get('validation_agrees') is False or r.get('same_generated_output') is False for r in records):raise SystemExit(1)
