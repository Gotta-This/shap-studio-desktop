"""Bounded local diagnostics without desktop filenames or document contents."""
from datetime import datetime
from pathlib import Path
import hashlib,json,platform,sys

LOG_NAME='desktop-layout-diagnostics.jsonl'
MAX_BYTES=2*1024*1024

def token(key):return hashlib.sha256(key.casefold().encode('utf8')).hexdigest()[:16]

def environment():
    try:
        from releases import VERSION
    except ImportError:VERSION='unknown'
    value=dict(application_version=VERSION,system=platform.system(),release=platform.release(),build=platform.version(),machine=platform.machine(),python=platform.python_version())
    if sys.platform=='win32':
        try:
            import winreg
            info={}
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
                for name in ('ProductName','DisplayVersion','EditionID','CurrentBuildNumber','UBR'):
                    try:info[name]=winreg.QueryValueEx(key,name)[0]
                    except OSError:pass
            value['windows']=info
        except (ImportError,OSError):value['windows']={'unavailable':True}
    return value

def record(profile,event,operation,**fields):
    try:
        root=Path(profile);root.mkdir(parents=True,exist_ok=True);path=root/LOG_NAME
        if path.exists() and path.stat().st_size>=MAX_BYTES:
            oldest=root/(LOG_NAME+'.2');oldest.unlink(missing_ok=True)
            previous=root/(LOG_NAME+'.1')
            if previous.exists():previous.replace(oldest)
            path.replace(previous)
        row=dict(time=datetime.now().astimezone().isoformat(timespec='milliseconds'),operation=operation,event=event,**fields)
        with path.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
        return True
    except (OSError,ValueError,TypeError):return False

def failure(error):
    result=dict(type=type(error).__name__,errno=getattr(error,'errno',None),winerror=getattr(error,'winerror',None))
    # Custom validation/COM errors contain no user paths. OS exceptions can.
    if isinstance(error,ValueError) or str(error).startswith('Windows 桌面接口调用失败'):
        result['message']=str(error)
    return result

def export(profile):
    rows=[];unreadable=0
    for suffix in ('.2','.1',''):
        path=Path(profile)/(LOG_NAME+suffix)
        if not path.exists():continue
        with path.open(encoding='utf8',errors='replace') as stream:
            for line in stream:
                try:rows.append(json.loads(line))
                except (ValueError,TypeError):unreadable+=1
    report=dict(schema=1,environment=environment(),privacy='不包含桌面文件名、完整路径或文件内容；图标以匿名标识及坐标表示。',events=rows,unreadable_lines=unreadable)
    return dict(name='desktop-layout-diagnostics-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json',content=json.dumps(report,ensure_ascii=False,indent=2),event_count=len(rows))
