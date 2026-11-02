"""Run the actual app-owned WKWebView UI audit without desktop input permissions."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import json,os,subprocess,sys
host=Path(sys.argv[1]).resolve();folder=Path(sys.argv[2]).resolve();folder.mkdir(parents=True,exist_ok=True)
w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
node=ET.Element(w+'document');body=ET.SubElement(node,w+'body');table=ET.SubElement(body,w+'tbl')
for values in [['项目','对照组(n=10)','中药组(n=12)'],['评分','50±5','60±5']]:
 row=ET.SubElement(table,w+'tr')
 for text in values:ET.SubElement(ET.SubElement(ET.SubElement(ET.SubElement(row,w+'tc'),w+'p'),w+'r'),w+'t').text=text
with ZipFile(folder/'fixture.docx','w') as archive:archive.writestr('word/document.xml',ET.tostring(node))
(folder/'fixture.csv').write_text('编号,分组,年龄\n'+'\n'.join(f'P{i},{i%2},{30+i}' for i in range(40)),encoding='utf-8-sig')
report=folder/'native-ui-report.json';report.unlink(missing_ok=True)
with (folder/'app.log').open('w') as log:
 result=subprocess.run([str(host),'--ui-review',str(folder)],stdout=log,stderr=log,env={**os.environ,'PYTHONUTF8':'1','RESEARCH_V3_DEBUG':'0'},timeout=500)
if not report.exists():raise SystemExit('App did not produce an audit report: '+(folder/'app.log').read_text()[-2000:])
value=json.loads(report.read_text());print(json.dumps(value,ensure_ascii=False,indent=2))
if result.returncode!=0 or not value.get('ok'):raise SystemExit(1)
print('Actual app-native UI audit passed; screenshots: '+str(folder))
