import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop_layout_sync as sync
from desktop_layout_sync import _layout_records, parse


class DesktopLayoutSyncTests(unittest.TestCase):
    @staticmethod
    def _record(path, name, index):
        path_bytes = path.encode("utf-16le") + b"\x00\x00"
        name_bytes = name.encode("utf-16le") + b"\x00\x00"
        return (
            b"s" + struct.pack("<I", len(path_bytes)) + path_bytes
            + b"s" + struct.pack("<I", len(name_bytes)) + name_bytes
            + b"\x64\x04\x00\x00\x00" + struct.pack("<i", index)
            + b"\x64\x04\x00\x00\x00" + struct.pack("<i", -1)
            + b"\x42\x04\x00\x00\x00"
        )

    def test_dtfence_index_field_is_parsed_without_decoding_unknown_binary(self):
        path = "C:\\Users\\Public\\Desktop\\demo.lnk".encode("utf-16le") + b"\x00\x00"
        name = "演示".encode("utf-16le") + b"\x00\x00"
        data = (
            b"\x53\xb4\x00\x00\x00"
            + b"\x73" + struct.pack("<I", len(path)) + path
            + b"\x73" + struct.pack("<I", len(name)) + name
            + b"\x64\x04\x00\x00\x00" + struct.pack("<i", 12)
            + b"\x64\x04\x00\x00\x00" + struct.pack("<i", -1)
            + b"\x42\x04\x00\x00\x00"
        )
        result = parse(data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], "C:\\Users\\Public\\Desktop\\demo.lnk")
        self.assertEqual(result[0]["name"], "演示")
        self.assertEqual(result[0]["index"], 12)

    def test_metadata_tail_is_not_treated_as_an_icon(self):
        records = [
            {"path": "C:\\demo.lnk", "name": "演示", "index": 3, "offset": 1},
            {"path": "C:\\desktop.ini", "name": "C:\\desktop.ini", "index": 1, "offset": 2},
            {"path": "", "name": "回收站", "index": -1, "offset": 3},
        ]
        result = _layout_records(records)
        self.assertEqual([item["name"] for item in result], ["演示"])

    def test_adjacent_records_keep_their_names_and_namespace_paths(self):
        data = self._record("C:\\Users\\Public\\Desktop\\a.lnk", "甲图", 0)
        data += self._record("::{2CC5CA98-6485-489A-920E-B3E88A6CCCE3}", "Learn about this picture", 1)
        result = _layout_records(parse(data))
        self.assertEqual([(item["path"], item["name"]) for item in result], [
            ("C:\\Users\\Public\\Desktop\\a.lnk", "甲图"),
            ("::{2CC5CA98-6485-489A-920E-B3E88A6CCCE3}", "Learn about this picture"),
        ])

    def test_parser_respects_string_lengths_without_nul_terminators(self):
        path = "C:\\Users\\Public\\Desktop\\demo.exe".encode("utf-16le")
        name = "演示程序".encode("utf-16le")
        # Real DTFence files commonly omit the NUL terminator.  The next
        # ``s`` marker must not be decoded as the final path character.
        data = (
            b"s" + struct.pack("<I", len(path)) + path
            + b"s" + struct.pack("<I", len(name)) + name
            + b"\x64\x04\x00\x00\x00" + struct.pack("<i", 4)
            + b"\x64\x04\x00\x00\x00" + struct.pack("<i", -1)
            + b"\x42\x04\x00\x00\x00"
        )
        result = _layout_records(parse(data))
        self.assertEqual(result[0]["path"], "C:\\Users\\Public\\Desktop\\demo.exe")
        self.assertEqual(result[0]["name"], "演示程序")

    @staticmethod
    def _current(icons):
        return {
            "icons": icons,
            "display": {
                "width": 1920,
                "height": 1080,
                "spacing": [76, 100],
                "workareas": [{"left": 0, "top": 0, "right": 1920, "bottom": 1032}],
            },
        }

    def test_system_from_360_keeps_slot_gaps(self):
        data = self._record("C:\\Users\\Public\\Desktop\\a.lnk", "甲图", 0)
        data += self._record("C:\\Users\\Public\\Desktop\\b.lnk", "乙图", 2)
        records = parse(data)
        current = self._current([
            {"key": "C:\\Users\\Public\\Desktop\\a.lnk", "name": "甲图", "x": 14, "y": 2},
            {"key": "C:\\Users\\Public\\Desktop\\b.lnk", "name": "乙图", "x": 90, "y": 2},
        ])
        with patch.object(sync, "_read_records", return_value=(Path("/tmp/DTFenceData.dtf"), data, records)):
            result = sync.system_from_360(current)
        by_name = {item["name"]: (item["x"], item["y"]) for item in result["items"]}
        self.assertEqual(by_name, {"甲图": (14, 2), "乙图": (14, 202)})

    def test_system_to_360_detects_position_change_with_same_order(self):
        data = self._record("C:\\Users\\Public\\Desktop\\a.lnk", "甲图", 0)
        data += self._record("C:\\Users\\Public\\Desktop\\b.lnk", "乙图", 1)
        records = parse(data)
        current = self._current([
            {"key": "C:\\Users\\Public\\Desktop\\a.lnk", "name": "甲图", "x": 14, "y": 2},
            {"key": "C:\\Users\\Public\\Desktop\\b.lnk", "name": "乙图", "x": 14, "y": 202},
        ])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "DTFenceData.dtf"
            path.write_bytes(data)
            with patch.object(sync, "_read_records", return_value=(path, data, records)), patch.object(sync.assistant, "probe", return_value={"running": False}):
                result = sync.system_to_360(current)
                verification = sync.verify_system_to_360(result)
        self.assertEqual((result["matched_count"], result["changed_count"]), (2, 1))
        self.assertEqual(verification["mismatches"], 0)

    def _sync_data(self, data, icons):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "DTFenceData.dtf"
            path.write_bytes(data)
            with patch.object(sync, "_read_records", return_value=(path, data, parse(data))), patch.object(sync.assistant, "probe", return_value={"running": False}):
                result = sync.system_to_360(self._current(icons))
                verification = sync.verify_system_to_360(result)
            return result, verification, path.read_bytes()

    def test_unmatched_360_record_moves_aside_for_windows_position(self):
        a, b, extra = r"C:\Desktop\a.lnk", r"C:\Desktop\b.lnk", r"C:\Desktop\old.lnk"
        data = self._record(a, "A", 4) + self._record(b, "B", 5) + self._record(extra, "Old", 0)
        result, verification, output = self._sync_data(data, [
            {"key": a, "name": "A", "x": 14, "y": 2},
            {"key": b, "name": "B", "x": 14, "y": 102},
        ])
        positions = {record["path"]: record["index"] for record in parse(output)}
        self.assertEqual(positions, {a: 0, b: 1, extra: 2})
        self.assertEqual((result["fallback_count"], result["relocated_count"]), (0, 1))
        self.assertEqual(verification["mismatches"], 0)
        # Only known index bytes may change, including in relocated records.
        restored = bytearray(output)
        for record in parse(data):
            offset = record["offset"] + 5
            restored[offset:offset + 4] = data[offset:offset + 4]
        self.assertEqual(bytes(restored), data)

    def test_conflict_fallback_does_not_take_a_later_windows_target(self):
        a, b, c = r"C:\Desktop\a.lnk", r"C:\Desktop\b.lnk", r"C:\Desktop\c.lnk"
        data = self._record(a, "A", 4) + self._record(b, "B", 5) + self._record(c, "C", 6)
        result, verification, output = self._sync_data(data, [
            {"key": a, "name": "A", "x": 14, "y": 2},
            {"key": b, "name": "B", "x": 14, "y": 2},
            {"key": c, "name": "C", "x": 14, "y": 102},
        ])
        self.assertEqual({r["path"]: r["index"] for r in parse(output)}, {a: 0, b: 2, c: 1})
        self.assertEqual((result["fallback_count"], result["position_conflicts"]), (1, 1))
        self.assertEqual(verification["verified_count"], 3)

    def test_off_grid_icon_with_a_record_gets_an_empty_slot(self):
        a, b = r"C:\Desktop\a.lnk", r"C:\Desktop\b.lnk"
        data = self._record(a, "A", 4) + self._record(b, "B", 5)
        result, verification, output = self._sync_data(data, [
            {"key": a, "name": "A", "x": 14, "y": 2},
            {"key": b, "name": "B", "x": 14, "y": -998},
        ])
        positions = {r["path"]: r["index"] for r in parse(output)}
        self.assertEqual((positions[a], positions[b]), (0, 1))
        self.assertEqual((result["position_unmapped_count"], result["fallback_count"], result["ignored_count"]), (1, 1, 0))
        self.assertEqual(verification["verified_count"], 2)

    def test_duplicate_path_no_longer_causes_repeated_false_failure(self):
        a, b = r"C:\Desktop\a.lnk", r"C:\Desktop\b.lnk"
        data = self._record(a, "A", 0) + self._record(b, "B", 1) + self._record(a, "A-old", 0)
        icons = [
            {"key": a, "name": "A", "x": 14, "y": 2},
            {"key": b, "name": "B", "x": 14, "y": 102},
        ]
        first, verification, output = self._sync_data(data, icons)
        self.assertEqual([r["index"] for r in parse(output)], [0, 1, 2])
        self.assertEqual(first["relocated_count"], 1)
        self.assertEqual(verification["mismatches"], 0)
        second, verification, repeated = self._sync_data(output, icons)
        self.assertEqual(second["changed_count"], 0)
        self.assertEqual(verification["mismatches"], 0)
        self.assertEqual(repeated, output)

    def test_verification_keeps_duplicate_tokens_and_detects_real_changes(self):
        a = r"C:\Desktop\a.lnk"
        data = self._record(a, "A", 0) + self._record(a, "A-copy", 2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "DTFenceData.dtf"
            path.write_bytes(data)
            result = {"dtf_path": str(path), "expected_positions": [
                {"token": sync._token(a), "index": 0},
                {"token": sync._token(a), "index": 1},
            ]}
            verification = sync.verify_system_to_360(result)
        self.assertEqual((verification["expected_count"], verification["verified_count"], verification["mismatches"]), (2, 1, 1))
        self.assertEqual(verification["sample"][0]["expected_index"], 1)

    def test_windows_icon_without_a_record_is_reported_without_inventing_binary(self):
        a, extra, new = r"C:\Desktop\a.lnk", r"C:\Desktop\old.lnk", r"C:\Desktop\new.lnk"
        data = self._record(a, "A", 0) + self._record(extra, "Old", 2)
        result, verification, output = self._sync_data(data, [
            {"key": a, "name": "A", "x": 14, "y": 2},
            {"key": new, "name": "New", "x": 14, "y": 102},
        ])
        self.assertEqual(result["ignored_count"], 1)
        self.assertIn("1 个 Windows 图标在 360 中没有可匹配记录", result["message"])
        self.assertEqual(output, data)
        self.assertEqual(verification["mismatches"], 0)

    def test_insufficient_space_does_not_write_partial_layout(self):
        a, b = r"C:\Desktop\a.lnk", r"C:\Desktop\b.lnk"
        data = self._record(a, "A", 0) + self._record(b, "B", 0)
        current = self._current([{"key": a, "name": "A", "x": 0, "y": 0}])
        current["display"]["workareas"] = [{"left": 0, "top": 0, "right": 76, "bottom": 100}]
        with patch.object(sync, "_read_records", return_value=(Path("/unused.dtf"), data, parse(data))), patch.object(sync.assistant, "probe", return_value={"running": False}), patch.object(sync, "_write") as write:
            with self.assertRaisesRegex(ValueError, "没有足够"):
                sync.system_to_360(current)
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
