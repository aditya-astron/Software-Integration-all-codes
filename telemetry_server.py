import sys
import json
import time
from cryptography.fernet import Fernet
from anomaly_detector import detect_anomalies
from influxdb_client import InfluxDBClient, Point, WriteOptions
import paho.mqtt.client as mqtt

# -----------------------
# Encryption
# -----------------------
KEY_FILE = "encryption_key.key"

def load_key():
    try:
        with open(KEY_FILE, "rb") as f:
            return f.read()
    except FileNotFoundError:
        print("[SERVER] WARNING: encryption_key.key not found. Running without decryption.", file=sys.stderr)
        return None

def decrypt_packet(encrypted_token, cipher):
    """Decrypt a Fernet token string into a JSON packet."""
    try:
        raw_json = cipher.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
        return json.loads(raw_json)
    except Exception as e:
        print(f"[SERVER] Failed to decrypt packet: {e}", file=sys.stderr)
        return None

def validate_packet(packet):
    """
    Normalize and validate packets:
    - Accepts either `sensor_id` or `device`.
    - Auto-adds timestamp if missing.
    """
    # If only "device" is present, map to "sensor_id"
    if "sensor_id" not in packet and "device" in packet:
        packet["sensor_id"] = packet["device"]

    # Add timestamp if missing
    if "timestamp" not in packet:
        packet["timestamp"] = time.time()

    # Ensure validation
    required_fields = ["sensor_id", "timestamp"]
    return all(field in packet for field in required_fields)

# -----------------------
# InfluxDB Config
# -----------------------
INFLUX_URL = "http://influxdb:8086"   # service name from docker-compose
INFLUX_TOKEN = "my-secret-token"
INFLUX_ORG = "essie_org"
INFLUX_BUCKET = "essie_telemetry"

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=WriteOptions(batch_size=100, flush_interval=1000))

def write_to_influx(packet: dict):
    """Write telemetry packet into InfluxDB."""
    try:
        sensor_id = packet.get("sensor_id", "unknown")
        box = packet.get("box", "unknown")  # e.g. internal/external
        ts = int(packet.get("timestamp", time.time()) * 1e9)  # Influx requires ns

        point = Point("telemetry") \
            .tag("sensor_id", sensor_id) \
            .tag("box", box) \
            .time(ts)

        # Add fields (skip reserved keys)
        for k, v in packet.items():
            if k not in ("sensor_id", "timestamp", "units", "box", "device") and v is not None:
                # If boolean, cast to int so Grafana graphs it
                if isinstance(v, bool):
                    point.field(k, int(v))
                else:
                    point.field(k, v)

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        print(f"[DB] Wrote packet from {sensor_id} ({box}) with fields: {list(packet.keys())}")
    except Exception as e:
        print(f"[DB] Failed to write packet: {e}", file=sys.stderr)

# -----------------------
# MQTT Config
# -----------------------
MQTT_BROKER = "mosquitto"  # service name from docker-compose
MQTT_PORT = 1883
MQTT_TOPIC = "essie/telemetry"

mqtt_client = mqtt.Client()
try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print(f"[MQTT] Connected to broker {MQTT_BROKER}:{MQTT_PORT}")
except Exception as e:
    print(f"[MQTT] Failed to connect to broker: {e}", file=sys.stderr)

def publish_to_mqtt(packet: dict):
    """Publish telemetry packet to MQTT broker."""
    try:
        mqtt_client.publish(MQTT_TOPIC, json.dumps(packet))
        print(f"[MQTT] Published packet from {packet.get('sensor_id')} ({packet.get('box','unknown')})")
    except Exception as e:
        print(f"[MQTT] Failed to publish: {e}", file=sys.stderr)

# -----------------------
# Main Server Loop
# -----------------------
def run_server():
    key = load_key()
    cipher = Fernet(key) if key else None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        packet = None

        # Case 1: Try plain JSON
        try:
            packet = json.loads(line)
        except json.JSONDecodeError:
            # Case 2: Try Fernet decryption
            if cipher:
                packet = decrypt_packet(line, cipher)

        if packet and validate_packet(packet):
            # Ensure "box" always exists
            if "box" not in packet:
                packet["box"] = "unknown"

            sid = packet["sensor_id"]
            ts = packet["timestamp"]

            print(f"[SERVER] Received packet from {sid} at {ts} (box={packet['box']})")
            print(f"         Data: {packet}")

            # Run anomaly detection
            alerts = detect_anomalies(packet)
            for alert in alerts:
                print(f"[ALERT] {alert}")

            # Write to DB
            write_to_influx(packet)

            # Publish to MQTT
            publish_to_mqtt(packet)

            sys.stdout.flush()
        else:
            print("[SERVER] Invalid or dropped packet.", file=sys.stderr)

if __name__ == "__main__":
    run_server()
