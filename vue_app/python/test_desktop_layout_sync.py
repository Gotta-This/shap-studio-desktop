import struct
import unittest

from desktop_layout_sync import _layout_records, parse


class DesktopLayoutSyncTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
