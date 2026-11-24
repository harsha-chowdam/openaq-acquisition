# Global Manifest Recovery & Regeneration Procedures

**Documentation Date:** 2026-11-25  
**File Target:** `manifest/s3_manifest_modern.csv.gz`  
**Integrity Baseline Checksum:** `b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a`  

---

## 1. Overview & Recovery Importance

The master manifest `s3_manifest_modern.csv.gz` is a critical operational asset. It provides the immutable ground truth against which all historical downloads, monthly TAR containers, and integrity audits are verified.

Because the manifest contains **25,587,335 records** and is **747 MB compressed**, it exceeds GitHub's 100 MB single-file limit and is therefore maintained in external backup storage.

Two recovery paths exist:
- **Path A (Preferred):** Restore the authoritative manifest file from external backup storage and verify its SHA-256 checksum.
- **Path B (Fallback):** Regenerate the manifest directly from OpenAQ's live S3 bucket using the included generation scripts.

---

## 2. Integrity Verification of Existing Manifest

Before using an existing manifest file on a new server, its cryptographic and format integrity must be validated.

### Step 1: Verify SHA-256 Checksum
```bash
sha256sum manifest/s3_manifest_modern.csv.gz
```
- **Expected Output:**
  ```text
  b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a  manifest/s3_manifest_modern.csv.gz
  ```

### Step 2: Verify Gzip Container Integrity
```bash
gzip -t manifest/s3_manifest_modern.csv.gz
echo $?
```
- **Expected Return Code:** `0` (Zero gzip CRC errors or truncated byte streams).

### Step 3: Verify Record Count
```bash
zcat manifest/s3_manifest_modern.csv.gz | wc -l
```
- **Expected Line Count:** `25587336` (1 header row + 25,587,335 data rows).

---

## 3. Path A: Restoring Manifest from External Backup

If provisioning a fresh server:

1. Create the project manifest directory:
   ```bash
   mkdir -p /home/harsha/openaq/manifest
   ```
2. Copy or download the manifest from your secure external backup storage (e.g. AWS S3 backup bucket, Google Cloud Storage, or external hard drive):
   ```bash
   # Example: Download from external backup storage
   aws s3 cp s3://my-secure-backup-bucket/openaq/manifest/s3_manifest_modern.csv.gz /home/harsha/openaq/manifest/
   ```
3. Run the verification commands from Section 2 to confirm that the restored file matches the canonical checksum.

---

## 4. Path B: Full Regeneration from OpenAQ S3 Source

If both production and external backups are unavailable, the manifest can be regenerated directly from OpenAQ's public S3 bucket using the scripts in `bin/`:

### Step 1: Discover Location Partitions
```bash
./venv/bin/python bin/save_location_ids.py
```
- Discovers all `records/csv.gz/locationid=` prefixes via anonymous S3 pagination.
- Outputs `manifest/location_ids.txt` (56,480 locations).

### Step 2: Enumerate Objects Across All Locations
```bash
./venv/bin/python bin/generate_manifest.py
```
- Spawns 50 concurrent worker threads querying S3.
- Streams results directly into `manifest/s3_manifest_modern.csv.gz`.
- Emits real-time progress logs every 500 locations.
- **Estimated Completion Time:** ~75–90 minutes on a 16+ core Linux server.

### Step 3: Resuming If Interrupted
If the process is stopped or interrupted:
```bash
./venv/bin/python bin/generate_manifest.py --resume
```
The script will inspect the existing partial manifest, identify all completed location IDs, and resume processing remaining locations without duplicating records.

### Step 4: Validate Summary Output
Upon completion, review `manifest/manifest_summary.json` to verify that all 56,480 locations were scanned and total files meet or exceed 25,587,335.
