"""Validated, stopped-process-only replacement of a 360 data directory."""
import hashlib,json,os,re,shutil,stat,tempfile,uuid,zipfile
from pathlib import Path,PureWindowsPath
import desktop_layout_assistant as assistant
import desktop_layout_assistant_control as control

class RecoveryRequired(ValueError):pass


def stopped():
    if assistant.sys.platform!='win32':raise ValueError('非windows电脑无法使用')
    state=assistant.probe()
    if not state['checked']:raise ValueError('无法检测 360 运行状态，请重新检测。')
    if state['running']:raise ValueError('请先从 360 菜单退出桌面助手，再恢复 360 数据；不会强制结束进程。')


def _root():
    root=assistant.data_root()
    if root is None or not root.parent.is_dir():raise ValueError('未找到当前用户的 360 数据路径。')
    if os.path.lexists(root):
        if root.is_symlink() or getattr(root.lstat(),'st_file_attributes',0)&0x400 or not root.is_dir():
            raise ValueError('360 数据目录为链接、重解析点或普通文件，无法恢复。')
    return root


def _digest(pairs):return hashlib.sha256(json.dumps(sorted(pairs),ensure_ascii=False).encode()).hexdigest()


def _current(root):
    if not root.exists():return 'absent'
    inventory=assistant._inventory(root);pairs=[]
    for name,size,_ in inventory:
        with (root/name).open('rb') as stream:content=stream.read(size+1)
        if len(content)!=size:raise ValueError('当前 360 配置发生变化，请重新预览。')
        pairs.append((name,hashlib.sha256(content).hexdigest()))
    if inventory!=assistant._inventory(root):raise ValueError('当前 360 配置发生变化，请重新预览。')
    return _digest(pairs)


def _archive(profile,metadata):
    if not isinstance(metadata,dict) or metadata.get('status')!='saved' or not re.fullmatch(r'[0-9a-f]{64}\.zip',str(metadata.get('archive',''))):
        raise ValueError('这份备份没有可恢复的 360 数据副本。')
    path=Path(profile)/'desktop-layouts'/'360-data'/metadata['archive']
    if not path.is_file() or path.stat().st_size>assistant.MAX_BYTES+4*1024*1024:raise ValueError('360 副本不存在或文件过大。')
    return path


def _contents(path):
    # Never use extractall: Windows accepts path aliases (drive names, ADS,
    # trailing dots/spaces, device names) that generic ZIP checks may miss.
    try:
        with zipfile.ZipFile(path) as archive:
            infos=archive.infolist();names=set();files={};pairs=[];total=0
            if not infos or len(infos)>assistant.MAX_FILES:raise ValueError('360 副本文件数量无效。')
            for entry in infos:
                name=entry.filename
                if entry.orig_filename!=name or '\\' in name or name.startswith('/') or entry.is_dir() or entry.flag_bits&1:
                    raise ValueError('360 副本包含无效路径或加密文件。')
                parts=name.split('/')
                for part in parts:
                    win=PureWindowsPath(part)
                    if not part or part in ('.','..') or part.endswith((' ','.')) or win.is_reserved() or any(c in part for c in '<>:"|?*') or any(ord(c)<32 for c in part):
                        raise ValueError('360 副本包含不安全的 Windows 文件名。')
                mode=entry.external_attr>>16
                if stat.S_IFMT(mode) not in (0,stat.S_IFREG):raise ValueError('360 副本包含链接或特殊文件。')
                key=name.casefold()
                if key in names:raise ValueError('360 副本包含重复文件。')
                names.add(key)
                total+=entry.file_size
                if entry.file_size<0 or total>assistant.MAX_BYTES:raise ValueError('360 副本解压后过大。')
                with archive.open(entry) as stream:content=stream.read(entry.file_size+1)
                if len(content)!=entry.file_size:raise ValueError('360 副本文件长度无效。')
                files[name]=content;pairs.append((name,hashlib.sha256(content).hexdigest()))
            for name in names:
                if any('/'.join(name.split('/')[:i]) in names for i in range(1,len(name.split('/')))):
                    raise ValueError('360 副本存在文件与目录冲突。')
            if _digest(pairs)!=path.stem:raise ValueError('360 副本完整性校验失败，未执行恢复。')
            return files,total
    except (zipfile.BadZipFile,RuntimeError,EOFError) as error:
        raise ValueError('360 副本损坏或无法读取，未执行恢复。') from error


def preview(profile,metadata):
    if assistant.sys.platform!='win32':raise ValueError('非windows电脑无法使用')
    running=control._running();root=_root()
    if Path(profile).resolve().is_relative_to(root.resolve()):raise ValueError('应用数据目录位于 360 目录内，不能整体替换。')
    path=_archive(profile,metadata);files,total=_contents(path)
    processes=control.process_snapshot() if running else []
    current='running:'+json.dumps(processes,sort_keys=True) if running else _current(root)
    return dict(file_count=len(files),bytes=total,fingerprint=hashlib.sha256((path.stem+'|'+current).encode()).hexdigest(),current_exists=root.exists(),auto_restart=running,message='将替换 360 数据目录（包括副本内设置及历史数据）。当前目录会保留为回退副本。'+('确认后将正常退出并重新启动 360；无法正常退出则停止恢复。' if running else '360 当前未运行，恢复后保持关闭。'))


def _restore_stopped(profile,metadata,fingerprint):
    stopped()
    plan=preview(profile,metadata)
    if not isinstance(fingerprint,str) or fingerprint!=plan['fingerprint']:raise ValueError('360 当前配置或备份已变化，请重新预览并确认。')
    root=_root();path=_archive(profile,metadata);files,total=_contents(path)
    stage=Path(tempfile.mkdtemp(prefix='.360DesktopLite-restore-',dir=root.parent))
    rollback=root.parent/('.360DesktopLite-before-restore-'+uuid.uuid4().hex)
    moved=False;installed=False
    try:
        for name,content in files.items():
            destination=stage/name;destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('xb') as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
        # Re-check after preparing files, before touching live configuration.
        stopped()
        latest=hashlib.sha256((path.stem+'|'+_current(root)).encode()).hexdigest()
        if latest!=fingerprint:raise ValueError('360 当前配置已变化，请重新预览。')
        if root.exists():os.replace(root,rollback);moved=True
        stopped()
        os.replace(stage,root);installed=True
        if _current(root)!=path.stem:raise ValueError('360 写入后内容校验失败。')
        return dict(file_count=len(files),bytes=total,rollback_directory=str(rollback) if moved else '',message='360 数据文件已恢复并校验。请手动启动 360 确认布局是否生效；当前状态不代表已经验证屏幕上的排列。')
    except Exception as error:
        # Keep the pre-restore directory even if recovery fails. Never erase
        # files that a restarted vendor process may have created in the target.
        try:
            if installed and root.exists():
                failed=root.parent/('.360DesktopLite-failed-restore-'+uuid.uuid4().hex)
                os.replace(root,failed)
            if moved:os.replace(rollback,root)
        except OSError as rollback_error:
            raise RecoveryRequired('360 恢复中断，自动回退失败。原配置仍保留在：'+str(rollback)+'；请退出 360 后手动检查。') from rollback_error
        raise ValueError('360 恢复未完成，已保留或回退原配置。'+str(error)) from error
    finally:
        if stage.exists():shutil.rmtree(stage,ignore_errors=True)


def restore(profile,metadata,fingerprint):
    plan=preview(profile,metadata)
    if not isinstance(fingerprint,str) or plan['fingerprint']!=fingerprint:raise ValueError('360 当前状态或备份已变化，请重新预览并确认。')
    if not plan['auto_restart']:
        result=_restore_stopped(profile,metadata,fingerprint)
        return dict(result,auto_restart=False,restarted=None)
    # Validate the exact same process generation before sending exit requests.
    processes=control.process_snapshot();path=_archive(profile,metadata)
    expected=hashlib.sha256((path.stem+'|running:'+json.dumps(processes,sort_keys=True)).encode()).hexdigest()
    if expected!=fingerprint:raise ValueError('360 进程已变化，请重新预览并确认。')
    cycle=control.ProcessCycle(processes);safe_to_restart=True
    try:
        cycle.shutdown()
        stopped()
        # Normal exit may flush 360's in-memory state. Preserve that final
        # on-disk state, rather than treating its legitimate flush as a conflict.
        closed_plan=preview(profile,metadata)
        result=_restore_stopped(profile,metadata,closed_plan['fingerprint'])
        resumed=cycle.resume()
        return dict(result,auto_restart=True,restarted=resumed,message='360 数据文件已恢复并校验。'+('已检测到 360 重新运行，请核对屏幕上的布局。' if resumed else '自动启动未成功，请手动打开 360 检查布局。'))
    except RecoveryRequired:
        safe_to_restart=False
        raise
    except Exception as error:
        resumed=cycle.resume() if safe_to_restart else False
        raise ValueError(str(error)+(' 已尝试重新打开 360。' if resumed else ' 如 360 已退出，请手动打开。')) from error
    finally:cycle.close()
