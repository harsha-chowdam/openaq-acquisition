# OpenAQ Historical Data Source Specification

**Documentation Date:** 2026-11-25  
**Verification Status:** Verified against upstream AWS S3 bucket and live pipeline  
**Target Repository:** `openaq-acquisition`  

---

## 1. Upstream Authority & Data Provider Overview

- **Organization:** OpenAQ Inc. (501(c)(3) environmental tech non-profit)
- **Official Website:** [https://openaq.org](https://openaq.org)
- **Official Documentation:** [https://docs.openaq.org](https://docs.openaq.org)
- **Registry of Open Data on AWS:** [https://registry.opendata.aws/openaq/](https://registry.opendata.aws/openaq/)
- **Sponsorship:** Hosted under the **AWS Open Data Sponsorship Program**, providing free, public, direct S3 access to global air quality measurements without egress billing.

---

## 2. AWS S3 Storage Architecture & Access Model

The acquisition pipeline interfaces directly with OpenAQ's authoritative AWS S3 bucket.

### S3 Endpoint & Bucket Parameters
| Parameter | Value | Notes |
| :--- | :--- | :--- |
| **S3 Bucket Name** | `openaq-data-archive` | Authoritative archive bucket |
| **AWS Region** | `us-east-1` (US East, N. Virginia) | Low-latency endpoint |
| **Public URL** | `https://openaq-data-archive.s3.us-east-1.amazonaws.com/` | Public HTTPS gateway |
| **Authentication Requirement** | **None (Anonymous / Unsigned)** | No AWS account, IAM user, access key, or secret key required |
| **Requester Pays** | **Disabled** (Free public egress) | Data egress is sponsored by AWS Open Data |
| **Boto3 Client Configuration** | `Config(signature_version=botocore.UNSIGNED)` | Instructs AWS SDK to omit `Authorization` headers |
| **AWS CLI Command Form** | `aws s3 ... --no-sign-request` | Standard command for testing without credentials |

---

## 3. Bucket Partitioning & Object Key Layout

OpenAQ organizes modern measurement records using a hierarchical Hive-style partitioning scheme based on location, year, and month.

### Modern Partition Hierarchy
```
records/csv.gz/locationid={LOCATION_ID}/year={YYYY}/month={MM}/location-{LOCATION_ID}-{YYYYMMDD}.csv.gz
```

### Component Breakdown
1. **Root Prefix:** `records/csv.gz/`  
   Distinguishes modern gzip CSV records from legacy or vendor-specific directories.
2. **Location Partition:** `locationid={LOCATION_ID}/`  
   Where `{LOCATION_ID}` is an integer representing a distinct monitoring station (e.g., `locationid=10`, `locationid=4619882`). Discovered total: **56,480 active locations**.
3. **Temporal Partitions:**  
   - `year={YYYY}/`: 4-digit calendar year (`2006` through `2026`).
   - `month={MM}/`: 2-digit zero-padded calendar month (`01` through `12`). Note: A small number of older keys (2016–2018) in S3 omitted the zero-padding (e.g. `month=3`); the acquisition pipeline automatically normalizes all months to two digits.
4. **Object Filename:** `location-{LOCATION_ID}-{YYYYMMDD}.csv.gz`  
   Each file contains the 24-hour aggregated sensor readings for that specific location on that UTC calendar date.

---

## 4. Object Format & Metadata Specifications

### Payload Compression & Encoding
- **Container Format:** Gzip compressed CSV (`.csv.gz`).
- **Compression Standard:** RFC 1952 deflate algorithm.
- **Payload Schema:** Tabular CSV with header row:
  ```csv
  location_id,sensors_id,datetime,value,lat,lon
  ```
  *(Note: Internal column names may vary slightly across provider generations, but all are RFC 4180 compliant CSVs).*
- **Decompression Expansion Ratio:** Measured at **12.42×** average expansion (e.g., 22.72 GB compressed expands to ~282 GB raw CSV text).

### S3 Metadata Attributes
For every object returned by `s3.list_objects_v2` or `s3.get_object`:
- **`Key`:** Complete path string.
- **`Size` (`ContentLength`):** Exact byte count of the compressed gzip object.
- **`ETag`:** Standard MD5 cryptographic digest formatted as a 32-character hexadecimal string inside quotes (e.g., `"35b835abe7235a6e49e257255be51336"`). All 25.58M objects in the modern archive are single-part uploads whose ETags match their standard MD5 checksum.
- **`LastModified`:** ISO 8601 UTC timestamp of S3 storage time.

---

## 5. Historical Dataset Inventory Profile

Across the entire 20-year span (2006–2026), the global modern archive contains:

- **Total Monitored Locations:** 56,480 unique stations
- **Total Objects / Daily Files:** 25,587,335 files
- **Total Compressed Payload:** 22,724,361,960 bytes (~22.72 GB / 21.16 GiB)
- **Uncompressed Raw CSV Text:** ~282 GB
- **Chronological Distribution:**
  - **2006–2015 (Early Era):** 5,694 files (~2.2 MB total). Sparse historical baseline records.
  - **2016–2021 (Global Expansion):** 9,728,575 files (~5.78 GB total). Rapid worldwide sensor onboarding.
  - **2022–2026 (Modern High-Frequency Era):** 15,853,066 files (~16.94 GB total). Dense global coverage (~3.7M–4.4M files/year).

---

## 6. Access Limitations & Rate Limiting Guidelines

### S3 Throughput & Thresholds
- AWS S3 natively scales to support at least **3,500 PUT/COPY/POST/DELETE** and **5,500 GET/HEAD** requests per second per partitioned prefix.
- Because OpenAQ keys are partitioned across 56,480 unique `locationid=` prefixes, request volume is distributed across multiple AWS S3 physical storage partitions.
- The pipeline's 50 concurrent worker threads produce an average download rate of **~210 GET requests per second**, which represents **<4% of a single prefix limit**.
- Over the acquisition of 25.5M files, zero HTTP 429 (Too Many Requests) or HTTP 503 (Slow Down) responses were encountered.

### Direct Access vs API Access
The pipeline intentionally utilizes **direct anonymous S3 bulk transfer** rather than OpenAQ's v3 REST API (`https://api.openaq.org/v3/`).
- *Why REST API is Not Used for Bulk Acquisition:* The REST API enforces strict rate limits (60 requests/minute on free keys) and API key requirements. Downloading 25.5M files via REST would take months. Direct S3 streaming bypasses rate limits entirely and downloads entire years in hours.
