import struct
import unittest

from desktop_layout_sync import parse


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


if __name__ == "__main__":
    unittest.main()
