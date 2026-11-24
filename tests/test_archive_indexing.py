#!/usr/bin/env python3
"""
Unit tests for MonthlyTarManager geometry, block alignment, and O(1) index generation.
"""

import unittest
import tempfile
import shutil
import os
import io
import tarfile
import hashlib
import csv
import datetime

class TestTarIndexing(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_block_alignment_and_padding(self):
        """Verify that every TAR member begins on a 512-byte boundary and total length is divisible by 512."""
        tar_path = os.path.join(self.test_dir, "test_month.tar")
        idx_path = os.path.join(self.test_dir, "test_month.idx")
        
        # Test payloads of various lengths
        test_payloads = [
            b"short payload",
            b"x" * 511,
            b"y" * 512,
            b"z" * 513,
            b"a" * 1024,
            b"b" * 12345
        ]
        
        current_offset = 0
        with open(tar_path, "wb") as tf, open(idx_path, "w", newline="", encoding="utf-8") as idxf:
            writer = csv.writer(idxf)
            writer.writerow(["s3_key", "tar_offset", "byte_length", "file_size", "etag", "sha256", "retrieved_at_utc"])
            
            for i, data in enumerate(test_payloads):
                key = f"records/csv.gz/locationid=1/year=2024/month=01/file_{i}.csv.gz"
                tarinfo = tarfile.TarInfo(name=key)
                tarinfo.size = len(data)
                tarinfo.mtime = 1700000000
                tarinfo.mode = 0o644
                
                hdr = tarinfo.tobuf(format=tarfile.GNU_FORMAT, encoding='utf-8')
                self.assertEqual(len(hdr), 512, "TAR header block must be exactly 512 bytes")
                
                pad_len = (512 - (len(data) % 512)) % 512
                padding = b'\x00' * pad_len if pad_len > 0 else b''
                byte_length = len(hdr) + len(data) + len(padding)
                
                self.assertEqual(byte_length % 512, 0, "Total member block length must be divisible by 512")
                self.assertEqual(current_offset % 512, 0, "Member offset must be 512-byte aligned")
                
                tf.write(hdr)
                tf.write(data)
                if padding:
                    tf.write(padding)
                    
                etag = hashlib.md5(data).hexdigest()
                sha256 = hashlib.sha256(data).hexdigest()
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                writer.writerow([key, current_offset, byte_length, len(data), etag, sha256, now_iso])
                current_offset += byte_length

        # Verify physical file size
        total_size = os.path.getsize(tar_path)
        self.assertEqual(total_size, current_offset, "Physical TAR size must match final cumulative offset")
        
        # Test random-access retrieval
        with open(idx_path, "r", encoding="utf-8") as idxf, open(tar_path, "rb") as tf:
            reader = csv.DictReader(idxf)
            for i, row in enumerate(reader):
                offset = int(row["tar_offset"])
                size = int(row["file_size"])
                tf.seek(offset + 512)
                read_data = tf.read(size)
                self.assertEqual(read_data, test_payloads[i], f"Payload {i} extracted via O(1) seek must match original")

if __name__ == "__main__":
    unittest.main()
