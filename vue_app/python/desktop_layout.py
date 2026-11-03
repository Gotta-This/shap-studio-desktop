"""Versioned desktop layout snapshots and non-overlapping merge restoration."""
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import hashlib,json,math,os,platform,re,sys,tempfile,threading,time,uuid
import desktop_layout_diagnostics as diagnostic

UNSUPPORTED='非windows电脑无法使用'
KEEP_RECENT=144
_LOCK=threading.RLock()

def _native():
    if sys.platform!='win32':raise ValueError(UNSUPPORTED)
    from desktop_layout_win32 import DesktopView
    return DesktopView()

def _folder(profile):
    path=Path(profile)/'desktop-layouts';path.mkdir(parents=True,exist_ok=True);return path

def _path(profile,identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('备份标识无效。')
    return _folder(profile)/(identifier+'.json')

@contextmanager
def _file_lock(profile):
    path=Path(profile)/'desktop-layout-operation.lock';path.parent.mkdir(parents=True,exist_ok=True)
    deadline=time.monotonic()+15
    while True:
        try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);break
        except FileExistsError:
            try:
                if time.time()-path.stat().st_mtime>300:path.unlink(missing_ok=True);continue
            except FileNotFoundError:continue
            if time.monotonic()>deadline:raise ValueError('另一个桌面备份操作正在进行，请稍后重试。')
            time.sleep(.05)
    try:os.close(fd);yield
    finally:path.unlink(missing_ok=True)

def _write(path,value):
    fd,tmp=tempfile.mkstemp(prefix='.layout-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as stream:
            json.dump(value,stream,ensure_ascii=False,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

def _read(path):
    if not path.exists():raise ValueError('此备份已不存在，请刷新历史记录。')
    if path.stat().st_size>16*1024*1024:raise ValueError('备份文件过大，无法读取。')
    data=json.loads(path.read_text(encoding='utf8'))
    if data.get('version')!=1 or data.get('id')!=path.stem or type(data.get('protected')) is not bool:raise ValueError('备份文件格式无效。')
    if any(not isinstance(data.get(k),str) for k in ('label','created_at','reason','computer')) or not isinstance(data.get('display'),dict):raise ValueError('备份描述无效。')
    _icons(data['icons']);return data

def _icons(items):
    if not isinstance(items,list) or len(items)>10000:raise ValueError('图标列表无效。')
    keys=set()
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('key'),str) or not item['key'] or len(item['key'])>32768:raise ValueError('图标标识无效。')
        if not isinstance(item.get('name'),str) or any(type(item.get(k)) is not int or abs(item[k])>1000000 for k in ('x','y')):raise ValueError('图标坐标无效。')
        key=item['key'].casefold()
        if key in keys:raise ValueError('图标标识重复，已停止操作。')
        keys.add(key)
    return {item['key'].casefold():item for item in items}

def _summary(data):return {**{k:data[k] for k in ('id','label','created_at','protected','reason','computer','display')},'icon_count':len(data['icons'])}

def history(profile):
    good=[];bad=0
    for path in _folder(profile).glob('*.json'):
        try:good.append(_summary(_read(path)))
        except (OSError,ValueError,KeyError,TypeError):bad+=1
    good.sort(key=lambda x:(x['created_at'],x['id']),reverse=True)
    return good,bad

def _settings(profile):
    path=Path(profile)/'desktop-layout-settings.json'
    config=dict(enabled=True,interval_minutes=10,keep_recent=KEEP_RECENT,next_due_at=None,last_automatic_at=None,last_automatic_epoch=None,last_error='')
    if path.exists():
        saved=json.loads(path.read_text(encoding='utf8'))
        if not isinstance(saved,dict):raise ValueError('桌面备份设置文件无效。')
        config.update(saved)
    if type(config['enabled']) is not bool or type(config['interval_minutes']) is not int or not 1<=config['interval_minutes']<=1440 or type(config['keep_recent']) is not int or not 1<=config['keep_recent']<=500:raise ValueError('桌面备份设置无效。')
    return config

def _prune(profile,keep):
    recent,_=history(profile);removed=0
    for entry in [v for v in recent if not v['protected']][keep:]:
        _path(profile,entry['id']).unlink(missing_ok=True);removed+=1
    return removed

def settings(profile,p):
    if sys.platform!='win32':raise ValueError(UNSUPPORTED)
    with _LOCK,_file_lock(profile):
        config=_settings(profile)
        for key in ('enabled','interval_minutes','keep_recent'):
            if key not in p:raise ValueError('备份设置不完整。')
            config[key]=p[key]
        if type(config['enabled']) is not bool or type(config['interval_minutes']) is not int or not 1<=config['interval_minutes']<=1440 or type(config['keep_recent']) is not int or not 1<=config['keep_recent']<=500:raise ValueError('频率应为 1～1440 分钟，普通备份份数应为 1～500。')
        config['next_due_at']=(config['last_automatic_epoch'] or time.time())+config['interval_minutes']*60 if config['enabled'] else None
        _write(Path(profile)/'desktop-layout-settings.json',config)
        return dict(settings=config,removed=_prune(profile,config['keep_recent']))

def tick(profile,p=None):
    if sys.platform!='win32':return dict(supported=False,message=UNSUPPORTED)
    with _LOCK,_file_lock(profile):
        config=_settings(profile);now=time.time()
        def status(created=None):return dict(supported=True,created=created,enabled=config['enabled'],next_due_at=config['next_due_at'],last_error=config['last_error'])
        if not config['enabled'] or (config['next_due_at'] is not None and now<config['next_due_at']):return status()
        try:
            with _native() as view:created=_save(profile,view.capture(),'自动备份',False,'automatic')
            config.update(last_automatic_at=created['created_at'],last_automatic_epoch=now,next_due_at=now+config['interval_minutes']*60,last_error='')
            _write(Path(profile)/'desktop-layout-settings.json',config);return status(created['id'])
        except Exception as exc:
            config.update(last_error=str(exc),next_due_at=now+60)
            _write(Path(profile)/'desktop-layout-settings.json',config);return status()

def info(profile):
    if sys.platform!='win32':return dict(supported=False,message=UNSUPPORTED,backups=[],directory='',keep_recent=KEEP_RECENT)
    with _LOCK:
        backups,bad=history(profile)
        config=_settings(profile)
        return dict(supported=True,message='',backups=backups,directory=str(_folder(profile)),keep_recent=config['keep_recent'],settings=config,unreadable=bad)

def _save(profile,current,label,protected=False,reason='manual'):
    _icons(current['icons'])
    label=label.strip()
    if len(label)>80:raise ValueError('备份名称最多 80 个字。')
    value=dict(version=1,id=uuid.uuid4().hex,label=label or '桌面排列备份',created_at=datetime.now().astimezone().isoformat(timespec='microseconds'),protected=protected,reason=reason,computer=platform.node(),display=current['display'],icons=current['icons'])
    _write(_path(profile,value['id']),value)
    # Only unprotected history is pruned. Protected snapshots have no expiry.
    _prune(profile,_settings(profile)['keep_recent'])
    return _summary(value)

def backup(profile,p):
    if type(p.get('protected',False)) is not bool:raise ValueError('永久保留选项无效。')
    label=p.get('label','')
    if not isinstance(label,str):raise ValueError('备份名称无效。')
    with _LOCK,_file_lock(profile),_native() as view:return _save(profile,view.capture(),label,p.get('protected',False))

def protect(profile,p):
    if sys.platform!='win32':raise ValueError(UNSUPPORTED)
    if type(p.get('protected')) is not bool:raise ValueError('永久保留选项无效。')
    with _LOCK,_file_lock(profile):
        path=_path(profile,p.get('id'));value=_read(path);value['protected']=p['protected'];_write(path,value)
        return _summary(value)

def delete(profile,p):
    if sys.platform!='win32':raise ValueError(UNSUPPORTED)
    with _LOCK,_file_lock(profile):
        path=_path(profile,p.get('id'));value=_read(path)
        if value['protected']:raise ValueError('此备份已永久保留，请先取消保护后再删除。')
        path.unlink();return dict(deleted=True)

def fingerprint(current):return hashlib.sha256(json.dumps(current,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()

def plan(saved,current):
    previous=_icons(saved['icons']);present=_icons(current['icons']);display=current['display']
    if current.get('auto_arrange'):raise ValueError('请先在 Windows 桌面右键 → 查看中关闭“自动排列图标”，再恢复。')
    sx,sy=display['spacing']
    if any(type(v) is not int or not 1<=v<=10000 for v in (sx,sy)):raise ValueError('桌面网格间距无效。')
    areas=display['workareas']
    if not areas or len(areas)>64:raise ValueError('桌面可用区域无效。')
    def inside(x,y,whole=False):return any(a['left']<=x and a['top']<=y and x+(sx if whole else 0)<=(a['right'] if whole else a['right']-1) and y+(sy if whole else 0)<=(a['bottom'] if whole else a['bottom']-1) for a in areas)
    matched=[dict(present[key],x=previous[key]['x'],y=previous[key]['y']) for key in present if key in previous]
    if not matched:raise ValueError('当前桌面没有与此备份匹配的图标，未执行恢复。')
    if any(not inside(i['x'],i['y']) for i in matched):raise ValueError('当前屏幕无法容纳备份中的图标位置，请先恢复原来的分辨率、缩放或显示器排列。')
    new=sorted([v for k,v in present.items() if k not in previous],key=lambda i:(i['name'].casefold(),i['key']))
    occupied=[(i['x'],i['y']) for i in matched];placed=[]
    origin_x=min(i['x'] for i in matched)%sx;origin_y=min(i['y'] for i in matched)%sy
    candidates=[]
    for area in areas:
        left=origin_x+math.ceil((area['left']-origin_x)/sx)*sx;top=origin_y+math.ceil((area['top']-origin_y)/sy)*sy
        for x in range(left,area['right']-sx+1,sx):
            for y in range(top,area['bottom']-sy+1,sy):
                if len(candidates)>100000:raise ValueError('桌面网格数量异常。')
                candidates.append((x,y))
    edge=max(i['x'] for i in matched)+sx
    candidates=sorted(set(candidates),key=lambda v:(v[0]<edge,v[0],v[1]))
    cursor=iter(candidates)
    for item in new:
        for x,y in cursor:
            if inside(x,y,True) and all(abs(x-a)>=sx or abs(y-b)>=sy for a,b in occupied):
                placed.append(dict(item,x=x,y=y));occupied.append((x,y));break
        else:raise ValueError('当前桌面没有足够的空位置放置新增图标，未移动任何图标。请扩大可用桌面或整理图标后重试。')
    return dict(items=matched+placed,restored_count=len(matched),new_count=len(placed),missing_count=len(previous.keys()-present.keys()),fingerprint=fingerprint(current),display_changed=saved['display']!=display)

def preview(profile,p):
    with _LOCK,_file_lock(profile):
        operation=uuid.uuid4().hex
        diagnostic.record(profile,'preview.begin',operation,environment=diagnostic.environment())
        try:
            with _native() as view:
                view.trace=lambda event,**fields:diagnostic.record(profile,event,operation,**fields)
                saved=_read(_path(profile,p.get('id')));current=view.capture();result=plan(saved,current)
                actual=_icons(current['icons'])
                changed=sum((actual[i['key'].casefold()]['x'],actual[i['key'].casefold()]['y'])!=(i['x'],i['y']) for i in result['items'])
                diagnostic.record(profile,'preview.complete',operation,backup_id=saved['id'],backup_reason=saved['reason'],backup_created_at=saved['created_at'],source_count=len(saved['icons']),current_count=len(current['icons']),restored_count=result['restored_count'],new_count=result['new_count'],missing_count=result['missing_count'],needs_move_count=changed,display=current['display'],source_display=saved['display'],auto_arrange=current.get('auto_arrange'))
                return {**{k:v for k,v in result.items() if k!='items'},'needs_move_count':changed}
        except Exception as error:
            diagnostic.record(profile,'preview.error',operation,error=diagnostic.failure(error));raise

def diagnostics(profile,p=None):
    with _LOCK,_file_lock(profile):return diagnostic.export(profile)

def restore(profile,p):
    with _LOCK,_file_lock(profile):
        operation=uuid.uuid4().hex
        diagnostic.record(profile,'restore.begin',operation,environment=diagnostic.environment())
        try:
            with _native() as view:
                view.trace=lambda event,**fields:diagnostic.record(profile,event,operation,**fields)
                saved=_read(_path(profile,p.get('id')));current=view.capture();result=plan(saved,current)
                if p.get('fingerprint')!=result['fingerprint']:raise ValueError('桌面已发生变化，请重新预览并确认恢复。')
                before=_icons(current['icons'])
                changed=sum((before[i['key'].casefold()]['x'],before[i['key'].casefold()]['y'])!=(i['x'],i['y']) for i in result['items'])
                positions=[dict(icon=diagnostic.token(i['key']),before=[before[i['key'].casefold()]['x'],before[i['key'].casefold()]['y']],target=[i['x'],i['y']]) for i in result['items']]
                diagnostic.record(profile,'restore.plan',operation,backup_id=saved['id'],backup_reason=saved['reason'],backup_created_at=saved['created_at'],source_count=len(saved['icons']),current_count=len(current['icons']),restored_count=result['restored_count'],new_count=result['new_count'],missing_count=result['missing_count'],needs_move_count=changed,positions=positions,display=current['display'],source_display=saved['display'],auto_arrange=current.get('auto_arrange'))
                safety=_save(profile,current,'恢复前自动备份',False,'before_restore')
                diagnostic.record(profile,'restore.safety_saved',operation,backup_id=safety['id'])
                view.position(result['items'])
                mismatches=len(result['items'])
                for attempt in range(8):
                    actual=_icons(view.capture()['icons']);wrong=[];moved=0
                    for i in result['items']:
                        key=i['key'].casefold();position=[actual[key]['x'],actual[key]['y']] if key in actual else None
                        if position!=[i['x'],i['y']]:wrong.append(dict(icon=diagnostic.token(i['key']),target=[i['x'],i['y']],actual=position))
                        if position is not None and position!=[before[key]['x'],before[key]['y']]:moved+=1
                    mismatches=len(wrong)
                    diagnostic.record(profile,'restore.verify',operation,attempt=attempt+1,unmatched_positions=mismatches,moved_count=moved,sample=wrong[:12])
                    if not mismatches:break
                    time.sleep(.1)
                logged=diagnostic.record(profile,'restore.complete',operation,unmatched_positions=mismatches,needs_move_count=changed,moved_count=moved)
                return {**{k:v for k,v in result.items() if k!='items'},'safety_backup':safety,'unmatched_positions':mismatches,'needs_move_count':changed,'diagnostic_id':operation,'diagnostic_saved':logged}
        except Exception as error:
            diagnostic.record(profile,'restore.error',operation,error=diagnostic.failure(error));raise
