# Manifest Inventory & Asset Register

**Documentation Date:** 2026-11-25  
**Component:** OpenAQ S3 Manifest Metadata Inventory  

---

## 1. Master Production Manifest Assets

| Asset Path | File Type | Size (Bytes) | SHA-256 Checksum | Record Count | Status / Preservation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `manifest/s3_manifest_modern.csv.gz` | Gzip CSV | 782,863,355 (~747 MB) | `b0c3c0d0a86e3b074eecad9e28bb207a306998c9886636b90f4c2f1beea36c6a` | 25,587,335 | **CRITICAL ASSET**: Preserved in external backup storage. |
| `manifest/manifest_summary.json` | JSON | 1,850 (~1.8 KB) | `f0da6b896b0eeaa05cfda24177b9d6fc573ec663df8a044703a4c0eb3f1ee22c` | N/A | **Committed to Git**: Official summary of global dataset distribution. |
| `manifest/location_ids.txt` | Plaintext | 386,909 (~386 KB) | `57f0ebc727bb13c9e6bbdfeb464871d3c0b53d47ad048f32230ef566f123a48e` | 56,480 lines | **Committed to Git**: Unique monitoring location IDs. |

---

## 2. Historical & Superseded Manifest Variants

The following intermediate manifest files were created during initial developmental phases and are documented for complete historical traceability:

| Asset Path | Size (Bytes) | Creation Context | Current Status |
| :--- | :--- | :--- | :--- |
| `manifest/s3_manifest_2025.csv.gz` | 135,648,652 | Single-year manifest generated during the Year 2025 pilot evaluation (4,365,888 entries). | **Superseded** by the global modern manifest. |
| `manifest/manifest_summary_2025.json` | 1,369 | Single-year analytical summary for the 2025 pilot. | **Superseded** by `manifest_summary.json`. |
| `manifest/remaining_location_ids.txt` | 382,741 | Intermediate file tracking unprocessed location IDs during a test run. | **Obsolete**. Replaced by native `--resume` flag logic in `bin/generate_manifest.py`. |
| `manifest/s3_manifest_modern.csv.gz.raw_unclosed` | 17,148,392 | Partial output from an early ungracefully terminated run before signal trapping was implemented. | **Obsolete**. Replaced by production manifest. |
| `manifest/legacy_prefixes_summary.txt` | 1,301 | Notes cataloging exploratory scans of legacy non-standard S3 prefixes (`realtime-gzipped/`, `ndjson/`). | **Historical Reference**. |

---

## 3. Data Distribution by Calendar Year

Summary of records cataloged in `s3_manifest_modern.csv.gz`:

| Year | Total Files | Total Compressed Bytes | Total MB / GB |
| :--- | :--- | :--- | :--- |
| **2006** | 113 | 19,698 | 0.02 MB |
| **2007** | 505 | 88,092 | 0.08 MB |
| **2008** | 182 | 31,874 | 0.03 MB |
| **2013** | 211 | 126,824 | 0.12 MB |
| **2014** | 1,093 | 332,237 | 0.32 MB |
| **2015** | 3,590 | 1,757,792 | 1.68 MB |
| **2016** | 640,863 | 250,423,735 | 238.82 MB |
| **2017** | 1,266,459 | 770,261,551 | 734.58 MB |
| **2018** | 1,588,276 | 1,001,485,772 | 955.09 MB |
| **2019** | 2,226,469 | 1,514,864,379 | 1.44 GB |
| **2020** | 2,404,833 | 1,257,139,551 | 1.20 GB |
| **2021** | 1,642,675 | 865,512,925 | 825.42 MB |
| **2022** | 1,200,351 | 1,077,667,220 | 1.03 GB |
| **2023** | 2,155,060 | 3,106,713,471 | 2.96 GB |
| **2024** | 3,707,241 | 3,928,203,292 | 3.75 GB |
| **2025** | 4,365,888 | 4,539,218,340 | 4.33 GB |
| **2026** | 4,383,524 | 4,410,502,911 | 4.21 GB |
| **unknown** | 2 | 12,296 | 0.01 MB |
| **TOTAL** | **25,587,335** | **22,724,361,960** | **21.16 GiB (22.72 GB)** |
