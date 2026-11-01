"""Run real frozen-engine jobs without opening app windows or using desktop input."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if len(sys.argv) != 2:
    raise SystemExit('Usage: python scripts/test-packaged-engine.py /path/to/research-python')
binary = Path(sys.argv[1]).resolve()
if not binary.is_file():
    raise SystemExit('Embedded engine does not exist: ' + str(binary))

with tempfile.TemporaryDirectory(prefix='dbq-v3-packaged-') as tmp:
    env = {**os.environ, 'RESEARCH_V3_PROFILE': tmp, 'MPLCONFIGDIR': tmp + '/mpl', 'MPLBACKEND': 'Agg'}

    def call(method, params=None):
        process = subprocess.run([str(binary)], input=json.dumps({'method': method, 'params': params or {}}),
                                 text=True, capture_output=True, env=env, timeout=45)
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
    print('Frozen Word background worker: 140 rows and Excel export OK', flush=True)

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
