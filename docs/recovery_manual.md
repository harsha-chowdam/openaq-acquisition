# Disaster Recovery & System Restoration Manual

**Documentation Date:** 2026-11-25  
**Component:** Disaster Recovery & Archive Repair Procedures  
**Primary Target:** Recovering from hardware failure, data loss, or container corruption  

---

## 1. Scenario 1: Total Server Loss (Bare-Metal Reconstruction)

If both production server and development workstation become permanently unavailable:

### Recovery Runbook
1. **Provision New Ubuntu 24.04 Server:**
   Deploy a fresh Ubuntu 24.04 LTS instance with at least 8 cores, 16 GB RAM, and 150+ GB SSD storage.
2. **Follow Installation Manual:**
   Execute all steps in `docs/installation.md`:
   - Install system packages (`python3`, `python3-venv`, `tar`, `gzip`, etc.).
   - Create user `harsha` and enable lingering (`loginctl enable-linger harsha`).
   - Clone the private `openaq-acquisition` repository.
   - Build Python virtual environment and install `requirements.txt`.
   - Register systemd unit `systemd/openaq-acquire@.service`.
3. **Restore Global Manifest:**
   - Copy `s3_manifest_modern.csv.gz` from your external backup storage into `/home/harsha/openaq/manifest/`.
   - Verify SHA-256 digest: `b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a`.
   *(If external backup is lost, regenerate manifest using `bin/save_location_ids.py` followed by `bin/generate_manifest.py`).*
4. **Restore or Reacquire Data:**
   - **Path A (Restoring from external backup):** Sync monthly TAR archives and `.idx` files from external storage into `/home/harsha/openaq/raw/s3_modern/`.
   - **Path B (Reacquiring from OpenAQ S3):** Run `bin/acquire_year.sh <YEAR>` for each historical year.
5. **Execute Fleet Audit:**
   Run `bin/audit_acquisition_integrity.py <YEAR>` across all years to certify 100% integrity.

---

## 2. Scenario 2: Corrupted or Missing Index File (`month=MM.idx`)

If an index file is accidentally deleted, modified, or corrupted:

### Mathematical Invariant
Because `month=MM.tar` contains complete GNU TAR headers for every single object, **the TAR container is self-describing**. The companion index can be rebuilt from scratch with 100% fidelity.

### Step-by-Step Rebuild Command
Run the Python reconstruction one-liner or script:

```bash
/home/harsha/openaq/venv/bin/python -c '
import os, sys, tarfile, hashlib, csv, datetime

year = sys.argv[1]
month = f"{int(sys.argv[2]):02d}"
tar_path = f"/home/harsha/openaq/raw/s3_modern/year={year}/month={month}.tar"
idx_path = f"/home/harsha/openaq/raw/s3_modern/year={year}/month={month}.idx"

print(f"Rebuilding index for {tar_path} -> {idx_path}...")
with open(tar_path, "rb") as tf, open(idx_path, "w", newline="", encoding="utf-8") as idxf:
    writer = csv.writer(idxf)
    writer.writerow(["s3_key", "tar_offset", "byte_length", "file_size", "etag", "sha256", "retrieved_at_utc"])
    
    current_offset = 0
    file_count = 0
    while True:
        hdr_bytes = tf.read(512)
        if not hdr_bytes or hdr_bytes == b"\x00" * 512:
            break
        tarinfo = tarfile.TarInfo.frombuf(hdr_bytes, encoding="utf-8")
        s3_key = tarinfo.name
        size = tarinfo.size
        
        payload = tf.read(size)
        sha256 = hashlib.sha256(payload).hexdigest()
        md5 = hashlib.md5(payload).hexdigest()
        
        pad_len = (512 - (size % 512)) % 512
        if pad_len > 0:
            tf.read(pad_len)
            
        byte_length = 512 + size + pad_len
        now_iso = datetime.datetime.fromtimestamp(tarinfo.mtime, datetime.timezone.utc).isoformat()
        writer.writerow([s3_key, current_offset, byte_length, size, md5, sha256, now_iso])
        current_offset += byte_length
        file_count += 1

print(f"Successfully reconstructed index: {file_count:,} records.")
' 2024 07
```

After reconstruction, run the integrity auditor to certify the restored index:
```bash
/home/harsha/openaq/venv/bin/python /home/harsha/openaq/bin/audit_acquisition_integrity.py 2024
```

---

## 3. Scenario 3: Trailing Incomplete Bytes in TAR Container

If a write process crashed mid-block (e.g. abrupt power failure), the `.tar` file on disk may have trailing unindexed bytes:

### Automatic Engine Recovery
When `acquire_s3_archive.py` starts, `MonthlyTarManager` automatically performs this check:
1. Reads `month=MM.idx` to find last valid offset $O_{\text{last}}$ and byte length $L_{\text{last}}$.
2. Compares physical TAR file size against $\text{Expected} = O_{\text{last}} + L_{\text{last}}$.
3. If physical size $>$ Expected, it truncates the file back to Expected size automatically.

### Manual Truncation Command (If Needed)
```bash
/home/harsha/openaq/venv/bin/python -c '
import sys, os, csv

year = sys.argv[1]
month = f"{int(sys.argv[2]):02d}"
tar_path = f"/home/harsha/openaq/raw/s3_modern/year={year}/month={month}.tar"
idx_path = f"/home/harsha/openaq/raw/s3_modern/year={year}/month={month}.idx"

with open(idx_path, "r", encoding="utf-8") as f:
    rows = list(csv.reader(f))
    last_row = rows[-1]
    expected_size = int(last_row[1]) + int(last_row[2])

actual_size = os.path.getsize(tar_path)
print(f"Actual TAR size: {actual_size:,} | Expected size: {expected_size:,}")
if actual_size > expected_size:
    print(f"Truncating {actual_size - expected_size:,} trailing corrupt bytes...")
    with open(tar_path, "a+b") as tf:
        tf.truncate(expected_size)
    print("Truncation complete.")
else:
    print("Container size is already perfectly aligned.")
' 2024 07
```

---

## 4. Scenario 4: Re-acquiring a Specific Year from Scratch

If a year's archive is deemed irreparably damaged:

```bash
# 1. Stop any running acquisition service for that year
sudo systemctl stop openaq-acquire@2024.service

# 2. Clear any lingering advisory lockfile
rm -f /home/harsha/openaq/tmp/acquire_year_2024.lock

# 3. Safely archive or remove the existing damaged year directory
mv /home/harsha/openaq/raw/s3_modern/year=2024 /home/harsha/openaq/raw/s3_modern/year=2024.corrupt_backup

# 4. Remove previous logs and reports
rm -f /home/harsha/openaq/logs/acquisition_2024.log /home/harsha/openaq/reports/acquisition_report_2024.json

# 5. Start clean unattended acquisition
sudo systemctl start openaq-acquire@2024.service
```
The pipeline will cleanly re-download all objects, create pristine 512-byte aligned monthly TARs, build new `.idx` files, and run the automated Stage 2 audit upon completion.
