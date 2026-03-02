# ajax_ingestor.py
import os
import sys
import time
import json
import random
import datetime

import paho.mqtt.client as mqtt

# ===============================
# MQTT CONFIG (Docker-friendly)
# ===============================
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_PREFIX = os.getenv("AJAX_MQTT_PREFIX", "ajax")  # base topic prefix
PUBLISH_INTERVAL_SEC = int(os.getenv("AJAX_PUBLISH_INTERVAL_SEC", "5"))

# Optional: make simulation more/less noisy
ALARM_PROB_FIREPROTECT = float(os.getenv("AJAX_SIM_PROB_FIREPROTECT_ALARM", "0.08"))  # 8%
ALARM_PROB_MCP = float(os.getenv("AJAX_SIM_PROB_MCP_ALARM", "0.03"))                  # 3%
ALARM_PROB_SIREN = float(os.getenv("AJAX_SIM_PROB_SIREN_ALARM", "0.04"))              # 4%
OFFLINE_PROB_ANY = float(os.getenv("AJAX_SIM_PROB_OFFLINE", "0.02"))                  # 2%

# ===============================
# YOUR AJAX DEVICE IDs (from app)
# ===============================
AJAX_DEVICES = [
    {
        "key": "hub",
        "sensor_id": "Ajax_Hub2_002DBD39",
        "device_id": "002DBD39",
        "name": "Container fire panel",
        "type": "hub",
        "room": "Room",
    },
    {
        "key": "kitchen_smoke",
        "sensor_id": "Ajax_FireProtectKitchen_7A6949031",
        "device_id": "7A6949031",
        "name": "Kitchen Smoke sensor",
        "type": "fireprotect",
        "room": "Room",
    },
    {
        "key": "bedroom_smoke",
        "sensor_id": "Ajax_FireProtectBedroom_2850BF031",
        "device_id": "2850BF031",
        "name": "Bedroom Smoke Sensor",
        "type": "fireprotect",
        "room": "Room",
    },
    {
        "key": "mcp",
        "sensor_id": "Ajax_MCP_3052A19C4F0",
        "device_id": "3052A19C4F0",
        "name": "MCP",
        "type": "manual_call_point",
        "room": "Room",
    },
    {
        "key": "siren",
        "sensor_id": "Ajax_Siren_30F609CE141",
        "device_id": "30F609CE141",
        "name": "Siren",
        "type": "siren",
        "room": "Room",
    },
]

# ===============================
# Helpers
# ===============================
def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def topic_base(device_key: str) -> str:
    return f"{MQTT_PREFIX}/{device_key}"

def make_packet(device: dict) -> dict:
    """
    SIMULATION ONLY.
    Later you can swap this function with real Ajax ingestion
    (HA, relay bridge, or official API key if available).
    """
    t = device["type"]

    # Simulate occasional offline
    offline = random.random() < OFFLINE_PROB_ANY
    connection = "offline" if offline else "online"

    packet = {
        "timestamp": time.time(),
        "time_iso": now_iso(),
        "sensor_id": device["sensor_id"],
        "device_id": device["device_id"],
        "device_key": device["key"],
        "device_name": device["name"],
        "device_type": t,
        "room": device.get("room", ""),
        "connection": connection,
        "battery_percent": random.randint(60, 100),
        "external_power": False,
        "lid_open": False,
    }

    if offline:
        packet["status"] = "OFFLINE"
        return packet

    if t == "hub":
        packet.update(
            {
                "status": "OK",
                "armed_state": "Disarmed",
                "ethernet": random.choice(["connected", "not_connected"]),
                "cellular": random.choice(["connected", "not_connected"]),
                "sim1": "active",
                "sim2": "inactive",
                "noise_dbm": random.randint(-95, -55),
            }
        )

    elif t == "fireprotect":
        # Choose alarm state sometimes
        roll = random.random()
        if roll < ALARM_PROB_FIREPROTECT:
            state = random.choice(["SMOKE", "FIRE", "TEMP_THRESHOLD"])
        else:
            state = "OK"

        packet.update(
            {
                "status": state,
                "smoke": (state == "SMOKE"),
                "fire": (state == "FIRE"),
                "temp_threshold_exceeded": (state == "TEMP_THRESHOLD"),
                "rapid_temp_rise": random.choice([False, False, False, True]),
                "dust_level": random.randint(0, 100),
            }
        )

    elif t == "manual_call_point":
        state = "ALARM" if (random.random() < ALARM_PROB_MCP) else "OK"
        packet.update(
            {
                "status": state,
                "current_state": "No alarm" if state == "OK" else "ALARM",
                "operating_mode": "Fire alarm",
                "local_alarm_only": False,
            }
        )

    elif t == "siren":
        state = "ALARM" if (random.random() < ALARM_PROB_SIREN) else "OK"
        packet.update(
            {
                "status": state,
                "entry_delays": False,
                "exit_delays": False,
                "night_mode_entry_delays": False,
                "night_mode_exit_delays": False,
                "chime_on_open": False,
            }
        )

    return packet

def status_string_for_ui(packet: dict) -> str:
    """
    Simple string payload for UI checks:
      "FIRE", "SMOKE", "ALARM", "OFFLINE", "OK"
    """
    status = str(packet.get("status", "UNKNOWN")).upper()

    if status == "FIRE":
        return "FIRE"
    if status == "SMOKE":
        return "SMOKE"
    if status in ("ALARM", "TEMP_THRESHOLD"):
        return "ALARM"
    if status == "OFFLINE":
        return "OFFLINE"
    return "OK"

# ===============================
# Main
# ===============================
def main():
    print(
        f"[ajax_ingestor] starting (SIMULATION). MQTT: {MQTT_BROKER}:{MQTT_PORT}, prefix='{MQTT_PREFIX}'",
        file=sys.stderr,
    )

    m = mqtt.Client(client_id="ajax_ingestor")
    m.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
    m.loop_start()

    try:
        while True:
            for dev in AJAX_DEVICES:
                packet = make_packet(dev)
                base = topic_base(dev["key"])

                # Topics
                topic_event = f"{base}/event"
                topic_status = f"{base}/status"
                topic_avail = f"{base}/available"

                # Payloads
                payload_json = json.dumps(packet)
                payload_status = status_string_for_ui(packet)
                payload_avail = "offline" if packet.get("connection") == "offline" else "online"

                # Publish (JSON + string status + availability)
                m.publish(topic_event, payload_json, qos=0, retain=False)
                m.publish(topic_status, payload_status, qos=0, retain=False)
                m.publish(topic_avail, payload_avail, qos=0, retain=False)

                # Debug print (optional but useful)
                sys.stdout.write(payload_json + "\n")
                sys.stdout.flush()

            time.sleep(PUBLISH_INTERVAL_SEC)

    except KeyboardInterrupt:
        print("[ajax_ingestor] stopping...", file=sys.stderr)
    except Exception as e:
        print(f"[ajax_ingestor] ERROR: {e}", file=sys.stderr)
        time.sleep(2)
    finally:
        try:
            m.loop_stop()
            m.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()
