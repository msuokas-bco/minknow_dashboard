import grpc
from minknow_api import manager
m = manager.Manager(host="localhost", port=9502, use_tls=True)
pos = m.flow_cell_positions()[0]
client = pos.connect()

runs = client.protocol.list_protocol_runs().run_ids
for rid in runs[-3:]:
    info = client.protocol.get_run_info(run_id=rid)
    print(f"Run: {rid}")
    print(f"State: {info.state}")
    print(f"Error: {getattr(info, 'error_message', 'No explicit error field')}")
    print(f"Args: {info.args}")
