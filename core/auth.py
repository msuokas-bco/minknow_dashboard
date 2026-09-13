import os
import json
import time
import logging
from functools import wraps
from flask import request, Response
from werkzeug.security import generate_password_hash, check_password_hash

CONFIG_FILE = '/etc/minknow-dashboard/config.json'
# Resolve the state directory to the root of the project (parent of core)
STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'state')

def get_credentials():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('username'), config.get('password')
        except Exception as e:
            logging.error(f"Error reading config: {e}")
            
    return os.environ.get('MINKNOW_ADMIN_USER', 'admin'), os.environ.get('MINKNOW_ADMIN_PASS', generate_password_hash('SecureMinknow!2026'))

def check_auth(username, password):
    """
    Checks if a username / password combination is valid.
    SECURITY: Fetches credentials and verifies securely using hashes. Backwards compatible with legacy plaintext.
    """
    valid_user, valid_pass = get_credentials()
    
    if username != valid_user:
        return False
        
    if valid_pass.startswith('scrypt:') or valid_pass.startswith('pbkdf2:'):
        return check_password_hash(valid_pass, password)
    else:
        # Legacy fallback: Verify plaintext, then auto-migrate to hash immediately
        if password == valid_pass:
            try:
                new_hash = generate_password_hash(password)
                with open(CONFIG_FILE, 'w') as f:
                    json.dump({"username": username, "password": new_hash}, f)
                logging.info("Successfully auto-migrated legacy plaintext password to secure hash.")
            except Exception as e:
                logging.error(f"Failed to auto-migrate password to hash: {e}")
            return True
        return False

import sqlite3

def get_db():
    os.makedirs(STATE_DIR, exist_ok=True)
    db_path = os.path.join(STATE_DIR, 'lockout.db')
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS lockout (ip TEXT PRIMARY KEY, attempts INTEGER, lockout_until REAL)")
    return conn

def get_failed_attempts(ip_address):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT attempts, lockout_until FROM lockout WHERE ip=?", (ip_address,))
            row = cur.fetchone()
            if row:
                attempts, lockout_until = row
                if time.time() < lockout_until:
                    return attempts, lockout_until
                else:
                    return 0, 0
    except Exception:
        pass
    return 0, 0

def set_failed_attempts(ip_address, attempts, lockout_until=0):
    try:
        with get_db() as conn:
            now = time.time()
            # Clean up expired lockouts
            conn.execute("DELETE FROM lockout WHERE lockout_until <= ? AND attempts = 0", (now,))
            if attempts == 0 and lockout_until == 0:
                conn.execute("DELETE FROM lockout WHERE ip=?", (ip_address,))
            else:
                conn.execute("INSERT OR REPLACE INTO lockout (ip, attempts, lockout_until) VALUES (?, ?, ?)", (ip_address, attempts, lockout_until))
    except Exception as e:
        logging.error(f"Error writing lockout db: {e}")

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    """Decorator to require HTTP Basic Auth on a specific route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        ip_address = request.remote_addr
        attempts, lockout_until = get_failed_attempts(ip_address)
        MAX_ATTEMPTS = 3
        LOCKOUT_PERIOD = 3 * 3600 # 3 hours
        now = time.time()
        
        if attempts >= MAX_ATTEMPTS and now < lockout_until:
            logging.warning(f"Blocked request from {ip_address}: Account locked")
            return Response(
                '<h2>Account Locked</h2><p>Account locked due to too many failed login attempts.</p><p>Please contact the administrator to reset access.</p>',
                403)
                
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            attempts += 1
            new_lockout = now + LOCKOUT_PERIOD if attempts >= MAX_ATTEMPTS else 0
            set_failed_attempts(ip_address, attempts, new_lockout)
            logging.warning(f"Failed authentication attempt from {ip_address}. Attempt {attempts} of {MAX_ATTEMPTS}")
            return authenticate()
            
        if attempts > 0:
            set_failed_attempts(ip_address, 0, 0)
            
        return f(*args, **kwargs)
    return decorated
