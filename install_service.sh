#!/bin/bash
# install_service.sh
# Run this script with sudo (or as root) on the Ubuntu machine.

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (e.g., sudo ./install_service.sh)"
  exit 1
fi

# The directory where the dashboard is located
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER=$(stat -c '%U' "$APP_DIR")
APP_GROUP=$(stat -c '%G' "$APP_DIR")

echo "Setting up MinKNOW dashboard in $APP_DIR"
echo "Service will run as user: $APP_USER"

# Install system dependencies (assuming Debian/Ubuntu)
apt-get update
apt-get install -y python3 python3-pip python3-venv

# Create a virtual environment as root to prevent LPE via venv hijacking
if [ ! -d "$APP_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$APP_DIR/venv"
fi

# Create state directory for caching and lockout data
mkdir -p "$APP_DIR/state"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR/state"

# Install python dependencies
echo "Installing Python dependencies..."
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
chmod -R 755 "$APP_DIR/venv"

# Create systemd service file
SERVICE_FILE="/etc/systemd/system/minknow-dashboard.service"
echo "Creating systemd service at $SERVICE_FILE..."

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=MinKNOW Dashboard Service
After=network.target

[Service]
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"

# Execute the secure dashboard (HTTPS)
ExecStart=$APP_DIR/venv/bin/gunicorn --certfile=$APP_DIR/certs/cert.pem --keyfile=$APP_DIR/certs/key.pem -w 4 -b 0.0.0.0:8443 run:app

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd, enable and start service
systemctl daemon-reload
systemctl enable minknow-dashboard.service
systemctl restart minknow-dashboard.service

echo "MinKNOW dashboard service has been installed and started."
echo "You can check the status with: sudo systemctl status minknow-dashboard"
echo "To view the logs, run: sudo journalctl -u minknow-dashboard -f"
