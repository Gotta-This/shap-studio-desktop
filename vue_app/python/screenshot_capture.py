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

        image = ImageGrab.grab(all_screens=True)
    except Exception as exc:  # pragma: no cover - requires a real desktop session
        raise ValueError("无法读取屏幕内容，请检查系统录屏权限后重试。") from exc
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

