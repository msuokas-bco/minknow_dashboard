#!/bin/bash
# create_deb_package.sh
# Run this script on an Ubuntu/Debian machine to generate the .deb package.
# It packages the current directory into a standard Debian installer.

PKG_NAME="minknow-dashboard"
PKG_VERSION="1.1.0"
ARCH="all"
STAGING_DIR="${PKG_NAME}_${PKG_VERSION}_${ARCH}"

echo "Building Debian package: $STAGING_DIR.deb"

# 1. Create directory structure
mkdir -p "$STAGING_DIR/DEBIAN"
mkdir -p "$STAGING_DIR/opt/$PKG_NAME"
mkdir -p "$STAGING_DIR/etc/systemd/system"
mkdir -p "$STAGING_DIR/usr/local/bin"
mkdir -p "$STAGING_DIR/etc/minknow-dashboard"

# 2. Copy application files (excluding the packaging script itself and staging dir)
echo "Copying application files..."
cp -r app.py app_secure.py certs templates static requirements.txt "$STAGING_DIR/opt/$PKG_NAME/"
cp minknow-passwd "$STAGING_DIR/usr/local/bin/minknow-passwd"
chmod +x "$STAGING_DIR/usr/local/bin/minknow-passwd"

# 3. Create the systemd service file
cat > "$STAGING_DIR/etc/systemd/system/$PKG_NAME.service" << 'EOF'
[Unit]
Description=MinKNOW Dashboard Service
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/minknow-dashboard
Environment="PATH=/opt/minknow-dashboard/venv/bin"
ExecStart=/opt/minknow-dashboard/venv/bin/gunicorn --certfile=/opt/minknow-dashboard/certs/cert.pem --keyfile=/opt/minknow-dashboard/certs/key.pem -w 4 -b 0.0.0.0:8443 app_secure:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 4. Create DEBIAN/control file
cat > "$STAGING_DIR/DEBIAN/control" << EOF
Package: $PKG_NAME
Version: $PKG_VERSION
Architecture: $ARCH
Maintainer: MinKNOW Dashboard Admin
Depends: python3, python3-venv, python3-pip
Description: A web dashboard for local MinKNOW instance management.
 This package installs the Flask application and sets it up
 to run automatically as a systemd service.
EOF

# 5. Create DEBIAN/postinst script (Runs after files are extracted)
cat > "$STAGING_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

echo "Setting up Python virtual environment..."
cd /opt/minknow-dashboard
python3 -m venv venv

echo "Installing Python dependencies..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Ensure SSL certificates exist
echo "Ensuring SSL certificates exist..."
if [ ! -f /opt/minknow-dashboard/certs/cert.pem ] || [ ! -f /opt/minknow-dashboard/certs/key.pem ]; then
    echo "Generating self-signed SSL certificates for secure HTTPS access..."
    mkdir -p /opt/minknow-dashboard/certs
    openssl req -x509 -newkey rsa:4096 -nodes -out /opt/minknow-dashboard/certs/cert.pem -keyout /opt/minknow-dashboard/certs/key.pem -days 365 -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
fi

# Ensure proper permissions
chmod -R 755 /opt/minknow-dashboard
chmod -R 755 /etc/minknow-dashboard

echo "Enabling and starting systemd service..."
systemctl daemon-reload
systemctl enable minknow-dashboard.service
systemctl restart minknow-dashboard.service

echo "MinKNOW Dashboard installation complete."
EOF
chmod 755 "$STAGING_DIR/DEBIAN/postinst"

# 6. Create DEBIAN/prerm script (Runs before package removal)
cat > "$STAGING_DIR/DEBIAN/prerm" << 'EOF'
#!/bin/bash
set -e

if systemctl is-active --quiet minknow-dashboard.service; then
    echo "Stopping systemd service..."
    systemctl stop minknow-dashboard.service
fi
if systemctl is-enabled --quiet minknow-dashboard.service; then
    systemctl disable minknow-dashboard.service
fi
EOF
chmod 755 "$STAGING_DIR/DEBIAN/prerm"

# 7. Create DEBIAN/postrm script (Runs after package is removed)
cat > "$STAGING_DIR/DEBIAN/postrm" << 'EOF'
#!/bin/bash
set -e

if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    echo "Reloading systemd daemon..."
    systemctl daemon-reload
    
    # We remove the /opt/minknow-dashboard directory fully
    # to clean up the virtual environment which wasn't part of the dpkg payload.
    if [ -d "/opt/minknow-dashboard" ]; then
        echo "Removing application files from /opt/minknow-dashboard..."
        rm -rf /opt/minknow-dashboard
    fi
fi
EOF
chmod 755 "$STAGING_DIR/DEBIAN/postrm"

# 8. Build the Debian package (if dpkg-deb is available)
if command -v dpkg-deb &> /dev/null; then
    echo "Building the .deb file..."
    dpkg-deb --build "$STAGING_DIR"
    echo "Success! The package $STAGING_DIR.deb is ready."
    echo "To clean up the staging folder, you can run: rm -rf $STAGING_DIR"
else
    echo "dpkg-deb is not installed on this system. Staging directory $STAGING_DIR is prepared."
    echo "Run this script on your Ubuntu machine to generate the .deb package."
fi
