# Production Server Prerequisites & Sizing Guide

**Documentation Date:** 2026-11-25  
**Component:** Infrastructure & Hardware Capacity Planning  
**Target Platform:** Ubuntu 24.04 LTS (x86_64 / arm64)  

---

## 1. Operating System & Architecture

The acquisition pipeline is tested and certified on **Ubuntu 24.04 LTS (Noble Numbat)** with Linux Kernel 6.8+. It relies strictly on standard POSIX semantics and GNU system utilities, making it compatible with any modern Debian-family Linux distribution.

| Specification | Minimum Requirement | Verified Production Standard |
| :--- | :--- | :--- |
| **OS Distribution** | Ubuntu 22.04 LTS / Debian 12 | Ubuntu 24.04.1 LTS |
| **Architecture** | 64-bit `x86_64` or `arm64` | `x86_64` (Intel/AMD) |
| **Linux Kernel** | Kernel `5.15+` | Kernel `6.8.0-149-generic` |
| **Init System** | `systemd` 249+ | `systemd` 255.4 |

---

## 2. Compute, Memory & Hardware Sizing

### Sizing Profiles

| Hardware Dimension | Minimum (Testing / Single Year) | Production Baseline (Full 20-Year Fleet) |
| :--- | :--- | :--- |
| **CPU Cores** | 4 cores | 16–24 cores (QEMU / Bare Metal) |
| **Physical Memory (RAM)** | 8 GiB | 32–64 GiB (Verified on 94 GiB host) |
| **Storage Capacity** | 80 GB SSD free | 200 GB+ SSD free (ext4) |
| **Network Throughput** | 25 Mbps sustained | 100 Mbps+ sustained outbound |

### Resource Consumption Breakdown
- **Compute Load:** With 50 concurrent worker threads, CPU utilization averages 15–25% on 24 cores (load average ~0.4–0.5).
- **RAM Headroom:** The streaming reader keeps RSS memory usage below **250 MB** for the Python worker process. Even during high-frequency I/O bursts, total system memory usage remains $< 2 \text{ GB}$.
- **Storage Breakdown Across 20 Years (2006–2026):**
  - Compressed Monthly TAR Archives: **~42.5 GB**
  - Companion Sidecar Index Files (`.idx`): **~5.5 GB**
  - Master Global Manifest (`s3_manifest_modern.csv.gz`): **0.75 GB**
  - Operational Logs & Reports: **~1.2 GB**
  - **Total Working Footprint:** **~50 GB**

---

## 3. Storage Architecture & Filesystem Optimization

- **Filesystem Type:** Standard `ext4` or `XFS`.
- **Inode Allocation:** Naive S3 downloads would require 25.5 million inodes, exhausting disk tables. The pipeline's **Monthly TAR Architecture** collapses 25.58M files into **240 container files**, consuming $< 500 \text{ inodes}$!
- **Block Allocation Slack:** Storing 25.5M loose files with 4 KB ext4 allocation wastes $> 80 \text{ GB}$ in slack space. The monthly TAR format writes contiguous 512-byte blocks, eliminating block slack entirely.
- **POSIX Advisory Locking:** The filesystem must support POSIX `fcntl.flock` locks across processes.

---

## 4. Network & Outbound Firewall Configuration

The acquisition system requires **zero inbound open ports**.

### Outbound Network Rules
| Destination Host | Destination Port | Protocol | Purpose |
| :--- | :--- | :--- | :--- |
| `*.s3.amazonaws.com` | `443` | HTTPS (TCP) | AWS S3 REST API & payload transfer |
| `openaq-data-archive.s3.us-east-1.amazonaws.com` | `443` | HTTPS (TCP) | Primary OpenAQ data archive endpoint |
| Ubuntu Archive Mirrors | `80` / `443` | HTTP/HTTPS | APT package installation |

---

## 5. User Account & Permissions Architecture

- **Service User:** Non-root user with dedicated home directory (e.g. `harsha` or `openaq`).
- **Sudo Rights:** Required only for initial package installation (`apt`) and systemd unit registration (`/etc/systemd/system/`).
- **Runtime Privilege:** All data downloads, script execution, file writing, and index generation run strictly under unprivileged user permissions (`User=harsha`, `Group=harsha`).
- **User Lingering:** **CRITICAL**: Systemd user lingering must be enabled:
  ```bash
  loginctl enable-linger <username>
  ```
  This ensures that background services and cgroups persist when the user disconnects from SSH.
