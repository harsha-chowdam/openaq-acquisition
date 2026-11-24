#!/usr/bin/env python3
"""
Comprehensive Year-Parameterized Raw Acquisition Integrity & Container Audit
Supports:
- Year parameterization (--year=YYYY)
- Reconciliation against global or year-specific manifest
- Container offset and header continuity verification
- Exhaustive Month 01 byte validation & Month 02-12 statistical sampling
- Production of structured JSON completion report (reports/acquisition_report_{year}.json)
- Dry-run pre-flight check mode (--dry-run)
- Strict non-zero exit code on missing or corrupt files
"""

import os
import sys
import gzip
import csv
import hashlib
import time
import tarfile
import random
import argparse
import json
import datetime
from collections import defaultdict

PROJECT_DIR = os.environ.get("OPENAQ_PROJECT_DIR", "/home/harsha/openaq")
DEFAULT_MANIFEST = os.path.join(PROJECT_DIR, "manifest/s3_manifest_modern.csv.gz")
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")

def run_audit(target_year="2025", manifest_path=DEFAULT_MANIFEST, dry_run=False, sample_size_per_month=1000):
    start_time = time.time()
    start_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw_year_dir = os.path.join(PROJECT_DIR, f"raw/s3_modern/year={target_year}")
    report_path = os.path.join(REPORTS_DIR, f"acquisition_report_{target_year}.json")
    os.makedirs(REPORTS_DIR, exist_ok=True)

    print("=" * 80)
    print(f"RAW ACQUISITION INTEGRITY & CONTAINER AUDIT: YEAR {target_year} (Dry-Run: {dry_run})")
    print(f"Timestamp: {start_time_iso}")
    print(f"Manifest:  {manifest_path}")
    print(f"Raw Dir:   {raw_year_dir}")
    print(f"Report:    {report_path}")
    print("=" * 80)

    # 1. Load and filter Manifest for target year
    print(f"\n[Step 1/5] Loading and filtering manifest for year={target_year}...")
    manifest_keys = set()
    manifest_total_bytes = 0
    t0 = time.time()
    
    if not os.path.exists(manifest_path):
        print(f"FATAL: Manifest path {manifest_path} does not exist!")
        sys.exit(1)

    with gzip.open(manifest_path, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        key_idx = header.index("s3_key") if header and "s3_key" in header else 3
        year_idx = header.index("year") if header and "year" in header else 1
        month_idx = header.index("month") if header and "month" in header else 2
        size_idx = header.index("size_bytes") if header and "size_bytes" in header else 4

        for row in reader:
            if len(row) > max(key_idx, year_idx, month_idx, size_idx):
                k = row[key_idx]
                yr = row[year_idx]
                mo = row[month_idx]
                # Skip non-measurement files or malformed entries (e.g. .DS_Store)
                if not mo.isdigit() or not k.endswith('.csv.gz'):
                    continue
                if yr == str(target_year):
                    manifest_keys.add(k)
                    manifest_total_bytes += int(row[size_idx])

    load_time = time.time() - t0
    print(f"  -> Manifest loaded in {load_time:.2f}s")
    print(f"  -> Target Year {target_year} Objects: {len(manifest_keys):,}")
    print(f"  -> Target Year Compressed Volume: {manifest_total_bytes:,} bytes ({manifest_total_bytes / (1024**3):.3f} GB)")

    if len(manifest_keys) == 0:
        print(f"FATAL: No manifest records found for year {target_year}!")
        sys.exit(1)

    # Handle dry-run mode
    if dry_run:
        print("\n[DRY-RUN] Checking container paths and index presence without performing full byte audit...")
        existing_containers = 0
        existing_indexes = 0
        if os.path.exists(raw_year_dir):
            for m in range(1, 13):
                m_str = f"{m:02d}"
                if os.path.exists(os.path.join(raw_year_dir, f"month={m_str}.tar")):
                    existing_containers += 1
                if os.path.exists(os.path.join(raw_year_dir, f"month={m_str}.idx")):
                    existing_indexes += 1
        print(f"  -> Existing physical containers: {existing_containers}/12")
        print(f"  -> Existing index files:         {existing_indexes}/12")

        report_data = {
            "year": str(target_year),
            "status": "DRY_RUN_PASSED",
            "start_time_utc": start_time_iso,
            "end_time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "duration_seconds": round(time.time() - start_time, 2),
            "expected_files": len(manifest_keys),
            "expected_bytes": manifest_total_bytes,
            "existing_containers": existing_containers,
            "existing_indexes": existing_indexes,
            "dry_run": True,
            "audit_passed": True
        }
        with open(report_path, 'w', encoding='utf-8') as rf:
            json.dump(report_data, rf, indent=2)
        print(f"\nDry-run report generated: {report_path}")
        print("=" * 80)
        print("DRY-RUN AUDIT COMPLETED SUCCESSFULLY")
        print("=" * 80)
        return True

    # 2. Audit Index Files and TAR Container Alignment
    print(f"\n[Step 2/5] Auditing Monthly TAR Indexes and Container Offsets (Months 01-12)...")
    all_index_keys = set()
    month_stats = {}
    duplicate_keys = []
    offset_errors = []
    size_mismatches = []
    missing_containers = []
    
    total_index_entries = 0
    total_compressed_bytes = 0
    total_tar_bytes = 0

    for m in range(1, 13):
        month_str = f"{m:02d}"
        idx_path = os.path.join(raw_year_dir, f"month={month_str}.idx")
        tar_path = os.path.join(raw_year_dir, f"month={month_str}.tar")
        
        if not os.path.exists(idx_path):
            print(f"  ERROR: Missing index file: {idx_path}")
            missing_containers.append(f"month={month_str}.idx")
            continue
        if not os.path.exists(tar_path):
            print(f"  ERROR: Missing tar file: {tar_path}")
            missing_containers.append(f"month={month_str}.tar")
            continue

        tar_actual_size = os.path.getsize(tar_path)
        total_tar_bytes += tar_actual_size
        
        entries = []
        expected_next_offset = 0
        month_bytes = 0
        
        with open(idx_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            idx_header = next(reader, None)
            for row in reader:
                if len(row) >= 6:
                    s3_k = row[0]
                    tar_offset = int(row[1])
                    byte_length = int(row[2])
                    file_size = int(row[3])
                    etag = row[4]
                    sha256 = row[5]
                    retrieved_at = row[6] if len(row) > 6 else ""
                    
                    if s3_k in all_index_keys:
                        duplicate_keys.append((month_str, s3_k))
                    all_index_keys.add(s3_k)
                    
                    if tar_offset != expected_next_offset:
                        offset_errors.append((month_str, s3_k, tar_offset, expected_next_offset))
                    
                    expected_next_offset = tar_offset + byte_length
                    month_bytes += file_size
                    entries.append((s3_k, tar_offset, byte_length, file_size, etag, sha256, retrieved_at))

        if tar_actual_size != expected_next_offset:
            size_mismatches.append((month_str, tar_actual_size, expected_next_offset))
            
        month_stats[month_str] = {
            'count': len(entries),
            'compressed_bytes': month_bytes,
            'tar_size': tar_actual_size,
            'entries': entries
        }
        total_index_entries += len(entries)
        total_compressed_bytes += month_bytes
        
        print(f"  Month {month_str}: {len(entries):,d} files | TAR: {tar_actual_size / (1024**2):.2f} MB | Offsets Contiguous: {len(offset_errors) == 0}")

    # 3. Set Reconciliation
    print(f"\n[Step 3/5] Reconciling Manifest vs Indexed Archive...")
    missing_from_archive = manifest_keys - all_index_keys
    dangling_in_archive = all_index_keys - manifest_keys
    
    print(f"  -> Missing Manifest Entries:         {len(missing_from_archive):,}")
    print(f"  -> Dangling / Unmanifested Entries:  {len(dangling_in_archive):,}")

    # 4. Exhaustive Byte-Level Audit on Month 01
    m01_corrupt = 0
    m01_sha_mismatch = 0
    m01_gzip_error = 0
    m01_count = 0
    
    if '01' in month_stats and month_stats['01']['count'] > 0:
        print(f"\n[Step 4/5] Exhaustive Byte-Level Audit on Month 01...")
        m01_stats = month_stats['01']
        m01_entries = m01_stats['entries']
        m01_count = len(m01_entries)
        tar01_path = os.path.join(raw_year_dir, "month=01.tar")
        
        print(f"  Verifying all {m01_count:,} members in month=01.tar (SHA-256 + Gzip CRC)...")
        t_m01 = time.time()
        
        with open(tar01_path, 'rb') as tf:
            for idx, (s3_k, tar_offset, byte_length, file_size, etag, sha256_exp, _) in enumerate(m01_entries):
                tf.seek(tar_offset)
                hdr = tf.read(512)
                if len(hdr) < 512:
                    m01_corrupt += 1
                    continue
                
                payload = tf.read(file_size)
                if len(payload) != file_size:
                    m01_corrupt += 1
                    continue
                    
                actual_sha = hashlib.sha256(payload).hexdigest()
                if actual_sha.lower() != sha256_exp.lower():
                    m01_sha_mismatch += 1
                    
                try:
                    decomp = gzip.decompress(payload)
                    if len(decomp) == 0:
                        m01_gzip_error += 1
                except Exception:
                    m01_gzip_error += 1
                    
                if (idx + 1) % 100000 == 0:
                    print(f"    Verified {idx+1:,} / {m01_count:,} files ({time.time() - t_m01:.1f}s)...")

        print(f"  -> Month 01 Complete: Corrupt={m01_corrupt}, SHA Mismatches={m01_sha_mismatch}, Gzip Errors={m01_gzip_error}")

    # 5. Statistical Sampling on Months 02-12
    print(f"\n[Step 5/5] Statistical Sampling on Months 02-12 ({sample_size_per_month:,} files/month)...")
    sample_corrupt = 0
    sample_sha_mismatch = 0
    sample_gzip_error = 0
    total_sampled = 0
    t_samp = time.time()
    
    for m in range(2, 13):
        m_str = f"{m:02d}"
        if m_str not in month_stats:
            continue
        entries = month_stats[m_str]['entries']
        if not entries:
            continue
        sample_entries = random.sample(entries, min(sample_size_per_month, len(entries)))
        tar_path = os.path.join(raw_year_dir, f"month={m_str}.tar")
        
        with open(tar_path, 'rb') as tf:
            for s3_k, tar_offset, byte_length, file_size, etag, sha256_exp, _ in sample_entries:
                total_sampled += 1
                tf.seek(tar_offset + 512)
                payload = tf.read(file_size)
                
                if len(payload) != file_size:
                    sample_corrupt += 1
                    continue
                actual_sha = hashlib.sha256(payload).hexdigest()
                if actual_sha.lower() != sha256_exp.lower():
                    sample_sha_mismatch += 1
                try:
                    decomp = gzip.decompress(payload)
                    if len(decomp) == 0:
                        sample_gzip_error += 1
                except Exception:
                    sample_gzip_error += 1

    print(f"  -> Sampled {total_sampled:,} files across months 02-12 in {time.time() - t_samp:.2f}s")
    print(f"  -> Sample Corrupt={sample_corrupt}, SHA Mismatches={sample_sha_mismatch}, Gzip Errors={sample_gzip_error}")

    # Final Evaluation & Structured JSON Report
    duration = round(time.time() - start_time, 2)
    end_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    audit_passed = (
        len(missing_containers) == 0 and
        len(missing_from_archive) == 0 and
        len(dangling_in_archive) == 0 and
        len(offset_errors) == 0 and
        len(size_mismatches) == 0 and
        m01_corrupt == 0 and
        m01_sha_mismatch == 0 and
        m01_gzip_error == 0 and
        sample_corrupt == 0 and
        sample_sha_mismatch == 0 and
        sample_gzip_error == 0
    )

    status_str = "SUCCESS" if audit_passed else "FAILED"

    report_data = {
        "year": str(target_year),
        "status": status_str,
        "start_time_utc": start_time_iso,
        "end_time_utc": end_time_iso,
        "duration_seconds": duration,
        "expected_files": len(manifest_keys),
        "acquired_files": total_index_entries,
        "missing_files_count": len(missing_from_archive),
        "dangling_files_count": len(dangling_in_archive),
        "expected_bytes": manifest_total_bytes,
        "actual_compressed_bytes": total_compressed_bytes,
        "tar_container_bytes": total_tar_bytes,
        "containers_verified": f"{12 - len(missing_containers)}/12",
        "missing_containers": missing_containers,
        "offset_gaps_overlaps": len(offset_errors),
        "size_mismatches": len(size_mismatches),
        "duplicate_keys": len(duplicate_keys),
        "integrity_check": {
            "month_01_exhaustive": {
                "verified": m01_count,
                "corrupt": m01_corrupt,
                "sha256_mismatches": m01_sha_mismatch,
                "gzip_errors": m01_gzip_error
            },
            "months_02_12_sampling": {
                "sampled": total_sampled,
                "corrupt": sample_corrupt,
                "sha256_mismatches": sample_sha_mismatch,
                "gzip_errors": sample_gzip_error
            }
        },
        "dry_run": False,
        "audit_passed": audit_passed
    }

    if missing_from_archive:
        report_data["missing_files_sample"] = list(missing_from_archive)[:10]

    with open(report_path, 'w', encoding='utf-8') as rf:
        json.dump(report_data, rf, indent=2)

    print("\n" + "=" * 80)
    print(f"STAGE 2 AUDIT SUMMARY REPORT: YEAR {target_year}")
    print("=" * 80)
    print(f"Overall Status:             {status_str}")
    print(f"Manifest Total Entries:     {len(manifest_keys):,}")
    print(f"Index Total Entries:        {total_index_entries:,}")
    match_pct = (len(all_index_keys) / len(manifest_keys) * 100) if manifest_keys else 0
    print(f"Manifest Match Rate:        {match_pct:.2f}% ({len(all_index_keys):,} / {len(manifest_keys):,})")
    print(f"Physical Containers:        {12 - len(missing_containers)} / 12 verified")
    print(f"Offset Gaps / Overlaps:     {len(offset_errors)}")
    print(f"Size Mismatches:            {len(size_mismatches)}")
    print(f"Month 01 Exhaustive:        Passed ({m01_count:,} files, 0 errors)" if (m01_corrupt + m01_sha_mismatch + m01_gzip_error == 0) else "FAILED")
    print(f"Months 02-12 Sampling:      Passed ({total_sampled:,} files sampled, 0 errors)" if (sample_corrupt + sample_sha_mismatch + sample_gzip_error == 0) else "FAILED")
    print(f"Report Written To:          {report_path}")
    print(f"Total Audit Execution Time: {duration:.2f} seconds")
    print("=" * 80)

    if not audit_passed:
        print(f"\nFATAL: Integrity audit FAILED for year {target_year}! Exiting with code 1.")
        sys.exit(1)

    print(f"\nAudit completed with 100% integrity match for year {target_year}.")
    return True

def main():
    parser = argparse.ArgumentParser(description="OpenAQ Raw Acquisition Integrity & Container Audit")
    parser.add_argument("--year", type=str, default="2025", help="Target year to audit (default: 2025)")
    parser.add_argument("--manifest-path", type=str, default=DEFAULT_MANIFEST, help=f"Path to manifest (default: {DEFAULT_MANIFEST})")
    parser.add_argument("--dry-run", action="store_true", help="Perform pre-flight manifest check and path validation without reading container contents")
    parser.add_argument("--sample-size", type=int, default=1000, help="Number of files to sample per month for months 02-12 (default: 1000)")
    args = parser.parse_args()

    run_audit(
        target_year=args.year,
        manifest_path=args.manifest_path,
        dry_run=args.dry_run,
        sample_size_per_month=args.sample_size
    )

if __name__ == "__main__":
    main()
