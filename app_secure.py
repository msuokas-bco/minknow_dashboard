# MinKNOW Dashboard
# Copyright (C) 2026 MinKNOW Dashboard Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import re
import subprocess
import time
import logging
import json
import grpc
from functools import wraps
from flask import Flask, render_template, jsonify, request, Response
from minknow_api.manager import Manager
from minknow_api.tools import protocols
from minknow_api import statistics_pb2

# Configure basic logging for debugging and security auditing
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def configure_minknow_certificates():
    """Finds the MinKNOW CA certificate and sets the environment variable so the PyPI library handles auth correctly."""
    cert_paths = [
        "/data/rpc-certs/minknow/ca.crt",
        "/opt/minknow/conf/rpc-certs/ca.crt", 
        "/var/lib/minknow/data/rpc-certs/minknow/ca.crt", 
        "/opt/minknow/conf/certs-bundle.crt"
    ]
    
    for cert_path in cert_paths:
        if os.path.exists(cert_path):
            os.environ["MINKNOW_TRUSTED_CA"] = cert_path
            return
            
    logging.warning(f"CRITICAL: Could not find ca.crt in any of {cert_paths}. Is MinKNOW installed?")

from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

CONFIG_FILE = '/etc/minknow-dashboard/config.json'

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
    lockout_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'state', 'lockout.json')
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
    state_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'state')
    os.makedirs(state_dir, exist_ok=True)
    lockout_file = os.path.join(state_dir, 'lockout.json')
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

def get_gpu_stats():
    try:
        # Use full path for nvidia-smi just in case it's missing from service PATH
        result = subprocess.run(['/usr/bin/nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu', '--format=csv,noheader,nounits'], stdout=subprocess.PIPE, timeout=2)
        if result.returncode == 0:
            lines = result.stdout.decode('utf-8').strip().split('\n')
            if lines:
                parts = lines[0].split(',')
                if len(parts) >= 2:
                    return {"temp": parts[0].strip(), "usage": parts[1].strip()}
    except Exception as e:
        logging.debug(f"GPU stats failed: {e}")
    return {"temp": "--", "usage": "--"}

import grpc
_USE_INSECURE_CHANNEL = None

def get_minknow_manager():
    """
    Creates a Manager instance with automatic fallback to insecure channels.
    minknow_api 6.10.3+ forces TLS, which breaks compatibility with MinKNOW < 5.5 
    or configurations where localhost:9502 is plaintext.
    """
    global _USE_INSECURE_CHANNEL
    
    if _USE_INSECURE_CHANNEL:
        from unittest.mock import patch
        with patch('minknow_api.manager.grpc.secure_channel', new=lambda target, creds, **kwargs: grpc.insecure_channel(target, **kwargs)):
            return Manager(host="localhost", port=9502)

    manager = Manager(host="localhost", port=9502)
    
    # If we haven't determined the channel type yet, test it
    if _USE_INSECURE_CHANNEL is None:
        try:
            list(manager.flow_cell_positions())
            _USE_INSECURE_CHANNEL = False
        except grpc.RpcError as e:
            if "Tls handshake failed" in str(e) or "WRONG_VERSION_NUMBER" in str(e) or "failed to connect" in str(e):
                logging.warning("TLS connection to MinKNOW failed. Falling back to insecure channel.")
                _USE_INSECURE_CHANNEL = True
                return get_minknow_manager()
            raise
            
    return manager

def get_target_position(manager, request_json):
    """Helper to cleanly resolve the requested flow cell position."""
    positions = list(manager.flow_cell_positions())
    if not positions:
        return None, "No positions found."
    target_pos = request_json.get("position") if request_json else None
    if target_pos:
        for p in positions:
            name = p.name if hasattr(p, 'name') else p.position
            if name == target_pos:
                return p, None
        return None, f"Position {target_pos} not found."
    return positions[0], None

def get_sequencing_data(active_tab='main', target_pos=None):
    """
    Connects to the local MinKNOW instance and fetches real-time telemetry.
    Returns a dictionary of parsed data suitable for the frontend.
    """
    data = {
        "status": "Disconnected",
        "active": False,
        "position": "--",
        "run_id": "--",
        "state": "Idle",
        "pores": {"sequencing": 0, "available": 0, "inactive": 0},
        "yield": {"bases": 0, "reads": 0},
        "read_length": {"n50": 0, "histogram": []},
        "min_qscore": None,
        "temperature": 0.0,
        "gpu": get_gpu_stats(),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        positions = list(manager.flow_cell_positions())
        
        if not positions:
            data["status"] = "No positions found"
            return data

        pos = None
        if target_pos:
            for p in positions:
                name = p.name if hasattr(p, 'name') else p.position
                if name == target_pos:
                    pos = p
                    break
        if not pos:
            pos = positions[0]

        data["position"] = pos.name if hasattr(pos, 'name') else pos.position
        
        try:
            client = pos.connect()
            data["status"] = "Connected"
            data["active"] = True
        except Exception as e:
            data["status"] = f"Failed to connect to position: {e}"
            return data
        
        # Fetch flow cell ID and last check result
        try:
            fc_info = client.device.get_flow_cell_info()
            real_fc_id = getattr(fc_info, 'flow_cell_id', None)
            data["flow_cell_id"] = getattr(fc_info, 'user_specified_flow_cell_id', None) or real_fc_id or '--'
            
            data["last_fc_check_pores"] = None
            if real_fc_id:
                # Use a file-based cache to share state across all Gunicorn workers
                state_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'state')
                os.makedirs(state_dir, exist_ok=True)
                cache_file = os.path.join(state_dir, 'minknow_fc_cache.json')
                fc_cache = {"id": None, "pores": None, "time": 0}
                import fcntl
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, 'r') as f:
                            fcntl.flock(f, fcntl.LOCK_SH)
                            fc_cache = json.load(f)
                            fcntl.flock(f, fcntl.LOCK_UN)
                    except Exception:
                        pass
                    
                now = time.time()
                # Refresh cache if ID changed or 15 seconds have passed
                if fc_cache.get("id") != real_fc_id or (now - fc_cache.get("time", 0) > 15):
                    fc_cache["id"] = real_fc_id
                    fc_cache["pores"] = None
                    fc_cache["time"] = now
                    try:
                        runs_resp = client.protocol.list_protocol_runs()
                        run_ids = list(getattr(runs_resp, 'run_ids', runs_resp))
                        
                        if not run_ids:
                            fc_cache["pores"] = None
                        else:
                            # Safely determine sort direction to always search the NEWEST runs first
                            first_run = client.protocol.get_run_info(run_id=run_ids[0])
                            last_run = client.protocol.get_run_info(run_id=run_ids[-1])
                            
                            if getattr(first_run.start_time, 'seconds', 0) > getattr(last_run.start_time, 'seconds', 0):
                                # Newest is at index 0
                                search_ids = run_ids[:50]
                            else:
                                # Newest is at index -1
                                search_ids = reversed(run_ids[-50:])
                                
                            for run_id in search_ids:
                                try:
                                    r = client.protocol.get_run_info(run_id=run_id)
                                    if hasattr(r, 'pqc_result') and getattr(r.pqc_result, 'flow_cell_id', ''):
                                        pqc_fc = getattr(r.pqc_result, 'flow_cell_id', '')
                                        if pqc_fc == real_fc_id:
                                            fc_cache["pores"] = getattr(r.pqc_result, 'total_pore_count', None)
                                            break
                                except Exception:
                                    continue
                    except Exception as e:
                        logging.debug(f"Failed to fetch platform qc results: {e}")
                    
                    try:
                        with open(cache_file, 'w') as f:
                            fcntl.flock(f, fcntl.LOCK_EX)
                            json.dump(fc_cache, f)
                            fcntl.flock(f, fcntl.LOCK_UN)
                    except Exception as e:
                        logging.debug(f"Failed to save fc_cache: {e}")
                        
                data["last_fc_check_pores"] = fc_cache.get("pores")
                    
        except Exception as e:
            logging.debug(f"Failed to fetch flow cell ID: {e}")
            data["flow_cell_id"] = '--'

        # Fetch run metadata
        acquisition_run_id = None
        try:
            run_info = client.protocol.get_run_info()
                
            try:
                data["run_id"] = run_info.run_id
            except Exception:
                data["run_id"] = getattr(run_info, 'protocol_run_id', '--')
            
            # Extract extended metadata
            data["experiment"] = "--"
            data["sample"] = "--"
            data["kit"] = "--"
            data["model"] = "Off"
            
            if hasattr(run_info, 'user_info'):
                uinfo = run_info.user_info
                
                exp_id = getattr(uinfo, 'protocol_group_id', None)
                if exp_id: data["experiment"] = getattr(exp_id, 'value', exp_id) or "--"
                
                samp_id = getattr(uinfo, 'sample_id', None)
                if samp_id: data["sample"] = getattr(samp_id, 'value', samp_id) or "--"
                
                if hasattr(uinfo, 'kit_info') and hasattr(uinfo.kit_info, 'sequencing_kit'):
                    data["kit"] = uinfo.kit_info.sequencing_kit or "--"
            
            if hasattr(run_info, 'args'):
                args_list = list(run_info.args)
                bc_on = False
                for arg in args_list:
                    if "base_calling=on" in arg or "basecalling=on" in arg:
                        bc_on = True
                    if "simplex_model=" in arg:
                        # extract model name
                        import re
                        m = re.search(r'simplex_model="([^"]+)"', arg)
                        if m: data["model"] = m.group(1)
                    if "--min_qscore" == arg or "min_qscore=" in arg:
                        # Sometimes passed as --min_qscore 9, sometimes as --min_qscore=9
                        pass # We will check this below more robustly
                
                # Check for min_qscore in args list robustly
                for i, arg in enumerate(args_list):
                    if arg.startswith("--min_qscore="):
                        data["min_qscore"] = float(arg.split("=")[1])
                    elif arg == "--min_qscore" and i + 1 < len(args_list):
                        try:
                            data["min_qscore"] = float(args_list[i+1])
                        except ValueError:
                            pass
                    elif "min_qscore=" in arg: # Catch cases like "--read_filtering min_qscore=10"
                        import re
                        m = re.search(r'min_qscore=([\d\.]+)', arg)
                        if m: data["min_qscore"] = float(m.group(1))
                if not bc_on and data["model"] != "Off":
                    pass # Keep model name if found but basecalling flag wasn't explicitly matched, maybe they used a different flag
            
            # ProtocolState mapping from protobuf:
            # 0=PROTOCOL_RUNNING, 1=PROTOCOL_COMPLETED, 2=PROTOCOL_STOPPED_BY_USER, 3=PROTOCOL_FINISHED_WITH_ERROR, 
            # 4=PROTOCOL_WAITING_FOR_TEMPERATURE, 5=PROTOCOL_WAITING_FOR_ACQUISITION, 10=PROTOCOL_WAITING_FOR_RESOURCE
            state_val = str(getattr(run_info, 'state', 'Unknown'))
            if 'PROTOCOL_RUNNING' in state_val or state_val == '0':
                phase_val = getattr(run_info, 'phase', None)
                if phase_val is not None:
                    try:
                        from minknow_api.protocol_pb2 import ProtocolPhase
                        phase_name = ProtocolPhase.Name(phase_val)
                        if phase_name == 'PHASE_PAUSED':
                            data["state"] = "Paused"
                        elif phase_name == 'PHASE_PAUSING':
                            data["state"] = "Pausing"
                        elif phase_name == 'PHASE_RESUMING':
                            data["state"] = "Resuming"
                        else:
                            data["state"] = "Running"
                    except Exception:
                        data["state"] = "Running"
                else:
                    data["state"] = "Running"
            elif state_val == '1':
                data["state"] = "Completed"
            elif state_val == '2':
                data["state"] = "Stopped by User"
            elif state_val == '3':
                data["state"] = "Finished with Error"
            elif state_val == '4':
                data["state"] = "Waiting for Temperature"
            elif state_val == '5':
                data["state"] = "Waiting for Acquisition"
            elif state_val == '10':
                data["state"] = "Waiting for Resource"
            else:
                data["state"] = f"Code {state_val}"
                
            if hasattr(run_info, 'acquisition_run_ids') and len(run_info.acquisition_run_ids) > 0:
                acquisition_run_id = run_info.acquisition_run_ids[-1]
        except Exception as e:
            logging.debug(f"Failed to fetch protocol run info: {e}")
            data["state"] = f"ERR: {type(e).__name__} {str(e)}"

        # Determine if we should fetch acquisition data (yield, mux scans).
        # If the protocol is newly spinning up and hasn't started an acquisition yet,
        # we must NOT fetch acquisition data, otherwise MinKNOW returns the previous run's data!
        is_new_protocol_warming_up = data["state"] in ("Waiting for Temperature", "Waiting for Acquisition", "Waiting for Resource") or (data["state"] == "Running" and not acquisition_run_id)
        
        if is_new_protocol_warming_up:
            acquisition_run_id = None
        elif not acquisition_run_id:
            # Fallback for older MinKNOW versions where protocol.get_run_info() didn't populate acquisition_run_ids
            try:
                if hasattr(client.acquisition, 'get_current_acquisition_run'):
                    acq_info = client.acquisition.get_current_acquisition_run()
                    acquisition_run_id = getattr(acq_info, 'run_id', None)
                elif hasattr(client.acquisition, 'current_acquisition_run'):
                    acq_info = client.acquisition.current_acquisition_run()
                    acquisition_run_id = getattr(acq_info, 'run_id', None)
            except Exception as e:
                logging.debug(f"Failed to get current_acquisition_run: {e}")

        # Fetch yield statistics only if we are confident the acquisition belongs to this run
        acquire_info = None
        if acquisition_run_id:
            try:
                acquire_info = client.acquisition.get_acquisition_info()
                
                # Yield info might be directly on acquire_info or inside yield_summary
                ys = getattr(acquire_info, 'yield_summary', acquire_info)
                data["yield"]["reads"] = getattr(ys, 'read_count', getattr(ys, 'reads', 0))
                data["yield"]["bases"] = getattr(ys, 'estimated_selected_bases', getattr(ys, 'bases', 0))
            except Exception as e:
                logging.debug(f"Failed to fetch yield: {e}")

        # Fetch temperature
        try:
            temp_res = client.device.get_temperature()
            if temp_res.HasField('minion'):
                data["temperature"] = temp_res.minion.heatsink_temperature.value
            elif temp_res.HasField('promethion'):
                data["temperature"] = temp_res.promethion.chamber_temperature.value
            elif temp_res.HasField('pebble'):
                data["temperature"] = temp_res.pebble.instrument_temperature.value
        except Exception as e:
            logging.debug(f"Failed to fetch temperature: {e}")

        # Fetch pore statistics if requested
        data["pore_scans"] = []
        if active_tab in ['main', 'pore-state']:
            try:
                state_counts = {"sequencing": 0, "available": 0, "inactive": 0}
                if hasattr(client, 'data') and hasattr(client.data, 'get_channel_states'):
                    max_channels = 512
                    try:
                        layout = client.device.get_channels_layout()
                        max_channels = getattr(layout, 'channel_count', 512)
                    except Exception:
                        pass
                        
                    state_stream = client.data.get_channel_states(first_channel=1, last_channel=max_channels)
                    for state_msg in state_stream:
                        for ch_data in state_msg.channel_states:
                            name = str(getattr(ch_data, 'state_name', getattr(ch_data, 'state', ''))).lower()
                            if name in ['strand', 'adapter', 'sequencing']:
                                state_counts["sequencing"] += 1
                            elif name in ['single_pore', 'available', 'good_single', 'pore', 'good']:
                                state_counts["available"] += 1
                            elif name:  # If it has any other state
                                state_counts["inactive"] += 1
                        break # Only need the first snapshot
                    
                data["pores"]["sequencing"] = state_counts["sequencing"]
                data["pores"]["available"] = state_counts["available"]
                data["pores"]["inactive"] = state_counts["inactive"]
            except Exception as e:
                logging.debug(f"Failed to fetch pore states: {e}")
                # We do not set debug_pores here to avoid showing ugly errors in the UI 
                # during expected FAILED_PRECONDITION states when flow cells are warming up.

            try:
                if acquire_info and hasattr(acquire_info, 'bream_info'):
                    bream_info = acquire_info.bream_info
                    
                    if hasattr(bream_info, 'mux_scan_results'):
                        for msr in bream_info.mux_scan_results:
                            ts = getattr(msr.mux_scan_timestamp, 'seconds', getattr(msr, 'mux_scan_timestamp', 0))
                            
                            # ts is already seconds since start
                            diff = max(0, ts)
                            
                            # format diff (seconds since start) into hours:minutes
                            time_lbl = f"{int(diff // 3600)}h {int((diff % 3600) // 60)}m"
                            if diff == 0:
                                time_lbl = "Start"
                            
                            counts = dict(getattr(msr, 'counts', {}))
                            
                            # "pore" or "good_single" usually represent working pores in mux scans
                            avail = counts.get('pore', counts.get('good_single', counts.get('single', counts.get('single_pore', 0))))
                            total = sum(counts.values())
                            inact = total - avail
                            
                            data["pore_scans"].append({
                                "time": time_lbl,
                                "sequencing": 0, # Mux scans don't sequence
                                "available": avail,
                                "inactive": inact
                            })
            except Exception as e:
                logging.debug(f"Failed to parse mux scans: {e}")

        # Fetch read length stats if requested
        if active_tab in ['main', 'read-length'] and acquisition_run_id:
            try:
                n50_res = client.statistics.read_length_n50(acquisition_run_id=acquisition_run_id)
                
                # Check for n50_data object first, then fallback to direct attributes
                if hasattr(n50_res, 'n50_data'):
                    data["read_length"]["n50"] = getattr(n50_res.n50_data, 'estimated_n50', getattr(n50_res.n50_data, 'basecalled_n50', 0))
                else:
                    data["read_length"]["n50"] = getattr(n50_res, 'estimated_n50', getattr(n50_res, 'basecalled_n50', 0))
            except Exception as e:
                logging.debug(f"Failed to fetch read length n50: {e}")
                data["read_length"]["unavailable"] = True
            
            try:
                # Dynamically set histogram step based on current N50
                # Amplicons get 100bp bins, standard get 500bp, ultra-long get 1000bp
                n50_val = data["read_length"].get("n50", 0)
                if 0 < n50_val < 3000:
                    step_val = 100
                elif 3000 <= n50_val < 15000:
                    step_val = 500
                else:
                    step_val = 1000
                    
                try:
                    # MinKNOW seems to enforce a maximum number of buckets (e.g., 100 buckets).
                    # If we request end=200000, it artificially forces the step size to 2000bp!
                    # So we dynamically scale the end boundary based on the N50 to get fine resolution.
                    end_val = max(5000, int(n50_val * 4))
                    
                    hist_stream = client.statistics.stream_read_length_histogram(
                        acquisition_run_id=acquisition_run_id,
                        data_selection=statistics_pb2.DataSelection(start=0, step=step_val, end=end_val)
                    )
                except Exception as bin_err:
                    logging.error(f"Failed to set custom bin step {step_val}: {bin_err}")
                    # Fallback for MinKNOW versions where stream_read_length_histogram doesn't accept these arguments
                    hist_stream = client.statistics.stream_read_length_histogram(acquisition_run_id=acquisition_run_id)
                    
                for h in hist_stream:
                    if hasattr(h, 'bucket_ranges') and hasattr(h, 'histogram_data') and len(h.histogram_data) > 0:
                        bucket_values = [0] * len(h.bucket_ranges)
                        for hdata in h.histogram_data:
                            for i, count in enumerate(hdata.bucket_values):
                                bucket_values[i] += count
                        
                        histogram = []
                        for br, count in zip(h.bucket_ranges, bucket_values):
                            histogram.append({
                                "start": br.start,
                                "end": br.end,
                                "count": count
                            })
                        data["read_length"]["histogram"] = histogram
                        
                        # Fallback N50 calculation if API returned 0
                        if data["read_length"]["n50"] == 0 and sum(b['count'] for b in histogram) > 0:
                            total_len = sum((b['start'] + b['end']) / 2 * b['count'] for b in histogram)
                            cumulative = 0
                            for b in sorted(histogram, key=lambda x: -x['start']):
                                L = (b['start'] + b['end']) / 2
                                cumulative += L * b['count']
                                if cumulative >= total_len / 2:
                                    data["read_length"]["n50"] = L
                                    break
                    break # Just need the first valid snapshot
            except Exception as e:
                logging.debug(f"Failed to fetch read length histogram: {e}")
                data["read_length"]["unavailable"] = True

        # Fetch q-score stats if requested
        if active_tab in ['main', 'qscore'] and acquisition_run_id:
            data["qscore"] = {"histogram": []}
            try:
                # Need to use the _message kwargs because this API method expects a StreamQScoreHistogramRequest object in 6.10.3
                hist_stream = client.statistics.stream_q_score_histogram(
                    acquisition_run_id=acquisition_run_id,
                    data_selection=statistics_pb2.FloatDataSelection(step=1.0)
                )
                for h in hist_stream:
                    if hasattr(h, 'bucket_ranges') and hasattr(h, 'histogram_data') and len(h.histogram_data) > 0:
                        bucket_values = [0] * len(h.bucket_ranges)
                        for hdata in h.histogram_data:
                            for i, count in enumerate(hdata.bucket_values):
                                bucket_values[i] += count
                                
                        histogram = []
                        for br, count in zip(h.bucket_ranges, bucket_values):
                            histogram.append({
                                "start": br.start,
                                "end": br.end,
                                "count": count
                            })
                        data["qscore"]["histogram"] = histogram
                    break # Just need the first valid snapshot
            except Exception as e:
                logging.debug(f"Failed to fetch qscore histogram: {e}")
                data["qscore"]["unavailable"] = True

    except Exception as e:
        logging.error(f"Error fetching sequencing data: {e}")
        data["status"] = f"Error: {str(e)}"
        
    return data

@app.route("/")
@requires_auth
def index():
    return render_template("index.html")

@app.route("/api/positions", methods=["GET"])
@requires_auth
def get_positions():
    """Returns a list of all connected flow cell positions."""
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        positions = list(manager.flow_cell_positions())
        pos_names = [pos.name if hasattr(pos, 'name') else pos.position for pos in positions]
        return jsonify({"success": True, "positions": pos_names})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/protocol_options", methods=["GET"])
@requires_auth
def get_protocol_options():
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        # Handle dict-like request.args
        pos, err = get_target_position(manager, {"position": request.args.get("position")} if request.args.get("position") else None)
        if err:
            return jsonify({"success": False, "message": err})
        
        client = pos.connect()
        try:
            flow_cell_info = client.device.get_flow_cell_info()
            product_code = flow_cell_info.user_specified_product_code or flow_cell_info.product_code
            
            if not product_code:
                return jsonify({"success": False, "message": "No product code found. Is a flow cell inserted?"})
                
            response = client.protocol.list_protocols()
            kits = set()
            models = set()
            
            for protocol in response.protocols:
                if not getattr(protocol.tag_extraction_result, 'success', True):
                    continue
                tags = dict(protocol.tags)
                if tags.get("experiment type") and tags["experiment type"].string_value != "sequencing":
                    continue
                if tags.get("flow cell") and tags["flow cell"].string_value != product_code:
                    continue
                    
                if tags.get("kit"):
                    kits.add(tags["kit"].string_value)
                if tags.get("available basecall models"):
                    for m in tags["available basecall models"].array_value:
                        models.add(m)
                        
            # Provide fallbacks if nothing was found
            if not kits:
                kits = {"SQK-LSK114", "SQK-RAD114", "SQK-NBD114.24", "SQK-NBD114.96", "SQK-ULK114", "SQK-16S114.24"}
            if not models:
                models = {"dna_r10.4.1_e8.2_400bps_fast.cfg", "dna_r10.4.1_e8.2_400bps_hac.cfg", "dna_r10.4.1_e8.2_400bps_sup.cfg"}
                
            return jsonify({
                "success": True, 
                "kits": sorted(list(kits)), 
                "models": sorted(list(models)),
                "product_code": product_code
            })
        except Exception as inner_e:
            return jsonify({"success": False, "message": f"Failed to get options: {str(inner_e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/stats")
@requires_auth
def stats():
    tab = request.args.get('tab', 'main')
    target_pos = request.args.get('position', None)
    return jsonify(get_sequencing_data(tab, target_pos))

@app.route("/api/start", methods=["POST"])
@requires_auth
def start_run():
    """Starts a new sequencing run."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format. JSON required."}), 400

    try:
        data = request.json or {}
        
        raw_exp = data.get("experiment_name", "").strip()
        experiment_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_exp or "MinKNOW_Run")
        
        raw_sample = data.get("sample_name", "").strip()
        sample_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_sample or "no_sample_id")
        
        output_dir = data.get("output_dir", "/data/sequencing_runs")
        # Prevent path traversal by resolving the path and ensuring it resides in the allowed data directory
        resolved_path = os.path.abspath(output_dir)
        if not resolved_path.startswith('/data/'):
            logging.warning(f"Path traversal or invalid output directory blocked: {output_dir}")
            return jsonify({"success": False, "message": "Output directory must be within /data/."}), 400
        output_dir = resolved_path

        basecall_model = data.get("basecall_model", "dna_r10.4.1_e8.2_400bps_hac.cfg")
        save_pod5 = data.get("save_pod5", True)
        save_fastq = data.get("save_fastq", True)
        save_bam = data.get("save_bam", False)
        
        try:
            run_duration = float(data.get("run_duration", 72.0))
        except (ValueError, TypeError):
            run_duration = 72.0
            
        kit = data.get("lib_kit", "SQK-LSK114")
        
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, data)
        if err:
            return jsonify({"success": False, "message": err})
        
        client = pos.connect()
        try:
            flow_cell_info = client.device.get_flow_cell_info()
            product_code = flow_cell_info.user_specified_product_code or flow_cell_info.product_code
            
            if not product_code:
                return jsonify({"success": False, "message": "No product code found. Is a flow cell inserted?"})
                
            protocol_info = protocols.find_protocol(
                client,
                product_code=product_code,
                kit=kit,
                experiment_type="sequencing",
            )
            
            if not protocol_info:
                return jsonify({"success": False, "message": f"No sequencing protocol found for flow cell {product_code} and kit {kit}"})
                
            protocol_id = protocol_info if isinstance(protocol_info, str) else protocol_info.identifier
            
            min_qscore = data.get("min_qscore", 10)
            
            protocol_args_list = [
                "--pod5=" + ("on" if save_pod5 else "off"),
                "--fastq=" + ("on" if save_fastq else "off"),
                "--bam=" + ("on" if save_bam else "off"),
                "--generate_bulk_file=off",
                "--mux_scan_period=1.5",
                "--poly_a_tail_length_estimation=off",
                "--split_files_by_barcode=off",
                "--split_pod5_files_by_barcode=off",
                "--read_filtering", f"min_qscore={min_qscore}"
            ]
            
            if save_fastq:
                protocol_args_list.extend([
                    "--fastq_batch_duration=3600",
                    "--fastq_data", "compress"
                ])
            if save_bam:
                protocol_args_list.append("--bam_batch_duration=3600")
            
            if not flow_cell_info.has_adapter:
                protocol_args_list.append("--pore_reserve=on")
            
            if basecall_model != "off":
                protocol_args_list.append("--base_calling=on")
                
                if flow_cell_info.has_adapter and "400bps" in basecall_model:
                    basecall_model = basecall_model.replace("400bps", "130bps")
                
                clean_model = basecall_model.replace(".cfg", "")
                if "@" not in clean_model:
                    clean_model += "@v5.2.0"
                    
                protocol_args_list.extend([
                    "--basecaller_models", f'simplex_model="{clean_model}"'
                ])
            
            from minknow_api.protocol_pb2 import ProtocolRunUserInfo, OffloadLocationInfo
            user_info = ProtocolRunUserInfo()
            user_info.sample_id.value = sample_name
            user_info.protocol_group_id.value = experiment_name
            
            offload_info = None
            if output_dir != "/data/sequencing_runs" and output_dir.strip():
                offload_info = OffloadLocationInfo(offload_location_path=output_dir)
                
            target_criteria = protocols.make_target_run_until_criteria(experiment_duration=run_duration)
            
            logging.info(f"Starting run on position {pos.name} with protocol {protocol_id}")
            
            start_req_kwargs = {
                "identifier": protocol_id,
                "args": protocol_args_list,
                "user_info": user_info,
                "target_run_until_criteria": target_criteria
            }
            if offload_info:
                start_req_kwargs["offload_location_info"] = offload_info
                
            run_response = client.protocol.start_protocol(**start_req_kwargs)
            run_id = run_response.run_id
            
            return jsonify({"success": True, "run_id": run_id, "message": "Start run command sent successfully with custom settings."})
        except Exception as inner_e:
            import traceback
            logging.error(f"Failed to start protocol on {pos.name}:\n{traceback.format_exc()}")
            return jsonify({"success": False, "message": f"Failed: {type(inner_e).__name__} - {str(inner_e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/pause", methods=["POST"])
@requires_auth
def pause_run():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400

    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, request.json)
        if err:
            return jsonify({"success": False, "message": err})
        
        client = pos.connect()
        try:
            logging.info(f"Pausing protocol on position {pos.name}")
            client.protocol.pause_protocol()
            return jsonify({"success": True, "message": f"Pause command sent successfully to {pos.name}."})
        except Exception as e:
            import traceback
            logging.error(f"Failed to pause on {pos.name}:\n{traceback.format_exc()}")
            return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/resume", methods=["POST"])
@requires_auth
def resume_run():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400

    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, request.json)
        if err:
            return jsonify({"success": False, "message": err})
        
        client = pos.connect()
        try:
            logging.info(f"Resuming protocol on position {pos.name}")
            client.protocol.resume_protocol()
            return jsonify({"success": True, "message": f"Resume command sent successfully to {pos.name}."})
        except Exception as e:
            import traceback
            logging.error(f"Failed to resume on {pos.name}:\n{traceback.format_exc()}")
            return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/stop", methods=["POST"])
@requires_auth
def stop_run():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400

    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, request.json)
        if err:
            return jsonify({"success": False, "message": err})
        
        client = pos.connect()
        try:
            logging.info(f"Stopping protocol on position {pos.name}")
            client.protocol.stop_protocol()
            return jsonify({"success": True, "message": f"Stop command sent successfully to {pos.name}. Data acquisition is halted."})
        except Exception as inner_e:
            import traceback
            logging.error(f"stop_protocol failed on {pos.name}:\n{traceback.format_exc()}")
            return jsonify({"success": False, "message": f"Failed to stop: {type(inner_e).__name__} - {str(inner_e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/flow_cell_check", methods=["POST"])
@requires_auth
def flow_cell_check():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400

    try:
        configure_minknow_certificates()
        manager = Manager(host="localhost", port=9502)
        pos, err = get_target_position(manager, request.json)
        if err:
            return jsonify({"success": False, "message": err})
        
        client = pos.connect()
        try:
            flow_cell_info = client.device.get_flow_cell_info()
            product_code = flow_cell_info.user_specified_product_code or flow_cell_info.product_code
            
            if not product_code:
                logging.warning(f"No product code found for position {pos.name}, skipping flow cell check.")
                return jsonify({"success": False, "message": "No product code found. Is a flow cell inserted?"})

            protocol_info = protocols.find_protocol(
                client,
                product_code=product_code,
                kit="",
                experiment_type="platform QC",
            )
            
            if not protocol_info:
                return jsonify({"success": False, "message": f"No QC protocol found for product {product_code}"})

            protocol_id = protocol_info if isinstance(protocol_info, str) else protocol_info.identifier

            logging.info(f"Starting flow cell check on position {pos.name} with protocol {protocol_id}")
            client.protocol.start_protocol(
                identifier=protocol_id,
                args=[]
            )
            return jsonify({"success": True, "message": f"Flow cell check command sent successfully to {pos.name}."})
        except Exception as e:
            import traceback
            logging.error(f"Failed to start flow cell check on {pos.name}:\n{traceback.format_exc()}")
            return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    # WARNING: Built-in Werkzeug development server is not recommended for production.
    # Consider using Gunicorn or Waitress with a reverse proxy for high traffic.
    logging.info("Starting secure MinKNOW dashboard on https://0.0.0.0:8443")
    app.run(host="0.0.0.0", port=8443, debug=False, ssl_context=('certs/cert.pem', 'certs/key.pem'))
