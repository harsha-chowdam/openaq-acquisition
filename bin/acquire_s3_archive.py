#!/usr/bin/env python3
"""
OpenAQ S3 Archive Acquisition Engine with Optimized O(1) Monthly TAR Packaging
Supports:
- Reusable year-parameterized acquisition (--year=YYYY)
- Direct manifest streaming (--manifest-path=...) or S3 partition scanning
- Dynamic disk-space pre-flight check based on manifest summary & safety margin
- Process concurrency protection via fcntl.flock on per-year lockfiles
- High-throughput multi-threaded downloads with streaming generator & bounded memory queue
- Resumable downloads (skips already-acquired objects via durable .idx check)
- Monthly TAR packaging with exact original S3 key preservation
- O(1) direct block append avoiding quadratic tarfile scan overhead
- Durable .idx sidecar with byte offsets, lengths, ETags, SHA-256
- Strict integrity checks: Content-Length, gzip magic/decompress, SHA-256, ETag
- Crash recovery: synchronizes TAR size to index on restart (truncates un-indexed writes)
- Dry-run validation mode (--dry-run)
- Per-year isolated logging and non-zero exit codes on failure
"""

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
import sys
import tarfile
import hashlib
import gzip
import io
import datetime
import argparse
import csv
import logging
import threading
import signal
import fcntl
import shutil
import json

PROJECT_DIR = os.environ.get("OPENAQ_PROJECT_DIR", "/home/harsha/openaq")
RAW_DIR = os.path.join(PROJECT_DIR, "raw")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
TMP_DIR = os.path.join(PROJECT_DIR, "tmp")
MANIFEST_DIR = os.path.join(PROJECT_DIR, "manifest")
DEFAULT_MANIFEST = os.path.join(MANIFEST_DIR, "s3_manifest_modern.csv.gz")
DEFAULT_SUMMARY = os.path.join(MANIFEST_DIR, "manifest_summary.json")

class YearLock:
    """Process-level non-blocking lock to prevent concurrent writers for the same year."""
    def __init__(self, year, lock_dir=TMP_DIR):
        self.year = str(year)
        self.lock_path = os.path.join(lock_dir, f"acquire_year_{self.year}.lock")
        self.fd = None

    def acquire(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.lock_path)), exist_ok=True)
            self.fd = open(self.lock_path, 'w')
            fcntl.flock(self.fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd.write(f"PID: {os.getpid()}\nStarted: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")
            self.fd.flush()
            return True
        except (BlockingIOError, IOError):
            existing_info = "Unknown"
            try:
                with open(self.lock_path, 'r') as f:
                    existing_info = f.read().strip().replace('\n', ', ')
            except Exception:
                pass
            logging.error(f"FATAL: Another acquisition process is currently running for year {self.year} ({existing_info}).")
            logging.error("Aborting immediately to prevent index and archive corruption.")
            return False

    def release(self):
        if self.fd:
            try:
                fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
                self.fd.close()
                if os.path.exists(self.lock_path):
                    os.unlink(self.lock_path)
            except Exception as e:
                logging.warning(f"Error releasing lock for year {self.year}: {e}")
            self.fd = None

    def __enter__(self):
        if not self.acquire():
            sys.exit(2)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

def check_disk_space(target_year, manifest_summary_path=DEFAULT_SUMMARY, raw_dir=RAW_DIR, safety_factor=3.0, min_gb_required=10.0):
    """
    Dynamically verify disk space for the target year.
    Calculates expected size from manifest summary, multiplies by safety factor (tar block overhead + padding + margin).
    """
    expected_bytes = 0
    if os.path.exists(manifest_summary_path):
        try:
            with open(manifest_summary_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)
            yd = summary.get("year_distribution", {})
            if str(target_year) in yd:
                expected_bytes = yd[str(target_year)].get("bytes", 0)
        except Exception as e:
            logging.warning(f"Could not read year size from {manifest_summary_path}: {e}")

    # Fallback if summary doesn't have the year: default to 5 GB payload estimate
    if expected_bytes == 0:
        expected_bytes = 5 * 1024 * 1024 * 1024
        logging.warning(f"Using conservative fallback expected payload size for year {target_year}: {expected_bytes / (1024**3):.2f} GB")

    expected_gb = expected_bytes / (1024**3)
    required_bytes = int(max(expected_bytes * safety_factor, min_gb_required * (1024**3)))
    required_gb = required_bytes / (1024**3)

    stat = shutil.disk_usage(raw_dir)
    free_bytes = stat.free
    free_gb = free_bytes / (1024**3)

    logging.info(
        f"Dynamic Disk Check: Target Year={target_year} | Expected Payload={expected_gb:.2f} GB | "
        f"Required with {safety_factor:.1f}x Margin={required_gb:.2f} GB | Free Disk Space={free_gb:.2f} GB"
    )

    if free_bytes < required_bytes:
        logging.error(
            f"FATAL: Insufficient disk space for year {target_year}! "
            f"Available: {free_gb:.2f} GB, Required: {required_gb:.2f} GB (minimum margin requirement)."
        )
        return False
    return True

def get_s3_client(max_conn=80):
    return boto3.client('s3', region_name='us-east-1', config=Config(signature_version=UNSIGNED, max_pool_connections=max_conn))

class MonthlyTarManager:
    """Manages high-throughput O(1) appending and durable indexing for a monthly TAR container."""
    def __init__(self, base_dir, year, month, read_only=False):
        self.year = str(year)
        self.month = f"{int(month):02d}" if str(month).isdigit() else str(month)
        self.month_dir = os.path.join(base_dir, f"year={self.year}")
        os.makedirs(self.month_dir, exist_ok=True)
        
        self.tar_path = os.path.join(self.month_dir, f"month={self.month}.tar")
        self.idx_path = os.path.join(self.month_dir, f"month={self.month}.idx")
        self.read_only = read_only
        
        self.lock = threading.Lock()
        self.acquired_keys = set()
        self.expected_tar_size = 0
        self._recover_and_load_index()
        
        if not self.read_only:
            # Open persistent handles
            self.tar_f = open(self.tar_path, 'a+b')
            self.tar_f.seek(0, io.SEEK_END)
            self.current_tar_offset = self.tar_f.tell()
            assert self.current_tar_offset == self.expected_tar_size, (
                f"Container {self.year}/{self.month}: TAR physical size {self.current_tar_offset} "
                f"!= index expected size {self.expected_tar_size}"
            )
                
            idx_exists = os.path.exists(self.idx_path)
            self.idx_f = open(self.idx_path, 'a', newline='', encoding='utf-8')
            self.idx_writer = csv.writer(self.idx_f)
            if not idx_exists or os.path.getsize(self.idx_path) == 0:
                self.idx_writer.writerow(["s3_key", "tar_offset", "byte_length", "file_size", "etag", "sha256", "retrieved_at_utc"])
                self.idx_f.flush()
        else:
            self.current_tar_offset = self.expected_tar_size

    def _recover_and_load_index(self):
        """Load index, check for mid-write corruption, and determine expected TAR size."""
        last_offset = 0
        last_length = 0
        valid_entries = 0
        
        if os.path.exists(self.idx_path):
            with open(self.idx_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 6:
                        s3_k, offset_str, len_str, sz_str, etag, sha256 = row[:6]
                        self.acquired_keys.add(s3_k)
                        last_offset = int(offset_str)
                        last_length = int(len_str)
                        valid_entries += 1
                        
        self.expected_tar_size = last_offset + last_length if valid_entries > 0 else 0
        
        # Verify TAR file integrity and size
        if os.path.exists(self.tar_path):
            actual_size = os.path.getsize(self.tar_path)
            if actual_size > self.expected_tar_size:
                if not self.read_only:
                    logging.warning(
                        f"Crash recovery: Truncating {self.tar_path} from {actual_size} to {self.expected_tar_size} "
                        f"bytes (removing {actual_size - self.expected_tar_size} un-indexed bytes)."
                    )
                    with open(self.tar_path, 'a+b') as tf:
                        tf.truncate(self.expected_tar_size)
                else:
                    logging.warning(f"Dry-run notice: {self.tar_path} has {actual_size - self.expected_tar_size} un-indexed bytes pending truncation.")
            elif actual_size < self.expected_tar_size:
                logging.error(f"FATAL: TAR {self.tar_path} size ({actual_size}) is smaller than index expected ({self.expected_tar_size})!")

        logging.info(f"Loaded container {self.year}/{self.month}: {len(self.acquired_keys):,} already-acquired objects ({self.expected_tar_size:,} bytes).")

    def is_acquired(self, s3_key):
        with self.lock:
            return s3_key in self.acquired_keys

    def append_object(self, s3_key, data, etag, sha256, mtime_dt):
        """O(1) direct block append into TAR container and index recording."""
        if self.read_only:
            return
        tarinfo = tarfile.TarInfo(name=s3_key)
        tarinfo.size = len(data)
        tarinfo.mtime = int(mtime_dt.timestamp()) if isinstance(mtime_dt, datetime.datetime) else int(time.time())
        tarinfo.mode = 0o644
        
        # Generate 512-byte header and padding outside of lock
        hdr = tarinfo.tobuf(format=tarfile.GNU_FORMAT, encoding='utf-8')
        pad_len = (512 - (len(data) % 512)) % 512
        padding = b'\x00' * pad_len if pad_len > 0 else b''
        byte_length = len(hdr) + len(data) + len(padding)
        
        with self.lock:
            current_offset = self.current_tar_offset
            self.tar_f.write(hdr)
            self.tar_f.write(data)
            if padding:
                self.tar_f.write(padding)
            self.tar_f.flush()
            self.current_tar_offset += byte_length
            assert self.tar_f.tell() == self.current_tar_offset, f"Physical offset mismatch: {self.tar_f.tell()} != {self.current_tar_offset}"
            
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.idx_writer.writerow([s3_key, current_offset, byte_length, len(data), etag, sha256, now_iso])
            self.idx_f.flush()
            self.acquired_keys.add(s3_key)

    def close(self):
        """Finalize container by flushing and closing handles."""
        with self.lock:
            if hasattr(self, 'tar_f') and not self.tar_f.closed:
                self.tar_f.flush()
                self.tar_f.close()
            if hasattr(self, 'idx_f') and not self.idx_f.closed:
                self.idx_f.flush()
                self.idx_f.close()

def download_and_validate_object(s3, s3_key, expected_size, max_retries=5):
    """Download an S3 object with exponential backoff and strict validation."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = s3.get_object(Bucket='openaq-data-archive', Key=s3_key)
            data = resp['Body'].read()
            actual_size = len(data)
            
            # 1. Content-Length Check
            if expected_size and actual_size != expected_size:
                raise ValueError(f"Size mismatch: expected {expected_size}, got {actual_size}")
                
            # 2. Gzip Header Magic Check (\x1f\x8b)
            if actual_size >= 2 and data[:2] != b'\x1f\x8b':
                raise ValueError("Corrupt gzip header: magic bytes 0x1f8b missing")
                
            # 3. Gzip Decompressibility / CRC Check
            try:
                gzip.decompress(data)
            except Exception as ge:
                raise ValueError(f"Gzip decompression/CRC failed: {ge}")
                
            # 4. Checksums
            sha256 = hashlib.sha256(data).hexdigest()
            md5_hex = hashlib.md5(data).hexdigest()
            etag = resp.get('ETag', '').strip('"')
            
            # If standard ETag (32-char hex), verify MD5 match
            if etag and len(etag) == 32 and '-' not in etag:
                if md5_hex.lower() != etag.lower():
                    raise ValueError(f"ETag mismatch: S3 ETag {etag} != local MD5 {md5_hex}")
                    
            mtime = resp.get('LastModified', datetime.datetime.now(datetime.timezone.utc))
            return data, etag, sha256, mtime
            
        except Exception as e:
            wait_time = 2 ** attempt
            if attempt < max_retries:
                logging.warning(f"Retry {attempt}/{max_retries} for {s3_key}: {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                logging.error(f"FAILED {s3_key} after {max_retries} attempts: {e}")
                raise

def manifest_task_stream(manifest_path, target_year=None, target_month=None):
    """Generator streaming tasks directly from gzipped manifest CSV."""
    with gzip.open(manifest_path, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        key_idx = header.index("s3_key") if header and "s3_key" in header else 3
        year_idx = header.index("year") if header and "year" in header else 1
        month_idx = header.index("month") if header and "month" in header else 2
        size_idx = header.index("size_bytes") if header and "size_bytes" in header else 4

        for row in reader:
            if len(row) > max(key_idx, year_idx, month_idx, size_idx):
                k = row[key_idx]
                yr = row[year_idx]
                mo = row[month_idx]
                sz = int(row[size_idx])
                # Skip non-measurement files or malformed entries (e.g. .DS_Store)
                if not mo.isdigit() or not k.endswith('.csv.gz'):
                    continue
                mo = f"{int(mo):02d}"
                if target_year and yr != str(target_year):
                    continue
                if target_month and mo != f"{int(target_month):02d}":
                    continue
                yield (k, yr, mo, sz)

def s3_partition_task_stream(s3, archive_type, loc_list, target_year=None, target_month=None):
    """Generator streaming tasks directly by scanning S3 partitions."""
    prefix_base = "records/csv.gz/locationid=" if archive_type == "modern" else "records/csv.gz/provider="
    paginator = s3.get_paginator('list_objects_v2')
    
    for lid in loc_list:
        prefix = f"{prefix_base}{lid}/" if lid else prefix_base
        if target_year:
            prefix += f"year={target_year}/"
            if target_month:
                prefix += f"month={int(target_month):02d}/"
                
        for page in paginator.paginate(Bucket='openaq-data-archive', Prefix=prefix):
            for obj in page.get('Contents', []):
                k = obj['Key']
                sz = obj['Size']
                parts = k.split('/')
                yr, mo = "0000", "00"
                for p in parts:
                    if p.startswith('year='): yr = p.split('=')[1]
                    elif p.startswith('month='):
                        raw_m = p.split('=')[1]
                        mo = f"{int(raw_m):02d}" if raw_m.isdigit() else raw_m
                yield (k, yr, mo, sz)

def setup_logging(year=None, custom_log_file=None):
    """Configure dual stream and file logging with per-year isolation."""
    if custom_log_file:
        log_path = custom_log_file
    elif year:
        log_path = os.path.join(LOGS_DIR, f"acquisition_{year}.log")
    else:
        log_path = os.path.join(LOGS_DIR, "acquisition.log")

    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = []

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    fh = logging.FileHandler(log_path)
    fh.setFormatter(formatter)

    root_logger.addHandler(sh)
    root_logger.addHandler(fh)
    logging.info(f"Logging initialized. Output file: {log_path}")

def main():
    parser = argparse.ArgumentParser(description="OpenAQ S3 Archive Acquisition Engine (O(1) Direct Append)")
    parser.add_argument("--archive-type", choices=["modern", "legacy"], default="modern")
    parser.add_argument("--manifest-path", type=str, default=DEFAULT_MANIFEST, help=f"Path to manifest CSV.gz (default: {DEFAULT_MANIFEST})")
    parser.add_argument("--year", type=str, required=True, help="Target year to acquire (e.g. 2024)")
    parser.add_argument("--month", type=str, help="Target month to acquire (optional, e.g. 11)")
    parser.add_argument("--location-id", type=str, help="Target specific location ID")
    parser.add_argument("--limit-objects", type=int, default=None, help="Stop after acquiring N objects (for pilot)")
    parser.add_argument("--workers", type=int, default=50, help="Number of download threads (default: 50)")
    parser.add_argument("--log-file", type=str, default=None, help="Custom log file path")
    parser.add_argument("--dry-run", action="store_true", help="Perform pre-flight checks, disk check, locking test, manifest task sampling without downloading")
    args = parser.parse_args()

    setup_logging(year=args.year, custom_log_file=args.log_file)

    logging.info("=" * 70)
    logging.info(f"OpenAQ S3 Acquisition Runner starting for YEAR={args.year} (Dry-Run: {args.dry_run})")
    logging.info("=" * 70)

    # 1. Concurrency Protection (Year Lock)
    with YearLock(args.year) as lock:
        logging.info(f"Process lock successfully acquired on {lock.lock_path} (PID: {os.getpid()})")

        # 2. Dynamic Disk Space Check
        base_raw = os.path.join(RAW_DIR, f"s3_{args.archive_type}")
        os.makedirs(base_raw, exist_ok=True)
        if not check_disk_space(args.year, raw_dir=base_raw):
            sys.exit(3)

        # 3. Check manifest exists
        if not os.path.exists(args.manifest_path):
            logging.error(f"FATAL: Manifest file not found at {args.manifest_path}!")
            sys.exit(4)

        # 4. Containers cache: (year, month) -> MonthlyTarManager
        containers = {}
        containers_lock = threading.Lock()
        
        def get_container(yr, mo):
            norm_mo = f"{int(mo):02d}" if str(mo).isdigit() else str(mo)
            key = (str(yr), norm_mo)
            if key not in containers:
                with containers_lock:
                    if key not in containers:
                        containers[key] = MonthlyTarManager(base_raw, str(yr), norm_mo, read_only=args.dry_run)
            return containers[key]

        # Pre-load existing containers for target year
        logging.info(f"Pre-loading monthly containers for year={args.year} (read_only={args.dry_run})...")
        for m in range(1, 13):
            get_container(args.year, f"{m:02d}")

        # 5. Handle Dry Run
        if args.dry_run:
            logging.info("DRY-RUN MODE ACTIVE: Sampling manifest tasks without downloading or writing S3 files...")
            sample_stream = manifest_task_stream(args.manifest_path, args.year, args.month)
            sampled_items = []
            for item in sample_stream:
                sampled_items.append(item)
                if len(sampled_items) >= 100:
                    break

            logging.info(f"Dry-run sample successful: parsed {len(sampled_items)} candidate tasks from manifest for year={args.year}.")
            if sampled_items:
                logging.info(f"First sampled task: key={sampled_items[0][0]}, size={sampled_items[0][3]:,} bytes")
                logging.info(f"Last sampled task:  key={sampled_items[-1][0]}, size={sampled_items[-1][3]:,} bytes")

            total_existing_indexed = sum(len(c.acquired_keys) for c in containers.values())
            logging.info(f"Existing indexed files for year={args.year}: {total_existing_indexed:,}")
            logging.info("=" * 70)
            logging.info("DRY-RUN COMPLETED SUCCESSFULLY! All pre-flight safeguards, locks, and streams verified.")
            logging.info("=" * 70)
            for c in list(containers.values()):
                c.close()
            return

        # 6. Setup Signal Handler for Graceful Shutdown
        stop_requested = threading.Event()
        def sig_handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logging.warning(f"Received {sig_name}! Gracefully stopping acquisition...")
            stop_requested.set()
            
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        s3 = get_s3_client(max_conn=args.workers + 20)

        # 7. Setup task generator
        logging.info(f"Streaming download tasks from manifest: {args.manifest_path}")
        raw_stream = manifest_task_stream(args.manifest_path, args.year, args.month)

        # Fast unacquired iterator
        def unacquired_task_stream(stream):
            nonlocal skipped_count
            for item in stream:
                if stop_requested.is_set():
                    break
                k, yr, mo, sz = item
                cont = get_container(yr, mo)
                if cont.is_acquired(k):
                    skipped_count += 1
                    if skipped_count % 10000 == 0:
                        logging.info(f"Fast-skipped {skipped_count:,} already-acquired objects...")
                    continue
                yield item

        # 8. Execute Downloads
        logging.info(f"Executing acquisition with {args.workers} concurrent workers (O(1) Direct Block Appender)...")
        acquired_count = 0
        skipped_count = 0
        failed_count = 0
        total_bytes_acquired = 0
        t0 = time.time()
        
        def process_item(item):
            k, yr, mo, sz = item
            cont = get_container(yr, mo)
            if cont.is_acquired(k):
                return "skipped", k, 0
            try:
                data, etag, sha256, mtime = download_and_validate_object(s3, k, sz)
                cont.append_object(k, data, etag, sha256, mtime)
                return "acquired", k, len(data)
            except Exception as e:
                return "failed", k, str(e)

        task_iter = unacquired_task_stream(raw_stream)
        SLIDING_WINDOW = args.workers * 2
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {}
            for _ in range(SLIDING_WINDOW):
                try:
                    it = next(task_iter)
                    futures[executor.submit(process_item, it)] = it
                except StopIteration:
                    break
                    
            while futures:
                if stop_requested.is_set():
                    break
                    
                f = next(as_completed(futures))
                it = futures.pop(f)
                
                # Submit next if limit not reached
                if not stop_requested.is_set():
                    if not args.limit_objects or acquired_count < args.limit_objects:
                        try:
                            next_it = next(task_iter)
                            futures[executor.submit(process_item, next_it)] = next_it
                        except StopIteration:
                            pass
                            
                status, k, val = f.result()
                del f
                
                if status == "acquired":
                    acquired_count += 1
                    total_bytes_acquired += val
                elif status == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
                    logging.error(f"Acquisition error for {k}: {val}")
                    
                if acquired_count > 0 and (acquired_count % 500 == 0 or (args.limit_objects and acquired_count >= args.limit_objects)):
                    elapsed = time.time() - t0
                    rate = acquired_count / elapsed if elapsed > 0 else 0
                    logging.info(
                        f"Progress: Acquired {acquired_count:,} files ({total_bytes_acquired/1024/1024:.2f} MB) | "
                        f"Skipped: {skipped_count:,} | Failed: {failed_count:,} | Rate: {rate:.1f} files/s"
                    )
                                 
                if args.limit_objects and acquired_count >= args.limit_objects:
                    logging.info(f"Target object limit reached ({args.limit_objects:,} files acquired). Stopping acquisition.")
                    break

        # Close all containers cleanly
        for c in list(containers.values()):
            c.close()

        elapsed = time.time() - t0
        logging.info("=" * 70)
        logging.info(f"ACQUISITION RUN FINISHED in {elapsed:.2f}s ({elapsed/60:.2f} min)")
        logging.info(f"Newly Acquired Files: {acquired_count:,}")
        logging.info(f"Skipped (Already Acquired): {skipped_count:,}")
        logging.info(f"Failed Files: {failed_count:,}")
        logging.info(f"Volume Acquired: {total_bytes_acquired:,} bytes ({total_bytes_acquired/1024/1024:.2f} MB)")
        if acquired_count > 0 and elapsed > 0:
            logging.info(f"Average Download Rate: {acquired_count/elapsed:.1f} files/s ({total_bytes_acquired/elapsed/1024:.1f} KB/s)")
        logging.info("=" * 70)

        # 9. Strict Failure Enforcement
        if failed_count > 0:
            logging.error(f"FATAL: Acquisition completed with {failed_count} errors! Exiting with error code 1.")
            sys.exit(1)

if __name__ == "__main__":
    main()
