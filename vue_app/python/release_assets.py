"""Shared public filenames for release packaging and in-app updates."""
from pathlib import PurePath
import re

def versioned_name(name, release_version):
    value=release_version.removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',value):
        raise ValueError('安装包版本号无效')
    if PurePath(name).name!=name or not name.startswith('ResearchDataTools-') or PurePath(name).suffix not in ('.exe','.zip'):
        raise ValueError('安装包文件名无效')
    path=PurePath(name)
    return path.stem+'-v'+value+path.suffix
