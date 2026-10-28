"""Convert legacy Word copies locally while retaining table and merge structure."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import is_zipfile,ZipFile

_CACHE={}
_TEMP=tempfile.TemporaryDirectory(prefix='clinical-word-')
WORD_SCRIPT='''on run argv
    set sourcePath to item 1 of argv
    set targetPath to item 2 of argv
    tell application "Microsoft Word"
        set convertedDoc to missing value
        try
            open (POSIX file sourcePath) read only true add to recent files false
            set convertedDoc to active document
            save as convertedDoc file name targetPath file format format document default add to recent files false
            close convertedDoc saving no
        on error messageText number messageNumber
            if convertedDoc is not missing value then
                try
                    close convertedDoc saving no
                end try
            end if
            error messageText number messageNumber
        end try
    end tell
end run'''


def ensure_docx(path):
    source=Path(path).resolve()
    if source.suffix.lower()=='.docx':return source
    if source.suffix.lower()!='.doc':raise ValueError('请选择 .doc 或 .docx Word 文件。')
    if not source.is_file():raise ValueError('Word 文件不存在。')
    stat=source.stat();key=(str(source),stat.st_mtime_ns,stat.st_size)
    if key in _CACHE and _CACHE[key].is_file():return _CACHE[key]
    folder=Path(tempfile.mkdtemp(dir=_TEMP.name));target=folder/'converted.docx'
    if is_zipfile(source):shutil.copyfile(source,target)
    else:
        # Work on a private copy; opening/saving must not alter the user's
        # original file or an existing Word editing session.
        copy=folder/'source.doc';shutil.copyfile(source,copy)
        office=shutil.which('soffice') or shutil.which('libreoffice')
        if not office and Path('/Applications/LibreOffice.app/Contents/MacOS/soffice').is_file():office='/Applications/LibreOffice.app/Contents/MacOS/soffice'
        try:
            if office:
                subprocess.run([office,'-env:UserInstallation='+ (folder/'profile').as_uri(),'--headless','--convert-to','docx','--outdir',str(folder),str(copy)],capture_output=True,timeout=90,check=True)
                (folder/'source.docx').replace(target)
            elif sys.platform=='darwin' and Path('/Applications/Microsoft Word.app').is_dir():
                subprocess.run(['/usr/bin/osascript','-',str(copy),str(target)],input=WORD_SCRIPT,text=True,capture_output=True,timeout=90,check=True)
            else:raise ValueError('读取旧版 .doc 需要 Microsoft Word（Mac）或 LibreOffice；也可先另存为 .docx 后导入。')
        except subprocess.TimeoutExpired as exc:raise ValueError('旧版 Word 转换超时，请检查 Word 是否有待处理弹窗，或另存为 .docx 后导入。') from exc
        except (subprocess.CalledProcessError,OSError) as exc:raise ValueError('旧版 Word 转换失败。请允许本软件控制 Microsoft Word，或将文件另存为 .docx 后导入。') from exc
    if not is_zipfile(target):raise ValueError('旧版 Word 转换未生成有效的 .docx 文件。')
    with ZipFile(target) as archive:
        if 'word/document.xml' not in archive.namelist():raise ValueError('转换结果缺少 Word 正文。')
    _CACHE[key]=target
    return target
