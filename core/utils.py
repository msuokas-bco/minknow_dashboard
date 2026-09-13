import subprocess
import logging

def get_gpu_stats():
    try:
        # Use full path for nvidia-smi just in case it's missing from service PATH
        result = subprocess.run(['/usr/bin/nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu', '--format=csv,noheader,nounits'], stdout=subprocess.PIPE, timeout=2)
        if result.returncode == 0:
            lines = result.stdout.decode('utf-8').strip().split('\n')
            if lines:
                parts = lines[0].split(',')
                if len(parts) >= 2:
                    return {"temp": parts[0].strip(), "usage": parts[1].strip()}
    except Exception as e:
        logging.debug(f"GPU stats failed: {e}")
    return {"temp": "--", "usage": "--"}
