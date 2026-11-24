#!/usr/bin/env python3
"""
OpenAQ S3 Modern Archive Manifest Generator (Resumable & Signal-Safe)
Runs on Ubuntu Server 130 with 50 concurrent worker threads.
Streams the inventory into a compressed CSV manifest:
  /home/harsha/openaq/manifest/s3_manifest_modern.csv.gz
and produces an analytical summary report:
  /home/harsha/openaq/manifest/manifest_summary.json

Usage:
  # Fresh run (scans all locations)
  ./venv/bin/python bin/generate_manifest.py

  # Resume run (skips already-manifested locations and appends)
  ./venv/bin/python bin/generate_manifest.py --resume

  # Testing mode (limit to N locations)
  ./venv/bin/python bin/generate_manifest.py --limit=100
"""

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import gzip
import os
import sys
import json
from collections import defaultdict
import threading
import datetime
import signal
import csv

PROJECT_DIR = os.environ.get("OPENAQ_PROJECT_DIR", "/home/harsha/openaq")
MANIFEST_DIR = os.path.join(PROJECT_DIR, "manifest")
OUT_GZ = os.path.join(MANIFEST_DIR, "s3_manifest_modern.csv.gz")
SUMMARY_JSON = os.path.join(MANIFEST_DIR, "manifest_summary.json")
LOC_IDS_FILE = os.path.join(MANIFEST_DIR, "location_ids.txt")

# Parse CLI flags
if "--help" in sys.argv or "-h" in sys.argv:
    print(__doc__)
    sys.exit(0)

limit = None
resume = False
for arg in sys.argv[1:]:
    if arg.startswith("--limit="):
        limit = int(arg.split("=", 1)[1])
    elif arg == "--resume":
        resume = True

os.makedirs(MANIFEST_DIR, exist_ok=True)
s3 = boto3.client('s3', region_name='us-east-1', config=Config(signature_version=UNSIGNED, max_pool_connections=60))

# Load all location IDs
with open(LOC_IDS_FILE) as f:
    all_locs = [line.strip() for line in f if line.strip()]

completed_locs = set()
total_files_count = 0
total_bytes_count = 0
year_files = defaultdict(int)
year_bytes = defaultdict(int)
etag_formats = defaultdict(int)

# If resume requested, inspect existing manifest
if resume and os.path.exists(OUT_GZ):
    print(f"Scanning existing manifest {OUT_GZ} to identify completed locations...")
    try:
        with gzip.open(OUT_GZ, 'rt', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 6:
                    completed_locs.add(row[0])
                    total_files_count += 1
                    yr = row[1]
                    sz = int(row[4])
                    etag = row[5]
                    total_bytes_count += sz
                    year_files[yr] += 1
                    year_bytes[yr] += sz
                    if '-' in etag:
                        etag_formats['multipart'] += 1
                    else:
                        etag_formats['standard_md5'] += 1
        print(f"Found {len(completed_locs):,} already-manifested locations ({total_files_count:,} files, {total_bytes_count/(1024**3):.2f} GB).")
    except Exception as e:
        print(f"Warning reading existing manifest: {e}. Starting fresh.")
        completed_locs = set()

# Filter target locations
target_locs = [loc for loc in all_locs if loc not in completed_locs]
if limit:
    target_locs = target_locs[:limit]

print(f"Locations to process: {len(target_locs):,} (out of {len(all_locs):,} total)")

if not target_locs:
    print("All locations have already been processed!")
    sys.exit(0)

# Open output file in append or write mode
write_header = not (resume and os.path.exists(OUT_GZ) and len(completed_locs) > 0)
out_file = gzip.open(OUT_GZ, 'at' if not write_header else 'wt', encoding='utf-8')
if write_header:
    out_file.write("location_id,year,month,s3_key,size_bytes,etag,last_modified\n")
    out_file.flush()

lock = threading.Lock()
stop_requested = threading.Event()

def signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name
    print(f"\nReceived {sig_name}! Gracefully stopping workers and flushing manifest to disk...", flush=True)
    stop_requested.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

empty_locations = []

def process_location(lid):
    if stop_requested.is_set():
        return lid, None, "stopped"
        
    paginator = s3.get_paginator('list_objects_v2')
    prefix = f'records/csv.gz/locationid={lid}/'
    loc_records = []
    
    try:
        for p in paginator.paginate(Bucket='openaq-data-archive', Prefix=prefix):
            if stop_requested.is_set():
                break
            for obj in p.get('Contents', []):
                k = obj['Key']
                sz = obj['Size']
                etag = obj['ETag'].strip('"')
                lm = obj['LastModified'].isoformat()
                
                parts = k.split('/')
                yr = 'unknown'
                mo = 'unknown'
                for part in parts:
                    if part.startswith('year='):
                        yr = part.split('=')[1]
                    elif part.startswith('month='):
                        mo = part.split('=')[1]
                        
                loc_records.append((lid, yr, mo, k, sz, etag, lm))
    except Exception as e:
        return lid, None, str(e)
        
    return lid, loc_records, None

t0 = time.time()
done_count = 0
total_locs = len(target_locs)

with ThreadPoolExecutor(max_workers=50) as executor:
    futures = {executor.submit(process_location, lid): lid for lid in target_locs}
    
    for f in as_completed(futures):
        if stop_requested.is_set():
            break
            
        lid, records, err = f.result()
        with lock:
            done_count += 1
            if err or records is None or len(records) == 0:
                empty_locations.append(lid)
            else:
                for rec in records:
                    _lid, yr, mo, k, sz, etag, lm = rec
                    total_files_count += 1
                    total_bytes_count += sz
                    year_files[yr] += 1
                    year_bytes[yr] += sz
                    
                    if '-' in etag:
                        etag_formats['multipart'] += 1
                    else:
                        etag_formats['standard_md5'] += 1
                        
                    out_file.write(f"{_lid},{yr},{mo},{k},{sz},{etag},{lm}\n")
                    
            if done_count % 100 == 0:
                out_file.flush()
                
            if done_count % 500 == 0 or done_count == total_locs:
                elapsed = time.time() - t0
                rate = done_count / elapsed if elapsed > 0 else 0
                rem = (total_locs - done_count) / rate if rate > 0 else 0
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                      f"Progress: {done_count:,}/{total_locs:,} locs ({done_count/total_locs*100:.1f}%) | "
                      f"{total_files_count:,} files ({total_bytes_count/(1024**3):.2f} GB) | "
                      f"Rate: {rate:.1f} loc/s | ETA: {rem/60:.1f} min", flush=True)

out_file.flush()
out_file.close()

elapsed = time.time() - t0
status_str = "INTERRUPTED (SAFELY PAUSED)" if stop_requested.is_set() else "COMPLETED"

print("\n" + "="*70)
print(f"MANIFEST RUN {status_str} in {elapsed/60:.2f} minutes")
print("="*70)
print(f"Locations Processed this Run: {done_count:,}")
print(f"Total S3 Files in Manifest:   {total_files_count:,}")
print(f"Total Compressed Volume:      {total_bytes_count:,} bytes ({total_bytes_count / (1024**3):.2f} GB)")

summary_data = {
    'updated_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': status_str,
    'total_locations_scanned': len(completed_locs) + done_count,
    'total_files': total_files_count,
    'total_bytes': total_bytes_count,
    'total_gb': round(total_bytes_count / (1024**3), 2),
    'year_distribution': {
        yr: {'files': year_files[yr], 'bytes': year_bytes[yr], 'mb': round(year_bytes[yr]/(1024*1024), 2)}
        for yr in sorted(year_files.keys())
    },
    'etag_formats': dict(etag_formats)
}

with open(SUMMARY_JSON, 'w') as f:
    json.dump(summary_data, f, indent=2)

print(f"Updated manifest: {OUT_GZ}")
print(f"Updated summary:  {SUMMARY_JSON}")
