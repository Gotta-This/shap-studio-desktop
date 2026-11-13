"""Best-effort bridge between Windows Shell positions and 360 DTFence order.

DTFenceData.dtf is a private binary format. The adapter intentionally changes
only the small integer slot field that is stable across the supplied before /
after samples; unknown records are preserved byte-for-byte.
"""

from __future__ import annotations

import os
import re
import struct
import tempfile
from pathlib import Path
from typing import Any

import desktop_layout_assistant as assistant

FIELD = b"\x64\x04\x00\x00\x00"
END_FIELD = b"\x42\x04\x00\x00\x00"


def _utf16_run(data: bytes, start: int, limit: int) -> tuple[str, int] | None:
    chars: list[str] = []
    pos = start
    while pos + 1 < limit:
        code = data[pos] | (data[pos + 1] << 8)
        if code == 0 or not (32 <= code <= 126 or 0x3000 <= code <= 0x9FFF):
            break
        chars.append(chr(code))
        pos += 2
    return ("".join(chars), pos) if len(chars) >= 2 else None


def _field_index(data: bytes, start: int) -> tuple[int, int] | None:
    end = min(len(data), start + 220)
    fields: list[tuple[int, int]] = []
    pos = start
    while pos < end:
        pos = data.find(FIELD, pos, end)
        if pos < 0 or pos + 9 > len(data):
            break
        fields.append((pos, struct.unpack_from("<i", data, pos + 5)[0]))
        pos += 1
    for (offset, value), (next_offset, next_value) in zip(fields, fields[1:]):
        if next_value == -1 and data[next_offset + 9 : next_offset + 14] == END_FIELD:
            return offset, value
    return None


def parse(data: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    marker = b"\x64\x04\x00\x00\x00"
    fields: list[tuple[int, int]] = []
    for offset in range(0, len(data) - 22):
        if data[offset : offset + 5] != marker:
            continue
        if data[offset + 9 : offset + 14] != marker:
            continue
        if struct.unpack_from("<i", data, offset + 14)[0] != -1:
            continue
        if data[offset + 18 : offset + 23] != END_FIELD:
            continue
        fields.append((offset, struct.unpack_from("<i", data, offset + 5)[0]))
    for offset, index in fields:
        window_start = max(0, offset - 700)
        path_starts = [
            pos
            for pos in range(window_start, offset - 5, 2)
            if data[pos : pos + 6] == b"C\x00:\x00\\\x00"
        ]
        path = ""
        name = ""
        if path_starts:
            path_start = path_starts[-1]
            path_run = _utf16_run(data, path_start, offset)
            if path_run:
                path, path_end = path_run
                runs: list[str] = []
                for marker_pos in range(path_end, offset - 5):
                    if data[marker_pos] != 0x73:
                        continue
                    length = struct.unpack_from("<I", data, marker_pos + 1)[0]
                    if not 2 <= length <= 2000:
                        continue
                    for start in (marker_pos + 5, marker_pos + 6):
                        run = _utf16_run(data, start, offset)
                        if run and not run[0].startswith("C:\\"):
                            runs.append(run[0])
                            break
                if runs:
                    name = runs[-1]
        if not name:
            # Namespace items such as Recycle Bin have no C:\ path.
            for marker_pos in range(window_start, offset - 5):
                if data[marker_pos] != 0x73:
                    continue
                length = struct.unpack_from("<I", data, marker_pos + 1)[0]
                if not 2 <= length <= 2000:
                    continue
                for start in (marker_pos + 5, marker_pos + 6):
                    run = _utf16_run(data, start, offset)
                    if run:
                        name = run[0]
                        break
        records.append({"path": path, "name": name, "index": index, "offset": offset})
    return records


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip())


def _basename(value: str) -> str:
    return re.split(r"[\\/]", value)[-1].casefold()


def _match(record: dict[str, Any], icons: list[dict[str, Any]]) -> dict[str, Any] | None:
    path = _norm(record["path"])
    name = _norm(record["name"])
    base = _basename(record["path"])
    for icon in icons:
        key = _norm(str(icon.get("key", "")))
        icon_name = _norm(str(icon.get("name", "")))
        if path == key or name == icon_name or base == _basename(key):
            return icon
    return None


def _grid(current: dict[str, Any], count: int) -> list[tuple[int, int]]:
    display = current["display"]
    sx, sy = display["spacing"]
    icons = current["icons"]
    origin_x = min((icon["x"] for icon in icons), default=0) % sx
    origin_y = min((icon["y"] for icon in icons), default=0) % sy
    result: list[tuple[int, int]] = []
    for area in display["workareas"]:
        left = origin_x + ((area["left"] - origin_x + sx - 1) // sx) * sx
        top = origin_y + ((area["top"] - origin_y + sy - 1) // sy) * sy
        for x in range(left, area["right"] - sx + 1, sx):
            for y in range(top, area["bottom"] - sy + 1, sy):
                result.append((x, y))
    return result[:count]


def _write(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".dtf-sync-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _dtf_path() -> Path:
    root = assistant.data_root()
    if not root:
        raise ValueError("未找到 360 数据目录。")
    path = root / "DTFence" / "DTFenceData.dtf"
    if not path.is_file():
        raise ValueError("未找到 360 DTFence 布局文件。")
    return path


def _read_records() -> tuple[Path, bytes, list[dict[str, Any]]]:
    path = _dtf_path()
    data = path.read_bytes()
    records = parse(data)
    if len(records) < 2:
        raise ValueError("360 布局文件中没有足够的可识别图标记录。")
    return path, data, records


def system_from_360(current: dict[str, Any]) -> dict[str, Any]:
    path, data, records = _read_records()
    ordered = sorted(records, key=lambda item: (item["index"], item["name"].casefold()))
    matched: list[dict[str, Any]] = []
    used: set[str] = set()
    for record in ordered:
        icon = _match(record, current["icons"])
        if icon and icon["key"].casefold() not in used:
            matched.append(icon)
            used.add(icon["key"].casefold())
    extras = [icon for icon in current["icons"] if icon["key"].casefold() not in used]
    target_order = matched + sorted(extras, key=lambda item: item["name"].casefold())
    cells = _grid(current, len(target_order))
    if len(cells) < len(target_order):
        raise ValueError("系统桌面没有足够的空白网格放置图标。")
    items = [dict(icon, x=x, y=y) for icon, (x, y) in zip(target_order, cells)]
    return {
        "items": items,
        "matched_count": len(matched),
        "extra_count": len(extras),
        "missing_count": max(0, len(records) - len(matched)),
        "dtf_records": len(records),
        "dtf_path": str(path),
        "message": f"已按 360 排列匹配 {len(matched)} 个图标，额外的 {len(extras)} 个系统图标放到空白网格。",
    }


def system_to_360(current: dict[str, Any]) -> dict[str, Any]:
    state = assistant.probe()
    if state.get("running"):
        raise ValueError("请先退出 360 桌面助手，再把 Windows 排列写入 360。")
    path, data, records = _read_records()
    ordered_icons = sorted(current["icons"], key=lambda item: (item["x"], item["y"], item["name"].casefold()))
    matched: list[dict[str, Any]] = []
    used: set[str] = set()
    record_by_offset: dict[int, dict[str, Any]] = {record["offset"]: record for record in records}
    for icon in ordered_icons:
        record = next((r for r in records if r["offset"] not in used and _match(r, [icon])), None)
        if record:
            matched.append(record)
            used.add(record["offset"])
    remaining = [record for record in records if record["offset"] not in used]
    target = matched + sorted(remaining, key=lambda item: (item["index"], item["name"].casefold()))
    changed = 0
    output = bytearray(data)
    for index, record in enumerate(target):
        offset = record["offset"]
        value = struct.unpack_from("<i", output, offset + 5)[0]
        if value != index:
            struct.pack_into("<i", output, offset + 5, index)
            changed += 1
    if changed:
        _write(path, bytes(output))
        backup = path.with_suffix(path.suffix + ".bk")
        _write(backup, bytes(output))
    return {
        "matched_count": len(matched),
        "missing_count": len(remaining),
        "changed_count": changed,
        "dtf_records": len(records),
        "dtf_path": str(path),
        "message": f"已将 Windows 顺序写入 360，匹配 {len(matched)} 个图标，忽略 {len(remaining)} 个未匹配记录。",
    }

