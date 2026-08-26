    import os
    import grpc
    from minknow_api.manager import Manager
    
    # Common places MinKNOW hides its certificates on Linux
    cert_paths = [
        "/opt/minknow/conf/rpc-certs/ca.crt", 
        "/var/lib/minknow/data/rpc-certs/minknow/ca.crt", 
        "/data/rpc-certs/minknow/ca.crt",
        "/opt/minknow/conf/certs-bundle.crt"
    ]
    
    for cert_path in cert_paths:
        if not os.path.exists(cert_path):
            continue
            
        print(f"Testing {cert_path}...")
        try:
            # Read the cert manually and force gRPC to use it
            with open(cert_path, "rb") as f:
                creds = grpc.ssl_channel_credentials(root_certificates=f.read())
                
            manager = Manager(host="localhost", port=9502, credentials=creds)
            # If it can successfully retrieve positions, the handshake passed!
            positions = list(manager.flow_cell_positions())
            print(f"SUCCESS! The correct certificate is: {cert_path}")
            break
        except Exception as e:
            # If it fails, print a short version of the error
            err = str(e).split("details = ")[-1].split("\n")[0] if "details =" in str(e) else str(e)
            print(f"  FAILED: {err}")
