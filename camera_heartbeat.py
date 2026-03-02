import time
import json
import socket
import sys

# ------------------------
# CONFIG
# ------------------------
CAMERAS = {
    "internal_cam1": {
        "host": "192.168.1.108",  # DVR IP
        "port": 554,              # RTSP default port
        "channel": 1
    },
    "internal_cam2": {
        "host": "192.168.1.108",
        "port": 554,
        "channel": 2
    },
    "external_cam": {
        "host": "192.168.1.108",
        "port": 554,
        "channel": 3
    }
}

CHECK_INTERVAL = 10  # seconds

# ------------------------
# FUNCTIONS
# ------------------------
def check_tcp(host, port, timeout=2.0):
    """Try to open a TCP socket, return True if reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def emit_status(cam_id, status):
    """Emit NDJSON line with status (to pipe into telemetry_server)."""
    packet = {
        "sensor_id": cam_id,
        "timestamp": time.time(),
        "type": "camera",
        "status": status,  # "online" or "offline"
        "units": {"status": "string"}
    }
    sys.stdout.write(json.dumps(packet) + "\n")
    sys.stdout.flush()

# ------------------------
# MAIN LOOP
# ------------------------
def main():
    while True:
        for cam_id, cfg in CAMERAS.items():
            ok = check_tcp(cfg["host"], cfg["port"])
            emit_status(cam_id, "online" if ok else "offline")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
