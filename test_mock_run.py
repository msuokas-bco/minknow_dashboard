import sys
import logging
from unittest.mock import patch

# Mock the authentication to bypass it completely for testing
def dummy_requires_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated

# Patch before importing routes
import core.auth
core.auth.requires_auth = dummy_requires_auth

from core import create_app
from core.routes import bp
import core.routes

# We want to mock get_sequencing_data to return a fake barcoded dataset
def fake_get_sequencing_data(active_tab='main', target_pos=None):
    import time
    
    # Generate some fake barcode data
    fake_barcodes = []
    for i in range(1, 25):
        # Let's say barcodes 1-5 are prominent, others are low/zero
        reads = 0
        if i <= 5:
            reads = 50000 - (i * 5000)
        elif i % 3 == 0:
            reads = 1500
            
        if reads > 0:
            fake_barcodes.append({
                "barcode": f"barcode{i:02d}",
                "reads": reads
            })
            
    return {
        "status": "Connected (MOCK DATA)",
        "active": True,
        "position": target_pos or "MN12345",
        "flow_cell_id": "FAK00001",
        "run_id": "mock_run_999",
        "state": "Running",
        "experiment": "Mock_Multiplex_Test",
        "sample": "Pooled_Samples",
        "kit": "SQK-NBD114.24",
        "barcoding": True,
        "model": "dna_r10.4.1_e8.2_400bps_hac.cfg",
        "pores": {"sequencing": 1200, "available": 400, "inactive": 50},
        "yield": {"bases": 1500000000, "reads": 450000},
        "read_length": {
            "n50": 4500, 
            "histogram": [
                {"start": 1000, "end": 2000, "count": 50000},
                {"start": 2000, "end": 3000, "count": 150000},
                {"start": 3000, "end": 4000, "count": 100000},
                {"start": 4000, "end": 5000, "count": 60000},
                {"start": 5000, "end": 6000, "count": 30000},
                {"start": 6000, "end": 7000, "count": 10000},
            ]
        },
        "qscore": {
            "histogram": [
                {"start": 8, "end": 9, "count": 5000},
                {"start": 9, "end": 10, "count": 10000},
                {"start": 10, "end": 11, "count": 25000},
                {"start": 11, "end": 12, "count": 80000},
                {"start": 12, "end": 13, "count": 120000},
                {"start": 13, "end": 14, "count": 150000},
                {"start": 14, "end": 15, "count": 80000},
                {"start": 15, "end": 16, "count": 20000},
            ]
        },
        "min_qscore": 10.0,
        "temperature": 34.5,
        "gpu": {"temp": "55", "usage": "85"},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pore_scans": [
            {"time": "Start", "sequencing": 1400, "available": 100, "inactive": 10},
            {"time": "1h 30m", "sequencing": 1300, "available": 150, "inactive": 20},
            {"time": "3h 0m", "sequencing": 1200, "available": 200, "inactive": 30},
        ],
        "barcodes": fake_barcodes,
        "barcodes_unavailable": False
    }

# Mock get_positions
def fake_get_positions():
    return ["MN12345"]

# Apply patches
patch('core.routes.get_sequencing_data', side_effect=fake_get_sequencing_data).start()
patch('core.routes.get_positions', return_value={"success": True, "positions": ["MN12345"]}).start()

# For the get_positions route specifically, since it queries get_minknow_manager directly
class MockManager:
    def flow_cell_positions(self):
        class MockPos:
            name = "MN12345"
        return [MockPos()]

patch('core.routes.get_minknow_manager', return_value=MockManager()).start()

app = create_app()

if __name__ == "__main__":
    print("\n" + "="*60)
    print(" MinKNOW Dashboard - SIMULATED MODE")
    print(" Test the UI at http://localhost:5001")
    print("="*60 + "\n")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)

