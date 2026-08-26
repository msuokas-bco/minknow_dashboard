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
import random
import logging
import json
import grpc
from functools import wraps
from flask import Flask, render_template, jsonify, request, Response
from minknow_api.manager import Manager
from minknow_api.tools import protocols

# Configure basic logging for debugging and security auditing
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_minknow_credentials():
    """Manually hunt for the MinKNOW CA certificate since minknow_api 5.9.1 removed some default paths."""
    cert_paths = [
        "/data/rpc-certs/minknow/ca.crt",
        "/opt/minknow/conf/rpc-certs/ca.crt", 
        "/var/lib/minknow/data/rpc-certs/minknow/ca.crt", 
        "/opt/minknow/conf/certs-bundle.crt"
    ]
    
    errors = []
    for cert_path in cert_paths:
        try:
            with open(cert_path, "rb") as f:
                import minknow_api
                return minknow_api.grpc_credentials(ca_certificate=f.read())
        except PermissionError as e:
            raise Exception(f"Permission denied reading {cert_path}! Run: sudo chmod 644 {cert_path}")
        except FileNotFoundError:
            errors.append(cert_path)
        except Exception as e:
            raise Exception(f"Failed reading {cert_path}: {e}")
            
    raise Exception(f"Could not find ca.crt in: {errors}")

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
            
    return os.environ.get('MINKNOW_ADMIN_USER', 'admin'), os.environ.get('MINKNOW_ADMIN_PASS', 'SecureMinknow!2026')

def check_auth(username, password):
    """
    Checks if a username / password combination is valid.
    SECURITY: Fetches credentials from config.json, environment variables, or defaults.
    """
    valid_user, valid_pass = get_credentials()
    return username == valid_user and password == valid_pass

def get_failed_attempts():
    lockout_file = '/etc/minknow-dashboard/lockout.json'
    if os.path.exists(lockout_file):
        try:
            with open(lockout_file, 'r') as f:
                data = json.load(f)
                return data.get('failed_attempts', 0)
        except Exception:
            return 0
    return 0

def set_failed_attempts(count):
    lockout_file = '/etc/minknow-dashboard/lockout.json'
    try:
        with open(lockout_file, 'w') as f:
            json.dump({'failed_attempts': count}, f)
        # Ensure correct permissions if running as root
        if os.geteuid() == 0:
            os.chmod(lockout_file, 0o666)
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
        attempts = get_failed_attempts()
        MAX_ATTEMPTS = 5
        
        if attempts >= MAX_ATTEMPTS:
            logging.warning(f"Blocked request from {request.remote_addr}: Account locked")
            return Response(
                '<h2>Account Locked</h2><p>Account locked due to too many failed login attempts.</p><p>Please contact the administrator to reset access.</p>',
                403)
                
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            set_failed_attempts(attempts + 1)
            logging.warning(f"Failed authentication attempt from {request.remote_addr}. Attempt {attempts + 1} of {MAX_ATTEMPTS}")
            return authenticate()
            
        if attempts > 0:
            set_failed_attempts(0)
            
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

def get_sequencing_data(active_tab='main'):
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
        "temperature": 0.0,
        "gpu": get_gpu_stats(),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        manager = Manager(host="localhost", port=9502, credentials=get_minknow_credentials())
        positions = list(manager.flow_cell_positions())
        
        if not positions:
            data["status"] = "No positions found"
            return data

        pos = positions[0]
        data["position"] = pos.name if hasattr(pos, 'name') else pos.position
        
        try:
            client = pos.connect()
            data["status"] = "Connected"
            data["active"] = True
        except Exception as e:
            data["status"] = f"Failed to connect to position: {e}"
            return data
        
        # Fetch flow cell ID
        try:
            fc_info = client.device.get_flow_cell_info()
            data["flow_cell_id"] = getattr(fc_info, 'user_specified_flow_cell_id', None) or getattr(fc_info, 'flow_cell_id', '--')
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
            
            # ProtocolState mapping from protobuf:
            # 0=PROTOCOL_RUNNING, 1=PROTOCOL_COMPLETED, 2=PROTOCOL_STOPPED_BY_USER, 3=PROTOCOL_FINISHED_WITH_ERROR, 
            # 4=PROTOCOL_WAITING_FOR_TEMPERATURE, 5=PROTOCOL_WAITING_FOR_ACQUISITION, 10=PROTOCOL_WAITING_FOR_RESOURCE
            state_val = str(getattr(run_info, 'state', 'Unknown'))
            if 'PROTOCOL_RUNNING' in state_val or state_val == '0':
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

        # Fallback for acquisition run id
        if not acquisition_run_id:
            try:
                if hasattr(client.acquisition, 'get_current_acquisition_run'):
                    acq_info = client.acquisition.get_current_acquisition_run()
                    acquisition_run_id = getattr(acq_info, 'run_id', None)
                elif hasattr(client.acquisition, 'current_acquisition_run'):
                    acq_info = client.acquisition.current_acquisition_run()
                    acquisition_run_id = getattr(acq_info, 'run_id', None)
            except Exception as e:
                logging.debug(f"Failed to get current_acquisition_run: {e}")
                data["state"] = f"ACQ_ERR: {type(e).__name__}"

        # Fetch yield statistics
        acquire_info = None
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
                            if name in ['strand', 'adapter', 'pore', 'good', 'sequencing']:
                                state_counts["sequencing"] += 1
                            elif name in ['single_pore', 'available', 'good_single']:
                                state_counts["available"] += 1
                            elif name:  # If it has any other state
                                state_counts["inactive"] += 1
                        break # Only need the first snapshot
                    
                data["pores"]["sequencing"] = state_counts["sequencing"]
                data["pores"]["available"] = state_counts["available"]
                data["pores"]["inactive"] = state_counts["inactive"]
            except Exception as e:
                logging.debug(f"Failed to fetch pore states: {e}")
                data["debug_pores"] = f"{type(e).__name__} {str(e)}"

            try:
                if acquire_info and hasattr(acquire_info, 'bream_info'):
                    bream_info = acquire_info.bream_info
                    start_ts = getattr(acquire_info.start_time, 'seconds', 0) if hasattr(acquire_info, 'start_time') else 0
                    
                    if hasattr(bream_info, 'mux_scan_results'):
                        for idx, msr in enumerate(bream_info.mux_scan_results):
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
                data["debug_pores"] = (data.get("debug_pores") or "") + f" | MUX ERR: {type(e).__name__} {str(e)}"

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
            
            try:
                hist_stream = client.statistics.stream_read_length_histogram(acquisition_run_id=acquisition_run_id)
                for h in hist_stream:
                    if hasattr(h, 'bucket_ranges') and hasattr(h, 'histogram_data') and len(h.histogram_data) > 0:
                        bucket_values = h.histogram_data[0].bucket_values
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

    except Exception as e:
        logging.error(f"Error fetching sequencing data: {e}")
        data["status"] = f"Error: {str(e)}"
        
    return data

@app.route("/")
@requires_auth
def index():
    return render_template("index.html")

@app.route("/api/stats")
@requires_auth
def stats():
    tab = request.args.get('tab', 'main')
    return jsonify(get_sequencing_data(tab))

@app.route("/api/start", methods=["POST"])
@requires_auth
def start_run():
    """
    Starts a new sequencing run. 
    SECURITY: Enforces JSON content-type to prevent CSRF, and sanitizes input paths.
    """
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format. JSON required."}), 400

    try:
        data = request.json or {}
        
        # Sanitize names to alphanumeric, dashes, and underscores to prevent injection
        raw_exp = data.get("experiment_name", "custom_experiment")
        experiment_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_exp)
        
        raw_sample = data.get("sample_name", "pooled_sample")
        sample_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_sample)
        
        # Validate output directory to prevent directory traversal attacks
        output_dir = data.get("output_dir", "/data/sequencing_runs")
        if '..' in output_dir:
            logging.warning(f"Directory traversal attempt blocked: {output_dir}")
            return jsonify({"success": False, "message": "Invalid output directory."}), 400

        basecall_model = data.get("basecall_model", "dna_r10.4.1_e8.2_400bps_hac.cfg")
        save_pod5 = data.get("save_pod5", True)
        save_fastq = data.get("save_fastq", True)
        kit = data.get("lib_kit", "SQK-LSK114")
        
        manager = Manager(host="localhost", port=9502, credentials=get_minknow_credentials())
        positions = list(manager.flow_cell_positions())
        if not positions:
            return jsonify({"success": False, "message": "No positions found."})
        
        for pos in positions:
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
                
                # Build arguments for MinKNOW 5.x+
                kwargs = {}
                if basecall_model != "off":
                    kwargs["basecalling"] = protocols.BasecallingArgs(
                        simplex_model=basecall_model, modified_models=None, stereo_model=None, 
                        barcoding=None, alignment=None, min_qscore=7
                    )
                
                out_args = protocols.OutputArgs(reads_per_file=4000, batch_duration=None)
                if save_pod5:
                    kwargs["pod5_arguments"] = out_args
                if save_fastq:
                    kwargs["fastq_arguments"] = out_args
                kwargs["fast5_arguments"] = None
                
                logging.info(f"Starting run on position {pos.name} with protocol {protocol_id}")
                
                protocols.start_protocol(
                    client,
                    identifier=protocol_id,
                    sample_id=sample_name,
                    experiment_group=experiment_name,
                    barcode_info=None,
                    **kwargs
                )
            except Exception as inner_e:
                import traceback
                logging.error(f"Failed to start protocol on {pos.name}:\n{traceback.format_exc()}")
                return jsonify({"success": False, "message": f"Failed: {type(inner_e).__name__} - {str(inner_e)}"})
        return jsonify({"success": True, "message": "Start run command sent successfully with custom settings."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/pause", methods=["POST"])
@requires_auth
def pause_run():
    """Pauses the current active sequencing run."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400

    try:
        manager = Manager(host="localhost", port=9502, credentials=get_minknow_credentials())
        positions = list(manager.flow_cell_positions())
        if not positions:
            return jsonify({"success": False, "message": "No positions found."})
        
        for pos in positions:
            client = pos.connect()
            try:
                logging.info(f"Pausing acquisition on position {pos.name}")
                client.acquisition.pause_acquisition()
            except Exception as e:
                import traceback
                logging.error(f"Failed to pause on {pos.name}:\n{traceback.format_exc()}")
                return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
        return jsonify({"success": True, "message": "Pause command sent successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/stop", methods=["POST"])
@requires_auth
def stop_run():
    """Aborts the current active sequencing run."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400

    try:
        manager = Manager(host="localhost", port=9502, credentials=get_minknow_credentials())
        positions = list(manager.flow_cell_positions())
        if not positions:
            return jsonify({"success": False, "message": "No positions found."})
        
        for pos in positions:
            client = pos.connect()
            try:
                # Stop acquisition to let basecalling finish naturally
                client.acquisition.stop_acquisition()
            except Exception as e:
                import traceback
                logging.error(f"stop_acquisition failed on {pos.name}:\n{traceback.format_exc()}")
                try:
                    logging.debug(f"stop_acquisition failed on {pos.name}, falling back to stop_protocol: {e}")
                    client.protocol.stop_protocol()
                except Exception as inner_e:
                    return jsonify({"success": False, "message": f"Failed to stop: {type(inner_e).__name__} - {str(inner_e)}"})
                    
        return jsonify({"success": True, "message": "Stop command sent successfully. Basecalling will finish naturally."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/flow_cell_check", methods=["POST"])
@requires_auth
def flow_cell_check():
    """Starts a flow cell check (platform QC) protocol."""
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400

    try:
        manager = Manager(host="localhost", port=9502, credentials=get_minknow_credentials())
        positions = list(manager.flow_cell_positions())
        if not positions:
            return jsonify({"success": False, "message": "No positions found."})
        
        for pos in positions:
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

                # In minknow-api 5.x, find_protocol returns a string identifier directly.
                protocol_id = protocol_info if isinstance(protocol_info, str) else protocol_info.identifier

                logging.info(f"Starting flow cell check on position {pos.name} with protocol {protocol_id}")
                client.protocol.start_protocol(
                    identifier=protocol_id,
                    args=[]
                )
            except Exception as e:
                import traceback
                logging.error(f"Failed to start flow cell check on {pos.name}:\n{traceback.format_exc()}")
                return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
                
        return jsonify({"success": True, "message": "Flow cell check command sent successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    # WARNING: Built-in Werkzeug development server is not recommended for production.
    # Consider using Gunicorn or Waitress with a reverse proxy for high traffic.
    logging.info("Starting secure MinKNOW dashboard on https://0.0.0.0:8443")
    app.run(host="0.0.0.0", port=8443, debug=False, ssl_context=('certs/cert.pem', 'certs/key.pem'))

