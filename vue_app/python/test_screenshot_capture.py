import importlib.util
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
