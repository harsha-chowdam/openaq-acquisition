# Installation & Provisioning Manual

**Documentation Date:** 2026-11-25  
**Target Platform:** Fresh Ubuntu 24.04 LTS Server  
**Goal:** Complete, reproducible deployment of the OpenAQ acquisition environment from scratch  

---

## 1. Step 1: Base Operating System & Packages

On a newly provisioned Ubuntu 24.04 server, update package repositories and install required system tools:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    tar \
    gzip \
    curl \
    util-linux \
    git
```

Verify installed versions:
```bash
python3 --version     # Expected: Python 3.12.x
tar --version         # Expected: tar (GNU tar) 1.35+
gzip --version        # Expected: gzip 1.12+
```

---

## 2. Step 2: User Account & Systemd Lingering Setup

Create the service user (if not already existing) and enable user lingering so background services survive SSH disconnects:

```bash
# Create user 'harsha' (or your designated deployment user)
sudo adduser --gecos "" harsha
sudo usermod -aG sudo harsha

# Enable systemd user lingering (CRITICAL)
sudo loginctl enable-linger harsha

# Verify lingering is active (should output: Linger=yes)
loginctl show-user harsha | grep Linger
```

Switch to the user session:
```bash
su - harsha
```

---

## 3. Step 3: Project Directory Hierarchy Creation

Create the canonical production directory structure under `/home/harsha/openaq`:

```bash
mkdir -p /home/harsha/openaq/{bin,config,manifest,raw/s3_modern,reports,logs,tmp}
chmod 755 /home/harsha/openaq
```

Directory structure overview:
- `bin/`: Executable scripts (`acquire_s3_archive.py`, `acquire_year.sh`, etc.).
- `config/`: Configuration files and requirement specifications.
- `manifest/`: Global manifest and partition location lists.
- `raw/s3_modern/`: Destination for downloaded monthly TAR archives and `.idx` sidecars.
- `reports/`: Destination for JSON integrity audit verification reports.
- `logs/`: Operational runner logs.
- `tmp/`: Runtime concurrency lockfiles.

---

## 4. Step 4: Deploying Source Code

Clone the private repository into the project directory:

```bash
git clone git@github.com:<your-user>/openaq-acquisition.git /home/harsha/openaq_repo

# Copy executables into project bin
cp -r /home/harsha/openaq_repo/bin/* /home/harsha/openaq/bin/
chmod +x /home/harsha/openaq/bin/*.py /home/harsha/openaq/bin/*.sh

# Copy configuration templates
cp -r /home/harsha/openaq_repo/config/* /home/harsha/openaq/config/

# Copy location IDs metadata
cp /home/harsha/openaq_repo/manifest/location_ids.txt /home/harsha/openaq/manifest/
cp /home/harsha/openaq_repo/manifest/manifest_summary.json /home/harsha/openaq/manifest/
```

---

## 5. Step 5: Python Virtual Environment Configuration

Create an isolated Python 3.12 virtual environment and install dependencies:

```bash
python3 -m venv /home/harsha/openaq/venv

# Activate and upgrade pip
/home/harsha/openaq/venv/bin/pip install --upgrade pip

# Install locked production dependencies
/home/harsha/openaq/venv/bin/pip install -r /home/harsha/openaq/config/requirements.txt
```

Verify Python package versions:
```bash
/home/harsha/openaq/venv/bin/pip list
```
Expected output:
```text
Package    Version
---------- -------
boto3      1.44.3
botocore   1.44.3
pip        24.0
urllib3    2.8.0
```

---

## 6. Step 6: Systemd Service Unit Registration

Install the systemd parameterized service template into the system unit path:

```bash
sudo cp /home/harsha/openaq_repo/systemd/openaq-acquire@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Verify systemd recognition:
```bash
systemctl list-unit-files | grep openaq-acquire
```
Expected output:
```text
openaq-acquire@.service    disabled    enabled
```

---

## 7. Step 7: Manifest Deployment

Deploy the master manifest `s3_manifest_modern.csv.gz` into `/home/harsha/openaq/manifest/`:

- **Option A (Restore from External Backup):**
  ```bash
  cp /path/to/backup/s3_manifest_modern.csv.gz /home/harsha/openaq/manifest/
  sha256sum /home/harsha/openaq/manifest/s3_manifest_modern.csv.gz
  # Confirm digest matches: b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a
  ```
- **Option B (Regenerate from S3):**
  ```bash
  /home/harsha/openaq/venv/bin/python /home/harsha/openaq/bin/generate_manifest.py
  ```

---

## 8. Step 8: Pre-Flight Verification & Dry Run

Run a dry-run test for Year 2006 to verify the entire pipeline infrastructure without downloading:

```bash
/home/harsha/openaq/venv/bin/python /home/harsha/openaq/bin/acquire_s3_archive.py --year 2006 --dry-run
```

Expected output:
```text
[INFO] DRY-RUN MODE ACTIVATED: Validating pre-flight parameters...
[INFO] Pre-flight disk space check: PASSED
[INFO] Concurrency lock check: PASSED
[INFO] Manifest stream validation: PASSED (113 objects sampled for year 2006)
[INFO] DRY-RUN COMPLETED SUCCESSFULLY.
```
Your server is now fully configured, verified, and ready for production acquisition.
