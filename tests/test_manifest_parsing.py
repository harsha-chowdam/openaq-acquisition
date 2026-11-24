#!/usr/bin/env python3
"""
Unit tests for S3 key parsing, temporal partition extraction, and month normalization.
"""

import unittest

def parse_s3_key_partitions(key):
    """Replicates the partition parsing logic of the acquisition engine."""
    parts = key.split('/')
    yr = 'unknown'
    mo = 'unknown'
    for part in parts:
        if part.startswith('year='):
            yr = part.split('=')[1]
        elif part.startswith('month='):
            raw_mo = part.split('=')[1]
            mo = f"{int(raw_mo):02d}" if raw_mo.isdigit() else raw_mo
    return yr, mo

class TestManifestParsing(unittest.TestCase):
    def test_standard_modern_key(self):
        key = "records/csv.gz/locationid=10/year=2024/month=05/location-10-20240512.csv.gz"
        yr, mo = parse_s3_key_partitions(key)
        self.assertEqual(yr, "2024")
        self.assertEqual(mo, "05")

    def test_single_digit_month_normalization(self):
        """Historical S3 partitions with month=3 must normalize to month=03."""
        key = "records/csv.gz/locationid=55/year=2016/month=3/location-55-20160315.csv.gz"
        yr, mo = parse_s3_key_partitions(key)
        self.assertEqual(yr, "2016")
        self.assertEqual(mo, "03")

    def test_rogue_object_detection(self):
        key = "records/csv.gz/locationid=61488/year=2019/.DS_Store"
        yr, mo = parse_s3_key_partitions(key)
        self.assertEqual(yr, "2019")
        self.assertEqual(mo, "unknown")
        # In pipeline: if not mo.isdigit() or not k.endswith('.csv.gz'): skip
        is_valid = mo.isdigit() and key.endswith('.csv.gz')
        self.assertFalse(is_valid, "Rogue non-CSV or unknown-month objects must be rejected")

if __name__ == "__main__":
    unittest.main()
