# OpenAQ Historical Data Acquisition Pipeline

A production-grade, reproducible data acquisition, packaging, and integrity verification system for the global **OpenAQ** historical air quality archive (2006–2026).

```
                          +-------------------------------+
                          |  OpenAQ Authoritative S3      |
                          |  (openaq-data-archive)        |
                          +---------------+---------------+
                                          | Anonymous HTTPS (443)
                                          v
+-----------------------------------------------------------------------------------------+
| openaq-acquisition pipeline                                                             |
|                                                                                         |
|  [STAGE 1: ACQUISITION ENGINE]                                                          |
|   • 50 Concurrent Worker Threads (~210 files/sec sustained)                             |
|   • Streaming Gzip Manifest Filter (25,587,335 total historical records)                |
|   • Dynamic Disk Pre-flight Check (available space >= 3.0x expected volume)             |
|   • O(1) Monthly TAR Packaging (collapses 25.5M files into 240 containers)              |
|   • Synchronous Sidecar Indexing (month=MM.idx with byte offsets & SHA-256)             |
|                                                                                         |
|  [STAGE 2: INTEGRITY VERIFICATION AUDITOR]                                              |
|   • Full Manifest vs Index Set Reconciliation (0 missing, 0 dangling)                   |
|   • Container Geometry Contiguity Check (0 offset gaps, 0 overlaps)                     |
|   • 100% Exhaustive Gzip Decompression & SHA-256 Check on Month 01                     |
|   • Statistical Sampling (1,000 files/month) across Months 02–12                        |
|   • JSON Certification Reports written to reports/acquisition_report_<YEAR>.json        |
+-----------------------------------------------------------------------------------------+
```

---

## Key Technical Features

- **Zero Inode Exhaustion & Zero Block Slack:** Rather than writing 25.5 million individual files to disk (which exhausts ext4 inode tables and wastes $>80\text{ GB}$ in 4 KB block slack), all daily station files are packed into monthly POSIX TAR archives (`month=01.tar` .. `month=12.tar`). Exactly **240 files** cover the entire 20-year history.
- **O(1) Random-Access Retrieval:** Each TAR container is accompanied by a `.idx` sidecar storing exact physical byte offsets. Any individual file can be read and decompressed in $<2\text{ ms}$ with a single filesystem seek, without reading earlier archive members.
- **Unattended Automation via Systemd:** Parameterized systemd template `systemd/openaq-acquire@.service` manages runs under PID 1 with user lingering (`loginctl enable-linger`), ensuring long acquisitions persist across SSH disconnects.
- **Built-in Concurrency & Crash Protection:** POSIX `fcntl.flock` prevents duplicate concurrent runs on the same year. If interrupted, the engine auto-truncates unindexed trailing bytes and fast-skips all previously acquired records.

---

## Quickstart Guide

### 1. One-Command Automated Provisioning (Recommended)

On any fresh Ubuntu/Debian server, run:

```bash
git clone git@github.com:harsha-chowdam/openaq-acquisition.git
cd openaq-acquisition
make install
```

`make install` automatically:
- Installs necessary system packages (`python3-venv`, `tar`, `gzip`, `curl`, `flock`, etc.).
- Enables systemd user lingering (`loginctl enable-linger`).
- Creates production directories under `~/openaq`.
- Provisions a dedicated virtual environment with locked dependencies.
- Templates and registers the systemd service unit `openaq-acquire@.service`.

---

### 2. The Core Prerequisite: Master Manifest

The acquisition engine relies on `manifest/s3_manifest_modern.csv.gz` as its ground truth. Before launching downloads, ensure the manifest is in place:

- **Option A (Restore from External Backup):**
  ```bash
  cp /path/to/backup/s3_manifest_modern.csv.gz ~/openaq/manifest/
  sha256sum ~/openaq/manifest/s3_manifest_modern.csv.gz
  # Baseline: b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a
  ```
- **Option B (Regenerate from Upstream S3):**
  ```bash
  ~/openaq/venv/bin/python ~/openaq/bin/generate_manifest.py
  ```

---

### 3. Running Acquisition & Verification

Once the manifest is present, **running a single command executes both Stage 1 (Download) and Stage 2 (Integrity Verification Audit)** automatically:

#### A. Single Year via Systemd (Unattended Background Run)
```bash
# Start acquisition and audit for 2024
sudo systemctl start openaq-acquire@2024.service

# Monitor live journal logs
journalctl -u openaq-acquire@2024.service -f
```

#### B. Single Year via Interactive CLI
```bash
make acquire YEAR=2024
# Or directly: ~/openaq/bin/acquire_year.sh 2024
```

#### C. Full Multi-Year Campaign (Sequential Execution)
To acquire and audit all historical years sequentially without manual intervention:
```bash
make campaign START=2006 END=2026
# Or directly: ~/openaq/bin/acquire_campaign.sh 2006 2026
```
The campaign runner executes year by year, ensuring each year passes its integrity audit before moving to the next. If any error occurs, it halts immediately to prevent cascading issues.

# Monitor status and progress
systemctl status openaq-acquire@2024.service
journalctl -u openaq-acquire@2024.service -f
```

---

## Repository Directory Map

```text
openaq-acquisition/
├── bin/
│   ├── acquire_s3_archive.py        # Core streaming multi-threaded acquisition engine
│   ├── acquire_year.sh              # Unattended 2-stage runner script
│   ├── audit_acquisition_integrity.py # 5-stage cryptographic and container auditor
│   ├── generate_manifest.py         # Resumable S3 manifest generator
│   ├── save_location_ids.py         # S3 location partition scanner
│   └── verify_tar_archive.py        # O(1) random-access TAR reader utility
├── config/
│   ├── requirements.txt             # Locked Python dependencies (boto3, botocore)
│   └── config.example               # Configuration template
├── systemd/
│   └── openaq-acquire@.service      # Parameterized systemd service template
├── docs/                            # In-depth technical documentation
│   ├── openaq_data_source.md        # Upstream S3 data source specification
│   ├── manifest_generation.md       # S3 discovery and manifest generation guide
│   ├── manifest_schema.md           # Manifest CSV and summary JSON schemas
│   ├── manifest_recovery.md         # Manifest recovery and validation runbook
│   ├── acquisition_pipeline.md      # Acquisition architecture & CLI reference
│   ├── archive_format_specification.md # Monthly TAR storage container specification
│   ├── index_format_specification.md   # Sidecar .idx format and O(1) seek formulas
│   ├── server_prerequisites.md      # Hardware sizing & OS prerequisites
│   ├── installation.md              # Fresh server provisioning step-by-step
│   ├── systemd_setup.md             # Systemd daemon integration guide
│   ├── operations_manual.md         # Routine operations & monitoring manual
│   ├── integrity_verification.md    # 5-stage verification audit methodology
│   ├── recovery_manual.md           # Disaster recovery & container repair runbook
│   ├── troubleshooting.md           # Root causes and fixes for failure modes
│   └── backup_policy.md             # Offsite external backup policy
├── inventory/                       # Complete system discovery inventories
│   ├── complete_file_inventory.csv  # 44-entry classified asset inventory
│   ├── server_environment_inventory.md # Production server hardware & environment
│   ├── mac_environment_inventory.md # Local workstation environment & file catalog
│   ├── missing_and_uncertain_items.md # Traceability of historical anomalies
│   ├── dependency_inventory.md      # System and package dependencies
│   ├── source_comparison.md         # Side-by-side Mac vs Server comparison
│   └── manifest_inventory.md        # Manifest metadata register & year distribution
├── reports/                         # Official Stage 2 verification JSON reports
│   ├── acquisition_report_2006.json ... acquisition_report_2024.json
├── tests/                           # Automated unit test suite
│   ├── test_archive_indexing.py     # 512-byte block alignment & random access tests
│   ├── test_manifest_parsing.py     # Partition extraction & normalization tests
│   └── test_concurrency_lock.py     # POSIX advisory locking tests
├── CHANGELOG.md                     # Engineering release notes
├── LICENSE                          # Permissive Open Source License
└── README.md                        # Project documentation overview
```

---

## Running Automated Tests

Run the test suite from the repository root:
```bash
python3 -m unittest discover tests
```

---

## License

This project is licensed under the terms of the MIT License. See [LICENSE](LICENSE) for details.
