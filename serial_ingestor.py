import os, re, time, json, serial, requests, datetime

COM_PORT = os.getenv("SENSOR_COM", "COM5")     # set your COM port via env
BAUD     = 115200
POST_URL = os.getenv("INGEST_URL", "http://localhost:5000/ingest")  # telemetry_server

# regexes to parse your current firmware prints (unchanged firmware)
re_bme = re.compile(r"BME280 - Temperature:\s*([-\d.]+)\s*°C,\s*Humidity:\s*([-\d.]+)\s*%,\s*Pressure:\s*([-\d.]+)\s*hPa")
re_bno = re.compile(r"BNO055 - Orientation X,Y,Z:\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)")
re_scd = re.compile(r"SCD40 - CO2:\s*([-\d.]+)\s*ppm,\s*Temp:\s*([-\d.]+)\s*°C,\s*Humidity:\s*([-\d.]+)\s*%")
re_mq  = re.compile(r"MQ9 \(CO/flammable gases\) ADC:\s*(\d+),\s*MQ135 \(Air quality\) ADC:\s*(\d+)")

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def accumulate_block(ser):
    """
    Reads lines until we see a full set (BME/BNO/SCD/MQ) or we time out; returns a dict.
    """
    data = {
        "timestamp": now_iso(),
        "source": "internal_sensor_box",
        "box": "internal"  # <--- label this ingestor as internal
    }
    deadline = time.time() + 3.5  # up to ~ one reading cycle
    while time.time() < deadline:
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue

        m = re_bme.search(line)
        if m:
            data["bme_temperature_c"] = float(m.group(1))
            data["bme_humidity_pct"]  = float(m.group(2))
            data["bme_pressure_hpa"]  = float(m.group(3))
            continue

        m = re_bno.search(line)
        if m:
            data["bno_ori_x"] = float(m.group(1))
            data["bno_ori_y"] = float(m.group(2))
            data["bno_ori_z"] = float(m.group(3))
            continue

        m = re_scd.search(line)
        if m:
            data["scd40_co2_ppm"]     = float(m.group(1))
            data["scd40_temperature"] = float(m.group(2))
            data["scd40_humidity"]    = float(m.group(3))
            continue

        m = re_mq.search(line)
        if m:
            data["mq9_adc"]   = int(m.group(1))
            data["mq135_adc"] = int(m.group(2))
            # once MQ line appears, it’s usually end of block
            break
    return data

def main():
    ser = serial.Serial(COM_PORT, BAUD, timeout=1.0)
    print(f"[serial_ingestor] reading {COM_PORT} @ {BAUD}, posting to {POST_URL}")
    while True:
        try:
            payload = accumulate_block(ser)
            # send as JSON body (server supports application/json)
            r = requests.post(POST_URL, json=payload, timeout=2.5)
            print(f"→ {r.status_code} {payload}")
        except Exception as e:
            print("ERROR:", e)
            time.sleep(1.0)

if __name__ == "__main__":
    main()
