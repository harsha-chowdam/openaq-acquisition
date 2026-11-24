# Local Mac Environment Inventory

**Assessment Date:** 2026-11-25  
**Local Host:** Sri's MacBook Air (`arm64`)  
**Local Workspace:** `/Users/harsha/data`  

---

## 1. Local Machine Specifications

| Attribute | Specification | Verification Evidence |
| :--- | :--- | :--- |
| **Operating System** | macOS 26.3 (Build 25D125) | `sw_vers` |
| **Architecture** | Apple Silicon (`arm64`) | `uname -m` |
| **Kernel** | Darwin Kernel Version 25.3.0 | `uname -v` |
| **Shell** | `/bin/zsh` | `echo $SHELL` |
| **Local Workspace Root** | `/Users/harsha/data` | Active working directory |
| **Primary Storage Volume** | APFS container (`/dev/disk3s1s1`), 228 GiB total, 15 GiB available | `df -h /` |

---

## 2. Local File Catalog & Classification

The `/Users/harsha/data` directory served as the initial development and staging workstation before jobs were migrated to the 24-core production server. A thorough audit reveals 58 distinct files categorized below:

### A. Core Acquisition Pipeline (Bit-for-Bit Synchronized with Server)
| Filename | Size | SHA-256 Checksum | Sync Status |
| :--- | :--- | :--- | :--- |
| `acquire_s3_archive.py` | 26,404 bytes | `42f9c0706677271304fa5176e05e31be80a3d7817f11ab3590cab2a3a1b8f417` | **Identical** to `/home/harsha/openaq/bin/acquire_s3_archive.py` |
| `acquire_year.sh` | 5,674 bytes | `b5dfd3bb5ea81193682c4afbde2c47548132eb1aa0ac02e3c3ebca95cf29f7a1` | **Identical** to `/home/harsha/openaq/bin/acquire_year.sh` |
| `audit_acquisition_integrity.py` | 16,375 bytes | `62926be9ce430547868f6d69361759047dfc055616572889b4388ffffcc91cfc` | **Identical** to `/home/harsha/openaq/audit_acquisition_integrity.py` |
| `save_location_ids.py` | 862 bytes | `05714388149c064258ad6ec4fcec8aea732e637ac39e86ae87da6b7d9333e174` | **Identical** to `/home/harsha/openaq/save_location_ids.py` |
| `verify_tar_archive.py` | 4,784 bytes | `b72fd33d5833f15ce3323638fbd606ab01a381e8397e5788a980f9598aa74fda` | **Identical** to `/home/harsha/openaq/bin/verify_tar_archive.py` |

### B. Remote Management & SSH Infrastructure
| Filename | Purpose | Security Classification |
| :--- | :--- | :--- |
| `remote.sh` | SSH wrapper invoking `ssh -i /path/to/key user@<PRODUCTION_SERVER_IP> "$@"` | Local helper script (Exclude from Git) |
| `.ssh/id_ed25519` | Ed25519 private SSH authentication key for Server 130 access | **CRITICAL PRIVATE KEY (Exclude from Git)** |
| `.ssh/id_ed25519.pub`| Ed25519 public SSH key | Public key |
| `copy_ssh_key.exp` | Expect script for automated SSH key installation | Local helper script (Exclude from Git) |
| `ssh_cmd.exp` | Expect script for interactive SSH command dispatch | Local helper script (Exclude from Git) |

### C. Manifest Generation & Exploratory Discovery
| Filename | Size | Purpose & Evaluation |
| :--- | :--- | :--- |
| `generate_manifest.py` | 6,043 bytes | Initial non-resumable generator. Superseded by server's resumable `bin/generate_manifest.py` (8,201 bytes). |
| `generate_full_manifest.py` | 5,744 bytes | Early variant exploring full bucket scan. Superseded. |
| `generate_manifest_2025.py` | 6,865 bytes | Scoped generator used during single-year 2025 pilot. |
| `location_ids.txt` | 386,909 bytes | Output of `save_location_ids.py` listing 56,480 discovered locations. |
| `openaq_s3_discovery.py` | 7,665 bytes | Initial exploratory S3 prefix scanner. |
| `count_locations.py` | 1,528 bytes | Quick count utility for location prefixes. |
| `scan_legacy_prefixes.py` | 2,260 bytes | Scanner targeting deprecated non-standard S3 structures. |
| `investigate_legacy_providers.py` | 6,395 bytes | Analyzed legacy provider S3 buckets. |
| `legacy_prefixes_summary.txt` | 1,301 bytes | Summary notes of legacy S3 structures. |
| `legacy_provider_investigation.json` | 25,407 bytes | Structured JSON output of legacy provider investigation. |

### D. Database Development & Ingestion Scripts (Reserved for Database Project)
| Filename | Purpose | Scope Boundary Handling |
| :--- | :--- | :--- |
| `openaq_v4.sql` | Initial PostgreSQL partitioned schema v4 | **Excluded from this Git repository** (Separate DB project) |
| `openaq_v4_1.sql` | Refined PostgreSQL partitioned schema v4.1 | **Excluded from this Git repository** (Separate DB project) |
| `ingest_full_year_2025.py` | Full-year database ingestion worker | **Excluded from this Git repository** (Separate DB project) |
| `ingest_month_pilot.py` | Single-month database ingestion test | **Excluded from this Git repository** (Separate DB project) |
| `test_v4_pipeline.py` | Schema and ingestion integration test | **Excluded from this Git repository** (Separate DB project) |
| `profile_2025_dataset.py` | Schema profiling and data type validation | **Excluded from this Git repository** (Separate DB project) |
| `validate_parameter_mapping.py` | Sensor-to-parameter relationship checks | **Excluded from this Git repository** (Separate DB project) |
| `validate_sensor_uniqueness_and_consistency.py` | Primary key and foreign key checks | **Excluded from this Git repository** (Separate DB project) |
| `verify_full_year_2025.py` | Ingested table row count verification | **Excluded from this DB repository** (Separate DB project) |
| `verify_january_ingestion.py` | Pilot ingestion table verification | **Excluded from this Git repository** (Separate DB project) |

---

## 3. Git Environment on Mac

- **Git Client:** `/usr/bin/git` (Apple Git-158)
- **Configured Identity:**
  - `user.name`: `harsha`
  - `user.email`: `harsha0632@gmail.com`
- **Current Workspace Git Status:** Not currently initialized as a git repository (`.git` absent in `/Users/harsha/data`).
- **Staging Plan:** The clean repository will be initialized in `/Users/harsha/data/openaq-acquisition` with strict `.gitignore` safeguards before publication.
