"""Durable per-user data directory, independent of the installed application."""
from pathlib import Path
import json,os,shutil,sqlite3,sys,tempfile

def windows_documents():
    import ctypes
    buffer=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buffer)==0 and buffer.value:
        return Path(buffer.value)
    return Path.home()/'Documents'

def data_root(system=None,home=None,documents=None):
    override=os.environ.get('RESEARCH_V3_DATA_ROOT')
    if override:return Path(override).expanduser().resolve()
    system=system or sys.platform
    home=Path(home) if home else Path.home()
    base=(Path(documents) if documents else windows_documents()) if system=='win32' else home
    return base/'.research-data-tools'

def initialize(root,legacy=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if sys.platform=='win32':
        import ctypes
        get=ctypes.windll.kernel32.GetFileAttributesW;get.argtypes=[ctypes.c_wchar_p];get.restype=ctypes.c_uint32
        put=ctypes.windll.kernel32.SetFileAttributesW;put.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32]
        attributes=get(str(root))
        if attributes!=0xffffffff:put(str(root),attributes|2)
    profile=root/'profile'
    if not profile.exists():
        temporary=Path(tempfile.mkdtemp(dir=root,prefix='.profile-'))
        try:
            source=Path(legacy).expanduser() if legacy else None
            if source and source.is_dir() and source.resolve()!=profile.resolve():
                shutil.copytree(source,temporary,dirs_exist_ok=True)
                # SQLite backup includes committed data even if an old V3 has a WAL.
                database=source/'personal.sqlite3'
                if database.is_file():
                    for copied in temporary.glob('personal.sqlite3*'):
                        if copied.is_file():copied.unlink()
                    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(temporary/'personal.sqlite3') as new:old.backup(new)
                prefixes={str(source),str(source.resolve())}
                def remap(value):
                    if isinstance(value,str):
                        for prefix in prefixes:
                            if value==prefix or value.startswith(prefix+os.sep):return str(profile)+value[len(prefix):]
                    if isinstance(value,list):return [remap(v) for v in value]
                    if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
                    return value
                for file in temporary.rglob('*.json'):
                    try:
                        original=json.loads(file.read_text(encoding='utf-8'));updated=remap(original)
                        if updated!=original:file.write_text(json.dumps(updated,ensure_ascii=False),encoding='utf-8')
                    except (ValueError,UnicodeError):pass
                (temporary/'storage-origin.json').write_text(json.dumps(dict(previous_profile=str(source)),ensure_ascii=False),encoding='utf-8')
            try:os.rename(temporary,profile)
            except OSError:
                if not profile.is_dir():raise
        finally:
            if temporary.exists():shutil.rmtree(temporary)
    return profile
