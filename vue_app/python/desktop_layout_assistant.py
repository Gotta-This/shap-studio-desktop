"""Read-only detection of desktop assistants in the current Windows session."""
import ctypes as C
import os,sys
from pathlib import Path,PureWindowsPath

# Deliberately excludes the security suite, updater, analyser and background
# service: their presence alone does not mean a desktop UI is running.
DESKTOP_EXECUTABLES=frozenset(('360desktop.exe','360desktop64.exe','360desktoplite.exe','360desktoplite64.exe','360desktopplus.exe','360desktopplus64.exe'))

def is_desktop_assistant(name):return PureWindowsPath(name).name.casefold() in DESKTOP_EXECUTABLES

def _windows_processes():
    U32=C.c_uint32;I32=C.c_int32;PTR=C.c_void_p
    class ProcessEntry(C.Structure):
        _fields_=[('size',U32),('usage',U32),('pid',U32),('heap',C.c_size_t),('module',U32),('threads',U32),('parent',U32),('priority',I32),('flags',U32),('name',C.c_wchar*260)]
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[U32,U32];kernel.CreateToolhelp32Snapshot.restype=PTR
    kernel.Process32FirstW.argtypes=[PTR,C.POINTER(ProcessEntry)];kernel.Process32FirstW.restype=I32
    kernel.Process32NextW.argtypes=[PTR,C.POINTER(ProcessEntry)];kernel.Process32NextW.restype=I32
    kernel.ProcessIdToSessionId.argtypes=[U32,C.POINTER(U32)];kernel.ProcessIdToSessionId.restype=I32
    kernel.CloseHandle.argtypes=[PTR];kernel.CloseHandle.restype=I32
    session=U32()
    if not kernel.ProcessIdToSessionId(os.getpid(),C.byref(session)):raise C.WinError(C.get_last_error())
    snapshot=kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot==PTR(-1).value:raise C.WinError(C.get_last_error())
    found=[]
    try:
        entry=ProcessEntry();entry.size=C.sizeof(entry)
        ok=kernel.Process32FirstW(snapshot,C.byref(entry))
        while ok:
            if is_desktop_assistant(entry.name):
                other=U32()
                if not kernel.ProcessIdToSessionId(entry.pid,C.byref(other)):raise C.WinError(C.get_last_error())
                if other.value==session.value:found.append(dict(name='360 桌面助手',executable=entry.name,pid=entry.pid))
            ok=kernel.Process32NextW(snapshot,C.byref(entry))
        error=C.get_last_error()
        if error not in (0,18):raise C.WinError(error)
    finally:kernel.CloseHandle(snapshot)
    return found


def data_root():
    from pathlib import Path
    value=os.environ.get('APPDATA')
    return Path(value)/'360DesktopLite' if value else None

def probe():
    root=data_root()
    result=dict(checked=True,running=False,data_found=bool(root and root.is_dir()),installed=False,message='')
    if sys.platform!='win32':return result
    try:
        result['running']=bool(_windows_processes())
        result['installed']=result['running'] or result['data_found'] or _registered()
    except (OSError,AttributeError):
        result.update(checked=False,message='360 运行状态检测失败，本次无法确认是否需要同步备份。')
    return result

def _registered():
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for access in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|access) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent,winreg.EnumKey(parent,index)) as child:
                                name=winreg.QueryValueEx(child,'DisplayName')[0].casefold()
                                if '360' in name and ('桌面助手' in name or 'desktop' in name):return True
                        except OSError:continue
            except OSError:continue
    return False

# Archive the vendor data without interpreting or editing its private schema.
# Immutable content-addressed archives are shared by unchanged snapshots.
MAX_BYTES=128*1024*1024
MAX_FILES=10000

def _inventory(root):
    import stat
    found=[];total=0
    def failed(error):raise error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=failed):
        for name in dirs+files:
            path=Path(directory)/name
            info=path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise ValueError('360 数据包含链接或重解析点，未复制。')
        for name in sorted(files):
            path=Path(directory)/name
            info=path.stat()
            if not stat.S_ISREG(info.st_mode):raise ValueError('360 数据包含特殊文件。')
            total+=info.st_size
            if total>MAX_BYTES or len(found)>=MAX_FILES:raise ValueError('360 数据超过 128 MB 或 10000 个文件，本次未同步。')
            found.append((path.relative_to(root).as_posix(),info.st_size,info.st_mtime_ns))
    return sorted(found)

def capture(profile):
    import hashlib,json,tempfile,zipfile
    from pathlib import Path
    state=probe()
    if not state['checked']:return dict(status='failed',message=state['message'])
    if not state['running']:return dict(status='not_running',message='360 未运行；本次仅备份 Windows 原生桌面。')
    root=data_root()
    if not root or not root.is_dir():return dict(status='failed',message='360 正在运行，但未找到默认数据目录。')
    target=Path(profile)/'desktop-layouts'/'360-data'
    temporary=None
    try:
        if target.resolve().is_relative_to(root.resolve()):raise ValueError('备份目录不能位于 360 数据目录内。')
        target.mkdir(parents=True,exist_ok=True)
        if root.is_symlink() or getattr(root.lstat(),'st_file_attributes',0)&0x400:raise ValueError('360 数据目录是链接或重解析点。')
        inventory=_inventory(root)
        if not inventory:raise ValueError('360 数据目录为空。')
        fd,temporary=tempfile.mkstemp(prefix='.capture-',suffix='.zip',dir=target);os.close(fd)
        hashes=[]
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,size,mtime in inventory:
                with (root/name).open('rb') as stream:content=stream.read(size+1)
                if len(content)!=size:raise ValueError('360 数据正在变化，请稍后重试。')
                hashes.append((name,hashlib.sha256(content).hexdigest()))
                archive.writestr(name,content)
        # A second pass detects ordinary writes during the live copy. This is
        # not a vendor-provided transactional snapshot and is labelled as such.
        if inventory!=_inventory(root):raise ValueError('360 数据正在变化，请稍后重试。')
        for name,digest in hashes:
            hasher=hashlib.sha256();count=0
            with (root/name).open('rb') as stream:
                while True:
                    chunk=stream.read(1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>MAX_BYTES:raise ValueError('360 数据正在变化，请稍后重试。')
                    hasher.update(chunk)
            if hasher.hexdigest()!=digest:raise ValueError('360 数据正在变化，请稍后重试。')
        key=hashlib.sha256(json.dumps(hashes,ensure_ascii=False).encode()).hexdigest()
        destination=target/(key+'.zip')
        os.replace(temporary,destination);temporary=None
        return dict(status='saved',archive=key+'.zip',file_count=len(inventory),bytes=sum(i[1] for i in inventory),message='已保存 360 数据目录副本（运行中复制，尚未经 360 恢复验证）。')
    except (OSError,ValueError,zipfile.BadZipFile):
        return dict(status='failed',message='360 数据未能完整复制，可能被占用、正在变化、超出限制或目录不可读；Windows 备份仍保留。')
    finally:
        if temporary:Path(temporary).unlink(missing_ok=True)

def cleanup(profile):
    import json,re
    from pathlib import Path
    folder=Path(profile)/'desktop-layouts';used=set()
    for path in folder.glob('*.json'):
        try:
            record=json.loads(path.read_text(encoding='utf8'))
            item=record.get('assistant',{}).get('archive','')
            if re.fullmatch(r'[0-9a-f]{64}\.zip',item):used.add(item)
        except (OSError,ValueError,AttributeError,TypeError):
            # Do not prune vendor copies if a referencing record is unreadable.
            return
    for path in (folder/'360-data').glob('*.zip'):
        if re.fullmatch(r'[0-9a-f]{64}\.zip',path.name) and path.name not in used:path.unlink(missing_ok=True)
