# MinKNOW Dashboard

A real-time web dashboard for local Oxford Nanopore MinKNOW instances. It shows flow cell telemetry (pore health, read length, yield, Q-scores, barcodes and temperature) and provides basic sequencing device control directly from your browser.

## Key Features

- **Real-time Telemetry:** Run info, yield (bases and reads), temperature, read length (N50 and histogram), channel state, pore scans, Q-score distribution and barcode distribution. Data refreshes every 10 seconds while the tab is visible.
- **Dynamic Quality Score Distribution:** Q-score histograms from Dorado with integer bucketing and the run's minimum Q-score threshold drawn on the chart.
- **Barcode Distribution:** Shown automatically for barcoded runs, detected from the run's barcoding settings or from the kit name (NBD, RBK, 16S, PCB and MAB kits).
- **Flow Cell Check History:** Shows the pore count from the last flow cell check (Platform QC) for the inserted flow cell, with the date and age of the check. Results older than 24 hours are highlighted, so it's obvious when a run was started without a fresh pore scan.
- **Multi-Device Support:** Supports PromethION P2 Solo and multi-MinION setups with a flow cell position selector.
- **Run Metadata:** Experiment, sample, kit and basecaller configuration read directly from MinKNOW.
- **Safeguarded Controls:** Device controls (Flow Cell Check, Start, Pause, Resume, Stop) are hidden behind an "Unlock Controls" toggle. Start-run settings are validated both in the browser and on the server.
- **Historical Pore Scans:** Tracks flow cell degradation during sequencing with stacked bar charts.
- **NVIDIA GPU Monitoring:** Shows NVIDIA GPU temperature and utilization when available.
- **Light and Dark Themes:** Frosted glass header, and all charts follow the selected theme.
- **Works Offline:** All scripts (Chart.js, Lucide icons) are served locally, so the dashboard works on sequencers without internet access.
- **Production Ready:** Installed as a `.deb` package running a `systemd` service with `gunicorn` (threaded workers) over HTTPS.

> [!WARNING]
> **Device Controls Disclaimer:** Device control features (Start, Stop, Pause and run configuration) have been tested and work on MinION and PromethION P2 Solo devices. They have not been tested across all MinKNOW edge cases or older hardware combinations, so they are provided as-is and used at your own risk. When in doubt, use the official MinKNOW desktop interface to start critical sequencing runs.

## What's New

### v1.5.7
- **Security:** The installer keeps `config.json` and the TLS private key readable only by the dashboard service (previously they became world-readable). Certificates are no longer shipped inside the package.
- **TLS:** 10-year self-signed certificate that includes the machine's host name and IP address.
- **Login lockout:** A successful login resets failed attempts, and failed attempts expire after 3 hours.
- **Flow cell check:** Shows when the last check was run, and picks up a new check's result as soon as it finishes.
- **Start run:** Minimum Q-score and run duration accept whole numbers only; all settings are validated on the server.
- **Performance and dependencies:** Much lighter MinKNOW polling, threaded gunicorn workers, gunicorn 23.0.0, and locally served icons.
- **UI:** Frosted glass header, theme toggle updates all charts, broader barcode kit detection.

See `Changelog.txt` for the full history.

## Requirements

- **Operating System:** Ubuntu 22.04 LTS or 24.04 LTS on the sequencing computer.
- **MinKNOW:** A running MinKNOW instance on `localhost:9502` (tested with MinKNOW API 6.10.3). The package runs the dashboard as the `minknow` user that MinKNOW creates.
- **For installing:** `git`, `openssl`, `python3-venv` (pulled in automatically by `apt`) and an internet connection during installation, to download the Python dependencies and the MinKNOW API from GitHub.
- **For building the package yourself (optional):** `dpkg-deb`, which is standard on Debian and Ubuntu.

------------------------------------------------------------------------

## 1. Installation

### Option A: Download the release package (recommended)

Download the latest `minknow-dashboard_<version>_all.deb` from the [GitHub Releases](https://github.com/msuokas-bco/minknow_dashboard/releases) page and install it with `apt`, which also installs any missing dependencies:

``` bash
sudo apt update
sudo apt install ./minknow-dashboard_1.5.7_all.deb
```

### Option B: Build the package yourself

Clone this repository on the Ubuntu machine and run the packaging script:

``` bash
cd /path/to/minknow_dashboard
chmod +x create_deb_package.sh
./create_deb_package.sh
sudo apt install ./minknow-dashboard_1.5.7_all.deb
```

### What the installer does

- Installs the application to `/opt/minknow-dashboard` with its own Python virtual environment (compatible with PEP 668 on Ubuntu 24.04).
- On first installation, asks you to set the administrator username and password.
- Generates a self-signed HTTPS certificate if none exists (see section 3).
- Sets up and starts the `minknow-dashboard` `systemd` service on port `8443`.

When the service is running, open `https://<sequencer-hostname>:8443` in a browser.

### Upgrading

Install the newer `.deb` the same way. Your credentials and certificates are kept.

> [!NOTE]
> **Upgrading to v1.5.7 from an older package:** older packages could include certificate files, which the upgrade removes. The installer then generates a new certificate, so each browser asks you to accept it once.

------------------------------------------------------------------------

## 2. Service Management

The dashboard runs in the background as a `systemd` service on port `8443`.

- **Check status:**

  ``` bash
  sudo systemctl status minknow-dashboard
  ```

- **Start / stop / restart:**

  ``` bash
  sudo systemctl restart minknow-dashboard
  sudo systemctl stop minknow-dashboard
  sudo systemctl start minknow-dashboard
  ```

- **View logs:**

  ``` bash
  sudo journalctl -u minknow-dashboard -f
  ```

------------------------------------------------------------------------

## 3. HTTPS and Certificates

The dashboard only runs over HTTPS on port `8443`.

During installation the package generates a self-signed certificate in `/opt/minknow-dashboard/certs/`:
- It is valid for 10 years.
- It covers `localhost`, `127.0.0.1`, the machine's full host name and its primary IP address.
- It is regenerated automatically on upgrade only if it is missing or has expired.
- The private key (`key.pem`) is readable only by the `minknow` service user.

### Browser warnings

Browsers show a warning for self-signed certificates.
- **Safari:** accept the certificate once and Safari remembers it.
- **Chrome:** to stop the warning (and the `certificate unknown` messages in the service log), import the certificate as trusted. Open `chrome://certificate-manager`, go to **Local certificates → Installed by you**, and import `/opt/minknow-dashboard/certs/cert.pem`.

The address you use in the browser must be one of the names covered by the certificate. To list them:

``` bash
openssl x509 -in /opt/minknow-dashboard/certs/cert.pem -noout -ext subjectAltName
```

### Using your own certificate

Replace `cert.pem` and `key.pem` in `/opt/minknow-dashboard/certs/` with your certificate and key, then restart the service:

``` bash
sudo chown minknow:minknow /opt/minknow-dashboard/certs/*.pem
sudo chmod 600 /opt/minknow-dashboard/certs/key.pem
sudo systemctl restart minknow-dashboard
```

Your own certificate is kept on later upgrades.

------------------------------------------------------------------------

## 4. Authentication and Security

The dashboard uses Basic Authentication over HTTPS. You set the administrator username and password during the first installation.

The credentials are stored in `/etc/minknow-dashboard/config.json`, which only `root` and the `minknow` service group can read.

### Changing credentials

To change the username or password, run:

``` bash
sudo minknow-passwd
```

It prompts for the new credentials, saves them, clears any lockouts and restarts the service.

### Account lockout

To prevent brute-force attacks, an IP address is locked for **3 hours after 3 failed login attempts**, and a locked browser shows an "Account Locked" message.
- A successful login resets the failed-attempt counter.
- Failed attempts are forgotten after 3 hours, so occasional typos don't add up over time.

To unlock manually:

``` bash
sudo minknow-passwd --unlock
```

------------------------------------------------------------------------

## 5. Uninstallation

To remove the dashboard, its virtual environment and the service:

``` bash
sudo apt remove minknow-dashboard
```

The credentials file in `/etc/minknow-dashboard/` is left in place, so a later reinstall keeps the same login.

------------------------------------------------------------------------

## Development

`test_mock_run.py` starts the dashboard with simulated MinKNOW data (no MinKNOW or authentication needed) at `http://localhost:5001`, for testing the user interface:

``` bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python test_mock_run.py
```

------------------------------------------------------------------------

## License

This project is open-source and released under the **GNU General Public License v3.0 (GPLv3)**.

**Notice regarding MinKNOW API:** This project uses the `minknow_api` library provided by Oxford Nanopore Technologies PLC. The `minknow_api` source code is licensed under the **Mozilla Public License Version 2.0 (MPL 2.0)**.
