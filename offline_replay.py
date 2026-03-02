import os, time, json
from offline_queue import fetch_unsent, mark_sent, backlog_count

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

def influx_ok():
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as c:
            c.health()
        return True
    except Exception:
        return False

def write_influx(payload: dict, ts_ms: int):
    # Adjust measurement/tags/fields to your schema
    p = (
        Point("hab_weather")
        .field("temperature", float(payload.get("temperature", 0)))
        .field("humidity", float(payload.get("humidity", 0)))
        .field("pressure", float(payload.get("pressure", 0)))
        .field("aqi", float(payload.get("aqi", 0)))
        .time(ts_ms * 1_000_000, WritePrecision.NS)
    )

    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as c:
        w = c.write_api(write_options=None)
        w.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)

def main():
    mc = mqtt.Client()
    mc.connect(MQTT_BROKER, MQTT_PORT, 60)
    mc.loop_start()

    while True:
        if backlog_count() == 0:
            time.sleep(2)
            continue

        if not influx_ok():
            time.sleep(3)
            continue

        rows = fetch_unsent(limit=200)
        sent_ids = []

        for _id, topic, payload_json, ts_ms in rows:
            payload = json.loads(payload_json)

            try:
                # Publish MQTT (optional, but useful for live dashboards)
                mc.publish(topic, payload_json, qos=1)

                # Write Influx (for history + dashboards)
                write_influx(payload, ts_ms)

                sent_ids.append(_id)
            except Exception:
                # Stop batch on first failure; retry later
                break

        mark_sent(sent_ids)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
