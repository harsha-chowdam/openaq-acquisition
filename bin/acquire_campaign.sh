#!/usr/bin/env bash
# ==============================================================================
# OpenAQ Multi-Year Fleet Acquisition Campaign Runner
# ==============================================================================
# Sequentially acquires and verifies a range of historical years.
# Enforces strict halt-on-failure to prevent cascading issues.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${OPENAQ_PROJECT_DIR:-/home/harsha/openaq}"
RUNNER="$SCRIPT_DIR/acquire_year.sh"

usage() {
    echo "Usage: $0 [START_YEAR] [END_YEAR] [--dry-run]"
    echo ""
    echo "Examples:"
    echo "  $0 2006 2026            # Acquire full 20-year history sequentially"
    echo "  $0 2020 2024            # Acquire years 2020 through 2024"
    echo "  $0 2020 2024 --dry-run  # Dry-run validation across years"
    exit 1
}

if [[ $# -lt 2 ]]; then
    usage
fi

START_YEAR="$1"
END_YEAR="$2"
shift 2

DRY_RUN=false
if [[ $# -gt 0 ]] && [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
fi

echo "======================================================================"
echo "OPENAQ MULTI-YEAR CAMPAIGN RUNNER"
echo "======================================================================"
echo "Target Year Span: $START_YEAR to $END_YEAR"
echo "Dry Run Mode:     $DRY_RUN"
echo "Timestamp:        $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "======================================================================"

CAMPAIGN_START=$(date +%s)
SUCCESSFUL_YEARS=()
FAILED_YEARS=()

for (( year=START_YEAR; year<=END_YEAR; year++ )); do
    echo ""
    echo "######################################################################"
    echo "CAMPAIGN PROGRESS: STARTING YEAR $year"
    echo "######################################################################"
    
    YEAR_CMD=("$RUNNER" "$year")
    if [ "$DRY_RUN" = true ]; then
        YEAR_CMD+=(--dry-run)
    fi

    if "${YEAR_CMD[@]}"; then
        echo "[SUCCESS] Year $year completed and verified cleanly."
        SUCCESSFUL_YEARS+=("$year")
    else
        echo "[FATAL] Year $year failed with exit code $?!" >&2
        FAILED_YEARS+=("$year")
        echo "Halting campaign to prevent cascading errors."
        break
    fi
done

CAMPAIGN_END=$(date +%s)
DURATION=$(( CAMPAIGN_END - CAMPAIGN_START ))

echo ""
echo "======================================================================"
echo "CAMPAIGN COMPLETED in $(( DURATION / 60 )) minutes ($DURATION seconds)"
echo "Successful Years: ${SUCCESSFUL_YEARS[*]:-None}"
echo "Failed Years:     ${FAILED_YEARS[*]:-None}"
echo "======================================================================"

if [ ${#FAILED_YEARS[@]} -gt 0 ]; then
    exit 1
fi
