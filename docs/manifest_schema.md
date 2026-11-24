# S3 Manifest Schema Specification

**Documentation Date:** 2026-11-25  
**File Target:** `manifest/s3_manifest_modern.csv.gz`  
**Analytical Companion:** `manifest/manifest_summary.json`  

---

## 1. Gzip CSV Manifest Schema

The master manifest is stored as an RFC 1952 Gzip-compressed, comma-separated values (CSV) document containing **25,587,335 data rows** plus a single header row.

### CSV Column Definitions

| Column Name | Data Type | Nullable | Description & Example |
| :--- | :--- | :--- | :--- |
| **`location_id`** | Integer / String | No | Unique identifier of the OpenAQ monitoring location. Example: `10`, `61488`. |
| **`year`** | String (4 chars) | No | Four-digit calendar year parsed from the Hive partition. Range: `2006`–`2026`. |
| **`month`** | String (1–2 chars)| No | Calendar month parsed from Hive partition. Range: `01`–`12` (or `1`–`12` in older unpadded keys). |
| **`s3_key`** | String | No | Authoritative S3 object key. Example: `records/csv.gz/locationid=10/year=2007/month=07/location-10-20070719.csv.gz`. |
| **`size_bytes`** | Integer (64-bit) | No | Exact byte length of the compressed object in S3. Used for disk allocation and download validation. |
| **`etag`** | Hexadecimal String| No | S3 ETag (standard MD5 digest, 32 hex characters without quotes). Used for data integrity verification. |
| **`last_modified`**| ISO 8601 Timestamp| No | UTC timestamp when S3 recorded the object. Example: `2023-11-09T09:03:20+00:00`. |

---

## 2. Sample Data Records

```csv
location_id,year,month,s3_key,size_bytes,etag,last_modified
10,2007,07,records/csv.gz/locationid=10/year=2007/month=07/location-10-20070719.csv.gz,179,35b835abe7235a6e49e257255be51336,2023-11-09T09:03:20+00:00
10,2007,07,records/csv.gz/locationid=10/year=2007/month=07/location-10-20070721.csv.gz,178,2a39cd53055de17935c258ee6d4b6630,2023-11-09T09:03:20+00:00
10,2007,07,records/csv.gz/locationid=10/year=2007/month=07/location-10-20070725.csv.gz,179,11c175fc169ef90d0ed3aad41473d241,2023-11-09T09:03:20+00:00
10,2007,07,records/csv.gz/locationid=10/year=2007/month=07/location-10-20070727.csv.gz,178,35d4b1c4ddcfd9ad97970c66429fe5e3,2023-11-09T09:03:05+00:00
```

---

## 3. Manifest Summary Metadata Schema (`manifest_summary.json`)

Along with the CSV manifest, the generator produces a structured analytical report:

```json
{
  "updated_at_utc": "ISO 8601 UTC timestamp",
  "status": "COMPLETED | INTERRUPTED (SAFELY PAUSED)",
  "total_locations_scanned": 56480,
  "total_files": 25587335,
  "total_bytes": 22724361960,
  "total_gb": 21.16,
  "year_distribution": {
    "YYYY": {
      "files": 4365888,
      "bytes": 4539218340,
      "mb": 4328.94
    }
  },
  "etag_formats": {
    "standard_md5": 25587335
  }
}
```

### Key Statistical Invariants
- **100% Single-Part Uploads:** All 25,587,335 objects have standard 32-character hexadecimal MD5 ETags. There are zero multipart uploads (`etag` containing `-`), confirming that every S3 ETag is a direct MD5 digest of the compressed payload.
- **Year Distribution Totals:**
  - `2006`: 113 files (19,698 bytes)
  - `2007`: 505 files (88,092 bytes)
  - `2008`: 182 files (31,874 bytes)
  - `2013`: 211 files (126,824 bytes)
  - `2014`: 1,093 files (332,237 bytes)
  - `2015`: 3,590 files (1,757,792 bytes)
  - `2016`: 640,863 files (250,423,735 bytes)
  - `2017`: 1,266,459 files (770,261,551 bytes)
  - `2018`: 1,588,276 files (1,001,485,772 bytes)
  - `2019`: 2,226,469 files (1,514,864,379 bytes)
  - `2020`: 2,404,833 files (1,257,139,551 bytes)
  - `2021`: 1,642,675 files (865,512,925 bytes)
  - `2022`: 1,200,351 files (1,077,667,220 bytes)
  - `2023`: 2,155,060 files (3,106,713,471 bytes)
  - `2024`: 3,707,241 files (3,928,203,292 bytes)
  - `2025`: 4,365,888 files (4,539,218,340 bytes)
  - `2026`: 4,383,524 files (4,410,502,911 bytes)
  - `unknown`: 2 files (12,296 bytes)
