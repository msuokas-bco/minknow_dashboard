import grpc

# Create local channel credentials (insecure TCP for localhost)
creds = grpc.local_channel_credentials()
channel = grpc.secure_channel('localhost:9502', creds)

# Test it using reflection or just try to connect
try:
    grpc.channel_ready_future(channel).result(timeout=2)
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
