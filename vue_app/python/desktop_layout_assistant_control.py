"""Graceful lifecycle control of known 360 UI processes in this user session.

Restart Manager: https://learn.microsoft.com/windows/win32/api/restartmanager/
No force-shutdown flag, service registration, taskkill or Explorer termination.
"""
import ctypes as C
import os,subprocess,threading,time
from pathlib import Path,PureWindowsPath
import desktop_layout_assistant as assistant

class FileTime(C.Structure):
    _fields_=[('low',C.c_uint32),('high',C.c_uint32)]
class UniqueProcess(C.Structure):
    _fields_=[('pid',C.c_uint32),('started',FileTime)]


def process_snapshot():
    if assistant.sys.platform!='win32':raise ValueError('非windows电脑无法使用')
    found=assistant._windows_processes()
    if not found:return []
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[C.c_uint32,C.c_int32,C.c_uint32];kernel.OpenProcess.restype=C.c_void_p
    kernel.CloseHandle.argtypes=[C.c_void_p];kernel.CloseHandle.restype=C.c_int32
    kernel.QueryFullProcessImageNameW.argtypes=[C.c_void_p,C.c_uint32,C.c_wchar_p,C.POINTER(C.c_uint32)];kernel.QueryFullProcessImageNameW.restype=C.c_int32
    kernel.GetProcessTimes.argtypes=[C.c_void_p]+[C.POINTER(FileTime)]*4;kernel.GetProcessTimes.restype=C.c_int32
    result=[]
    for item in found:
        handle=kernel.OpenProcess(0x1000,0,item['pid'])
        if not handle:raise ValueError('无法读取 360 进程信息，请手动退出后重试。')
        try:
            path=C.create_unicode_buffer(32768);length=C.c_uint32(len(path));times=[FileTime() for _ in range(4)]
            if not kernel.QueryFullProcessImageNameW(handle,0,path,C.byref(length)) or not kernel.GetProcessTimes(handle,*[C.byref(t) for t in times]):
                raise ValueError('无法确认 360 程序位置，请手动退出后重试。')
            if not assistant.is_desktop_assistant(path.value) or PureWindowsPath(path.value).name.casefold()!=item['executable'].casefold():
                raise ValueError('360 进程标识发生变化，请重新预览。')
            info=Path(path.value).stat()
            result.append(dict(pid=item['pid'],low=times[0].low,high=times[0].high,path=path.value,size=info.st_size,modified=info.st_mtime_ns))
        finally:kernel.CloseHandle(handle)
    return sorted(result,key=lambda p:p['pid'])


def _running():
    state=assistant.probe()
    if not state['checked']:raise ValueError('无法检测 360 运行状态，请刷新重试。')
    return state['running']


def _wait_running(expected,seconds):
    deadline=time.monotonic()+seconds
    while True:
        if _running()==expected:return True
        if time.monotonic()>=deadline:return False
        time.sleep(.2)


class ProcessCycle:
    def __init__(self,processes):
        self.processes=processes;self.session=None;self.attempted=False
        self.rm=C.WinDLL('Rstrtmgr',use_last_error=True)
        U32=C.c_uint32
        self.rm.RmStartSession.argtypes=[C.POINTER(U32),U32,C.c_wchar_p];self.rm.RmStartSession.restype=U32
        self.rm.RmRegisterResources.argtypes=[U32,U32,C.c_void_p,U32,C.POINTER(UniqueProcess),U32,C.c_void_p];self.rm.RmRegisterResources.restype=U32
        for name in ('RmShutdown','RmRestart'):
            function=getattr(self.rm,name);function.argtypes=[U32,U32,C.c_void_p];function.restype=U32
        self.rm.RmEndSession.argtypes=[U32];self.rm.RmEndSession.restype=U32
    def shutdown(self):
        if not self.processes:raise ValueError('360 进程已变化，请重新预览。')
        for item in self.processes:
            if not assistant.is_desktop_assistant(item['path']):raise ValueError('拒绝操作非 360 桌面进程。')
        handle=C.c_uint32();key=C.create_unicode_buffer(33)
        code=self.rm.RmStartSession(C.byref(handle),0,key)
        if code:raise ValueError('无法启动 360 正常退出流程（系统代码 '+str(code)+'）。')
        self.session=handle.value
        apps=(UniqueProcess*len(self.processes))(*[UniqueProcess(p['pid'],FileTime(p['low'],p['high'])) for p in self.processes])
        code=self.rm.RmRegisterResources(self.session,0,None,len(apps),apps,0,None)
        if code:raise ValueError('无法登记 360 进程（系统代码 '+str(code)+'）。')
        self.attempted=True
        code=self.rm.RmShutdown(self.session,0,None) # 0: never force unresponsive apps
        if code or not _wait_running(False,5):raise ValueError('360 未能正常退出，未覆盖配置。请手动退出后重试（系统代码 '+str(code)+'）。')
    def resume(self):
        if not self.attempted:return None
        try:
            self.rm.RmRestart(self.session,0,None)
            if _wait_running(True,2):return True
            # Restart Manager only reopens applications that registered restart.
            # Fall back to the exact executable observed before shutdown.
            preferred=sorted(self.processes,key=lambda p:('64' in PureWindowsPath(p['path']).stem,p['path'].casefold()))[0]
            executable=Path(preferred['path']);info=executable.stat()
            if not assistant.is_desktop_assistant(str(executable)) or (info.st_size,info.st_mtime_ns)!=(preferred['size'],preferred['modified']):return False
            process=subprocess.Popen([str(executable)],cwd=str(executable.parent),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x208,shell=False)
            threading.Thread(target=process.wait,daemon=True).start()
            return _wait_running(True,8)
        except (OSError,ValueError):return False
    def close(self):
        if self.session is not None:self.rm.RmEndSession(self.session);self.session=None
