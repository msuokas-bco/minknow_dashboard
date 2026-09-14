import os
import json
import time
import logging
import grpc
from minknow_api.manager import Manager
from minknow_api.tools import protocols
from minknow_api import statistics_pb2
from .utils import get_gpu_stats

MINKNOW_HOST = os.environ.get("MINKNOW_HOST", "localhost")
MINKNOW_PORT = int(os.environ.get("MINKNOW_PORT", 9502))

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'state')

def configure_minknow_certificates():
    """Finds the MinKNOW CA certificate and sets the environment variable so the PyPI library handles auth correctly."""
    cert_paths = [
        "/data/rpc-certs/minknow/ca.crt",
        "/opt/minknow/conf/rpc-certs/ca.crt", 
        "/var/lib/minknow/data/rpc-certs/minknow/ca.crt", 
        "/opt/minknow/conf/certs-bundle.crt",
        r"C:\data\rpc-certs\minknow\ca.crt",
        r"C:\ProgramData\MinKNOW\data\rpc-certs\minknow\ca.crt"
    ]
    
    for cert_path in cert_paths:
        if os.path.exists(cert_path):
            os.environ["MINKNOW_TRUSTED_CA"] = cert_path
            return
            
    logging.warning(f"CRITICAL: Could not find ca.crt in any of {cert_paths}. Is MinKNOW installed?")

def get_minknow_manager():
    """
    Creates a Manager instance using secure channels.
    """
    return Manager(host=MINKNOW_HOST, port=MINKNOW_PORT)

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
                os.makedirs(STATE_DIR, exist_ok=True)
                db_path = os.path.join(STATE_DIR, 'cache.db')
                
                fc_cache = {"id": None, "pores": None, "time": 0}
                import sqlite3
                try:
                    with sqlite3.connect(db_path, timeout=15.0) as conn:
                        conn.execute("CREATE TABLE IF NOT EXISTS fc_cache (id TEXT PRIMARY KEY, pores INTEGER, time REAL)")
                        cur = conn.cursor()
                        cur.execute("SELECT pores, time FROM fc_cache WHERE id=?", (real_fc_id,))
                        row = cur.fetchone()
                        if row:
                            fc_cache["id"] = real_fc_id
                            fc_cache["pores"] = row[0]
                            fc_cache["time"] = row[1]
                except Exception:
                    pass
                    
                now = time.time()
                if fc_cache.get("id") != real_fc_id or (now - fc_cache.get("time", 0) > 15):
                    fc_cache["id"] = real_fc_id
                    fc_cache["pores"] = None
                    fc_cache["time"] = now
                    try:
                        runs_resp = client.protocol.list_protocol_runs(_timeout=2.0)
                        run_ids = list(getattr(runs_resp, 'run_ids', runs_resp))
                        
                        if not run_ids:
                            fc_cache["pores"] = None
                        else:
                            first_run = client.protocol.get_run_info(run_id=run_ids[0], _timeout=2.0)
                            last_run = client.protocol.get_run_info(run_id=run_ids[-1], _timeout=2.0)
                            
                            if getattr(first_run.start_time, 'seconds', 0) > getattr(last_run.start_time, 'seconds', 0):
                                search_ids = run_ids[:50]
                            else:
                                search_ids = reversed(run_ids[-50:])
                                
                            for run_id in search_ids:
                                try:
                                    r = client.protocol.get_run_info(run_id=run_id, _timeout=2.0)
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
                        with sqlite3.connect(db_path, timeout=15.0) as conn:
                            conn.execute("INSERT OR REPLACE INTO fc_cache (id, pores, time) VALUES (?, ?, ?)", 
                                         (fc_cache["id"], fc_cache["pores"], fc_cache["time"]))
                    except Exception as e:
                        logging.debug(f"Failed to save fc_cache: {e}")
                        
                data["last_fc_check_pores"] = fc_cache.get("pores")
                    
        except Exception as e:
            logging.debug(f"Failed to fetch flow cell ID: {e}")
            data["flow_cell_id"] = '--'

        # Fetch run metadata
        acquisition_run_id = None
        try:
            run_info = client.protocol.get_run_info(_timeout=2.0)
                
            try:
                data["run_id"] = run_info.run_id
            except Exception:
                data["run_id"] = getattr(run_info, 'protocol_run_id', '--')
            
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
                for i, arg in enumerate(args_list):
                    if "base_calling=on" in arg or "basecalling=on" in arg:
                        bc_on = True
                    if "simplex_model=" in arg:
                        import re
                        m = re.search(r'simplex_model="([^"]+)"', arg)
                        if m: data["model"] = m.group(1)
                    if arg.startswith("--min_qscore="):
                        data["min_qscore"] = float(arg.split("=")[1])
                    elif arg == "--min_qscore" and i + 1 < len(args_list):
                        try:
                            data["min_qscore"] = float(args_list[i+1])
                        except ValueError:
                            pass
                    elif "min_qscore=" in arg:
                        import re
                        m = re.search(r'min_qscore=([\d\.]+)', arg)
                        if m: data["min_qscore"] = float(m.group(1))
            
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
            elif state_val == '1': data["state"] = "Completed"
            elif state_val == '2': data["state"] = "Stopped by User"
            elif state_val == '3': data["state"] = "Finished with Error"
            elif state_val == '4': data["state"] = "Waiting for Temperature"
            elif state_val == '5': data["state"] = "Waiting for Acquisition"
            elif state_val == '10': data["state"] = "Waiting for Resource"
            else: data["state"] = f"Code {state_val}"
                
            if hasattr(run_info, 'acquisition_run_ids') and len(run_info.acquisition_run_ids) > 0:
                acquisition_run_id = run_info.acquisition_run_ids[-1]
        except Exception as e:
            logging.debug(f"Failed to fetch protocol run info: {e}")
            data["state"] = f"ERR: {type(e).__name__} {str(e)}"

        is_new_protocol_warming_up = data["state"] in ("Waiting for Temperature", "Waiting for Acquisition", "Waiting for Resource") or (data["state"] == "Running" and not acquisition_run_id)
        
        if is_new_protocol_warming_up:
            acquisition_run_id = None
        elif not acquisition_run_id:
            try:
                if hasattr(client.acquisition, 'get_current_acquisition_run'):
                    acq_info = client.acquisition.get_current_acquisition_run(_timeout=2.0)
                    acquisition_run_id = getattr(acq_info, 'run_id', None)
                elif hasattr(client.acquisition, 'current_acquisition_run'):
                    acq_info = client.acquisition.current_acquisition_run(_timeout=2.0)
                    acquisition_run_id = getattr(acq_info, 'run_id', None)
            except Exception as e:
                logging.debug(f"Failed to get current_acquisition_run: {e}")

        acquire_info = None
        if acquisition_run_id:
            try:
                acquire_info = client.acquisition.get_acquisition_info(_timeout=2.0)
                ys = getattr(acquire_info, 'yield_summary', acquire_info)
                data["yield"]["reads"] = getattr(ys, 'read_count', getattr(ys, 'reads', 0))
                data["yield"]["bases"] = getattr(ys, 'estimated_selected_bases', getattr(ys, 'bases', 0))
            except Exception as e:
                logging.debug(f"Failed to fetch yield: {e}")

        try:
            temp_res = client.device.get_temperature(_timeout=2.0)
            if temp_res.HasField('minion'): data["temperature"] = temp_res.minion.heatsink_temperature.value
            elif temp_res.HasField('promethion'): data["temperature"] = temp_res.promethion.chamber_temperature.value
            elif temp_res.HasField('pebble'): data["temperature"] = temp_res.pebble.instrument_temperature.value
        except Exception as e:
            logging.debug(f"Failed to fetch temperature: {e}")

        data["pore_scans"] = []
        if active_tab in ['main', 'pore-state']:
            try:
                state_counts = {"sequencing": 0, "available": 0, "inactive": 0}
                if hasattr(client, 'data') and hasattr(client.data, 'get_channel_states'):
                    max_channels = 512
                    try:
                        layout = client.device.get_channels_layout(_timeout=2.0)
                        max_channels = getattr(layout, 'channel_count', 512)
                    except Exception:
                        pass
                        
                    state_stream = client.data.get_channel_states(first_channel=1, last_channel=max_channels, _timeout=2.0)
                    for state_msg in state_stream:
                        for ch_data in state_msg.channel_states:
                            name = str(getattr(ch_data, 'state_name', getattr(ch_data, 'state', ''))).lower()
                            if name in ['strand', 'adapter', 'sequencing']:
                                state_counts["sequencing"] += 1
                            elif name in ['single_pore', 'available', 'good_single', 'pore', 'good']:
                                state_counts["available"] += 1
                            elif name:  
                                state_counts["inactive"] += 1
                        break 
                    
                data["pores"]["sequencing"] = state_counts["sequencing"]
                data["pores"]["available"] = state_counts["available"]
                data["pores"]["inactive"] = state_counts["inactive"]
            except Exception as e:
                logging.debug(f"Failed to fetch pore states: {e}")

            try:
                if acquire_info and hasattr(acquire_info, 'bream_info'):
                    bream_info = acquire_info.bream_info
                    if hasattr(bream_info, 'mux_scan_results'):
                        for msr in bream_info.mux_scan_results:
                            ts = getattr(msr.mux_scan_timestamp, 'seconds', getattr(msr, 'mux_scan_timestamp', 0))
                            diff = max(0, ts)
                            time_lbl = f"{int(diff // 3600)}h {int((diff % 3600) // 60)}m"
                            if diff == 0: time_lbl = "Start"
                            counts = dict(getattr(msr, 'counts', {}))
                            avail = counts.get('pore', counts.get('good_single', counts.get('single', counts.get('single_pore', 0))))
                            total = sum(counts.values())
                            inact = total - avail
                            data["pore_scans"].append({
                                "time": time_lbl, "sequencing": 0, "available": avail, "inactive": inact
                            })
            except Exception as e:
                logging.debug(f"Failed to parse mux scans: {e}")

        if active_tab in ['main', 'read-length'] and acquisition_run_id:
            try:
                n50_res = client.statistics.read_length_n50(acquisition_run_id=acquisition_run_id, _timeout=2.0)
                if hasattr(n50_res, 'n50_data'):
                    data["read_length"]["n50"] = getattr(n50_res.n50_data, 'estimated_n50', getattr(n50_res.n50_data, 'basecalled_n50', 0))
                else:
                    data["read_length"]["n50"] = getattr(n50_res, 'estimated_n50', getattr(n50_res, 'basecalled_n50', 0))
            except Exception as e:
                logging.debug(f"Failed to fetch read length n50: {e}")
                data["read_length"]["unavailable"] = True
            
            try:
                n50_val = data["read_length"].get("n50", 0)
                if 0 < n50_val < 3000: step_val = 100
                elif 3000 <= n50_val < 15000: step_val = 500
                else: step_val = 1000
                    
                try:
                    end_val = max(5000, int(n50_val * 4))
                    hist_stream = client.statistics.stream_read_length_histogram(
                        acquisition_run_id=acquisition_run_id,
                        data_selection=statistics_pb2.DataSelection(start=0, step=step_val, end=end_val),
                        _timeout=2.0
                    )
                except Exception as bin_err:
                    logging.error(f"Failed to set custom bin step {step_val}: {bin_err}")
                    hist_stream = client.statistics.stream_read_length_histogram(
                        acquisition_run_id=acquisition_run_id, _timeout=2.0
                    )
                    
                for h in hist_stream:
                    if hasattr(h, 'bucket_ranges') and hasattr(h, 'histogram_data') and len(h.histogram_data) > 0:
                        bucket_values = [0] * len(h.bucket_ranges)
                        for hdata in h.histogram_data:
                            for i, count in enumerate(hdata.bucket_values):
                                bucket_values[i] += count
                        histogram = []
                        for br, count in zip(h.bucket_ranges, bucket_values):
                            histogram.append({"start": br.start, "end": br.end, "count": count})
                        data["read_length"]["histogram"] = histogram
                        
                        if data["read_length"]["n50"] == 0 and sum(b['count'] for b in histogram) > 0:
                            total_len = sum((b['start'] + b['end']) / 2 * b['count'] for b in histogram)
                            cumulative = 0
                            for b in sorted(histogram, key=lambda x: -x['start']):
                                L = (b['start'] + b['end']) / 2
                                cumulative += L * b['count']
                                if cumulative >= total_len / 2:
                                    data["read_length"]["n50"] = L
                                    break
                    break
            except Exception as e:
                logging.debug(f"Failed to fetch read length histogram: {e}")
                data["read_length"]["unavailable"] = True

        if active_tab in ['main', 'qscore'] and acquisition_run_id:
            data["qscore"] = {"histogram": []}
            try:
                hist_stream = client.statistics.stream_q_score_histogram(
                    acquisition_run_id=acquisition_run_id,
                    data_selection=statistics_pb2.FloatDataSelection(step=1.0),
                    _timeout=2.0
                )
                for h in hist_stream:
                    if hasattr(h, 'bucket_ranges') and hasattr(h, 'histogram_data') and len(h.histogram_data) > 0:
                        bucket_values = [0] * len(h.bucket_ranges)
                        for hdata in h.histogram_data:
                            for i, count in enumerate(hdata.bucket_values):
                                bucket_values[i] += count
                        histogram = []
                        for br, count in zip(h.bucket_ranges, bucket_values):
                            histogram.append({"start": br.start, "end": br.end, "count": count})
                        data["qscore"]["histogram"] = histogram
                    break
            except Exception as e:
                logging.debug(f"Failed to fetch qscore histogram: {e}")
                data["qscore"]["unavailable"] = True

        if active_tab in ['main', 'barcodes'] and acquisition_run_id and data.get("kit") and ("NBD" in data["kit"] or "RBK" in data["kit"]):
            data["barcodes"] = []
            try:
                split_req = statistics_pb2.AcquisitionOutputSplit(barcode_name=True)
                stream = client.statistics.stream_acquisition_output(
                    acquisition_run_id=acquisition_run_id,
                    split=split_req,
                    _timeout=2.0
                )
                for response in stream:
                    for group in getattr(response, 'snapshots', []):
                        barcode_name = None
                        for key in getattr(group, 'filtering', []):
                            if getattr(key, 'barcode_name', None):
                                barcode_name = key.barcode_name
                        if barcode_name and barcode_name not in ["classified", "unclassified"]:
                            if getattr(group, 'snapshots', []):
                                latest = group.snapshots[-1]
                                ys = getattr(latest, 'yield_summary', None)
                                if ys:
                                    reads = getattr(ys, 'read_count', getattr(ys, 'reads', 0))
                                    if reads > 0:
                                        data["barcodes"].append({
                                            "barcode": barcode_name,
                                            "reads": reads
                                        })
                    break
                data["barcodes"] = sorted(data["barcodes"], key=lambda x: x["barcode"])
            except Exception as e:
                logging.debug(f"Failed to fetch barcode statistics: {e}")
                data["barcodes_unavailable"] = True

    except Exception as e:
        logging.error(f"Error fetching sequencing data: {e}")
        data["status"] = f"Error: {str(e)}"
        
    return data
