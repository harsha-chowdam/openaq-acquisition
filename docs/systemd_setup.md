# Systemd Service Template Setup & Process Management

**Documentation Date:** 2026-11-25  
**Component:** Production Process Supervision  
**Unit File:** `systemd/openaq-acquire@.service`  

---

## 1. Systemd Template Architecture

The acquisition pipeline uses a **parameterized systemd template service** (`openaq-acquire@.service`). Parameterized units allow dynamic instantiation per target year using the `%I` specifier.

When you execute:
```bash
sudo systemctl start openaq-acquire@2024.service
```
systemd automatically replaces `%I` with `2024`, invoking `/home/harsha/openaq/bin/acquire_year.sh 2024`.

---

## 2. Unit File Specification (`openaq-acquire@.service`)

```ini
[Unit]
Description=OpenAQ S3 Archive Acquisition and Integrity Audit for Year %I
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=harsha
Group=harsha
WorkingDirectory=/home/harsha/openaq
ExecStart=/home/harsha/openaq/bin/acquire_year.sh %I
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=180
StandardOutput=journal
StandardError=journal
Restart=no

[Install]
WantedBy=multi-user.target
```

### Directive Explanations
1. **`After=network-online.target` / `Wants=network-online.target`:**  
   Guarantees that the service only starts once the system's network interfaces are fully initialized and can resolve DNS/HTTPS.
2. **`User=harsha` / `Group=harsha`:**  
   Runs the entire acquisition process as an unprivileged user, preventing security escalations and maintaining consistent filesystem permissions (`0644`/`0755`).
3. **`WorkingDirectory=/home/harsha/openaq`:**  
   Sets the working directory, ensuring relative paths to `manifest/`, `raw/`, and `logs/` resolve accurately.
4. **`ExecStart=/home/harsha/openaq/bin/acquire_year.sh %I`:**  
   Launches the master unattended runner for the requested year.
5. **`KillMode=mixed` / `KillSignal=SIGTERM`:**  
   When stopping, systemd sends `SIGTERM` to the parent bash process (`acquire_year.sh`) and all child Python threads.
6. **`TimeoutStopSec=180`:**  
   Grants a generous 3-minute window for active S3 downloads to finish flushing in-memory TAR blocks and index records to disk before forcing termination.
7. **`Restart=no`:**  
   Disables automatic restarting on failure to prevent crash-restart loops if an unrecoverable disk full or upstream error occurs.

---

## 3. Installation & Registration

1. Copy unit template to system directory:
   ```bash
   sudo cp systemd/openaq-acquire@.service /etc/systemd/system/
   ```
2. Reload systemd daemon to recognize new unit:
   ```bash
   sudo systemctl daemon-reload
   ```
3. Enable user lingering (CRITICAL):
   ```bash
   sudo loginctl enable-linger harsha
   ```
   *Why Lingering is Mandatory:* Without lingering, Ubuntu terminates background user processes and systemd user slices as soon as all interactive SSH sessions close. Lingering guarantees that the service runs uninterrupted 24/7 until completion.

---

## 4. Operational Commands & Lifecycle Management

### Starting an Acquisition
```bash
sudo systemctl start openaq-acquire@2024.service
```

### Checking Real-Time Service Status
```bash
systemctl status openaq-acquire@2024.service
```

### Stopping an Active Acquisition Gracefully
```bash
sudo systemctl stop openaq-acquire@2024.service
```
*(Systemd sends `SIGTERM`, allowing active worker threads to flush current blocks and close TAR and index descriptors safely).*

### Inspecting Live Journal Logs
```bash
journalctl -u openaq-acquire@2024.service -f
```

### Viewing Previous Boot or Historical Logs
```bash
journalctl -u openaq-acquire@2024.service --no-pager -n 100
```
