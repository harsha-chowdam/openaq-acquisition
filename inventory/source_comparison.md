# Source Comparison: Mac vs Production Server

**Audit Date:** 2026-11-25  
**Local Workspace:** `/Users/harsha/data` (macOS arm64)  
**Production Server:** `/home/harsha/openaq` (Ubuntu 24.04 x86_64, IP: `<PRODUCTION_SERVER_IP>`)  

---

## 1. Bit-for-Bit Synchronized Pipeline Scripts

The core acquisition and verification scripts were verified across both systems using cryptographic SHA-256 digests. They are identical:

| Script | Size (Bytes) | SHA-256 Checksum | Sync Verification |
| :--- | :--- | :--- | :--- |
| **`acquire_s3_archive.py`** | 26,404 | `42f9c0706677271304fa5176e05e31be80a3d7817f11ab3590cab2a3a1b8f417` | **Bit-for-bit identical** |
| **`acquire_year.sh`** | 5,674 | `b5dfd3bb5ea81193682c4afbde2c47548132eb1aa0ac02e3c3ebca95cf29f7a1` | **Bit-for-bit identical** |
| **`audit_acquisition_integrity.py`** | 16,375 | `62926be9ce430547868f6d69361759047dfc055616572889b4388ffffcc91cfc` | **Bit-for-bit identical** |
| **`save_location_ids.py`** | 862 | `05714388149c064258ad6ec4fcec8aea732e637ac39e86ae87da6b7d9333e174` | **Bit-for-bit identical** |
| **`verify_tar_archive.py`** | 4,784 | `b72fd33d5833f15ce3323638fbd606ab01a381e8397e5788a980f9598aa74fda` | **Bit-for-bit identical** |

---

## 2. Implementation Differences & Historical Evolution

### A. Manifest Generator Evolution (`generate_manifest.py`)
- **Mac Version (`generate_manifest.py`, 6,043 bytes):**
  - This was the initial implementation. It read `location_ids.txt` and streamed records directly to `s3_manifest_modern.csv.gz`.
  - Limitations: No `--resume` flag; if interrupted, it had to restart from location 0. No POSIX signal handling (`SIGINT`/`SIGTERM`).
- **Production Server Version (`bin/generate_manifest.py`, 8,201 bytes):**
  - Upgraded on the production server.
  - Features:
    - `--resume`: Scans the existing `s3_manifest_modern.csv.gz` header and records to identify already-processed location IDs, fast-forwarding to remaining partitions.
    - Signal-Safe: Traps `SIGINT` (Ctrl+C) and `SIGTERM` (systemd stop), allowing in-flight worker threads to complete and cleanly closing the gzip stream with valid CRC footers.
    - Status Tracking: Emits structured completion metadata into `manifest_summary.json`.
  - Decision: The production server version (`bin/generate_manifest.py`) is preserved in the backup repository as the definitive manifest generation engine.

### B. Location of Systemd Service Definition
- **Production Server:** `/etc/systemd/system/openaq-acquire@.service`
  - Integrated into systemd daemon with `%I` parameterization and user lingering enabled.
- **Mac:** Absent (macOS uses `launchd`, not `systemd`).
  - Decision: Captured and placed in `systemd/openaq-acquire@.service` within the repository.

### C. Data Assets and Storage Distribution
- **Production Server Exclusive Assets:**
  - `manifest/s3_manifest_modern.csv.gz` (747 MB gzipped master manifest).
  - `manifest/manifest_summary.json` (Analytical manifest summary).
  - `raw/s3_modern/year=2006` through `year=2026` (~43 GB across 240 monthly TAR containers and 240 `.idx` sidecars).
  - `reports/acquisition_report_2006.json` through `acquisition_report_2024.json`.
- **Mac Exclusive Assets:**
  - Remote automation keys: `/Users/harsha/data/.ssh/id_ed25519`.
  - Orchestration scripts: `/Users/harsha/data/remote.sh`, `copy_ssh_key.exp`, `ssh_cmd.exp`.

---

## 3. Database & SQL Artifacts (Common Across Both)

The following files exist in both `/Users/harsha/data` and `/home/harsha/openaq` but are **excluded from this repository** as they belong to the downstream PostgreSQL database project:

- `openaq_v4.sql` & `openaq_v4_1.sql` (Relational DDL schemas)
- `ingest_full_year_2025.py` & `ingest_month_pilot.py` (Database ingestion)
- `test_v4_pipeline.py` & `verify_full_year_2025.py` (Database verification tests)
- `profile_2025_dataset.py` & `validate_parameter_mapping.py` (Database column profiling)
