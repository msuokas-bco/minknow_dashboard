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

# Create a virtual environment
if [ ! -d "$APP_DIR/venv" ]; then
    echo "Creating virtual environment..."
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
fi

# Install python dependencies
echo "Installing Python dependencies..."
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

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

# To use the secure app (HTTPS), comment out the line below and uncomment the next one:
ExecStart=$APP_DIR/venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app:app
# ExecStart=$APP_DIR/venv/bin/gunicorn --certfile=$APP_DIR/certs/cert.pem --keyfile=$APP_DIR/certs/key.pem -w 4 -b 0.0.0.0:8000 app_secure:app

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
