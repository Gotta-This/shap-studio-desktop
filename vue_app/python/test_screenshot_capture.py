import importlib.util
import sys
import types
import unittest
from unittest.mock import Mock, patch

from screenshot_capture import capture


class ScreenshotCaptureTests(unittest.TestCase):
    @patch("screenshot_capture.platform.system", return_value="Linux")
    def test_unsupported_platform_has_clear_error(self, _system):
        with self.assertRaisesRegex(ValueError, "支持 Windows 和 macOS"):
            capture()

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is provided by the packaged scientific environment")
    @patch("screenshot_capture.platform.system", return_value="Darwin")
    @patch("PIL.ImageGrab.grab", return_value=type("FakeImage", (), {"width": 2, "height": 3, "save": lambda self, output, format, optimize: output.write(b"png-data")})())
    def test_capture_encodes_png(self, _grab, _system):
        result = capture()
        self.assertEqual(result["mime"], "image/png")
        self.assertEqual(result["width"], 2)
        self.assertEqual(result["height"], 3)
        self.assertEqual(result["base64"], "cG5nLWRhdGE=")

    def test_macos_capture_does_not_pass_windows_only_flag(self):
        image = type("FakeImage", (), {"width": 2, "height": 3, "save": lambda self, output, format, optimize: output.write(b"png-data")})()
        grab = Mock(return_value=image)
        pil = types.ModuleType("PIL")
        image_grab = types.ModuleType("PIL.ImageGrab")
        image_grab.grab = grab
        pil.ImageGrab = image_grab
        with patch.dict(sys.modules, {"PIL": pil, "PIL.ImageGrab": image_grab}), patch(
            "screenshot_capture.platform.system", return_value="Darwin"
        ):
            capture()
        grab.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
