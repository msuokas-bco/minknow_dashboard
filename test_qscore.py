import logging
from minknow_api.manager import Manager
from minknow_api import statistics_pb2

manager = Manager("localhost", 9502)
positions = list(manager.flow_cell_positions())
for p in positions:
    client = p.connect()
    try:
        acq_info = client.acquisition.get_current_acquisition_run()
        if not acq_info or not acq_info.run_id:
            continue
            
        print(f"\nPosition: {p.name}")
        stream = client.statistics.stream_q_score_histogram(
            acquisition_run_id=acq_info.run_id,
            data_selection=statistics_pb2.FloatDataSelection(step=1.0)
        )
        for h in stream:
            print("Received histogram update:")
            for i, hdata in enumerate(h.histogram_data):
                total = sum(hdata.bucket_values)
                print(f"  Data group {i}: {total} total counts")
                if total > 0:
                    for br, c in zip(h.bucket_ranges, hdata.bucket_values):
                        if c > 0:
                            print(f"    Q{br.start} - Q{br.end}: {c}")
            break # Just one
    except Exception as e:
        print(e)
