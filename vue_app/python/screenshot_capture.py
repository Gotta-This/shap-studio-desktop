"""Native full-screen capture used by the annotation overlay."""

from __future__ import annotations

import base64
import io
import platform


def capture() -> dict[str, object]:
    if platform.system() not in {"Windows", "Darwin"}:
        raise ValueError("截图工具目前支持 Windows 和 macOS。")
    try:
        from PIL import ImageGrab

        # Pillow only implements the multi-monitor flag on Windows.  Passing
        # it on macOS makes the capture fail before the native screen API is
        # even attempted.  Use a single-screen fallback for older Pillow and
        # for Windows sessions where all_screens is unavailable.
        if platform.system() == "Windows":
            try:
                image = ImageGrab.grab(all_screens=True)
            except TypeError:
                image = ImageGrab.grab()
        else:
            image = ImageGrab.grab()
    except Exception as exc:  # pragma: no cover - requires a real desktop session
        detail = str(exc).strip()
        suffix = f"（{detail}）" if detail else ""
        raise ValueError(f"无法读取屏幕内容，请检查系统录屏权限后重试{suffix}。") from exc
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    data = output.getvalue()
    if len(data) > 32 * 1024 * 1024:
        raise ValueError("截图过大，请缩小显示区域后重试。")
    return {
        "mime": "image/png",
        "width": image.width,
        "height": image.height,
        "base64": base64.b64encode(data).decode("ascii"),
    }

