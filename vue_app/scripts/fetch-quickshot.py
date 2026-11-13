"""Fetch the pinned QuickShot release binary for the current Tauri target."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.3.0"
ASSETS = {
    "aarch64-apple-darwin": (
        "https://github.com/simmzl/QuickShot/releases/download/v1.3.0/QuickShot-1.3.0.dmg",
        "058208aa00667eaf590102a4f6cb82ef719dd272d0124ed938ed4f61b148760d",
    ),
    "x86_64-apple-darwin": (
        "https://github.com/simmzl/QuickShot/releases/download/v1.3.0/QuickShot-1.3.0.dmg",
        "058208aa00667eaf590102a4f6cb82ef719dd272d0124ed938ed4f61b148760d",
    ),
    "x86_64-pc-windows-msvc": (
        "https://github.com/simmzl/QuickShot/releases/download/v1.3.0/QuickShot-1.3.0-windows-x64.zip",
        "ec90bb471283aafb969cee6906f4ec0535400087ce1638cff99a687f72603ae3",
    ),
}


def download(url: str, digest: str, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    hasher = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
            hasher.update(chunk)
    if hasher.hexdigest() != digest:
        partial.unlink(missing_ok=True)
        raise RuntimeError("QuickShot 下载校验失败")
    partial.replace(destination)


def main() -> None:
    target = os.environ.get("TAURI_ENV_TARGET_TRIPLE")
    if target not in ASSETS:
        raise SystemExit(f"QuickShot 暂不支持目标平台：{target}")
    root = Path(__file__).resolve().parents[1]
    binaries = root / "src-tauri" / "binaries"
    resources = root / "src-tauri" / "resources" / "quickshot"
    binaries.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    url, digest = ASSETS[target]
    suffix = ".exe" if target.endswith("windows-msvc") else ""
    output = binaries / f"quickshot-{target}{suffix}"
    with tempfile.TemporaryDirectory(prefix="quickshot-") as folder:
        archive = Path(folder) / ("QuickShot.dmg" if url.endswith(".dmg") else "QuickShot.zip")
        download(url, digest, archive)
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as package:
                entry = next(name for name in package.namelist() if name.endswith("QuickShot.exe"))
                output.write_bytes(package.read(entry))
        else:
            mount = Path(folder) / "mount"
            mount.mkdir()
            subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(archive)], check=True, stdout=subprocess.DEVNULL)
            try:
                app_bundle = mount / "QuickShot.app"
                shutil.copy2(app_bundle / "Contents" / "MacOS" / "QuickShot", output)
                bundled_app = resources / "QuickShot.app"
                if bundled_app.exists():
                    shutil.rmtree(bundled_app)
                shutil.copytree(app_bundle, bundled_app)
            finally:
                subprocess.run(["hdiutil", "detach", str(mount)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output.chmod(0o755)
    print(f"QuickShot {VERSION}: {output}")


if __name__ == "__main__":
    main()
