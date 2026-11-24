#!/usr/bin/env python3
"""
S3 Partition Scanner for OpenAQ Modern Archive
Discovers all unique locationid= prefixes in openaq-data-archive/records/csv.gz/
and writes them to manifest/location_ids.txt.
"""

import boto3
from botocore import UNSIGNED
from botocore.client import Config
import time
import os

PROJECT_DIR = os.environ.get("OPENAQ_PROJECT_DIR", "/home/harsha/openaq")
MANIFEST_DIR = os.path.join(PROJECT_DIR, "manifest")
OUT_FILE = os.path.join(MANIFEST_DIR, "location_ids.txt")

os.makedirs(MANIFEST_DIR, exist_ok=True)

s3 = boto3.client('s3', region_name='us-east-1', config=Config(signature_version=UNSIGNED))

paginator = s3.get_paginator('list_objects_v2')
page_iterator = paginator.paginate(
    Bucket='openaq-data-archive',
    Prefix='records/csv.gz/',
    Delimiter='/'
)

locations = []
t0 = time.time()
print(f"Scanning S3 prefixes in bucket 'openaq-data-archive' (prefix: records/csv.gz/)...")
for page in page_iterator:
    for cp in page.get('CommonPrefixes', []):
        prefix = cp['Prefix']
        sub = prefix[len('records/csv.gz/'):].rstrip('/')
        if sub.startswith('locationid='):
            locations.append(sub.split('=')[1])

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    for lid in locations:
        f.write(lid + '\n')

print(f"Saved {len(locations):,} location IDs to {OUT_FILE} in {time.time()-t0:.2f}s")
