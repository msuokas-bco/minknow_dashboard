import sys
sys.path.append('minknow_api/python')
try:
    from minknow_api import protocol_pb2
    for k, v in protocol_pb2.ProtocolPhase.items():
        print(f"{k} = {v}")
except Exception as e:
    print(e)
