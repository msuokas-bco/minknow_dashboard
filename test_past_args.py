import sys
import grpc
from minknow_api import manager
m = manager.Manager(host="localhost", port=9502, use_tls=True)
pos = m.flow_cell_positions()[0]
client = pos.connect()

runs = client.protocol.list_protocol_runs().run_ids
for rid in runs:
    if "8148d8ab" in rid:
        info = client.protocol.get_run_info(run_id=rid)
        print("FOUND RUN!")
        print("ARGS:")
        for arg in info.args:
            print(arg)
        sys.exit(0)
print("Run not found")
