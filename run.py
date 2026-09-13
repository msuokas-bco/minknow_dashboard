import sys
import subprocess
import shutil
import logging
from core import create_app

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = create_app()

if __name__ == "__main__":
    print("\n" + "="*60)
    print(" MinKNOW Dashboard")
    print("="*60 + "\n")

    if sys.platform == "win32":
        app.run(host="0.0.0.0", port=8443, debug=False, threaded=True, ssl_context=('certs/cert.pem', 'certs/key.pem'))
    elif shutil.which("gunicorn"):
        cmd = [
            "gunicorn",
            "--certfile=certs/cert.pem",
            "--keyfile=certs/key.pem",
            "--bind", "0.0.0.0:8443",
            "--worker-class", "gthread",
            "--threads", "10",
            "run:app"
        ]
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            pass
    else:
        app.run(host="0.0.0.0", port=8443, debug=False, threaded=True, ssl_context=('certs/cert.pem', 'certs/key.pem'))
