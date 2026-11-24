#!/usr/bin/env bash
# ==============================================================================
# OpenAQ Automated Year Acquisition & Integrity Verification Runner
# ==============================================================================
# Safe, reusable, unattended acquisition for any year in OpenAQ global manifest.
# Features:
# - Dynamic disk-space validation with safety margin
# - Process concurrency lock (fcntl.flock) per year
# - Isolated per-year logging and O(1) TAR indexing
# - Automated post-acquisition integrity verification & JSON audit report
# - Strict failure exit codes and graceful signal handling
# ==============================================================================

set -euo pipefail

usage() {
    echo "Usage: $0 <YEAR> [--dry-run] [--workers <N>] [--limit <N>]"
    echo ""
    echo "Examples:"
    echo "  $0 2024 --dry-run                 # Test pre-flight checks, lock, disk check without downloading"
    echo "  $0 2024                           # Full unattended acquisition of 2024"
    echo "  $0 2024 --workers 60              # Custom worker concurrency"
    echo "  $0 2024 --limit 500               # Acquire first 500 files for testing"
    exit 1
}

if [[ $# -lt 1 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    usage
fi

PROJECT_DIR="${OPENAQ_PROJECT_DIR:-/home/harsha/openaq}"
mkdir -p "$PROJECT_DIR" 2>/dev/null || true
cd "$PROJECT_DIR"

if [[ -x "${PROJECT_DIR}/venv/bin/python3" ]]; then
    PYTHON_BIN="${PROJECT_DIR}/venv/bin/python3"
else
    PYTHON_BIN="python3"
fi
MANIFEST_PATH="${PROJECT_DIR}/manifest/s3_manifest_modern.csv.gz"
MANIFEST_SUMMARY="${PROJECT_DIR}/manifest/manifest_summary.json"

LOGS_DIR="${PROJECT_DIR}/logs"
TMP_DIR="${PROJECT_DIR}/tmp"
REPORTS_DIR="${PROJECT_DIR}/reports"
RAW_DIR="${PROJECT_DIR}/raw/s3_modern"

mkdir -p "$LOGS_DIR" "$TMP_DIR" "$REPORTS_DIR" "$RAW_DIR"

YEAR="$1"
shift

# Validate 4-digit year format
if ! [[ "$YEAR" =~ ^[12][0-9]{3}$ ]]; then
    echo "ERROR: Invalid year format '$YEAR'. Expected 4-digit year (e.g. 2024)." >&2
    exit 1
fi

DRY_RUN=false
WORKERS=50
LIMIT_ARGS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --limit)
            LIMIT_ARGS="--limit-objects $2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

RUNNER_LOG="${LOGS_DIR}/acquire_year_${YEAR}.runner.log"
ACQ_LOG="${LOGS_DIR}/acquisition_${YEAR}.log"
REPORT_JSON="${REPORTS_DIR}/acquisition_report_${YEAR}.json"

echo "========================================================================" | tee -a "$RUNNER_LOG"
echo "OPENAQ ACQUISITION RUNNER: YEAR ${YEAR}" | tee -a "$RUNNER_LOG"
echo "Timestamp:      $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee -a "$RUNNER_LOG"
echo "Dry Run:        ${DRY_RUN}" | tee -a "$RUNNER_LOG"
echo "Workers:        ${WORKERS}" | tee -a "$RUNNER_LOG"
echo "Manifest:       ${MANIFEST_PATH}" | tee -a "$RUNNER_LOG"
echo "Acquisition Log:${ACQ_LOG}" | tee -a "$RUNNER_LOG"
echo "Runner Log:     ${RUNNER_LOG}" | tee -a "$RUNNER_LOG"
echo "Report Path:    ${REPORT_JSON}" | tee -a "$RUNNER_LOG"
echo "========================================================================" | tee -a "$RUNNER_LOG"

# Verify environment
if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "ERROR: Python interpreter not found at $PYTHON_BIN" | tee -a "$RUNNER_LOG" >&2
    exit 1
fi

if [[ ! -f "$MANIFEST_PATH" ]]; then
    echo "ERROR: Global manifest not found at $MANIFEST_PATH" | tee -a "$RUNNER_LOG" >&2
    exit 1
fi

# Step 1: Run Acquisition Engine
EXTRA_FLAGS=""
if [[ "$DRY_RUN" == "true" ]]; then
    EXTRA_FLAGS="--dry-run"
fi

echo "" | tee -a "$RUNNER_LOG"
echo "[STEP 1/2] Executing S3 Acquisition Engine for Year ${YEAR}..." | tee -a "$RUNNER_LOG"

ACQ_CMD=(
    "$PYTHON_BIN" "${PROJECT_DIR}/bin/acquire_s3_archive.py"
    --archive-type modern
    --manifest-path "$MANIFEST_PATH"
    --year "$YEAR"
    --workers "$WORKERS"
    --log-file "$ACQ_LOG"
)

if [[ -n "$LIMIT_ARGS" ]]; then
    # shellcheck disable=SC2206
    ACQ_CMD+=($LIMIT_ARGS)
fi

if [[ -n "$EXTRA_FLAGS" ]]; then
    ACQ_CMD+=($EXTRA_FLAGS)
fi

echo "Running: ${ACQ_CMD[*]}" | tee -a "$RUNNER_LOG"

"${ACQ_CMD[@]}" 2>&1 | tee -a "$RUNNER_LOG"
ACQ_EXIT_CODE=${PIPESTATUS[0]}

if [[ $ACQ_EXIT_CODE -ne 0 ]]; then
    echo "ERROR: Acquisition engine failed with exit code $ACQ_EXIT_CODE!" | tee -a "$RUNNER_LOG" >&2
    exit $ACQ_EXIT_CODE
fi

echo "[STEP 1/2] Acquisition step completed successfully." | tee -a "$RUNNER_LOG"

# Step 2: Run Post-Acquisition Integrity Audit
echo "" | tee -a "$RUNNER_LOG"
echo "[STEP 2/2] Executing Post-Acquisition Integrity Verification for Year ${YEAR}..." | tee -a "$RUNNER_LOG"

AUDIT_SCRIPT="${PROJECT_DIR}/bin/audit_acquisition_integrity.py"
if [[ ! -f "$AUDIT_SCRIPT" ]]; then
    AUDIT_SCRIPT="${PROJECT_DIR}/audit_acquisition_integrity.py"
fi

AUDIT_CMD=(
    "$PYTHON_BIN" "$AUDIT_SCRIPT"
    --year "$YEAR"
    --manifest-path "$MANIFEST_PATH"
)

if [[ "$DRY_RUN" == "true" ]]; then
    AUDIT_CMD+=(--dry-run)
fi

echo "Running: ${AUDIT_CMD[*]}" | tee -a "$RUNNER_LOG"

"${AUDIT_CMD[@]}" 2>&1 | tee -a "$RUNNER_LOG"
AUDIT_EXIT_CODE=${PIPESTATUS[0]}

if [[ $AUDIT_EXIT_CODE -ne 0 ]]; then
    echo "ERROR: Integrity verification failed with exit code $AUDIT_EXIT_CODE!" | tee -a "$RUNNER_LOG" >&2
    exit $AUDIT_EXIT_CODE
fi

echo "" | tee -a "$RUNNER_LOG"
echo "========================================================================" | tee -a "$RUNNER_LOG"
echo "ACQUISITION WORKFLOW FOR YEAR ${YEAR} COMPLETED WITH 100% INTEGRITY!" | tee -a "$RUNNER_LOG"
echo "Audit Report Saved: ${REPORT_JSON}" | tee -a "$RUNNER_LOG"
echo "Finished at:        $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee -a "$RUNNER_LOG"
echo "========================================================================" | tee -a "$RUNNER_LOG"

exit 0
