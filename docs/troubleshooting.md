# Troubleshooting & Historical Failure Modes

**Documentation Date:** 2026-11-25  
**Component:** Diagnostic Runbook & Known Issue Resolution  
**Scope:** Root-cause analysis and verified solutions for all production failure modes  

---

## 1. Single-Digit Month Partition Collision

### Symptoms
During multi-threaded acquisition of historical years (notably 2016, 2017, and 2018), downloads failed with an unhandled assertion error:
```text
AssertionError: Physical offset mismatch: 12058624 != 12059648
```
or
```text
AssertionError: Container 2016/03: TAR physical size 24058880 != index expected size 24057856
```

### Root Cause
In early S3 partitions, data providers inconsistently used both single-digit (`month=3`) and zero-padded (`month=03`) folder keys. When the acquisition engine preloaded containers, it created one `MonthlyTarManager` for `month=3` and another for `month=03`. Because both managers resolved to the exact same physical file (`month=03.tar`), two worker threads with independent write descriptors and locks wrote to the file concurrently, causing race conditions in `tell()` offset calculations.

### Definitive Solution
The engine normalizes all month keys to 2-digit zero-padded strings across all routines:
```python
month = f"{int(mo):02d}" if str(mo).isdigit() else str(mo)
```
This guarantees a strict 1-to-1 mapping between calendar months and container managers.

---

## 2. Rogue Non-Data S3 Objects (`.DS_Store`)

### Symptoms
During Year 2019 and 2014 scans, manifest generation and acquisition crashed with:
```text
ValueError: invalid literal for int() with base 10: 'unknown'
```

### Root Cause
Four non-CSV objects exist inside OpenAQ's authoritative bucket (e.g. `records/csv.gz/locationid=61488/year=2019/.DS_Store`), accidentally uploaded by external data providers using macOS Finder. These paths do not have a `month=` Hive partition, leaving `month = 'unknown'`.

### Definitive Solution
Explicit validation filters were added to `acquire_s3_archive.py`, `generate_manifest.py`, and `audit_acquisition_integrity.py`:
```python
if not mo.isdigit() or not k.endswith('.csv.gz'):
    continue
```
All non-numeric partitions and non-`.csv.gz` files are gracefully ignored.

---

## 3. Live Upstream Data Mutability in Active Months

### Symptoms
In Year 2026, exactly 3 files out of 4.38 million failed with:
```text
[ERROR] FAILED records/csv.gz/locationid=151/year=2026/month=11/location-151-20261112.csv.gz: Size mismatch: expected 323, got 335
```

### Root Cause
The master manifest snapshot was generated on November 16, 2026. For active ongoing months (e.g. November 2026), data providers frequently append additional sensor readings to daily aggregates several days later. The downloaded file is valid gzip CSV, but its live byte size grew relative to the historical snapshot.

### Resolution & Diagnostic Guidance
- For all completed historical years (2006–2025), upstream data is immutable and exhibits 0 size mismatches.
- For active ongoing calendar months, minor byte differences reflect live updates. To verify payload validity independently:
  ```bash
  aws s3 cp s3://openaq-data-archive/records/csv.gz/locationid=151/year=2026/month=11/location-151-20261112.csv.gz /tmp/test.csv.gz --no-sign-request
  gzip -t /tmp/test.csv.gz && echo "Gzip is authentic and valid!"
  ```

---

## 4. SSH Session Disconnection Terminating Unattended Jobs

### Symptoms
Starting long-running multi-year downloads interactively over SSH resulted in aborted processes when the SSH connection dropped or laptop lid closed.

### Root Cause
Systemd's default PAM configuration kills all processes in a user's session cgroup when the last interactive session closes, unless user lingering is enabled.

### Definitive Solution
1. Always enable user lingering:
   ```bash
   sudo loginctl enable-linger harsha
   ```
2. Supervise all long-running acquisition jobs via systemd services (`openaq-acquire@<YEAR>.service`) rather than interactive SSH terminals.

---

## 5. Concurrency Race Conditions & Conflicting Jobs

### Symptoms
Attempting to start an acquisition job while another is already running produces:
```text
[ERROR] Could not acquire lock on /home/harsha/openaq/tmp/acquire_year_2024.lock. Another acquisition process is currently running for year 2024.
```

### Root Cause
The pipeline uses POSIX advisory file locking via `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)` to ensure only one process can manipulate a year's archives at any time.

### Resolution
- Check if another process is actively running:
  ```bash
  systemctl status openaq-acquire@2024.service
  ps aux | grep acquire_year
  ```
- If a previous process was killed abruptly with `kill -9` and left an unreleased lockfile, the Linux kernel automatically releases `flock` locks when the file descriptor closes. If needed, the stale lockfile can be removed safely:
  ```bash
  rm -f /home/harsha/openaq/tmp/acquire_year_2024.lock
  ```

---

## 6. Pre-Flight Disk Full Prevention

### Symptoms
Job refuses to start with:
```text
[ERROR] Pre-flight disk check failed: Insufficient disk space on /home/harsha/openaq.
Required: 12.87 GB (3.0x safety factor), Available: 8.42 GB.
```

### Root Cause
`acquire_s3_archive.py` calculates expected bytes from the manifest and requires:
$$\text{Free Disk Bytes} \ge \text{Expected Payload Bytes} \times 3.0$$
This safety buffer accounts for temporary buffers, index files, and runner logs.

### Resolution
- Free up disk space on the target partition, or mount an additional external volume to `/home/harsha/openaq/raw`.
