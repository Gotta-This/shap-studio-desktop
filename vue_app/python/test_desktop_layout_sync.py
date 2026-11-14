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

    def test_system_to_360_preserves_existing_dtf_gaps(self):
        data = self._record("C:\\Users\\Public\\Desktop\\a.lnk", "甲图", 0)
        data += self._record("C:\\Users\\Public\\Desktop\\b.lnk", "乙图", 2)
        records = parse(data)
        current = {"icons": [
            {"key": "C:\\Users\\Public\\Desktop\\a.lnk", "name": "甲图", "x": 0, "y": 0},
            {"key": "C:\\Users\\Public\\Desktop\\b.lnk", "name": "乙图", "x": 0, "y": 100},
        ]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "DTFenceData.dtf"
            path.write_bytes(data)
            with patch.object(sync, "_read_records", return_value=(path, data, records)), patch.object(sync.assistant, "probe", return_value={"running": False}):
                result = sync.system_to_360(current)
        self.assertEqual((result["matched_count"], result["changed_count"]), (2, 0))


if __name__ == "__main__":
    unittest.main()
