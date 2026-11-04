"""Desktop coordinates via Microsoft's IFolderView API (no registry/ListView writes)."""
import ctypes as C
import uuid

I32=C.c_int32;U32=C.c_uint32;PTR=C.c_void_p
class Point(C.Structure):_fields_=[('x',I32),('y',I32)]
class Rect(C.Structure):_fields_=[('left',I32),('top',I32),('right',I32),('bottom',I32)]
class Guid(C.Structure):
    _fields_=[('a',U32),('b',C.c_uint16),('c',C.c_uint16),('d',C.c_ubyte*8)]
    @classmethod
    def of(cls,text):return cls.from_buffer_copy(uuid.UUID(text).bytes_le)
class VariantValue(C.Union):_fields_=[('integer',I32),('wide',C.c_int64),('record',PTR*2)]
class Variant(C.Structure):_fields_=[('vt',C.c_uint16),('reserved',C.c_uint16*3),('value',VariantValue)]

class DesktopView:
    def _trace(self,event,**fields):
        callback=getattr(self,'trace',None)
        if callback:callback(event,**fields)
    def _window_info(self):
        try:
            self.user.GetClassNameW.argtypes=[PTR,C.c_wchar_p,I32];self.user.GetClassNameW.restype=I32
            self.user.IsWindowVisible.argtypes=[PTR];self.user.IsWindowVisible.restype=I32
            self.user.GetWindowThreadProcessId.argtypes=[PTR,C.POINTER(U32)];self.user.GetWindowThreadProcessId.restype=U32
            self.user.GetShellWindow.argtypes=[];self.user.GetShellWindow.restype=PTR
            name=C.create_unicode_buffer(256);pid=U32()
            self.user.GetClassNameW(self.hwnd,name,len(name));self.user.GetWindowThreadProcessId(self.hwnd,C.byref(pid))
            return dict(handle=hex(self.hwnd.value or 0),window_class=name.value,visible=bool(self.user.IsWindowVisible(self.hwnd)),process_id=pid.value,shell_handle=hex(self.user.GetShellWindow() or 0))
        except Exception as error:return dict(unavailable=type(error).__name__)
    def _check(self,hr):
        if hr<0:raise OSError('Windows 桌面接口调用失败（0x%08X）。请确认资源管理器正在运行。'%(hr&0xffffffff))
    def _call(self,ptr,index,types,*args):
        table=C.cast(ptr,C.POINTER(C.POINTER(PTR))).contents
        return C.WINFUNCTYPE(I32,PTR,*types)(table[index])(ptr,*args)
    def _query(self,ptr,iid):
        out=PTR();guid=Guid.of(iid);self._check(self._call(ptr,0,[C.POINTER(Guid),C.POINTER(PTR)],C.byref(guid),C.byref(out)))
        self.refs.append(out);return out
    def __enter__(self):
        self.refs=[];self.initialized=False;self.dpi_context=None
        self.ole=C.OleDLL('ole32');self.shell=C.WinDLL('shell32');self.user=C.WinDLL('user32',use_last_error=True)
        self.ole.CoInitializeEx.argtypes=[PTR,U32];self.ole.CoInitializeEx.restype=I32
        self.ole.CoCreateInstance.argtypes=[C.POINTER(Guid),PTR,U32,C.POINTER(Guid),C.POINTER(PTR)];self.ole.CoCreateInstance.restype=I32
        self.ole.CoTaskMemFree.argtypes=[PTR];self.ole.CoTaskMemFree.restype=None
        self.shell.SHGetNameFromIDList.argtypes=[PTR,U32,C.POINTER(PTR)];self.shell.SHGetNameFromIDList.restype=I32
        self.user.GetClientRect.argtypes=[PTR,C.POINTER(Rect)];self.user.GetClientRect.restype=I32
        self.user.MapWindowPoints.argtypes=[PTR,PTR,C.POINTER(Point),U32];self.user.MapWindowPoints.restype=I32
        try:
            self._check(self.ole.CoInitializeEx(None,2));self.initialized=True
            windows=PTR();clsid=Guid.of('9BA05972-F6A8-11CF-A442-00A0C90A8F39');iid=Guid.of('85CB6900-4D95-11CF-960C-0080C7F4EE85')
            self._check(self.ole.CoCreateInstance(C.byref(clsid),None,23,C.byref(iid),C.byref(windows)));self.refs.append(windows)
            loc=Variant();loc.vt=3;loc.value.integer=0;empty=Variant();hwnd=I32();dispatch=PTR()
            self._check(self._call(windows,15,[C.POINTER(Variant),C.POINTER(Variant),I32,C.POINTER(I32),I32,C.POINTER(PTR)],C.byref(loc),C.byref(empty),8,C.byref(hwnd),1,C.byref(dispatch)))
            if not dispatch:raise OSError('未找到当前用户的 Windows 桌面。')
            self.refs.append(dispatch);service=self._query(dispatch,'6D5140C1-7436-11CE-8034-00AA006009FA')
            sid=Guid.of('4C96BE40-915C-11CF-99D3-00AA004AE837');bid=Guid.of('000214E2-0000-0000-C000-000000000046');browser=PTR()
            self._check(self._call(service,3,[C.POINTER(Guid),C.POINTER(Guid),C.POINTER(PTR)],C.byref(sid),C.byref(bid),C.byref(browser)));self.refs.append(browser)
            view=PTR();self._check(self._call(browser,15,[C.POINTER(PTR)],C.byref(view)));self.refs.append(view)
            self.folder=self._query(view,'CDE725B0-CCC9-4519-917E-325D72FAB4CE')
            self.hwnd=PTR();self._check(self._call(view,3,[C.POINTER(PTR)],C.byref(self.hwnd)))
            if hasattr(self.user,'GetWindowDpiAwarenessContext'):
                self.user.GetWindowDpiAwarenessContext.argtypes=[PTR];self.user.GetWindowDpiAwarenessContext.restype=PTR
                self.user.SetThreadDpiAwarenessContext.argtypes=[PTR];self.user.SetThreadDpiAwarenessContext.restype=PTR
                self.dpi_context=self.user.SetThreadDpiAwarenessContext(self.user.GetWindowDpiAwarenessContext(self.hwnd))
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def __exit__(self,*args):
        if self.dpi_context:self.user.SetThreadDpiAwarenessContext(self.dpi_context)
        for ptr in reversed(self.refs):
            if ptr:self._call(ptr,2,[])
        if self.initialized:self.ole.CoUninitialize()
    def _name(self,pidl,kind):
        text=PTR();self._check(self.shell.SHGetNameFromIDList(pidl,kind,C.byref(text)))
        try:return C.wstring_at(text)
        finally:self.ole.CoTaskMemFree(text)
    def _items(self):
        count=I32();self._check(self._call(self.folder,7,[U32,C.POINTER(I32)],2,C.byref(count)))
        if not 0<=count.value<=10000:raise ValueError('桌面图标数量异常，已停止操作。')
        for index in range(count.value):
            pidl=PTR();self._check(self._call(self.folder,6,[I32,C.POINTER(PTR)],index,C.byref(pidl)))
            try:yield pidl,self._name(pidl,0x80028000),self._name(pidl,0)
            finally:self.ole.CoTaskMemFree(pidl)
    def capture(self):
        icons=[]
        for pidl,key,name in self._items():
            pt=Point();self._check(self._call(self.folder,11,[PTR,C.POINTER(Point)],pidl,C.byref(pt)))
            icons.append(dict(key=key,name=name,x=pt.x,y=pt.y))
        spacing=Point();self._check(self._call(self.folder,12,[C.POINTER(Point)],C.byref(spacing)))
        rect=Rect()
        if not self.user.GetClientRect(self.hwnd,C.byref(rect)):raise OSError('无法读取桌面尺寸。')
        workareas=[]
        class MonitorInfo(C.Structure):_fields_=[('size',U32),('monitor',Rect),('work',Rect),('flags',U32)]
        callback_type=C.WINFUNCTYPE(I32,PTR,PTR,C.POINTER(Rect),C.c_ssize_t)
        self.user.GetMonitorInfoW.argtypes=[PTR,C.POINTER(MonitorInfo)];self.user.GetMonitorInfoW.restype=I32
        def monitor_callback(handle,dc,bounds,param):
            info=MonitorInfo();info.size=C.sizeof(info)
            if self.user.GetMonitorInfoW(handle,C.byref(info)):
                points=(Point*2)(Point(info.work.left,info.work.top),Point(info.work.right,info.work.bottom))
                self.user.MapWindowPoints(None,self.hwnd,points,2)
                workareas.append(dict(left=max(0,points[0].x),top=max(0,points[0].y),right=min(rect.right,points[1].x),bottom=min(rect.bottom,points[1].y)))
            return 1
        callback=callback_type(monitor_callback)
        self.user.EnumDisplayMonitors.argtypes=[PTR,PTR,callback_type,C.c_ssize_t];self.user.EnumDisplayMonitors.restype=I32
        if not self.user.EnumDisplayMonitors(None,None,callback,0):raise OSError('无法读取显示器可用区域。')
        workareas=[a for a in workareas if a['right']>a['left'] and a['bottom']>a['top']]
        if not workareas:raise OSError('未找到可用的桌面区域。')
        hr=self._call(self.folder,14,[]);self._check(hr)
        dpi=96
        if hasattr(self.user,'GetDpiForWindow'):
            self.user.GetDpiForWindow.argtypes=[PTR];self.user.GetDpiForWindow.restype=U32;dpi=self.user.GetDpiForWindow(self.hwnd) or 96
        value=dict(icons=icons,display=dict(width=rect.right,height=rect.bottom,dpi=dpi,spacing=[max(1,spacing.x),max(1,spacing.y)],workareas=sorted(workareas,key=lambda a:(a['left'],a['top']))),auto_arrange=hr==0)
        if getattr(self,'trace',None):self._trace('native.capture',count=len(icons),window=self._window_info(),auto_arrange_hresult='0x%08X'%(hr&0xffffffff),display=value['display'])
        return value
    def position(self,items):
        wanted={i['key'].casefold():i for i in items};held=[];points=[]
        # Clone current PIDLs: never deserialize arbitrary PIDL data from disk.
        self.shell.ILClone.argtypes=[PTR];self.shell.ILClone.restype=PTR
        try:
            for pidl,key,name in self._items():
                item=wanted.get(key.casefold())
                if item:
                    copy=self.shell.ILClone(pidl)
                    if not copy:raise MemoryError('无法复制桌面图标标识。')
                    held.append(copy);points.append(Point(item['x'],item['y']))
            if len(held)!=len(wanted):raise ValueError('桌面图标已经变化，请重新预览恢复。')
            if held:
                self._trace('native.position.begin',method='IFolderView.SelectAndPositionItems',count=len(held),flags='0x00000080',window=self._window_info())
                hr=self._call(self.folder,16,[U32,C.POINTER(PTR),C.POINTER(Point),U32],len(held),(PTR*len(held))(*held),(Point*len(points))(*points),0x80)
                self._trace('native.position.result',hresult='0x%08X'%(hr&0xffffffff),succeeded=hr>=0)
                self._check(hr)
        finally:
            for ptr in held:self.ole.CoTaskMemFree(ptr)
