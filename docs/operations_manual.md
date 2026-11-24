# Pipeline Operations & Monitoring Manual

**Documentation Date:** 2026-11-25  
**Component:** Production Operations & Administration  
**Target Audience:** Linux System Administrators & Data Engineers  

---

## 1. Standard Operating Procedures

### A. Running Unattended Background Acquisition (Recommended)
Always use systemd for unattended runs:
```bash
sudo systemctl start openaq-acquire@2024.service
```
Monitor status:
```bash
systemctl status openaq-acquire@2024.service
```

### B. Running Interactive Foreground Acquisition (Debugging / Testing)
To run directly in your terminal for immediate visual feedback:
```bash
/home/harsha/openaq/bin/acquire_year.sh 2024
```
To run with custom worker concurrency (e.g. 75 workers):
```bash
/home/harsha/openaq/bin/acquire_year.sh 2024 75
```

---

## 2. Real-Time Progress Monitoring & Metric Interpretation

During Stage 1 acquisition, the engine logs real-time metrics every 500 files:

```text
2026-11-24 15:30:35,122 [INFO] Progress: Acquired 4,336,500 files (4174.94 MB) | Skipped: 125 | Failed: 3 | Rate: 210.5 files/s
```

### Field Definitions
- **`Acquired X files (Y MB)`:** Total objects successfully downloaded and committed to monthly TAR containers and index files during the active run.
- **`Skipped: S`:** Objects already recorded in the target month's `.idx` file prior to process launch. The engine fast-forwards past these without issuing network requests.
- **`Failed: F`:** Objects that failed after 5 retry attempts (e.g. transient S3 errors or active month byte length mutations).
- **`Rate: R files/s`:** Moving average throughput in completed S3 downloads per second. Typical performance on 50 threads: **180–230 files/second**.

---

## 3. System Resource & Process Inspection

### Inspecting Process Hierarchy
```bash
systemd-cgls /system.slice/system-openaq\\x2dacquire.slice
```
Expected cgroup hierarchy:
```text
openaq-acquire@2024.service
  ├─208367 bash /home/harsha/openaq/bin/acquire_year.sh 2024
  ├─208396 /home/harsha/openaq/venv/bin/python3 /home/harsha/openaq/bin/acquire_s3_archive.py ...
  └─208397 tee -a /home/harsha/openaq/logs/acquire_year_2024.runner.log
```

### Monitoring Storage & Disk Health
Monitor disk space during active downloads:
```bash
df -h /home/harsha/openaq
```
Monitor disk I/O write operations:
```bash
iostat -x 2
```

---

## 4. Multi-Year Batch Campaigns

To download a sequence of historical years without overlapping, run a simple sequential bash loop:

```bash
for year in 2020 2021 2022 2023; do
    echo "=========================================================="
    echo "STARTING CAMPAIGN ACQUISITION FOR YEAR: $year"
    echo "=========================================================="
    /home/harsha/openaq/bin/acquire_year.sh "$year"
    echo "YEAR $year COMPLETED WITH RETURN CODE: $?"
done
```

Because `acquire_year.sh` executes synchronously in foreground mode, each year will complete both Stage 1 (Download) and Stage 2 (Integrity Audit) before the next year starts.

---

## 5. Handling Interruptions & Process Termination

If an acquisition must be stopped:
1. **Graceful Stop (Systemd):**
   ```bash
   sudo systemctl stop openaq-acquire@2024.service
   ```
2. **Graceful Stop (Interactive):**
   Press `Ctrl+C` once. The engine catches `SIGINT`, waits for active worker threads to finish their current chunk, flushes descriptors, and exits cleanly.
3. **Resuming:**
   Simply re-run the command or restart the systemd service:
   ```bash
   sudo systemctl start openaq-acquire@2024.service
   ```
   The engine reads the existing `.idx` files, fast-forwards past all previously acquired keys in $< 5 \text{ seconds}$, and resumes downloading from the exact point of interruption.
