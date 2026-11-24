# OpenAQ Historical Data Acquisition Pipeline Specification

**Documentation Date:** 2026-11-25  
**Component:** OpenAQ Historical Data Acquisition Subsystem  
**Key Scripts:** `bin/acquire_s3_archive.py`, `bin/acquire_year.sh`, `bin/audit_acquisition_integrity.py`, `bin/verify_tar_archive.py`  

---

## 1. High-Level Architecture & Lifecycle

The acquisition pipeline is engineered to download, package, index, and audit 20 years of global air quality measurements (25.58 million objects, 22.72 GB compressed payload) with zero manual intervention, zero data loss, and complete reproducibility.

```
                           +--------------------------------+
                           | s3_manifest_modern.csv.gz      |
                           | (25,587,335 Master S3 Records) |
                           +---------------+----------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
| acquire_year.sh <YEAR>                                                                  |
|                                                                                         |
|  [STAGE 1: ACQUISITION ENGINE (acquire_s3_archive.py)]                                  |
|   1. Acquire Exclusive Advisory Lock (fcntl.flock on /tmp/acquire_year_<YEAR>.lock)     |
|   2. Pre-flight Disk Check (Free partition space >= Expected Year Bytes * 3.0)          |
|   3. Fast-forward Pre-existing .idx Files (Resume capability, skip acquired keys)       |
|   4. Streaming Manifest Filter (Streams only target year, skips non-matching rows)      |
|   5. 50-Worker Concurrent Download Pool (Anonymous S3, exponential backoff)             |
|   6. Byte-level & ETag Validation (Verify payload length and MD5 digest)                |
|   7. O(1) Monthly TAR Append (GNU format, 512-byte aligned blocks)                      |
|   8. Real-time Sidecar Indexing (month=MM.idx updated synchronously)                    |
|                                                                                         |
|  [STAGE 2: INTEGRITY VERIFICATION (audit_acquisition_integrity.py)]                     |
|   1. Set Reconciliation (Manifest keys vs .idx keys: 0 missing, 0 dangling)             |
|   2. Container Geometry Check (Physical TAR size == Last IDX Offset + Length)           |
|   3. Month 01 Exhaustive Decompression (100% SHA-256 and Gzip CRC validation)           |
|   4. Months 02-12 Statistical Sampling (1,000 files/month decompressed)                 |
|   5. Generate Completion Report (/home/harsha/openaq/reports/acquisition_report_<YEAR>.json)|
+-----------------------------------------------------------------------------------------+
```

---

## 2. Core Acquisition Engine: `acquire_s3_archive.py`

### CLI Arguments & Default Values
```text
usage: acquire_s3_archive.py [-h] [--archive-type {modern,legacy}]
                             [--manifest-path MANIFEST_PATH] --year YEAR
                             [--month MONTH] [--location-id LOCATION_ID]
                             [--limit-objects LIMIT_OBJECTS]
                             [--workers WORKERS] [--log-file LOG_FILE]
                             [--dry-run]
```

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--year` | String | **Required** | Target 4-digit calendar year to acquire (e.g. `2024`). |
| `--archive-type` | Choice | `modern` | Archive layout type (`modern` or `legacy`). Modern uses `records/csv.gz/`. |
| `--manifest-path` | String | `/home/harsha/openaq/manifest/s3_manifest_modern.csv.gz` | Path to master compressed manifest. |
| `--workers` | Integer | `50` | Number of concurrent download threads in `ThreadPoolExecutor`. |
| `--month` | String | `None` (All) | Optional: Restrict acquisition to a single month (e.g. `01` or `11`). |
| `--location-id` | String | `None` (All) | Optional: Restrict acquisition to a single location station. |
| `--limit-objects` | Integer | `None` (All) | Optional: Stop after acquiring N objects (used for smoke tests). |
| `--log-file` | String | `None` | Custom path for acquisition log. Defaults to `logs/acquisition_<YEAR>.log`. |
| `--dry-run` | Flag | `False` | Run pre-flight checks, lock checks, and manifest sampling without downloading. |

### Operational Mechanisms

#### A. Concurrency Protection via POSIX Advisory Locking
To prevent split-brain archive corruption or dual execution, `acquire_s3_archive.py` opens a lockfile at:
```text
/home/harsha/openaq/tmp/acquire_year_<YEAR>.lock
```
and applies a non-blocking exclusive lock:
```python
fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```
If another process is already acquiring that year, it immediately terminates with exit code 1.

#### B. Dynamic Pre-Flight Disk Space Verification
Before initiating downloads, the script scans the manifest to calculate total expected payload bytes for the target year. It queries the destination partition's available space and requires:
$$\text{Free Disk Bytes} \ge \text{Expected Payload Bytes} \times 3.0$$
If free disk space is insufficient, the job aborts immediately with a safety error.

#### C. Streaming Manifest Reader
Rather than loading 25.5 million rows into memory, `acquire_s3_archive.py` opens `s3_manifest_modern.csv.gz` as a generator stream (`gzip.open(..., 'rt')`). It reads lines one by one, filters rows where `row[1] == target_year`, and yields work tasks. Memory footprint remains $< 150 \text{ MB}$.

#### D. Month Key Normalization
In older S3 partitions (2016–2018), some keys used unpadded months (e.g. `month=3`). The engine normalizes all months:
```python
month = f"{int(mo):02d}"
```
This guarantees that tasks route to canonical container files (`month=01.tar` through `month=12.tar`), eliminating multi-threaded write collisions.

#### E. Robust Download Worker with Exponential Backoff
Worker threads use anonymous `boto3.client('s3')` with:
- Retry logic: Up to 5 retry attempts per object.
- Exponential backoff jitter: $(0.5 \times 2^{\text{attempt}}) + \text{jitter}$.
- Validation:
  - Byte length: `len(downloaded_bytes) == expected_size`.
  - ETag match: `md5(downloaded_bytes).hexdigest() == s3_etag`.
  - Cryptographic checksum: SHA-256 computed on the fly.

---

## 3. Production Pipeline Runner: `acquire_year.sh`

### Purpose & Shell Robustness
`bin/acquire_year.sh` is the master orchestration shell script invoked by systemd. It enforces strict Bash error handling:
```bash
set -euo pipefail
```
- `-e`: Exit immediately if any command exits with a non-zero status.
- `-u`: Treat unset variables as an error.
- `-o pipefail`: Return the exit status of the last command in the pipeline that failed.

### Usage
```bash
# Acquire year 2024 using 50 workers
/home/harsha/openaq/bin/acquire_year.sh 2024

# Acquire year 2024 specifying 75 workers
/home/harsha/openaq/bin/acquire_year.sh 2024 75
```

### Execution Flow
1. **Stage 1 (Acquisition):**
   ```bash
   $PYTHON "$SCRIPT_DIR/acquire_s3_archive.py" \
       --archive-type modern \
       --manifest-path "$PROJECT_DIR/manifest/s3_manifest_modern.csv.gz" \
       --year "$YEAR" \
       --workers "$WORKERS" \
       --log-file "$LOG_DIR/acquisition_${YEAR}.log" 2>&1 | tee -a "$RUNNER_LOG"
   ```
2. **Stage 2 (Automated Integrity Audit):**
   Upon successful exit of Stage 1 (code 0), it automatically triggers Stage 2:
   ```bash
   $PYTHON "$PROJECT_DIR/audit_acquisition_integrity.py" "$YEAR" 2>&1 | tee -a "$RUNNER_LOG"
   ```
3. **Dual Logging:**
   All stdout and stderr output is simultaneously streamed to the terminal/journal and logged to `/home/harsha/openaq/logs/acquire_year_<YEAR>.runner.log`.

---

## 4. Integrity Auditor: `audit_acquisition_integrity.py`

### 5-Step Verification Methodology
1. **Step 1: Set Reconciliation:**
   Loads all records for the year from `s3_manifest_modern.csv.gz` into memory. Reads all 12 monthly `.idx` files. Reconciles key sets:
   - Identifies any missing objects ($\text{Manifest} \setminus \text{Index}$).
   - Identifies any dangling objects ($\text{Index} \setminus \text{Manifest}$).
2. **Step 2: Physical Container Geometry Verification:**
   Iterates through each `.idx` file in ascending offset order. Verifies:
   - Offset contiguity: Each record's `tar_offset` equals the preceding record's `tar_offset + byte_length`.
   - File termination: Total physical file size on disk equals `last_offset + last_byte_length`.
   - Gaps and overlaps: Must be exactly 0.
3. **Step 3: Month 01 100% Exhaustive Byte Audit:**
   Opens `month=01.tar`. For every single file in January:
   - Seeks directly to payload offset (`tar_offset + 512`).
   - Reads exact `file_size` bytes.
   - Verifies SHA-256 matches index `sha256`.
   - Decompresses gzip stream to verify CRC32 and data integrity.
4. **Step 4: Months 02–12 Statistical Sampling:**
   Draws 1,000 random files per month from Months 02 through 12 (11,000 total files sampled). Performs exact SHA-256 and gzip decompression verification on each sampled file.
5. **Step 5: Completion Report Generation:**
   Writes structured JSON verification report to `reports/acquisition_report_<YEAR>.json`.

---

## 5. Independent Archive Reader: `verify_tar_archive.py`

A standalone utility demonstrating O(1) random-access retrieval without reading earlier entries:
```bash
./venv/bin/python bin/verify_tar_archive.py <YEAR> <MONTH> <S3_KEY>
```
- Looks up `tar_offset` and `byte_length` in `month=MM.idx`.
- Seeks directly to offset in `month=MM.tar`.
- Validates TAR header and gzip CRC in $< 5 \text{ milliseconds}$.
