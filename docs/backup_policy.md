# External Backup Strategy & Disaster Recovery Policy

**Documentation Date:** 2026-11-25  
**Component:** Long-Term Data Preservation & Offsite Backup  
**Target Dataset:** 20-Year OpenAQ Historical Archive (~50 GB Total)  

---

## 1. Scope Boundary: What Goes to Git vs External Backup

In adherence to strict software engineering standards, **Git is reserved exclusively for source code, configuration templates, documentation, inventory catalogs, tests, and lightweight metadata**:

| Data Category | Target Location | Rationale |
| :--- | :--- | :--- |
| **Source Code, Scripts, Tests** | **Git Repository** | Version control, peer review, code auditability |
| **Systemd Services & Configs** | **Git Repository** | Reproducibility across server environments |
| **Architecture & Operation Docs** | **Git Repository** | Permanent technical knowledge base |
| **JSON Audit Completion Reports** | **Git Repository** | Proof of integrity verification (~60 KB total) |
| **Discovered Location IDs** | **Git Repository** | Low-weight metadata (`location_ids.txt`, 386 KB) |
| **Global Manifest (`s3_manifest_modern.csv.gz`)** | **External Backup** | Exceeds GitHub 100 MB file limit (747 MB gzipped) |
| **Monthly TAR Archives (`month=MM.tar`)** | **External Backup** | Large binary data payload (~42.5 GB total) |
| **Index Sidecars (`month=MM.idx`)** | **External Backup** | High-volume index tables (~5.5 GB total) |
| **Secret API Keys & SSH Credentials** | **Secure Vault** | Strict zero-trust security policy |

---

## 2. External Backup Assets Register

To achieve total disaster recovery capability, the following assets must be preserved in external offsite storage:

```text
openaq-external-backup/
├── manifest/
│   ├── s3_manifest_modern.csv.gz       # 782,863,355 bytes (SHA-256: b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a)
│   ├── manifest_summary.json           # Global file count and distribution summary
│   └── location_ids.txt                # 56,480 unique location IDs
└── raw/
    └── s3_modern/                      # Monthly TAR containers and index sidecars
        ├── year=2006/ ... year=2026/
        │   ├── month=01.tar ... month=12.tar
        │   └── month=01.idx ... month=12.idx
```

- **Total Offsite Storage Capacity Required:** **~50 GB**.

---

## 3. Recommended Storage Providers & Tiers

Because historical years (2006–2025) are immutable and sealed, they require **Write-Once-Read-Rarely** storage:

| Storage Provider | Storage Class | Estimated Monthly Cost | Advantage |
| :--- | :--- | :--- | :--- |
| **AWS S3** | Glacier Instant Retrieval | ~$0.20 / month | Sub-second restore time, high durability ($99.999999999\%$) |
| **Cloudflare R2** | Standard | ~$0.75 / month | **Zero egress fees** when restoring |
| **Backblaze B2** | Standard | ~$0.30 / month | Extremely low cost, S3-compatible API |
| **Google Cloud (GCS)**| Archive / Coldline | ~$0.25 / month | Robust IAM and cross-region replication |
| **Local Physical NAS** | ZFS RAID-Z2 / External SSD | One-time hardware cost | Air-gapped on-premise physical copy |

---

## 4. Automated Backup Procedure (S3 Example)

To back up the complete dataset from production to an external secure backup bucket:

### Step 1: Generate Master Checksum Manifest
```bash
cd /home/harsha/openaq
find raw/s3_modern/ -type f \( -name "*.tar" -o -name "*.idx" \) -exec sha256sum {} + > manifest/archive_checksums.sha256
```

### Step 2: Sync to Offsite Cloud Storage
```bash
# Sync manifest and checksums
aws s3 sync /home/harsha/openaq/manifest/ s3://my-openaq-backup-vault/manifest/ --exclude "*" --include "s3_manifest_modern.csv.gz" --include "archive_checksums.sha256"

# Sync all monthly TAR containers and index sidecars
aws s3 sync /home/harsha/openaq/raw/s3_modern/ s3://my-openaq-backup-vault/raw/s3_modern/ --storage-class GLACIER_IR
```

---

## 5. Restoration Runbook from External Backup

If restoring onto a freshly installed server:

### Step 1: Restore Directory Tree
```bash
mkdir -p /home/harsha/openaq/{manifest,raw/s3_modern}
```

### Step 2: Pull Manifest and Validate Checksum
```bash
aws s3 cp s3://my-openaq-backup-vault/manifest/s3_manifest_modern.csv.gz /home/harsha/openaq/manifest/

# Confirm checksum matches authoritative baseline
echo "b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a  /home/harsha/openaq/manifest/s3_manifest_modern.csv.gz" | sha256sum -c -
```

### Step 3: Pull Data Containers
```bash
aws s3 sync s3://my-openaq-backup-vault/raw/s3_modern/ /home/harsha/openaq/raw/s3_modern/
```

### Step 4: Run Verification Fleet
```bash
for yr in $(seq 2006 2026); do
    if [ -d "/home/harsha/openaq/raw/s3_modern/year=$yr" ]; then
        /home/harsha/openaq/venv/bin/python /home/harsha/openaq/bin/audit_acquisition_integrity.py "$yr"
    fi
done
```
Once all audits return exit code 0 and output `audit_passed: true`, the acquisition environment is 100% restored and certified.
