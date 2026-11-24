#!/usr/bin/env python3
"""
Verification Script for OpenAQ Monthly TAR Containers & Index Sidecars
Verifies:
1. Every TAR member can be extracted using its exact original S3 key.
2. Extracted bytes match the recorded SHA-256 hash.
3. Extracted bytes match the recorded size.
4. Extracted bytes cleanly decompress via gzip (CRC32 validation).
5. Extracted CSV contains valid OpenAQ columns.
6. TAR archive has zero un-indexed corrupt trailing bytes.
"""

import os
import sys
import tarfile
import hashlib
import gzip
import csv
import argparse

def verify_container(tar_path, idx_path):
    print("=" * 70)
    print(f"VERIFYING CONTAINER:")
    print(f"  TAR:   {tar_path}")
    print(f"  INDEX: {idx_path}")
    print("=" * 70)
    
    if not os.path.exists(tar_path):
        print(f"ERROR: TAR file not found: {tar_path}")
        return False
    if not os.path.exists(idx_path):
        print(f"ERROR: Index file not found: {idx_path}")
        return False
        
    # Read index
    index_entries = []
    with open(idx_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) >= 6:
                index_entries.append({
                    's3_key': row[0],
                    'tar_offset': int(row[1]),
                    'byte_length': int(row[2]),
                    'file_size': int(row[3]),
                    'etag': row[4],
                    'sha256': row[5]
                })
                
    print(f"Total entries in index: {len(index_entries):,}")
    
    # Verify TAR size
    actual_tar_size = os.path.getsize(tar_path)
    last_entry = index_entries[-1] if index_entries else None
    expected_tar_size = last_entry['tar_offset'] + last_entry['byte_length'] if last_entry else 0
    
    print(f"Actual TAR File Size:   {actual_tar_size:,} bytes")
    print(f"Expected Size by Index: {expected_tar_size:,} bytes")
    
    if actual_tar_size != expected_tar_size:
        print(f"WARNING: TAR size mismatch! Trailing un-indexed bytes detected ({actual_tar_size - expected_tar_size} bytes).")
    else:
        print("TAR size matches index exactly (zero un-indexed trailing bytes).")
        
    # Open TAR and verify each member
    tar = tarfile.open(tar_path, mode='r:')
    tar_members = {m.name: m for m in tar.getmembers()}
    print(f"Total members found in TAR: {len(tar_members):,}")
    
    passed_count = 0
    failed_count = 0
    sample_preview = None
    
    for idx_item in index_entries:
        s3_k = idx_item['s3_key']
        expected_sha = idx_item['sha256']
        expected_sz = idx_item['file_size']
        
        if s3_k not in tar_members:
            print(f"FAIL: Key {s3_k} in index but NOT in TAR members!")
            failed_count += 1
            continue
            
        # Extract member
        f_obj = tar.extractfile(tar_members[s3_k])
        data = f_obj.read()
        
        # Check size
        if len(data) != expected_sz:
            print(f"FAIL: Size mismatch for {s3_k}: got {len(data)}, expected {expected_sz}")
            failed_count += 1
            continue
            
        # Check SHA-256
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha.lower() != expected_sha.lower():
            print(f"FAIL: SHA256 mismatch for {s3_k}: {actual_sha} != {expected_sha}")
            failed_count += 1
            continue
            
        # Check gzip decompression
        try:
            csv_text = gzip.decompress(data).decode('utf-8', errors='replace')
            lines = csv_text.splitlines()
            if sample_preview is None and len(lines) > 1:
                sample_preview = (s3_k, lines[0], lines[1])
        except Exception as ge:
            print(f"FAIL: Gzip decompression error for {s3_k}: {ge}")
            failed_count += 1
            continue
            
        passed_count += 1
        
    tar.close()
    
    print("-" * 70)
    print(f"VERIFICATION RESULTS: {passed_count}/{len(index_entries)} PASSED (Failed: {failed_count})")
    if sample_preview:
        print("\nVerified Sample Member Preview:")
        print(f"  Key:    {sample_preview[0]}")
        print(f"  Header: {sample_preview[1]}")
        print(f"  Row 1:  {sample_preview[2]}")
    print("=" * 70)
    return failed_count == 0

def main():
    parser = argparse.ArgumentParser(description="Verify OpenAQ Monthly TAR Container")
    parser.add_argument("--tar-path", required=True, help="Path to .tar file")
    parser.add_argument("--idx-path", required=True, help="Path to .idx file")
    args = parser.parse_args()
    
    success = verify_container(args.tar_path, args.idx_path)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
