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

def get_failed_attempts(ip_address):
    lockout_file = os.path.join(STATE_DIR, 'lockout.json')
    now = time.time()
    if os.path.exists(lockout_file):
        try:
            with open(lockout_file, 'r') as f:
                data = json.load(f)
                ip_data = data.get(ip_address, {})
                attempts = ip_data.get('attempts', 0)
                lockout_until = ip_data.get('lockout_until', 0)
                if now < lockout_until:
                    return attempts, lockout_until
                else:
                    return 0, 0
        except Exception:
            return 0, 0
    return 0, 0

def set_failed_attempts(ip_address, attempts, lockout_until=0):
    os.makedirs(STATE_DIR, exist_ok=True)
    lockout_file = os.path.join(STATE_DIR, 'lockout.json')
    now = time.time()
    try:
        data = {}
        if os.path.exists(lockout_file):
            try:
                with open(lockout_file, 'r') as f:
                    data = json.load(f)
            except Exception:
                pass
        
        # Clean up expired lockouts to prevent file growth
        data = {ip: info for ip, info in data.items() if info.get('lockout_until', 0) > now or info.get('attempts', 0) > 0}
        
        if attempts == 0 and lockout_until == 0:
            if ip_address in data:
                del data[ip_address]
        else:
            data[ip_address] = {'attempts': attempts, 'lockout_until': lockout_until}
            
        # Write securely using an atomic replace to prevent symlink attacks
        tmp_file = lockout_file + '.tmp'
        with open(tmp_file, 'w') as f:
            json.dump(data, f)
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, lockout_file)
    except Exception as e:
        logging.error(f"Error writing lockout file: {e}")

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
