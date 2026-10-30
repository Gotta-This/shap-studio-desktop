"""Non-modal release checks and verified downloads, shared by all sidebar views."""
import hashlib
import json
from pathlib import Path
import platform
import re
import ssl
import subprocess
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi

from PySide6.QtCore import QObject, QThread, QTimer, QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from .version import APP_VERSION

REPOSITORY = "Gotta-This/shap-studio-desktop"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"


def https_context():
    # Frozen Python cannot rely on the build machine's OpenSSL CA paths.
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def version_tuple(value):
    match = re.fullmatch(r"[vV]?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("版本号无效")
    return tuple(map(int, match.groups()))


def asset_name(system=None, machine=None, installed=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if system == "win32" and machine in ("amd64", "x86_64", "x64"):
        if installed is None:
            installed = bool(getattr(sys, "frozen", False) and
                             (Path(sys.executable).parent / "unins000.exe").exists())
        return ("ResearchDataTools-Setup-Windows-x64.exe" if installed else
                "ResearchDataTools-Portable-Windows-x64.zip")
    if system == "darwin" and machine in ("arm64", "aarch64", "x86_64", "amd64"):
        arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
        return f"ResearchDataTools-macOS-{arch}.zip"
    return None


def select_release(payload, name):
    tag = payload["tag_name"]
    newer = version_tuple(tag) > version_tuple(APP_VERSION)
    if payload.get("draft") or payload.get("prerelease"):
        raise ValueError("暂未发布稳定版本")
    asset = next((a for a in payload.get("assets", []) if a["name"] == name), None)
    return dict(version=tag.lstrip("vV"), newer=newer, asset=asset,
                assets=payload.get("assets", []))


def open_download(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not url.startswith(DOWNLOAD_PREFIX):
        raise ValueError("更新下载地址无效")
    return urlopen(Request(url, headers={"User-Agent": f"ResearchDataTools/{APP_VERSION}"}), timeout=20,
                   context=https_context())


def download_release(release, directory, progress, cancelled):
    asset = release["asset"]
    name = asset["name"]
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("更新文件名无效")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        checksums = next((a for a in release["assets"] if a["name"] == "SHA256SUMS.txt"), None)
        if not checksums:
            raise ValueError("更新包缺少校验信息")
        with open_download(checksums["browser_download_url"]) as response:
            lines = response.read(1024 * 1024).decode("utf-8").splitlines()
        digest = next(("sha256:" + parts[0] for line in lines
                       if len(parts := line.split()) == 2 and parts[1].lstrip("*") == name), "")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("更新包校验信息无效")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / name
    partial = directory / (name + ".part")
    hasher = hashlib.sha256()
    try:
        received = 0
        expected = int(asset["size"])
        if expected <= 0:
            raise ValueError("更新包大小无效")
        with open_download(asset["browser_download_url"]) as response, partial.open("wb") as output:
            while True:
                if cancelled():
                    raise InterruptedError("已取消更新")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > expected:
                    raise ValueError("更新包大小不符")
                output.write(chunk)
                hasher.update(chunk)
                progress(min(100, received * 100 // expected))
        if cancelled():
            raise InterruptedError("已取消更新")
        if received != expected or hasher.hexdigest() != digest[7:].lower():
            raise ValueError("更新包校验失败，请重试")
        partial.replace(destination)
        return destination
    finally:
        partial.unlink(missing_ok=True)


class UpdateWorker(QThread):
    progress = Signal(int)

    def __init__(self, release=None, parent=None):
        super().__init__(parent)
        self.release = release
        self.result = None
        self.error = None

    def run(self):
        try:
            if self.release is None:
                request = Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                  "User-Agent": f"ResearchDataTools/{APP_VERSION}"})
                with urlopen(request, timeout=15, context=https_context()) as response:
                    payload = json.loads(response.read(2 * 1024 * 1024))
                self.result = select_release(payload, asset_name())
            else:
                cache = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation))
                directory = cache / "ResearchDataTools" / "updates" / self.release["version"]
                self.result = download_release(self.release, directory, self.progress.emit,
                                               self.isInterruptionRequested)
        except Exception as exc:
            self.error = str(exc)


class UpdateController(QObject):
    changed = Signal()
    idle = Signal()

    def __init__(self, window, auto_check=None):
        super().__init__(window)
        self.window = window
        self.worker = None
        self.release = None
        self.downloaded = None
        self.message = "尚未检查更新"
        self.action = "检查更新"
        self.detail = ""
        self.closing = False
        self.timer = QTimer(self)
        self.timer.setInterval(6 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.check)
        if auto_check is None:
            auto_check = getattr(sys, "frozen", False)
        if auto_check:
            self.timer.start()
            QTimer.singleShot(1500, self.check)

    def show_status(self, message, action="", detail=""):
        self.message, self.action, self.detail = message, action, detail
        self.changed.emit()

    def check(self):
        if self.worker or self.closing or self.downloaded:
            return
        self.show_status("正在检查更新…")
        self.start_worker(UpdateWorker(parent=self))

    def start_worker(self, worker):
        self.worker = worker
        worker.progress.connect(lambda value: self.show_status(f"正在下载 {value}%"))
        worker.finished.connect(self.finished)
        worker.start()

    def finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        if self.closing:
            self.idle.emit()
            return
        if worker.error:
            self.show_status("下载失败" if worker.release else "检查失败", "重试", worker.error)
        elif worker.release:
            self.downloaded = worker.result
            self.install()
        else:
            self.release = worker.result
            if self.release["newer"]:
                self.show_status("有新版 V" + self.release["version"],
                                 "立即更新" if self.release["asset"] else "重新检查",
                                 "" if self.release["asset"] else "此版本暂无适合当前系统的更新包")
            else:
                self.show_status("已是最新", "检查更新")

    def activate(self):
        if self.worker:
            return
        if self.downloaded:
            self.install()
        elif self.release and self.release["newer"] and self.release["asset"]:
            self.show_status("正在下载 0%")
            self.start_worker(UpdateWorker(self.release, self))
        else:
            self.check()

    def install(self):
        if self.window.has_running_tasks():
            self.show_status("请等待当前任务完成", "安装更新")
            return
        try:
            if self.downloaded.suffix.lower() == ".exe":
                # The setup wizard owns replacement and relaunch. Do not force
                # close other processes or silently overwrite a portable copy.
                subprocess.Popen([str(self.downloaded), "/SP-", "/NORESTART",
                                  "/NOFORCECLOSEAPPLICATIONS",
                                  f"/DIR={Path(sys.executable).parent}"])
                self.show_status("安装程序已启动")
                self.window.close()
            else:
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.downloaded))):
                    raise OSError("无法打开更新包")
                self.show_status("已下载，请替换应用", "打开更新包", str(self.downloaded))
        except OSError as exc:
            self.show_status("无法打开更新包", "重试", str(exc))

    def prepare_close(self):
        self.closing = True
        self.timer.stop()
        if self.worker:
            self.worker.requestInterruption()
            self.show_status("正在停止更新…")
            return False
        return True


class UpdateFooter(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setStyleSheet("QWidget{background:white;} QLabel{color:#738477;font-size:11px;} "
                           "QPushButton{background:transparent;color:#087B59;border:0;"
                           "text-align:left;padding:0;font-size:12px;min-height:22px;} "
                           "QPushButton:hover{color:#075641;text-decoration:underline;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.version = QLabel(f"当前版本 V{APP_VERSION}")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.button = QPushButton()
        from PySide6.QtCore import Qt
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(controller.activate)
        layout.addWidget(self.version)
        layout.addWidget(self.status)
        layout.addWidget(self.button)
        layout.addStretch()
        controller.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.status.setText(self.controller.message)
        self.status.setToolTip(self.controller.detail)
        self.button.setText(self.controller.action)
        self.button.setVisible(bool(self.controller.action))
        self.button.setAccessibleName(self.controller.action)
