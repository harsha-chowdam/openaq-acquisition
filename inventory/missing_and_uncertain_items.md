# Missing, Uncertain, and Historical Items Inventory

**Audit Date:** 2026-11-25  
**Scope:** OpenAQ Historical Data Acquisition Pipeline  

---

## 1. Manifest Provenance & Generation Scripts

### Status: Fully Resolved & Preserved
- **Initial Uncertainty:** Whether the original script that produced the 25.58M-row global manifest (`s3_manifest_modern.csv.gz`) was preserved or lost.
- **Investigation Outcome:** The exact generation script was located on the production server at `/home/harsha/openaq/bin/generate_manifest.py` (8,201 bytes), along with the partition discovery script `/home/harsha/openaq/save_location_ids.py` (862 bytes).
- **Evolution Cataloged:**
  1. `save_location_ids.py`: Scanned S3 delimiter `records/csv.gz/` to discover all 56,480 unique location IDs.
  2. `generate_manifest.py.mac_initial` (6,043 bytes): The initial generator written on Mac. Lacked pause/resume and signal trapping.
  3. `bin/generate_manifest.py` (8,201 bytes): The production-grade generator deployed on Server 130. Added `SIGINT`/`SIGTERM` signal safety, `--resume` support (scanning existing gzip manifests before resuming), and incremental flushing.
- **Integrity Baseline:** The global manifest `s3_manifest_modern.csv.gz` generated on November 16, 2026 has SHA-256 `b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a` and is preserved as an external recovery asset.

---

## 2. Upstream Data Anomalies & Edge Cases in S3

### A. Mixed Single-Digit and Double-Digit Month Keys
- **Observation:** In historical years 2016 through 2018, certain data partitions in S3 used single-digit month keys (e.g. `month=3` or `month=7`) while others used zero-padded keys (e.g. `month=03` or `month=07`).
- **Impact on Acquisition:** When preloading existing `.idx` records, files with `month=3` instantiated a separate container manager from `month=03`, resulting in concurrent file descriptor collisions on the same physical archive (`month=03.tar`).
- **Definitive Fix:** Normalized month parsing across all pipeline tools:
  ```python
  month_str = f"{int(raw_month):02d}"
  ```
  Both `acquire_s3_archive.py` and `audit_acquisition_integrity.py` enforce this normalization.

### B. Rogue Non-Data S3 Objects
- **Observation:** Exactly 4 non-CSV objects exist inside OpenAQ's S3 bucket:
  - `records/csv.gz/locationid=61488/year=2019/.DS_Store`
  - `records/csv.gz/locationid=61495/year=2014/.DS_Store`
- **Impact on Acquisition:** Initial parsing attempted `int("unknown")` for month extraction, causing an unhandled `ValueError`.
- **Definitive Fix:** Explicit sanity checks were introduced:
  ```python
  if not mo.isdigit() or not k.endswith('.csv.gz'):
      continue
  ```

### C. Live Upstream Data Mutability in Active Months (November 2026)
- **Observation:** During the Year 2026 acquisition run, exactly 3 files out of 4,383,524 failed byte-length validation:
  1. `records/csv.gz/locationid=151/year=2026/month=11/location-151-20261112.csv.gz` (expected 323, got 335)
  2. `records/csv.gz/locationid=3394242/year=2026/month=11/location-3394242-20261112.csv.gz` (expected 453, got 478)
  3. `records/csv.gz/locationid=4619882/year=2026/month=11/location-4619882-20261112.csv.gz` (expected 484, got 497)
- **Root Cause Analysis:** The global manifest snapshot was taken on 2026-11-16. Because November 2026 was the active ongoing calendar month, the data provider uploaded additional sensor readings for November 12 after the manifest snapshot was frozen. The downloaded files are authentic, non-corrupted gzip archives, but their live S3 size increased by 12–25 bytes relative to the historical snapshot.
- **Documented Behavior:** Historical sealed years (2006–2025) have zero upstream mutations. For active ongoing months, slight size expansions represent live data updates.

---

## 3. Scope Boundaries & Excluded Subsystems

The following components reside in the working directories but are **strictly excluded from this repository** per project instructions:

1. **PostgreSQL Relational Schemas:**
   - Files: `openaq_v4.sql`, `openaq_v4_1.sql`, `artifact_backups/openaq_v4_baseline.sql`, `artifact_backups/openaq_v4_1_validated.sql`.
   - Reason: Database table architecture, partitioning rules, and index tuning will be documented and backed up in a dedicated database recovery project.
2. **Database Ingestion Engine:**
   - Files: `ingest_full_year_2025.py`, `ingest_month_pilot.py`, `test_v4_pipeline.py`, `verify_full_year_2025.py`, `verify_january_ingestion.py`.
   - Reason: Ingestion from TAR containers into relational PostgreSQL tables belongs to the database pipeline project.
3. **Database Query Dumps & Presentations:**
   - Files: `db_exports/*`, `demo_data/*`, `dataset_overview.md`, `dataset_overview.docx`.
   - Reason: Presentation assets and CSV table exports are derived database products.
4. **Secret Keys & SSH Credentials:**
   - Files: `config/.env`, `.ssh/id_ed25519`, `.ssh/id_ed25519.pub`.
   - Reason: Strict operational security prohibits committing API keys or SSH private keys to version control.
