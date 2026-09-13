import re
import os
import logging
from flask import Blueprint, render_template, jsonify, request
from .auth import requires_auth
from .minknow_client import (
    configure_minknow_certificates,
    get_minknow_manager,
    get_target_position,
    get_sequencing_data
)
from minknow_api.tools import protocols

bp = Blueprint('main', __name__)

VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'VERSION')
try:
    with open(VERSION_FILE) as f:
        APP_VERSION = f.read().strip()
except Exception:
    APP_VERSION = "unknown"

@bp.route("/")
@requires_auth
def index():
    return render_template("index.html", version=APP_VERSION)

@bp.route("/api/positions", methods=["GET"])
@requires_auth
def get_positions():
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        positions = list(manager.flow_cell_positions())
        pos_names = [pos.name if hasattr(pos, 'name') else pos.position for pos in positions]
        return jsonify({"success": True, "positions": pos_names})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@bp.route("/api/protocol_options", methods=["GET"])
@requires_auth
def get_protocol_options():
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
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

@bp.route("/api/stats")
@requires_auth
def stats():
    tab = request.args.get('tab', 'main')
    target_pos = request.args.get('position', None)
    return jsonify(get_sequencing_data(tab, target_pos))

@bp.route("/api/start", methods=["POST"])
@requires_auth
def start_run():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format. JSON required."}), 400

    try:
        data = request.json or {}
        raw_exp = data.get("experiment_name", "").strip()
        experiment_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_exp or "MinKNOW_Run")
        raw_sample = data.get("sample_name", "").strip()
        sample_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_sample or "no_sample_id")
        output_dir = data.get("output_dir", "/data/sequencing_runs")
        
        import pathlib
        resolved_path = pathlib.Path(output_dir).resolve()
        if len(resolved_path.parts) < 2 or resolved_path.parts[1] != 'data':
            logging.warning(f"Path traversal or invalid output directory blocked: {output_dir}")
            return jsonify({"success": False, "message": "Output directory must be within a /data/ folder."}), 400
        output_dir = str(resolved_path)

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
                client, product_code=product_code, kit=kit, experiment_type="sequencing"
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
                protocol_args_list.extend(["--fastq_batch_duration=3600", "--fastq_data", "compress"])
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
                protocol_args_list.extend(["--basecaller_models", f'simplex_model="{clean_model}"'])
            
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
            return jsonify({"success": True, "run_id": run_response.run_id, "message": "Start run command sent successfully with custom settings."})
        except Exception as inner_e:
            import traceback
            logging.error(f"Failed to start protocol on {pos.name}:\n{traceback.format_exc()}")
            return jsonify({"success": False, "message": f"Failed: {type(inner_e).__name__} - {str(inner_e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@bp.route("/api/pause", methods=["POST"])
@requires_auth
def pause_run():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, request.json)
        if err: return jsonify({"success": False, "message": err})
        client = pos.connect()
        try:
            logging.info(f"Pausing protocol on position {pos.name}")
            client.protocol.pause_protocol()
            return jsonify({"success": True, "message": f"Pause command sent successfully to {pos.name}."})
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@bp.route("/api/resume", methods=["POST"])
@requires_auth
def resume_run():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, request.json)
        if err: return jsonify({"success": False, "message": err})
        client = pos.connect()
        try:
            logging.info(f"Resuming protocol on position {pos.name}")
            client.protocol.resume_protocol()
            return jsonify({"success": True, "message": f"Resume command sent successfully to {pos.name}."})
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@bp.route("/api/stop", methods=["POST"])
@requires_auth
def stop_run():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, request.json)
        if err: return jsonify({"success": False, "message": err})
        client = pos.connect()
        try:
            logging.info(f"Stopping protocol on position {pos.name}")
            client.protocol.stop_protocol()
            return jsonify({"success": True, "message": f"Stop command sent successfully to {pos.name}. Data acquisition is halted."})
        except Exception as inner_e:
            return jsonify({"success": False, "message": f"Failed to stop: {type(inner_e).__name__} - {str(inner_e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@bp.route("/api/flow_cell_check", methods=["POST"])
@requires_auth
def flow_cell_check():
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format."}), 400
    try:
        configure_minknow_certificates()
        manager = get_minknow_manager()
        pos, err = get_target_position(manager, request.json)
        if err: return jsonify({"success": False, "message": err})
        client = pos.connect()
        try:
            flow_cell_info = client.device.get_flow_cell_info()
            product_code = flow_cell_info.user_specified_product_code or flow_cell_info.product_code
            if not product_code:
                return jsonify({"success": False, "message": "No product code found. Is a flow cell inserted?"})
            protocol_info = protocols.find_protocol(client, product_code=product_code, kit="", experiment_type="platform QC")
            if not protocol_info:
                return jsonify({"success": False, "message": f"No QC protocol found for product {product_code}"})
            protocol_id = protocol_info if isinstance(protocol_info, str) else protocol_info.identifier
            logging.info(f"Starting flow cell check on position {pos.name} with protocol {protocol_id}")
            client.protocol.start_protocol(identifier=protocol_id, args=[])
            return jsonify({"success": True, "message": f"Flow cell check command sent successfully to {pos.name}."})
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed: {type(e).__name__} - {str(e)}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
