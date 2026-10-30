"""Release selection, verified downloads and non-modal sidebar behavior."""
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtWidgets import QApplication
from clinical_studio.updates import (
    APP_VERSION, DOWNLOAD_PREFIX, UpdateController, UpdateFooter, UpdateWorker,
    asset_name, download_release, select_release, version_tuple,
)

APP = QApplication.instance() or QApplication([])


def release_fixture(data=b"verified installer", manifest=False):
    name = "ResearchDataTools-Setup-Windows-x64.exe"
    digest = hashlib.sha256(data).hexdigest()
    asset = dict(name=name, size=len(data), browser_download_url=DOWNLOAD_PREFIX + "v9.0.0/" + name)
    assets = [asset]
    if manifest:
        assets.append(dict(name="SHA256SUMS.txt", browser_download_url=DOWNLOAD_PREFIX + "v9.0.0/SHA256SUMS.txt"))
    else:
        asset["digest"] = "sha256:" + digest
    return dict(version="9.0.0", newer=True, asset=asset, assets=assets)


class ReleaseTests(unittest.TestCase):
    def test_numeric_versions_and_stable_releases(self):
        self.assertGreater(version_tuple("v1.0.100"), version_tuple("1.0.99"))
        payload = dict(tag_name="v" + APP_VERSION, assets=[])
        self.assertFalse(select_release(payload, None)["newer"])
        payload["tag_name"] = "v9.0.0"
        self.assertTrue(select_release(payload, None)["newer"])
        payload["prerelease"] = True
        with self.assertRaises(ValueError):
            select_release(payload, None)
        for version in ("latest", "v1.2.3-beta", "../1.2.3"):
            with self.assertRaises(ValueError):
                version_tuple(version)

    def test_platform_and_installation_selection(self):
        self.assertIn("Setup", asset_name("win32", "AMD64", True))
        self.assertIn("Portable", asset_name("win32", "AMD64", False))
        self.assertEqual(asset_name("darwin", "arm64"), "ResearchDataTools-macOS-arm64.zip")
        self.assertEqual(asset_name("darwin", "x86_64"), "ResearchDataTools-macOS-x86_64.zip")
        self.assertIsNone(asset_name("linux", "x86_64"))
        self.assertIsNone(asset_name("win32", "arm64"))

    def test_digest_and_manifest_downloads(self):
        data = b"verified installer"
        for manifest in (False, True):
            release = release_fixture(data, manifest)
            def response(url):
                if url.endswith("SHA256SUMS.txt"):
                    return io.BytesIO((hashlib.sha256(data).hexdigest() + "  " + release["asset"]["name"]).encode())
                return io.BytesIO(data)
            with tempfile.TemporaryDirectory() as temp, patch("clinical_studio.updates.open_download", side_effect=response):
                values = []
                result = download_release(release, Path(temp), values.append, lambda: False)
                self.assertEqual(result.read_bytes(), data)
                self.assertEqual(values[-1], 100)
                self.assertFalse(list(Path(temp).glob("*.part")))

    def test_corrupt_truncated_and_cancelled_downloads_are_removed(self):
        release = release_fixture()
        for data, cancelled in ((b"bad", False), (b"x" * release["asset"]["size"], False), (b"verified installer", True)):
            with tempfile.TemporaryDirectory() as temp, patch("clinical_studio.updates.open_download", return_value=io.BytesIO(data)):
                with self.assertRaises((ValueError, InterruptedError)):
                    download_release(release, Path(temp), lambda value: None, lambda: cancelled)
                self.assertEqual(list(Path(temp).iterdir()), [])

    def test_missing_checksum_and_untrusted_url_rejected(self):
        from clinical_studio.updates import open_download
        release = release_fixture()
        release["asset"].pop("digest")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                download_release(release, Path(temp), lambda value: None, lambda: False)
        for url in ("http://github.com/file", "https://example.com/file", "https://github.com/other/repo/releases/download/test.exe"):
            with self.assertRaises(ValueError):
                open_download(url)

    def test_https_uses_bundled_roots_and_verifies_hosts(self):
        import ssl
        from clinical_studio.updates import https_context
        with patch("clinical_studio.updates.ssl.create_default_context", return_value=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)):
            context = https_context()
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)


class FakeWindow(QObject):
    busy = False

    def has_running_tasks(self):
        return self.busy

    def close(self):
        self.closed = True


class SidebarUpdateTests(unittest.TestCase):
    def setUp(self):
        self.window = FakeWindow()
        self.controller = UpdateController(self.window, auto_check=False)

    def tearDown(self):
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def complete(self, result=None, error=None, release=None):
        worker = UpdateWorker(release)
        worker.result, worker.error = result, error
        self.controller.worker = worker
        self.controller.finished()

    def test_all_footers_share_status_without_modal(self):
        footers = [UpdateFooter(self.controller), UpdateFooter(self.controller)]
        self.complete(dict(newer=False))
        self.assertTrue(all(f.status.text() == "已是最新" for f in footers))
        self.complete(release_fixture())
        self.assertTrue(all(f.status.text() == "有新版 V9.0.0" for f in footers))
        self.assertTrue(all(f.button.text() == "立即更新" for f in footers))
        self.complete(error="offline")
        self.assertTrue(all(f.status.text() == "检查失败" for f in footers))
        self.assertIsNone(APP.activeModalWidget())
        for footer in footers:
            footer.deleteLater()

    def test_missing_platform_asset_is_visible(self):
        self.complete(dict(version="9.0.0", newer=True, asset=None))
        self.assertEqual(self.controller.action, "重新检查")
        self.assertIn("当前系统", self.controller.detail)

    def test_busy_task_blocks_installer_then_allows_retry(self):
        self.controller.downloaded = Path("/tmp/update.exe")
        self.window.busy = True
        with patch("clinical_studio.updates.subprocess.Popen") as launch:
            self.controller.install()
            launch.assert_not_called()
            self.assertEqual(self.controller.action, "安装更新")
            self.window.busy = False
            self.controller.activate()
            launch.assert_called_once()
            self.assertTrue(self.window.closed)

    def test_archive_opening_failure_is_inline_and_retryable(self):
        self.controller.downloaded = Path("/tmp/update.zip")
        with patch("clinical_studio.updates.QDesktopServices.openUrl", return_value=False):
            self.controller.install()
        self.assertEqual(self.controller.message, "无法打开更新包")
        self.assertEqual(self.controller.action, "重试")
        self.assertIsNone(APP.activeModalWidget())

    def test_worker_check_failure_returns_to_retry(self):
        with patch("clinical_studio.updates.urlopen", side_effect=OSError("offline")):
            self.controller.check()
            worker = self.controller.worker
            self.assertTrue(worker.wait(2000))
            APP.processEvents()
        self.assertIsNone(self.controller.worker)
        self.assertEqual(self.controller.message, "检查失败")
        self.assertEqual(self.controller.action, "重试")

    def test_close_waits_for_worker_cancellation(self):
        worker = UpdateWorker()
        self.controller.worker = worker
        self.assertFalse(self.controller.prepare_close())
        observed = []
        self.controller.idle.connect(lambda: observed.append(True))
        self.controller.finished()
        self.assertEqual(observed, [True])
        self.assertTrue(self.controller.prepare_close())

    def test_sidebar_stays_at_bottom_when_resizing_and_switching(self):
        from clinical_studio.strict_ui import DesktopWindow
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"CLINICAL_STUDIO_TODO_PATH": str(Path(temp) / "todos.json")}):
            window = DesktopWindow()
            window.timer.stop()
            window.show()
            try:
                window.updates.show_status("有新版 V9.0.0", "立即更新")
                for index, size in ((0, (1440, 960)), (9, (1008, 672)), (0, (1200, 800))):
                    window.show_board(index)
                    window.resize(*size)
                    APP.processEvents()
                    view = window.views[index]
                    footer = view.footer
                    self.assertIs(footer.parentWidget(), view.viewport())
                    self.assertEqual(footer.status.text(), "有新版 V9.0.0")
                    self.assertEqual(footer.button.text(), "立即更新")
                    self.assertEqual(footer.x(), 20)
                    self.assertEqual(footer.y(), view.viewport().height() - 110)
                    self.assertLess(footer.geometry().bottom(), view.viewport().height())
                    self.assertLess(footer.button.geometry().bottom(), footer.height())
                self.assertIsNone(APP.activeModalWidget())
            finally:
                window.close()
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
