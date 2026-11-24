# Global S3 Manifest Generation Guide

**Documentation Date:** 2026-11-25  
**Component:** OpenAQ S3 Modern Archive Manifest Subsystem  
**Target Scripts:** `bin/save_location_ids.py`, `bin/generate_manifest.py`  

---

## 1. Architecture & Design Principles

Generating a complete catalog of OpenAQ's 20-year historical dataset presents unique challenges:
- S3 contains **25,587,335 objects** across **56,480 location partitions**.
- Performing a single sequential recursive scan from the root prefix (`records/csv.gz/`) would take days and is vulnerable to transient network drops.
- Memory constraints prohibit holding 25.5 million metadata records in RAM.

To solve this, the acquisition pipeline utilizes a **two-stage streaming architecture**:
1. **Stage 1 (Partition Discovery):** Rapidly scans the S3 top-level common prefixes using a delimiter to extract all 56,480 unique `locationid=` keys into `location_ids.txt`.
2. **Stage 2 (Parallel Partition Enumeration):** Dispatches 50 concurrent worker threads to paginate each location partition independently, streaming metadata records directly into an appendable, compressed gzip CSV file (`s3_manifest_modern.csv.gz`).

---

## 2. Stage 1: Location Partition Discovery (`save_location_ids.py`)

### Purpose & Algorithm
`save_location_ids.py` connects to AWS S3 anonymously (`signature_version=botocore.UNSIGNED`) and uses the S3 `list_objects_v2` paginator configured with `Delimiter='/'`.

```python
paginator = s3.get_paginator('list_objects_v2')
page_iterator = paginator.paginate(
    Bucket='openaq-data-archive',
    Prefix='records/csv.gz/',
    Delimiter='/'
)
```

By requesting only `CommonPrefixes` with a delimiter, S3 returns only folder boundaries rather than millions of individual files. The script strips the prefix, extracts the integer location ID, and saves the ordered list to `manifest/location_ids.txt`.

### Execution
```bash
./venv/bin/python bin/save_location_ids.py
```
- **Duration:** ~12–18 seconds.
- **Output:** `manifest/location_ids.txt` (56,480 entries, 386 KB).

---

## 3. Stage 2: Resumable Manifest Enumeration (`generate_manifest.py`)

### Features & Capabilities
`bin/generate_manifest.py` is the production manifest generation engine:
1. **Concurrency Pool:** Runs 50 parallel workers using `concurrent.futures.ThreadPoolExecutor`.
2. **Direct Gzip Streaming:** Writes rows directly to `s3_manifest_modern.csv.gz` using Python's `gzip.open` in append/write mode with UTF-8 encoding.
3. **Resumability (`--resume`):** If interrupted, passing `--resume` causes the script to scan the existing compressed manifest, extract all completed `location_id` values into a memory set, and skip directly to unmanifested locations.
4. **Signal Safety:** Intercepts `SIGINT` (Ctrl+C) and `SIGTERM` (systemd stop signals). It signals all workers to cease pagination, waits for active partition flushes to complete, and cleanly closes the gzip file, ensuring no dangling or corrupt gzip blocks.
5. **Analytical Summary:** Upon completion (or pause), writes comprehensive metrics to `manifest/manifest_summary.json`.

### CLI Arguments & Modes
- **Full Production Generation:**
  ```bash
  ./venv/bin/python bin/generate_manifest.py
  ```
- **Resuming an Interrupted Generation:**
  ```bash
  ./venv/bin/python bin/generate_manifest.py --resume
  ```
- **Testing Mode (First N Locations):**
  ```bash
  ./venv/bin/python bin/generate_manifest.py --limit=100
  ```

---

## 4. Metadata Extraction & Filtering Logic

For each object in partition `records/csv.gz/locationid={lid}/`:
1. **S3 Object Attributes:**
   - `s3_key`: Full S3 key string.
   - `size_bytes`: ContentLength in bytes.
   - `etag`: MD5 checksum with surrounding quotes stripped.
   - `last_modified`: ISO 8601 UTC timestamp.
2. **Temporal Parsing:**
   The key is split on `/` to extract Hive partitions:
   ```python
   for part in parts:
       if part.startswith('year='):
           yr = part.split('=')[1]
       elif part.startswith('month='):
           mo = part.split('=')[1]
   ```
3. **Filtering:**
   - Objects must end with `.csv.gz`.
   - Non-data files (such as rare `.DS_Store` objects) are skipped.
4. **CSV Row Format:**
   ```csv
   location_id,year,month,s3_key,size_bytes,etag,last_modified
   ```

---

## 5. Performance Benchmarks

- **Worker Concurrency:** 50 threads.
- **S3 Listing Rate:** ~150–220 locations/second (~4,000–6,500 file records/sec).
- **Total Runtime:** ~75–90 minutes for all 56,480 locations and 25,587,335 objects.
- **Peak RAM Utilization:** < 500 MB (streaming output avoids holding records in memory).
- **Compressed Output Size:** 782,863,355 bytes (~747 MB).
