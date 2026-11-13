"""Native full-screen capture used by the annotation overlay."""

from __future__ import annotations

import base64
import io
import os
import platform
import subprocess
import tempfile
from pathlib import Path


def _darwin_capture() -> tuple[bytes, int, int]:
    """Use macOS's native capture path instead of Pillow's slow 5K grab."""
    fd, name = tempfile.mkstemp(prefix="research-screenshot-", suffix=".png")
    os.close(fd)
    path = Path(name)
    try:
        subprocess.run(
            ["/usr/sbin/screencapture", "-x", "-t", "png", str(path)],
            check=True,
            timeout=15,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        data = path.read_bytes()
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            return data, image.width, image.height
    finally:
        path.unlink(missing_ok=True)


def capture() -> dict[str, object]:
    if platform.system() not in {"Windows", "Darwin"}:
        raise ValueError("截图工具目前支持 Windows 和 macOS。")
    raw_data: bytes | None = None
    width = height = 0
    try:
        if platform.system() == "Darwin":
            try:
                raw_data, width, height = _darwin_capture()
            except Exception:
                # Pillow remains a fallback for environments where the native
                # command is unavailable or screen recording permission is
                # being granted for the first time.
                raw_data = None
        from PIL import ImageGrab

        # Pillow only implements the multi-monitor flag on Windows.  Passing
        # it on macOS makes the capture fail before the native screen API is
        # even attempted.  Use a single-screen fallback for older Pillow and
        # for Windows sessions where all_screens is unavailable.
        if raw_data is None:
            if platform.system() == "Windows":
                try:
                    image = ImageGrab.grab(all_screens=True)
                except TypeError:
                    image = ImageGrab.grab()
            else:
                image = ImageGrab.grab()
            width, height = image.width, image.height
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=False, compress_level=1)
            raw_data = output.getvalue()
    except Exception as exc:  # pragma: no cover - requires a real desktop session
        detail = str(exc).strip()
        suffix = f"（{detail}）" if detail else ""
        raise ValueError(f"无法读取屏幕内容，请检查系统录屏权限后重试{suffix}。") from exc
    data = raw_data
    if len(data) > 32 * 1024 * 1024:
        raise ValueError("截图过大，请缩小显示区域后重试。")
    return {
        "mime": "image/png",
        "width": width,
        "height": height,
        "base64": base64.b64encode(data).decode("ascii"),
    }

