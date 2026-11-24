# Complete Dependency Inventory

**Target Pipeline:** OpenAQ Historical Data Acquisition & Verification System  
**Repository:** `openaq-acquisition`  

---

## 1. Operating System & System-Level Packages

The acquisition pipeline runs on standard Linux environments. While developed and verified on **Ubuntu 24.04 LTS (Noble Numbat)**, it relies strictly on POSIX and standard GNU utilities.

| Package | Minimum Version | Verified Production Version | Installation Command | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Python** | `3.10+` | `3.12.3` | `sudo apt install python3` | Primary script runtime |
| **Python venv** | Any standard | Standard library | `sudo apt install python3-venv` | Isolated execution environment |
| **Python pip** | `22.0+` | `24.0` | `sudo apt install python3-pip` | Package manager |
| **tar (GNU tar)** | `1.34+` | `1.35` | Standard system utility | POSIX archive operations & verification |
| **gzip** | `1.10+` | `1.12` | Standard system utility | Stream decompression & CRC audits |
| **util-linux** | `2.37+` | `2.39.3` | Standard system utility | Provides `flock` and filesystem utilities |
| **systemd** | `249+` | `255.4-1ubuntu8` | Standard system init | Supervised unattended execution |
| **curl** | Any | `8.5.0` | `sudo apt install curl` | S3 connectivity verification & healthchecks |

---

## 2. Python Package Dependencies

The acquisition pipeline has been deliberately designed with an exceptionally small dependency footprint. Only `boto3` and its low-level foundation `botocore` are required.

```txt
boto3==1.44.3
botocore==1.44.3
urllib3==2.8.0
```

### Dependency Roles & Configuration
1. **`botocore` (v1.44.3):**
   - Configured with `signature_version=botocore.UNSIGNED`.
   - Bypasses AWS authentication entirely, preventing any dependency on AWS access keys, secret keys, or IAM roles.
   - Manages HTTP connection pooling (`max_pool_connections=60` on 50 worker threads).
2. **`boto3` (v1.44.3):**
   - High-level S3 client wrapper for object streaming (`get_object`, `list_objects_v2`).
3. **Python Standard Library (Zero External Installation):**
   - `tarfile`: Low-level TAR block parsing, header unpacking (`struct.unpack`), and byte alignment.
   - `gzip`: Streaming decompressor for gzip-compressed CSV chunks.
   - `hashlib`: SHA-256 and MD5 cryptographic integrity verification.
   - `concurrent.futures`: ThreadPoolExecutor managing worker concurrency.
   - `fcntl`: POSIX file descriptor advisory locking (`LOCK_EX | LOCK_NB`).
   - `threading`: Mutex locks guarding shared TAR write descriptors.

---

## 3. Cloud Storage & Network Prerequisites

| Attribute | Value | Verification / Specification |
| :--- | :--- | :--- |
| **AWS S3 Bucket** | `openaq-data-archive` | Hosted under the AWS Open Data Sponsorship Program |
| **S3 AWS Region** | `us-east-1` (US East, N. Virginia) | Low-latency endpoint: `openaq-data-archive.s3.us-east-1.amazonaws.com` |
| **Authentication Scheme** | **Anonymous / Unsigned** | Publicly accessible. No AWS account or credentials needed. |
| **Network Protocol** | Outbound HTTPS (Port 443) | Standard TLS 1.3 |
| **S3 Rate Limits** | 5,500 GET req/sec per prefix | 50 concurrent workers operate safely at ~210 req/sec |
| **Bandwidth Demand** | ~15–25 Mbps sustained | ~22.72 GB total compressed payload across 20-year history |

---

## 4. Hardware & Storage Prerequisites

| Hardware Dimension | Minimum Required | Recommended Production Target | Justification |
| :--- | :--- | :--- | :--- |
| **CPU Cores** | 4 cores | 16–24 cores | Multi-threaded downloads and parallel CRC decompression |
| **RAM** | 8 GiB | 32–64 GiB | Sufficient headroom for 50 worker thread buffers |
| **Disk Space** | 80 GB free | 200 GB+ free | Holds global manifest (0.75 GB), monthly TARs (~43 GB), index files (~6 GB), and logs |
| **Filesystem Type** | ext4 / XFS / ZFS | ext4 | Standard Linux filesystem with POSIX `flock` and 64-bit offsets |
| **Inodes** | 100,000 inodes | 500,000 inodes | Monthly TAR containers collapse 25.5M files into just 240 TAR files! |
