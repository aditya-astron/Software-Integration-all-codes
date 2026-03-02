import sys
import time
import json
import random
import threading
import paho.mqtt.client as mqtt

# ✅ NEW: Offline durable queue (store-and-forward)
from offline_queue import enqueue

# -------------------------
# Base Sensor # -------------------------
class BaseSensorSimulator:
    def __init__(self, sensor_id, hz=1.0, units=None, value_fn=None):
        self.sensor_id = sensor_id
        self.hz = hz
        self.period = 1.0 / hz
        self.units = units if units else {}
        self.value_fn = value_fn if value_fn else (lambda: {})

    def run(self):
        while True:
            data = self.value_fn()
            packet = {
                "sensor_id": self.sensor_id,
                "timestamp": time.time(),
                **data,
                "units": self.units
            }

            # ✅ EXISTING BEHAVIOR (stdout)
            sys.stdout.write(json.dumps(packet) + "\n")
            sys.stdout.flush()

            # ✅ NEW: store locally (ALWAYS)
            try:
                enqueue(f"hab/sensors/{self.sensor_id}", packet)
            except Exception as e:
                sys.stderr.write(f"Offline queue error: {e}\n")

            time.sleep(self.period)

# -------------------------
# MQTT Subscriber 
# -------------------------
MQTT_BROKER = "192.168.1.100"
MQTT_PORT = 1883
MQTT_TOPIC = "hab/#"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        sys.stderr.write("✅ MQTT connected\n")
        client.subscribe(MQTT_TOPIC)
    else:
        sys.stderr.write(f"❌ MQTT connection failed: {rc}\n")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        packet = {
            "sensor_id": data.get("device", msg.topic),
            "timestamp": time.time(),
            **data
        }

        # ✅ EXISTING BEHAVIOR (stdout)
        sys.stdout.write(json.dumps(packet) + "\n")
        sys.stdout.flush()

        # ✅ NEW: store MQTT-origin data locally too
        enqueue(msg.topic, packet)

    except Exception as e:
        sys.stderr.write(f"MQTT message error: {e}\n")

def mqtt_listener():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            sys.stderr.write(f"MQTT reconnect error: {e}\n")
            time.sleep(5)

# -------------------------
# SENSOR REGISTRY 
# -------------------------
def sensor_definitions():
    return [
        # ------------------ Environmental ------------------
        ("SEN0189_Turbidity", 1.0, {"turbidity": "NTU"},
            lambda: {"turbidity": round(random.uniform(0, 100), 2)}),
        ("SEN0257_Pressure", 1.0, {"pressure": "bar"},
            lambda: {"pressure": round(random.uniform(1.0, 3.0), 2)}),
        ("BME280_1", 1.0, {"temp": "C", "humidity": "%", "pressure": "hPa"},
            lambda: {"temp": round(random.uniform(20, 25), 2),
                     "humidity": round(random.uniform(40, 60), 2),
                     "pressure": round(random.uniform(1000, 1025), 2)}),
        ("BME280_2", 1.0, {"temp": "C", "humidity": "%", "pressure": "hPa"},
            lambda: {"temp": round(random.uniform(20, 25), 2),
                     "humidity": round(random.uniform(40, 60), 2),
                     "pressure": round(random.uniform(1000, 1025), 2)}),
        ("BNO055_1", 1.0, {"orientation": "deg"},
            lambda: {"orientation": round(random.uniform(0, 360), 2)}),
        ("BNO055_2", 1.0, {"orientation": "deg"},
            lambda: {"orientation": round(random.uniform(0, 360), 2)}),
        ("SEN0169_pH", 1.0, {"pH": "pH"},
            lambda: {"pH": round(random.uniform(6.5, 8.5), 2)}),
        ("DO2_Oxygen", 1.0, {"oxygen": "%"},
            lambda: {"oxygen": round(random.uniform(18.0, 21.0), 2)}),
        ("DS18B20_1", 1.0, {"water_temp": "C"},
            lambda: {"water_temp": round(random.uniform(10, 25), 2)}),
        ("DS18B20_2", 1.0, {"water_temp": "C"},
            lambda: {"water_temp": round(random.uniform(10, 25), 2)}),
        ("MQ9_1", 1.0, {"co": "ppm"}, lambda: {"co": random.randint(0, 100)}),
        ("MQ9_2", 1.0, {"co": "ppm"}, lambda: {"co": random.randint(0, 100)}),
        ("MQ135_1", 1.0, {"air_quality": "ppm"},
            lambda: {"air_quality": random.randint(200, 1000)}),
        ("MQ135_2", 1.0, {"air_quality": "ppm"},
            lambda: {"air_quality": random.randint(200, 1000)}),
        ("FS300A_Flow", 1.0, {"flow": "L/min"},
            lambda: {"flow": round(random.uniform(0, 10), 2)}),
        ("SEN0463_Radiation", 1.0, {"radiation": "µSv/h"},
            lambda: {"radiation": round(random.uniform(0.05, 0.3), 3)}),
        ("SEN0322_O2", 1.0, {"oxygen": "%"},
            lambda: {"oxygen": round(random.uniform(18, 21), 2)}),
        ("SCD40_CO2", 1.0, {"co2": "ppm"},
            lambda: {"co2": random.randint(400, 6000)}),
        ("Anemometer", 1.0, {"windspeed": "m/s"},
            lambda: {"windspeed": round(random.uniform(0, 20), 2)}),
        ("NPN_LiquidLevel", 1.0, {"level": "cm"},
            lambda: {"level": random.randint(0, 100)}),
        ("RC0603JR_1", 1.0, {"leak": "bool"},
            lambda: {"leak": random.choice([0, 1])}),
        ("RC0603JR_2", 1.0, {"leak": "bool"},
            lambda: {"leak": random.choice([0, 1])}),
        ("EZO_ORP", 1.0, {"orp": "mV"},
            lambda: {"orp": round(random.uniform(200, 600), 2)}),

        # ------------------ Biometric ------------------
        ("MAX30100_1", 1.0, {"spo2": "%"},
            lambda: {"spo2": round(random.uniform(90, 100), 1)}),
        ("MAX30100_2", 1.0, {"spo2": "%"},
            lambda: {"spo2": round(random.uniform(90, 100), 1)}),
        ("AD8232_1", 1.0, {"ecg": "mV"},
            lambda: {"ecg": round(random.uniform(-1, 1), 3)}),
        ("AD8232_2", 1.0, {"ecg": "mV"},
            lambda: {"ecg": round(random.uniform(-1, 1), 3)}),
        ("Grove_GSR", 1.0, {"gsr": "kΩ"},
            lambda: {"gsr": round(random.uniform(10, 100), 2)}),
        ("BG03_Glucose", 1.0, {"glucose": "mg/dL"},
            lambda: {"glucose": random.randint(70, 180)}),
        ("Fitbit_Sense2", 1.0, {"heart_rate": "bpm"},
            lambda: {"heart_rate": random.randint(50, 120)}),

        # ------------------ Positioning ------------------
        ("TEL0157_GPS1", 1.0, {"lat": "deg", "lon": "deg"},
            lambda: {"lat": round(random.uniform(-90, 90), 6),
                     "lon": round(random.uniform(-180, 180), 6)}),
        ("TEL0157_GPS2", 1.0, {"lat": "deg", "lon": "deg"},
            lambda: {"lat": round(random.uniform(-90, 90), 6),
                     "lon": round(random.uniform(-180, 180), 6)}),

        # ------------------ Cameras (metadata telemetry) ------------------
        ("internal_cam1", 1.0, {"stream_url": "rtsp"},
            lambda: {"stream_url": "rtsp://admin:Amorfati%402025@192.168.1.108:554/cam/realmonitor?channel=1&subtype=0"}),
        ("internal_cam2", 1.0, {"stream_url": "rtsp"},
            lambda: {"stream_url": "rtsp://admin:Amorfati%402025@192.168.1.108:554/cam/realmonitor?channel=2&subtype=0"}),
        ("external_cam", 1.0, {"stream_url": "rtsp"},
            lambda: {"stream_url": "rtsp://admin:Amorfati%402025@192.168.1.108:554/cam/realmonitor?channel=3&subtype=0"}),

        # ------------------ Fire / Smoke (Ajax system simulated) ------------------
        ("Ajax_FireProtect_1", 1.0, {"status": "str", "battery": "%"},
            lambda: {"status": random.choice(["OK", "ALARM"]),
                     "battery": f"{random.randint(70,100)}%"}),
        ("Ajax_ManualCallPoint_1", 1.0, {"status": "str"},
            lambda: {"status": random.choice(["IDLE", "PRESSED"])}),
        ("Ajax_Siren_1", 1.0, {"status": "str"},
            lambda: {"status": random.choice(["OFF", "ON"])}),

        # ------------------ Habitat Comms (simulated) ------------------
        ("HabComms", 1.0,
            {"O2_level": "%", "CO2_level": "%", "Temperature": "C"},
            lambda: {"O2_level": round(random.uniform(19, 21), 2),
                     "CO2_level": round(random.uniform(0.03, 0.07), 3),
                     "Temperature": round(random.uniform(20, 24), 1)}),
    ]

# -------------------------
# HUB TO RUN ALL
# -------------------------
def run_sensor(sensor):
    sensor.run()

def main():
    # Start simulator threads
    sensors = [BaseSensorSimulator(sid, hz, units, fn)
               for sid, hz, units, fn in sensor_definitions()]

    threads = []
    for s in sensors:
        t = threading.Thread(target=run_sensor, args=(s,), daemon=True)
        threads.append(t)
        t.start()

    # Start MQTT listener thread
    t_mqtt = threading.Thread(target=mqtt_listener, daemon=True)
    threads.append(t_mqtt)
    t_mqtt.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.stderr.write("Sensor hub stopped.\n")

if __name__ == "__main__":
    main()
