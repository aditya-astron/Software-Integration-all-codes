import sys
import json
import csv
import os
from datetime import datetime

LOG_FILE = "telemetry_log.csv"
MAX_LINES = 100000  # ~48h buffer at 1Hz (tune as needed)

def init_log():
    """Initialize CSV file with headers if not present."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "sensor_id", "data"])  # generic schema

def log_packet(packet: dict):
    """Append telemetry packet to CSV file."""
    with open(LOG_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([packet.get("timestamp"), packet.get("sensor_id"), json.dumps(packet)])

def rotate_log():
    """Prevent unlimited file growth by keeping a rolling buffer."""
    with open(LOG_FILE, "r") as f:
        lines = f.readlines()
    if len(lines) > MAX_LINES:
        with open(LOG_FILE, "w") as f:
            f.writelines(lines[-MAX_LINES:])  # keep last N lines

def run_logger():
    """Read JSON packets from stdin, log them, and pass them forward."""
    init_log()
    for line in sys.stdin:
        try:
            packet = json.loads(line.strip())
            log_packet(packet)
            rotate_log()
            # Send status to stderr
            print(f"[LOGGER] Logged packet from {packet.get('sensor_id')} at {datetime.now()}", file=sys.stderr)
            # Forward JSON packet downstream
            sys.stdout.write(json.dumps(packet) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            print("[LOGGER] Invalid JSON packet, skipping...", file=sys.stderr)

if __name__ == "__main__":
    run_logger()
