"""Run real frozen-engine jobs without opening app windows or using desktop input."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from xml.etree import ElementTree as ET
from zipfile import ZipFile

if len(sys.argv) != 2:
    raise SystemExit('Usage: python scripts/test-packaged-engine.py /path/to/research-python')
binary = Path(sys.argv[1]).resolve()
if not binary.is_file():
    raise SystemExit('Embedded engine does not exist: ' + str(binary))

with tempfile.TemporaryDirectory(prefix='dbq-v3-packaged-') as tmp:
    env = {**os.environ, 'RESEARCH_V3_PROFILE': tmp, 'MPLCONFIGDIR': tmp + '/mpl', 'MPLBACKEND': 'Agg', 'PYTHONUTF8': '1'}

    def call(method, params=None):
        process = subprocess.run([str(binary)], input=json.dumps({'method': method, 'params': params or {}}),
                                 text=True, encoding="utf-8", capture_output=True, env=env, timeout=45)
        response = json.loads(process.stdout)
        assert response['ok'], response
        return response['result']

    def job(kind, params):
        jid = call('tool.job.start', {'kind': kind, 'params': params})['id']
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = call('tool.job.status', {'id': jid})
            if state['status'] != 'running':
                break
            time.sleep(.2)
        if state['status'] != 'done':
            log = Path(tmp) / 'jobs' / jid / 'worker.log'
            raise AssertionError(str(state) + '\n' + log.read_text())
        return state['result']

    word = call('tool.word.defaults')
    word['indicators'] = [dict(name='评分', group=g['name'], mean=50, sd=5, digits=0,
                               parity='any', lower=None, upper=None) for g in word['groups']]
    result = job('word', {'config': word})
    assert result['total'] == 140 and result['base64']
    saved=call('exports.save',dict(path=str(Path(tmp)/'导出.xlsx'),content=result['base64'],base64=True))
    with ZipFile(saved['path']) as archive:assert 'xl/workbook.xml' in archive.namelist()
    print('Frozen Word background worker: 140 rows and native Excel save OK', flush=True)

    numeric = job('numeric', dict(n=20,mean=50,sd=5,digits=1,seed=42))
    assert len(numeric['values'])==20 and numeric['params']['digits']==1
    category = job('category', dict(rows=[dict(value=1,count=3),dict(value=0,count=7)],seed=42))
    assert category['values'].count(1)==3 and category['values'].count(0)==7
    print('Frozen numeric and category workers with result snapshots: OK',flush=True)

    # A legacy-named OOXML exercises conversion lifetime without launching Word.
    w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    root=ET.Element(w+'document');body=ET.SubElement(root,w+'body');table=ET.SubElement(body,w+'tbl')
    for values in [['项目','对照组(n=10)','中药组(n=12)'],['评分','50±5','60±5']]:
        row=ET.SubElement(table,w+'tr')
        for value in values:ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(row,w+'tc'),w+'p'),w+'r'),w+'t').text=value
    source=Path(tmp)/'临时旧版.doc'
    with ZipFile(source,'w') as archive:archive.writestr('word/document.xml',ET.tostring(root))
    scanned=call('tool.word.scan',dict(paths=[str(source)]))
    applied=call('tool.word.apply',dict(session=scanned['session'],groups=scanned['scan']['candidates']))
    assert applied['config']['source']==source.name
    print('Frozen legacy Word import remains usable after bridge exit: OK',flush=True)

    config = call('tool.shap.defaults')
    config['data']['n_samples'] = 40
    result = job('shap', {'config': config, 'data_only': True})
    assert result['total'] == 40
    assert call('tool.shap.table', {'id': result['id'], 'kind': 'data'})['total'] == 40
    print('Frozen SHAP data worker and persisted result table: OK', flush=True)

    config['data']['n_samples'] = 80
    config['plots']['dpi'] = 72
    config['explanation']['background_max_samples'] = 10
    for name, style in config['plots']['plots'].items():
        style['enabled'] = name == 'bar'
    result = job('shap', {'config': config})
    assert result['has_model'] and result['images']
    config['plots']['common']['font_size'] = 13
    redraw = job('shap', {'config': config, 'previous': result['id']})
    assert redraw['images'] and redraw['metrics']['auc'] == result['metrics']['auc']
    print('Frozen full SHAP analysis, real image and model reuse: OK', flush=True)

    import runpy
    smoke=runpy.run_path(str(Path(__file__).with_name('prediction-smoke.py')))
    smoke['verify_prediction'](call,job,tmp)
