import sys
import json
import time
import os
from influxdb_client import InfluxDBClient, Point, WriteOptions

# -----------------------
# InfluxDB Config (from environment or defaults)
# -----------------------
INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-secret-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "essie_org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "essie_telemetry")

# -----------------------
# Init Client
# -----------------------
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=100, flush_interval=1000))

def write_packet(packet: dict):
    try:
        sensor_id = packet.get("sensor_id", "unknown")
        ts = int(packet.get("timestamp", time.time()) * 1e9)  # Influx expects ns timestamps

        # Build point
        point = Point("telemetry") \
            .tag("sensor_id", sensor_id) \
            .time(ts)

        # Add all numeric/text fields except reserved keys
        for k, v in packet.items():
            if k not in ("sensor_id", "timestamp", "units") and v is not None:
                point.field(k, v)

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

    except Exception as e:
        print(f"[DB] Failed to write packet: {e}", file=sys.stderr)

def run_db_writer():
    for line in sys.stdin:
        try:
            packet = json.loads(line.strip())
            write_packet(packet)
            print(f"[DB] Wrote packet from {packet.get('sensor_id')}")
        except Exception as e:
            print(f"[DB] Invalid JSON input: {e}", file=sys.stderr)

if __name__ == "__main__":
    run_db_writer()
