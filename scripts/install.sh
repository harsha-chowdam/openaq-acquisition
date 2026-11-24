#!/usr/bin/env bash
# ==============================================================================
# OpenAQ Acquisition Pipeline - Universal Server Provisioner & Installer
# ==============================================================================
# Detects current user, sets up directories, provisions virtualenv, templates
# and registers systemd service units, and validates operational readiness.
# ==============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="${TARGET_USER:-$USER}"
TARGET_GROUP="${TARGET_GROUP:-$(id -gn "$TARGET_USER")}"
TARGET_DIR="${TARGET_DIR:-$HOME/openaq}"

echo "======================================================================"
echo "OpenAQ Acquisition Pipeline - Automated Installer"
echo "======================================================================"
echo "Repository Source: $REPO_DIR"
echo "Target User:       $TARGET_USER ($TARGET_GROUP)"
echo "Installation Path: $TARGET_DIR"
echo "======================================================================"

# 1. System packages check / install
if command -v apt-get >/dev/null 2>&1; then
    echo "[1/6] Installing required system packages via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-venv python3-pip tar gzip curl util-linux git
else
    echo "[1/6] Non-Debian system detected. Verifying required binaries..."
    for bin in python3 tar gzip curl flock; do
        if ! command -v "$bin" >/dev/null 2>&1; then
            echo "ERROR: Missing required binary '$bin'. Please install it using your package manager." >&2
            exit 1
        fi
    done
fi

# 2. Enable systemd user lingering
if command -v loginctl >/dev/null 2>&1; then
    echo "[2/6] Enabling systemd user lingering for '$TARGET_USER'..."
    sudo loginctl enable-linger "$TARGET_USER" || echo "Warning: loginctl enable-linger returned non-zero (non-fatal in containers)"
else
    echo "[2/6] Skipping loginctl (not present on this system)"
fi

# 3. Create target directory tree
echo "[3/6] Creating project directories in $TARGET_DIR..."
mkdir -p "$TARGET_DIR"/{bin,config,manifest,raw/s3_modern,reports,logs,tmp}
chmod 755 "$TARGET_DIR"

# Copy executables
cp -r "$REPO_DIR"/bin/* "$TARGET_DIR"/bin/
chmod +x "$TARGET_DIR"/bin/*.py "$TARGET_DIR"/bin/*.sh

# Copy config and manifest metadata
cp -r "$REPO_DIR"/config/* "$TARGET_DIR"/config/
if [ -d "$REPO_DIR/manifest" ]; then
    cp -r "$REPO_DIR"/manifest/* "$TARGET_DIR"/manifest/ 2>/dev/null || true
fi

# 4. Provision Python virtual environment
echo "[4/6] Provisioning Python virtual environment in $TARGET_DIR/venv..."
if [ ! -d "$TARGET_DIR/venv" ]; then
    python3 -m venv "$TARGET_DIR/venv"
fi
"$TARGET_DIR/venv/bin/pip" install --upgrade pip -q
"$TARGET_DIR/venv/bin/pip" install -r "$TARGET_DIR/config/requirements.txt" -q

# 5. Template and register systemd service
if command -v systemctl >/dev/null 2>&1 && [ -d /etc/systemd/system ]; then
    echo "[5/6] Templating and registering systemd service unit..."
    SERVICE_FILE="/etc/systemd/system/openaq-acquire@.service"
    
    sudo bash -c "cat << 'EOF' > $SERVICE_FILE
[Unit]
Description=OpenAQ S3 Archive Acquisition and Integrity Audit for Year %I
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_GROUP
WorkingDirectory=$TARGET_DIR
ExecStart=$TARGET_DIR/bin/acquire_year.sh %I
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=180
StandardOutput=journal
StandardError=journal
Restart=no

[Install]
WantedBy=multi-user.target
EOF"
    sudo systemctl daemon-reload
    echo "Registered: $SERVICE_FILE"
else
    echo "[5/6] Systemd not running. Skipping unit file registration."
fi

# 6. Verification test
echo "[6/6] Verifying installation..."
"$TARGET_DIR/venv/bin/python" "$TARGET_DIR/bin/acquire_s3_archive.py" --help >/dev/null
"$TARGET_DIR/venv/bin/python" "$TARGET_DIR/bin/audit_acquisition_integrity.py" --help >/dev/null

echo "======================================================================"
echo "INSTALLATION COMPLETE!"
echo "======================================================================"
echo "Next Steps:"
echo "1. Place the master manifest in: $TARGET_DIR/manifest/s3_manifest_modern.csv.gz"
echo "   (Or generate it from S3: '$TARGET_DIR/venv/bin/python $TARGET_DIR/bin/generate_manifest.py')"
echo "2. Start acquisition for any year:"
echo "   sudo systemctl start openaq-acquire@2024.service"
echo "   (Or run interactively: '$TARGET_DIR/bin/acquire_year.sh 2024')"
echo "======================================================================"
