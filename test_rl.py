import logging
from minknow_api.manager import Manager
from minknow_api import statistics_pb2

manager = Manager("localhost", 9502)
positions = list(manager.flow_cell_positions())
for p in positions:
    client = p.connect()
    try:
        acq = client.acquisition.get_current_acquisition_run()
        if not acq or not acq.run_id: continue
        
        # Check if we can pass a step size
        stream = client.statistics.stream_read_length_histogram(
            acquisition_run_id=acq.run_id,
            # Let's try passing data_selection like we did for Q-score
            data_selection=statistics_pb2.FloatDataSelection(step=500.0) 
        )
        for h in stream:
            print(f"Bucket 0: {h.bucket_ranges[0]}")
            break
    except Exception as e:
        print(f"Error: {e}")
