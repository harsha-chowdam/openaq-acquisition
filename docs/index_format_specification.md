# Sidecar Index (.idx) Format Specification & Random-Access Retrieval

**Documentation Date:** 2026-11-25  
**Component:** OpenAQ Storage Indexing Subsystem  
**File Target:** `raw/s3_modern/year={YYYY}/month={MM}.idx`  

---

## 1. Purpose & Design Objectives

Every monthly TAR container (`month=MM.tar`) is accompanied by an exact companion sidecar index file:
```text
raw/s3_modern/year={YYYY}/month={MM}.idx
```

### Key Objectives
1. **O(1) Random-Access Retrieval:** Allows applications to extract any single file from a 5 GB TAR archive in $< 2 \text{ milliseconds}$ without reading or decompressing any preceding entries.
2. **Cryptographic Integrity Ledger:** Stores cryptographic SHA-256 and MD5 digests computed at retrieval time for continuous tamper detection.
3. **Resumable State Tracker:** Acts as an immutable record of completed downloads; on restart, the acquisition engine reads the index into a set to skip already-acquired files instantly.
4. **Disaster Recovery Anchor:** Enables physical container geometry audits and corrupt-byte truncation.

---

## 2. CSV Index Schema & Field Definitions

The index is formatted as a comma-separated values (CSV) document with an explicit header row:

```csv
s3_key,tar_offset,byte_length,file_size,etag,sha256,retrieved_at_utc
```

### Field Definitions

| Column | Data Type | Description |
| :--- | :--- | :--- |
| **`s3_key`** | String | Complete authoritative S3 object key. Example: `records/csv.gz/locationid=10/year=2007/month=07/location-10-20070719.csv.gz` |
| **`tar_offset`** | Integer (64-bit) | The absolute physical byte offset in `month=MM.tar` where this member's **512-byte TAR header block** begins. |
| **`byte_length`** | Integer (64-bit) | The total byte span occupied in `month=MM.tar` by this member (512-byte header + payload + zero-padding). |
| **`file_size`** | Integer (64-bit) | The exact byte length of the compressed `.csv.gz` data payload. |
| **`etag`** | Hexadecimal | S3 ETag (32-character MD5 checksum) recorded from S3 metadata. |
| **`sha256`** | Hexadecimal | Cryptographic SHA-256 checksum (64 characters) computed over the downloaded payload. |
| **`retrieved_at_utc`**| ISO 8601 Timestamp | UTC timestamp when the object was written to disk. |

### Sample Index Records
```csv
s3_key,tar_offset,byte_length,file_size,etag,sha256,retrieved_at_utc
records/csv.gz/locationid=10/year=2007/month=07/location-10-20070719.csv.gz,0,1024,179,35b835abe7235a6e49e257255be51336,7c4b8b6d859fa21ec46369f69741b2e652a265691eef350c3d97b0a8809fc575,2026-11-24T09:39:10.123456+00:00
records/csv.gz/locationid=10/year=2007/month=07/location-10-20070721.csv.gz,1024,1024,178,2a39cd53055de17935c258ee6d4b6630,94273fdcf4ae996efc0d995966624f706d87f5898305c486e9aa40538059f812,2026-11-24T09:39:10.134567+00:00
records/csv.gz/locationid=10/year=2007/month=07/location-10-20070725.csv.gz,2048,1024,179,11c175fc169ef90d0ed3aad41473d241,1ab23cd4ef...4920,2026-11-24T09:39:10.145678+00:00
```

---

## 3. Byte Offset Arithmetic & Geometry Formulas

Because standard GNU TAR records headers in 512-byte blocks and pads data to 512-byte boundaries:

1. **Header Location:**
   $$\text{Offset}_{\text{header}} = \text{tar\_offset}$$
2. **Payload Location (Data Seek Target):**
   $$\text{Offset}_{\text{payload}} = \text{tar\_offset} + 512$$
3. **Padding Length:**
   $$\text{Length}_{\text{padding}} = \text{byte\_length} - 512 - \text{file\_size}$$
4. **Contiguity Invariant (Zero Gaps / Overlaps):**
   For any consecutive records $i$ and $i+1$:
   $$\text{tar\_offset}_{i+1} = \text{tar\_offset}_i + \text{byte\_length}_i$$
5. **Container Termination Invariant:**
   For a container with $N$ records:
   $$\text{Physical File Size of TAR} = \text{tar\_offset}_N + \text{byte\_length}_N$$

---

## 4. O(1) Random-Access Retrieval Algorithm

To retrieve any object without reading earlier entries or extracting the archive:

```python
import gzip

def get_file_from_tar(tar_path, tar_offset, file_size):
    """O(1) random-access file retrieval from TAR container."""
    with open(tar_path, "rb") as f:
        # Seek directly past the 512-byte TAR header to the payload
        f.seek(tar_offset + 512)
        # Read exact compressed payload
        compressed_bytes = f.read(file_size)
        
    # Decompress gzip CSV data in memory
    csv_text = gzip.decompress(compressed_bytes).decode('utf-8')
    return csv_text
```

This procedure requires only **one filesystem `seek` and one `read`**, executing in sub-millisecond time.

---

## 5. Index Reconstruction Procedure (If `.idx` Is Lost)

If an index file is accidentally deleted or corrupted, it can be mathematically reconstructed directly from `month=MM.tar` using the included recovery script or standard Python TAR parsing:

```python
import tarfile
import hashlib
import csv
import datetime

def rebuild_index(tar_path, idx_path):
    with open(tar_path, "rb") as tf, open(idx_path, "w", newline="", encoding="utf-8") as idxf:
        writer = csv.writer(idxf)
        writer.writerow(["s3_key", "tar_offset", "byte_length", "file_size", "etag", "sha256", "retrieved_at_utc"])
        
        current_offset = 0
        while True:
            header_bytes = tf.read(512)
            if not header_bytes or header_bytes == b'\x00' * 512:
                break
                
            tarinfo = tarfile.TarInfo.frombuf(header_bytes, encoding='utf-8')
            s3_key = tarinfo.name
            size = tarinfo.size
            
            # Read payload
            payload = tf.read(size)
            sha256 = hashlib.sha256(payload).hexdigest()
            md5 = hashlib.md5(payload).hexdigest()
            
            # Read alignment padding
            pad_len = (512 - (size % 512)) % 512
            if pad_len > 0:
                tf.read(pad_len)
                
            byte_length = 512 + size + pad_len
            now_iso = datetime.datetime.fromtimestamp(tarinfo.mtime, datetime.timezone.utc).isoformat()
            
            writer.writerow([s3_key, current_offset, byte_length, size, md5, sha256, now_iso])
            current_offset += byte_length
            
    print(f"Reconstructed index: {idx_path}")
```
This guarantees that **the TAR containers are self-describing and independently recoverable**.
