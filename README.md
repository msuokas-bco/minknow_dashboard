# MinKNOW Dashboard

A real-time web dashboard for local Oxford Nanopore MinKNOW instances. This dashboard provides a web interface to monitor flow cell telemetry (such as pore health, read length, yield, and temperature) and execute basic sequencing device control commands directly from your browser.

## Key Features

- **Real-time Telemetry:** Monitor flow cell status, temperature, yield (bases & reads), and pore health natively. Rapid polling refreshes data every 10 seconds.
- **Multi-Device Support:** Natively supports PromethION P2-Solo and multi-MinION setups using a built-in flow cell Position Selector.
- **Comprehensive Run Metadata:** Extracts and cleanly displays full experiment, sample, kit, and basecaller configuration info directly from the MinKNOW gRPC engine.
- **Safeguarded Controls:** Device control features (Start, Stop, Pause) are locked behind a safeguard toggle by default, making the dashboard safely deployable as a viewer-only interface.
- **Historical Pore Scans:** Dedicated visualization tab tracks flow cell degradation during sequencing using stacked bar charts.
- **NVIDIA GPU Monitoring:** Automatically detects and displays NVIDIA GPU temperature and utilization.
- **Modern Zephyr UI:** A clean, flat Material-inspired interface (Bootswatch Zephyr design language) that supports Light and Dark modes.
- **Production Ready:** Can be packaged as a standard `.deb` file, deploying a secure, isolated `systemd` service utilizing `gunicorn`.
- **Secure Access:** Supports running securely over HTTPS with `app_secure.py` and local certificates.

> [!WARNING]
> **Device Controls Disclaimer:** The remote device control features (Start, Stop, Pause) and custom protocol configuration options provided in this dashboard have not been extensively tested across all MinKNOW edge cases or hardware combinations. They are provided as-is, and should be used strictly at your own risk. When in doubt, prefer using the official MinKNOW desktop interface for initiating critical sequencing runs.

## Requirements

- **Operating System:** Ubuntu 22.04 LTS or Ubuntu 24.04 LTS (Dedicated Linux environment required for production use).
- **Software Dependencies (for building):** `dpkg-deb` (standard on Debian/Ubuntu).
- **Software Dependencies (for installing):** `git` and an active internet connection (to pull the 6.10.3 API from GitHub during package installation).
- **MinKNOW Instance:** A running MinKNOW instance (fully compatible with v6.10.3) on `localhost:9502`.

------------------------------------------------------------------------

## 1. Building the Debian Package

For a robust, system-wide installation that respects modern Python environment policies (such as PEP-668 on Ubuntu 24.04), we utilize a `.deb` package.

To build the installer package, clone or copy this repository to your Ubuntu machine and run the packaging script:

``` bash
cd /path/to/minknow_dashboard
chmod +x create_deb_package.sh
./create_deb_package.sh
```

This will generate a ready-to-use Debian package (e.g., `minknow-dashboard_1.2.0_all.deb`).

------------------------------------------------------------------------

## 2. Installation

Once the `.deb` file is generated, you can install it using `dpkg`. The installer automatically sets up a dedicated `minknow` system user, an isolated Python virtual environment, and configures the application as a `systemd` service.

``` bash
sudo apt update
sudo dpkg -i minknow-dashboard_1.2.0_all.deb
```

*(Note: If `dpkg` reports any missing dependencies during the install, simply run `sudo apt --fix-broken install` to resolve them).*

------------------------------------------------------------------------

## 3. Service Management

The application runs in the background via `systemd` on port `8443`. You can control the service using standard commands:

- **Check Status:**

  ``` bash
  sudo systemctl status minknow-dashboard
  ```

- **Start / Stop / Restart:**

  ``` bash
  sudo systemctl restart minknow-dashboard
  sudo systemctl stop minknow-dashboard
  sudo systemctl start minknow-dashboard
  ```

- **View Logs:**

  ``` bash
  sudo journalctl -u minknow-dashboard -f
  ```

------------------------------------------------------------------------

## 4. Configuration (HTTPS/Secure Mode)

By default, the `.deb` package installs and runs the secure, HTTPS-encrypted version of the dashboard (`app_secure.py`) on port `8443`. This ensures all local network traffic to your MinKNOW instance is encrypted.

During installation, the package automatically generates local self-signed SSL certificates (`cert.pem` and `key.pem`) and stores them in `/opt/minknow-dashboard/certs/`.

To use your own trusted SSL certificates: 1. Replace the `cert.pem` and `key.pem` files in the `/opt/minknow-dashboard/certs/` directory with your trusted certificates. 2. Restart the background service to load the new certificates: `bash    sudo systemctl restart minknow-dashboard`

------------------------------------------------------------------------

## 5. Authentication & Security
The dashboard is secured by Basic Authentication. The default credentials are:
- **Username**: `admin`
- **Password**: `SecureMinknow!2026`

### Changing Credentials
To securely change the username or password, you must use the `sudo minknow-passwd` CLI tool provided by the `.deb` package. 

``` bash
sudo minknow-passwd
```

This script will securely prompt you for the new credentials, write them to a protected configuration file (`/etc/minknow-dashboard/config.json`), and automatically restart the service to apply the changes.

### Account Lockout
To prevent brute-force attacks, the application automatically locks the account after **5 failed login attempts**. When locked, users will see an "Account Locked" message in their browser.

To unlock an account, an administrator must run the following command in the terminal:
``` bash
sudo minknow-passwd --unlock
```
*(Note: Changing the password using `sudo minknow-passwd` will also automatically clear any existing lockouts.)*

------------------------------------------------------------------------

## 6. Uninstallation

To cleanly remove the dashboard, virtual environment, and background service, run:

``` bash
sudo dpkg -r minknow-dashboard
```

------------------------------------------------------------------------

## License

This project is open-source and released under the **GNU General Public License v3.0 (GPLv3)**.

**Notice regarding MinKNOW API:** This project utilizes the `minknow_api` library provided by Oxford Nanopore Technologies PLC. The `minknow_api` source code is licensed under the **Mozilla Public License Version 2.0 (MPL 2.0)**.
