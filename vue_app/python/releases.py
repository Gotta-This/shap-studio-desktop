"""V3 stable releases: platform selection and checksum-verified staged installers."""
import hashlib
import json
import platform
import re
import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen
import certifi
from release_assets import versioned_name

VERSION = "3.2.9"
REPO = "Gotta-This/shap-studio-desktop"
PREFIX = f"https://github.com/{REPO}/releases/download/"

def read_url(url):
    context = ssl.create_default_context(cafile=certifi.where())
    return urlopen(Request(url, headers={"User-Agent": f"ResearchDataTools/{VERSION}", "Accept": "application/vnd.github+json"}), context=context, timeout=30)

def version(value):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not m: raise ValueError("版本号无效")
    return tuple(map(int, m.groups()))

def asset_name(system=None, machine=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if system == "win32" and machine in ("amd64", "x86_64", "x64"):
        return "ResearchDataTools-Setup-Windows-x64.exe"
    if system == "darwin" and machine in ("arm64", "aarch64", "x86_64", "amd64"):
        return "ResearchDataTools-macOS-" + ("arm64" if machine in ("arm64", "aarch64") else "x86_64") + ".zip"
    return None

def select(payload, name=None):
    v = version(payload["tag_name"])
    if payload.get("draft") or payload.get("prerelease") or v < (3, 0, 0):
        raise ValueError("暂未发布 V3 正式版")
    name = name or asset_name()
    # Prefer the version-labelled download, while accepting older releases.
    candidates = [versioned_name(name,payload['tag_name']),name] if name else []
    asset = next((a for candidate in candidates for a in payload.get("assets", []) if a["name"] == candidate), None)
    return dict(current=VERSION, version=payload["tag_name"].lstrip("v"), newer=v > version(VERSION),
                asset=asset, assets=payload.get("assets", []), name=payload.get("name", ""),
                url=f"https://github.com/{REPO}/releases/tag/{payload['tag_name']}")

def check():
    try:
        with read_url(f"https://api.github.com/repos/{REPO}/releases/latest") as response:
            return select(json.loads(response.read(2 * 1024 * 1024)))
    except ValueError as e:
        if str(e) == "暂未发布 V3 正式版":
            return dict(current=VERSION, version=VERSION, newer=False, asset=None, assets=[], name="V3 发布准备中")
        raise

def download(profile):
    # Re-read release metadata instead of trusting URLs supplied by the UI.
    release = check()
    if not release["newer"] or not release["asset"]: raise ValueError("没有适合当前系统的新版安装包")
    asset = release["asset"]
    name = asset['name']
    directory = profile / "updates" / release["version"]
    directory.mkdir(parents=True, exist_ok=True)
    def open_asset(item):
        url = item["browser_download_url"]
        if not url.startswith(PREFIX + "v" + release["version"] + "/"): raise ValueError("更新地址无效")
        return read_url(url)
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        checksum = next((a for a in release["assets"] if a["name"] == "SHA256SUMS.txt"), None)
        if not checksum: raise ValueError("更新包缺少校验信息")
        with open_asset(checksum) as response: lines = response.read(1024 * 1024).decode().splitlines()
        digest = next(("sha256:" + p[0] for line in lines if len(p := line.split()) == 2 and p[1].lstrip("*") == name), "")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest): raise ValueError("更新包校验信息无效")
    partial = directory / (name + ".part")
    target = directory / name
    hasher = hashlib.sha256()
    count = 0
    expected = int(asset["size"])
    if expected <= 0: raise ValueError("更新包大小无效")
    try:
        with open_asset(asset) as response, partial.open("wb") as out:
            while chunk := response.read(256 * 1024):
                count += len(chunk)
                if count > expected: raise ValueError("更新包大小不符")
                out.write(chunk)
                hasher.update(chunk)
        if count != expected or hasher.hexdigest() != digest[7:].lower(): raise ValueError("更新包校验失败，请重试")
        partial.replace(target)
        return dict(path=str(target), version=release["version"])
    finally:
        partial.unlink(missing_ok=True)
