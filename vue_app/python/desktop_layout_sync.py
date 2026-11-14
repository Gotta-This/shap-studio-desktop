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
import hashlib
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
    return ("".join(chars), pos) if chars else None


def _string_field(data: bytes, marker_pos: int, limit: int) -> tuple[str, int] | None:
    """Decode a DTF ``s<length><UTF-16LE payload>`` field exactly.

    DTFence records do not consistently include a UTF-16 NUL terminator in
    the payload.  Reading until the next binary field therefore consumes the
    first two bytes of that field as a Chinese character (for example the
    ``sT`` marker becomes ``味``).  The declared byte length is the reliable
    boundary and must be preferred.
    """
    if marker_pos < 0 or marker_pos + 5 > limit or data[marker_pos] != 0x73:
        return None
    length = struct.unpack_from("<I", data, marker_pos + 1)[0]
    if length < 2 or length > 2000 or length % 2:
        return None
    start = marker_pos + 5
    end = start + length
    if end > limit or end > len(data):
        return None
    try:
        text = data[start:end].decode("utf-16le", errors="strict").rstrip("\x00")
    except UnicodeDecodeError:
        return None
    return (text, end) if text else None


def _looks_like_path(value: str) -> bool:
    value = value.strip()
    return bool(re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|::)", value))


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
        path = ""
        name = ""
        string_fields: list[tuple[int, str, int]] = []
        for marker_pos in range(window_start, offset - 5):
            field = _string_field(data, marker_pos, offset)
            if field:
                value, end = field
                string_fields.append((marker_pos, value, end))
        path_fields = [field for field in string_fields if _looks_like_path(field[1])]
        if path_fields:
            _, path, path_end = path_fields[-1]
            # The display name follows the path field.  Use the last exact
            # string field before the index marker, excluding path fields.
            names = [field[1] for field in string_fields if field[0] >= path_end and not _looks_like_path(field[1])]
            if names:
                name = names[-1]
        else:
            # Namespace-only records (Recycle Bin, wallpaper item, etc.) may
            # not have a path-like field.  Their last string field is the name.
            names = [field[1] for field in string_fields if not _looks_like_path(field[1])]
            if names:
                name = names[-1]
        records.append({"path": path, "name": name, "index": index, "offset": offset})
    return records


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip())


def _basename(value: str) -> str:
    return re.split(r"[\\/]", value)[-1].casefold()


def _path_norm(value: str) -> str:
    value = value.strip().replace("/", "\\")
    value = re.sub(r"^file:\\+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\\\\\?\\", "", value)
    return _norm(value)


def _name_variants(value: str) -> set[str]:
    value = _norm(value)
    if not value:
        return set()
    values = {value}
    stem = re.sub(r"\.(?:lnk|url|exe)$", "", value)
    stem = re.sub(r"\s+-\s*(?:快捷方式|shortcut)$", "", stem)
    values.add(stem)
    return {item for item in values if item}


def _token(value: str) -> str:
    return hashlib.sha256(_norm(value).encode("utf-8")).hexdigest()[:12]


def _match_details(record: dict[str, Any], icons: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    path = _path_norm(str(record.get("path", "")))
    name_variants = _name_variants(str(record.get("name", "")))
    base_variants = _name_variants(_basename(str(record.get("path", ""))))
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for icon in icons:
        key = _path_norm(str(icon.get("key", "")))
        icon_names = _name_variants(str(icon.get("name", "")))
        icon_bases = _name_variants(_basename(str(icon.get("key", ""))))
        if path and key and path == key:
            scored.append((100, "path", icon))
        elif name_variants & icon_names:
            scored.append((90, "name", icon))
        elif base_variants & icon_bases:
            scored.append((80, "basename", icon))
        elif name_variants & icon_bases or base_variants & icon_names:
            scored.append((70, "stem", icon))
    if not scored:
        return None, None
    best_score = max(item[0] for item in scored)
    best = [(reason, icon) for score, reason, icon in scored if score == best_score]
    unique = {str(icon.get("key", "")).casefold(): (reason, icon) for reason, icon in best}
    if len(unique) != 1:
        return None, "ambiguous"
    reason, icon = next(iter(unique.values()))
    return icon, reason


def _match(record: dict[str, Any], icons: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _match_details(record, icons)[0]


def _layout_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return actual icon records and discard DTF metadata tail markers.

    Some 360DesktopLite files contain a final marker whose decoded name and
    path are the same ``desktop.ini`` path.  It is not an icon record, but it
    looks like one if every integer field is treated as an index.  Never write
    a Windows ordering into that metadata slot.
    """
    return [
        record
        for record in records
        if record["index"] >= 0
        and record["name"]
        and _norm(record["name"]) != _norm(record["path"])
        and not (_basename(record["path"]) == "desktop.ini" and _norm(record["name"]) == _norm(record["path"]))
    ]


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
    layout_records = _layout_records(records)
    ordered = sorted(layout_records, key=lambda item: (item["index"], item["name"].casefold()))
    matched: list[dict[str, Any]] = []
    used: set[str] = set()
    match_modes: dict[str, int] = {"path": 0, "name": 0, "basename": 0, "stem": 0, "ambiguous": 0, "unmatched": 0}
    for record in ordered:
        icon, reason = _match_details(record, current["icons"])
        if icon and icon["key"].casefold() not in used:
            matched.append(icon)
            used.add(icon["key"].casefold())
            match_modes[reason or "unmatched"] = match_modes.get(reason or "unmatched", 0) + 1
        elif reason == "ambiguous":
            match_modes["ambiguous"] += 1
        else:
            match_modes["unmatched"] += 1
    if not matched:
        raise ValueError(f"未找到可匹配的 360 桌面图标（360记录 {len(layout_records)}，Windows图标 {len(current['icons'])}），未修改 Windows 排列。请确认 360 与 Windows 使用的是同一批桌面快捷方式。")
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
        "missing_count": max(0, len(layout_records) - len(matched)),
        "dtf_records": len(layout_records),
        "match_modes": match_modes,
        "dtf_path": str(path),
        "message": f"已按 360 排列匹配 {len(matched)} 个图标，额外的 {len(extras)} 个系统图标放到空白网格。",
    }


def system_to_360(current: dict[str, Any]) -> dict[str, Any]:
    state = assistant.probe()
    if state.get("running"):
        raise ValueError("请先退出 360 桌面助手，再把 Windows 排列写入 360。")
    path, data, records = _read_records()
    layout_records = _layout_records(records)
    ordered_icons = sorted(current["icons"], key=lambda item: (item["x"], item["y"], item["name"].casefold()))
    matched: list[dict[str, Any]] = []
    used: set[str] = set()
    match_modes: dict[str, int] = {"path": 0, "name": 0, "basename": 0, "stem": 0, "ambiguous": 0, "unmatched": 0}
    for icon in ordered_icons:
        record = None
        reason = None
        for candidate in layout_records:
            if candidate["offset"] in used:
                continue
            candidate_icon, candidate_reason = _match_details(candidate, [icon])
            if candidate_icon:
                record, reason = candidate, candidate_reason
                break
        if record:
            matched.append(record)
            used.add(record["offset"])
            match_modes[reason or "unmatched"] = match_modes.get(reason or "unmatched", 0) + 1
        elif reason == "ambiguous":
            match_modes["ambiguous"] += 1
        else:
            match_modes["unmatched"] += 1
    if not matched:
        raise ValueError(f"未找到可匹配的 Windows 桌面图标（360记录 {len(layout_records)}，Windows图标 {len(current['icons'])}），未修改 360 排列。请确认 360 与 Windows 使用的是同一批桌面快捷方式。")
    remaining = [record for record in layout_records if record["offset"] not in used]
    # Keep slots that 360 already reserves for records we cannot see in the
    # current Windows desktop.  The DTF samples legitimately contain gaps
    # (for example a 360-only item at slot 34); collapsing those gaps shifts
    # every later icon even when the two layouts are already identical.
    slots = sorted(record["index"] for record in layout_records if record["offset"] in used)
    changed = 0
    output = bytearray(data)
    for record, index in zip(matched, slots):
        offset = record["offset"]
        value = struct.unpack_from("<i", output, offset + 5)[0]
        if value != index:
            struct.pack_into("<i", output, offset + 5, index)
            changed += 1
    if changed:
        backup = path.with_suffix(path.suffix + ".bk")
        _write(backup, data)
        _write(path, bytes(output))
    return {
        "matched_count": len(matched),
        "missing_count": len(remaining),
        "ignored_count": max(0, len(current["icons"]) - len(matched)),
        "changed_count": changed,
        "dtf_records": len(layout_records),
        "match_modes": match_modes,
        "dtf_path": str(path),
        "message": f"已将 Windows 顺序写入 360，匹配 {len(matched)} 个图标，忽略 {len(remaining) + max(0, len(current['icons']) - len(matched))} 个无法双向匹配的图标。",
    }

