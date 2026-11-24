# Changelog

All notable changes to the OpenAQ Historical Data Acquisition Pipeline are documented in this file.

## [1.0.0] - 2026-11-25

### Added
- **Core Acquisition Engine (`bin/acquire_s3_archive.py`)**:
  - Direct S3 streaming acquisition with anonymous unsigned access under AWS Open Data sponsorship.
  - ThreadPoolExecutor concurrency pool (default 50 workers) running at ~210 files/second.
  - Constant time O(1) block append into monthly POSIX TAR archives.
  - Synchronous `.idx` sidecar tracking byte offsets, member lengths, payload sizes, ETags, and SHA-256 hashes.
  - Dynamic disk space pre-flight check enforcing `available_bytes >= expected_bytes * 3.0`.
  - Advisory file locking via `fcntl.flock(LOCK_EX | LOCK_NB)` on `/tmp/acquire_year_<YEAR>.lock`.
- **Master Pipeline Runner (`bin/acquire_year.sh`)**:
  - Unattended dual-stage supervisor using `set -euo pipefail`.
  - Dual runner logging using `tee -a logs/acquire_year_<YEAR>.runner.log`.
  - Automated transition to Stage 2 integrity verification upon Stage 1 success.
- **Integrity Auditor (`bin/audit_acquisition_integrity.py`)**:
  - 5-stage verification reconciles manifest set against `.idx` keys (zero missing, zero dangling).
  - Physical container offset contiguity and file size verification (zero gaps, zero overlaps).
  - 100% exhaustive SHA-256 and Gzip CRC32 decompression audit on Month 01.
  - Statistical sampling audit (1,000 files/month) on Months 02 through 12.
  - Standardized JSON completion reports saved to `reports/acquisition_report_<YEAR>.json`.
- **Systemd Service Template (`systemd/openaq-acquire@.service`)**:
  - Parameterized daemon unit supervised by PID 1 with `%I` year mapping.
  - Integration with systemd user lingering (`loginctl enable-linger`) to persist across SSH disconnects.
- **Manifest Utilities**:
  - `bin/save_location_ids.py`: Fast partition discovery scanner finding 56,480 unique location IDs.
  - `bin/generate_manifest.py`: Multi-threaded resumable S3 enumerator with `SIGINT`/`SIGTERM` signal safety.
  - `bin/verify_tar_archive.py`: O(1) random-access TAR extractor verifying direct offset seek.
- **Automated Unit Tests (`tests/`)**:
  - `test_archive_indexing.py`: 512-byte TAR block alignment, padding math, and O(1) random access.
  - `test_manifest_parsing.py`: Hive partition extraction and month normalization.
  - `test_concurrency_lock.py`: POSIX advisory file locking exclusion.

### Fixed
- **Month Partition Collision**: Fixed race condition where unpadded month keys (e.g. `month=3`) in older years (2016–2018) collided with zero-padded containers (`month=03.tar`) by normalizing all months to two digits.
- **Rogue S3 Metadata Crash**: Handled rare `.DS_Store` objects in S3 by filtering non-numeric month keys and non-`.csv.gz` extensions.
- **Crash Recovery**: Added automatic truncation of unindexed trailing partial bytes in TAR files upon process restart.
