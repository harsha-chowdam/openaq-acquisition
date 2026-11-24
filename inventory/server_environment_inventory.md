# Production Server Environment Inventory

**Assessment Date:** 2026-11-25  
**Target Host:** Production Server (`<PRODUCTION_SERVER_IP>`)  
**Project Root:** `/home/harsha/openaq`  

---

## 1. Host & Operating System Specifications

| Attribute | Specification | Verification Command / Evidence |
| :--- | :--- | :--- |
| **Operating System** | Ubuntu 24.04.1 LTS (Noble Numbat) | `cat /etc/os-release` |
| **OS Architecture** | `x86_64` (64-bit) | `uname -m` |
| **Linux Kernel** | `6.8.0-149-generic #149-Ubuntu SMP PREEMPT_DYNAMIC` | `uname -r` |
| **System Uptime** | 6+ days | `uptime` |
| **System Hostname** | `server` | `hostname` |
| **Primary Network Interface** | Public IP: `<PRODUCTION_SERVER_IP>` (SSH on Port 22) | `ip a` / SSH Connection |

---

## 2. Hardware Resource Profile

| Resource Component | Allocated Capacity | Utilization / Available | Notes |
| :--- | :--- | :--- | :--- |
| **Compute (vCPUs)** | 24 vCPUs | Load average: ~0.37 (Quiescent) | QEMU Virtual CPU 2.5+ (1 socket, NUMA node 0: 0-23) |
| **Physical Memory (RAM)** | 94 GiB total | 22 GiB used / 71 GiB available / 35 GiB free | Ample buffer for 50-worker I/O pools and streaming buffers |
| **Swap Space** | 4.0 GiB | 3.9 GiB used / 119 MiB free | Secondary page cache |
| **Primary Storage Volume** | 1.5 TB ext4 (`/dev/mapper/ubuntu--vg-ubuntu--lv`) | 522 GiB used (37%) / 915 GiB free | Mount point `/`. Holds raw archives, manifest, and logs |
| **Open File Limits** | `nofile`: 1,024 soft / 1,048,576 hard | Tested under 50 concurrent S3 threads | Well within kernel thresholds |
| **Max User Processes** | 385,888 | Standard systemd slice allocation | Unrestricted concurrency |

---

## 3. User, Permissions & Process Execution Context

- **Operating User:** `harsha` (UID 1000, GID 1000).
- **Group Memberships:** `harsha`, `sudo`.
- **Sudo Privilege:** Passwordless sudo configured in `/etc/sudoers.d/`.
- **Systemd User Lingering:** **ENABLED** via `loginctl enable-linger harsha` (`Linger=yes`).
  - *Critical Purpose:* Ensures background systemd services and user slices persist across SSH disconnection or terminal termination.
- **Scheduled Tasks (Cron):** None in `/var/spool/cron/crontabs/` or `/etc/crontab`. All acquisition automation is orchestrated through systemd units.

---

## 4. Production Directory Structure (`/home/harsha/openaq`)

```
/home/harsha/openaq/
├── bin/                             # Production executable scripts
│   ├── acquire_s3_archive.py        # Core acquisition engine (26,404 bytes)
│   ├── acquire_year.sh              # Master runner script (5,674 bytes)
│   ├── generate_manifest.py         # Resumable S3 manifest generator (8,201 bytes)
│   ├── save_location_ids.py         # Initial S3 location partition scanner (862 bytes)
│   └── verify_tar_archive.py        # Standalone random-access TAR reader (4,784 bytes)
├── audit_acquisition_integrity.py   # Comprehensive 5-stage integrity auditor (16,375 bytes)
├── config/                          # Configuration and secrets
│   └── .env                         # (Excluded from Git) Contains OpenAQ API key for discovery
├── manifest/                        # S3 inventory manifests and metadata
│   ├── s3_manifest_modern.csv.gz    # Master global manifest (782,863,355 bytes, 25.58M rows)
│   ├── manifest_summary.json        # Global manifest statistics summary (1,850 bytes)
│   └── location_ids.txt             # 56,480 unique location IDs (386,909 bytes)
├── raw/                             # Downloaded OpenAQ TAR archives and index files
│   └── s3_modern/                   # Modern layout (records/csv.gz/locationid=...)
│       ├── year=2006/ ... year=2026/# 20 historical annual subdirectories containing monthly TAR/IDX
├── reports/                         # Official Stage 2 integrity verification JSON reports
│   ├── acquisition_report_2006.json
│   ├── ...
│   └── acquisition_report_2024.json
├── logs/                            # Operational logs from acquisition and runner scripts
│   ├── acquisition_YYYY.log
│   └── acquire_year_YYYY.runner.log
├── tmp/                             # Inter-process concurrency locks
│   └── acquire_year_YYYY.lock       # fcntl advisory file locks
└── venv/                            # Python 3.12.3 virtual environment
```

---

## 5. Python Runtime & Virtual Environment Profile

- **Virtual Environment Path:** `/home/harsha/openaq/venv`
- **Python Binary:** `/home/harsha/openaq/venv/bin/python3`
- **Python Version:** `Python 3.12.3`
- **Core Pipeline Dependencies:**
  - `boto3==1.44.3` (AWS S3 SDK client)
  - `botocore==1.44.3` (Low-level HTTP/S3 transport with anonymous unsigned configuration)
  - `urllib3==2.8.0` (Underlying connection pooling)
- **Standard Library Modules Relied Upon:**
  - `gzip`, `tarfile`, `csv`, `hashlib`, `concurrent.futures`, `threading`, `fcntl`, `signal`, `argparse`, `logging`, `shutil`, `json`, `datetime`, `collections`.

---

## 6. Systemd Integration Architecture

- **Unit File Path:** `/etc/systemd/system/openaq-acquire@.service`
- **Template Parameter:** `%I` maps to the 4-digit acquisition year (e.g. `openaq-acquire@2024.service`).
- **Service Configuration:**
  ```ini
  [Unit]
  Description=OpenAQ S3 Archive Acquisition and Integrity Audit for Year %I
  After=network-online.target
  Wants=network-online.target

  [Service]
  Type=simple
  User=harsha
  Group=harsha
  WorkingDirectory=/home/harsha/openaq
  ExecStart=/home/harsha/openaq/bin/acquire_year.sh %I
  KillMode=mixed
  KillSignal=SIGTERM
  TimeoutStopSec=180
  StandardOutput=journal
  StandardError=journal
  Restart=no

  [Install]
  WantedBy=multi-user.target
  ```
- **Lifecycle Management:**
  - Start: `sudo systemctl start openaq-acquire@YYYY.service`
  - Status: `systemctl status openaq-acquire@YYYY.service`
  - Real-time Journal: `journalctl -u openaq-acquire@YYYY.service -f`
