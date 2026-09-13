import os
import json
import time
import logging
import secrets
from functools import wraps
from flask import request, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

CONFIG_FILE = '/etc/minknow-dashboard/config.json'
# Resolve the state directory to the root of the project (parent of core)
STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'state')

# Generate a random fallback hash on boot to fail closed if unconfigured
_FALLBACK_HASH = generate_password_hash(secrets.token_urlsafe(32))

def get_credentials():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('username'), config.get('password')
        except Exception as e:
            logging.error(f"Error reading config: {e}")
            
    return os.environ.get('MINKNOW_ADMIN_USER', 'admin'), os.environ.get('MINKNOW_ADMIN_PASS', _FALLBACK_HASH)

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
                import tempfile
                new_hash = generate_password_hash(password)
                fd, temp_config = tempfile.mkstemp(dir=os.path.dirname(CONFIG_FILE), prefix='config_', suffix='.tmp')
                with os.fdopen(fd, 'w') as f:
                    json.dump({"username": username, "password": new_hash}, f)
                os.chmod(temp_config, 0o640)
                os.replace(temp_config, CONFIG_FILE)
                logging.info("Successfully auto-migrated legacy plaintext password to secure hash.")
            except Exception as e:
                logging.error(f"Failed to auto-migrate password to hash: {e}")
            return True
        return False
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
    except Exception:
        pass
    return 0, 0

def record_failed_attempt(ip_address, max_attempts, lockout_period):
    try:
        with get_db() as conn:
            conn.execute("BEGIN EXCLUSIVE")
            cur = conn.cursor()
            now = time.time()
            cur.execute("SELECT attempts, lockout_until FROM lockout WHERE ip=?", (ip_address,))
            row = cur.fetchone()
            attempts = row[0] if row and now < row[1] or (row and row[1] == 0) else 0
            attempts += 1
            new_lockout = now + lockout_period if attempts >= max_attempts else 0
            conn.execute("INSERT OR REPLACE INTO lockout (ip, attempts, lockout_until) VALUES (?, ?, ?)", (ip_address, attempts, new_lockout))
            return attempts
    except Exception as e:
        logging.error(f"Error recording failed attempt: {e}")
    return 1

def clear_failed_attempts(ip_address):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM lockout WHERE ip=?", (ip_address,))
    except Exception:
        pass

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
            attempts = record_failed_attempt(ip_address, MAX_ATTEMPTS, LOCKOUT_PERIOD)
            logging.warning(f"Failed authentication attempt from {ip_address}. Attempt {attempts} of {MAX_ATTEMPTS}")
            return authenticate()
            
        if attempts > 0:
            clear_failed_attempts(ip_address)
            
        return f(*args, **kwargs)
    return decorated
