# Data Integrity Verification & Audit Framework

**Documentation Date:** 2026-11-25  
**Component:** Automated Integrity Verification Subsystem  
**Key Script:** `bin/audit_acquisition_integrity.py`  

---

## 1. Multi-Tier Verification Philosophy

Given the scale of the OpenAQ historical dataset (25.58 million files across 20 years), data corruption, bit rot, truncated downloads, or split-brain write collisions could easily pass unnoticed without rigorous mathematical verification.

The pipeline enforces a **three-tier defense-in-depth model**:
1. **Tier 1 (In-flight S3 Ingestion):** Immediate validation of byte length, MD5 ETag matching, and SHA-256 calculation prior to TAR container appending.
2. **Tier 2 (Physical Container Geometry):** Verification of byte-offset contiguity, 512-byte block alignment, and strict physical archive size equivalence against index sidecars.
3. **Tier 3 (Cryptographic & Decompression Auditing):** 100% exhaustive SHA-256 and Gzip CRC32 decompression on Month 01, combined with statistical sampling (11,000 files/year) across Months 02–12.

---

## 2. 5-Stage Audit Architecture (`audit_acquisition_integrity.py`)

When Stage 2 executes, it performs five sequential verification stages:

### Stage 1: Full Set Reconciliation
- Reads all records for target year from `manifest/s3_manifest_modern.csv.gz` into set $M$.
- Reads all records from `raw/s3_modern/year=YYYY/month=*.idx` into set $I$.
- Calculates:
  - Missing Objects: $M \setminus I$ (must be $\emptyset$).
  - Dangling Objects: $I \setminus M$ (must be $\emptyset$).
  - Duplicate Keys: Keys appearing $> 1$ time in index (must be 0).

### Stage 2: Physical Container Geometry & Offset Contiguity
- For each month container (`month=01.tar` through `month=12.tar`), reads index entries sorted by `tar_offset`.
- Verifies contiguity invariant:
  $$\text{tar\_offset}_{i+1} = \text{tar\_offset}_i + \text{byte\_length}_i$$
- Verifies termination invariant:
  $$\text{Total Size of .tar on Disk} = \text{tar\_offset}_N + \text{byte\_length}_N$$
- Detects any unindexed padding gaps, overlapping entries, or truncated records.

### Stage 3: Month 01 100% Exhaustive Cryptographic & Gzip Audit
- For January (`month=01.tar`), audits **every single file**:
  1. Seeks directly to `tar_offset + 512`.
  2. Reads exact `file_size` bytes.
  3. Computes `hashlib.sha256(data).hexdigest()` and verifies it matches `index.sha256`.
  4. Decompresses stream using `gzip.decompress(data)`. Gzip natively validates the internal RFC 1952 CRC32 checksum and uncompressed byte size.
  5. Any CRC error, EOF error, or SHA mismatch increments `corrupt` count.

### Stage 4: Months 02–12 Statistical Sampling
- Draws $S=1,000$ random files per month from Months 02 through 12 (11,000 total files sampled per year).
- Performs the identical direct-seek, SHA-256 verification, and full gzip decompression check on each sample.

### Stage 5: Structured JSON Report Generation
- Emits standardized report to `reports/acquisition_report_<YEAR>.json`.
- Exits with return code `0` if all tests pass, or code `1` if any failure is detected.

---

## 3. JSON Audit Report Schema

Every audited year produces a standardized JSON report:

```json
{
  "year": "2024",
  "status": "SUCCESS",
  "start_time_utc": "2026-11-19T06:29:38.194619+00:00",
  "end_time_utc": "2026-11-19T06:30:51.491097+00:00",
  "duration_seconds": 73.3,
  "expected_files": 3707241,
  "acquired_files": 3707241,
  "missing_files_count": 0,
  "dangling_files_count": 0,
  "expected_bytes": 3928203292,
  "actual_compressed_bytes": 3928203292,
  "tar_container_bytes": 6727756288,
  "containers_verified": "12/12",
  "missing_containers": [],
  "offset_gaps_overlaps": 0,
  "size_mismatches": 0,
  "duplicate_keys": 0,
  "integrity_check": {
    "month_01_exhaustive": {
      "verified": 247965,
      "corrupt": 0,
      "sha256_mismatches": 0,
      "gzip_errors": 0
    },
    "months_02_12_sampling": {
      "sampled": 11000,
      "corrupt": 0,
      "sha256_mismatches": 0,
      "gzip_errors": 0
    }
  },
  "dry_run": false,
  "audit_passed": true
}
```

### Passing Criteria Invariants
An acquisition year is certified **100% SUCCESSFUL** if and only if:
1. `status == "SUCCESS"`
2. `missing_files_count == 0` and `dangling_files_count == 0`
3. `expected_files == acquired_files`
4. `expected_bytes == actual_compressed_bytes`
5. `offset_gaps_overlaps == 0`
6. `corrupt == 0`, `sha256_mismatches == 0`, and `gzip_errors == 0` across all exhaustive and sampled checks.
7. `audit_passed == true`

---

## 4. Re-running Integrity Audits on Demand

To independently audit any historical year at any time:

```bash
# Run full 5-stage audit on Year 2024
/home/harsha/openaq/venv/bin/python /home/harsha/openaq/bin/audit_acquisition_integrity.py 2024

# Run fast dry-run check (verifies manifest and container paths without reading bytes)
/home/harsha/openaq/venv/bin/python /home/harsha/openaq/bin/audit_acquisition_integrity.py 2024 --dry-run

# Run audit with custom sample size (e.g. 5,000 files/month)
/home/harsha/openaq/venv/bin/python /home/harsha/openaq/bin/audit_acquisition_integrity.py 2024 --sample-size=5000
```
