def detect_anomalies(packet: dict) -> list:
    """
    Return a list of anomaly alerts based on telemetry packet.
    Includes rules for all ESSIE sensors.
    """
    alerts = []
    sid = packet.get("sensor_id")

    # --------------------
    # Environmental Sensors
    # --------------------
    if sid.startswith("SEN0189"):  # Turbidity
        turbidity = packet.get("turbidity")
        if turbidity is not None and turbidity > 50:
            alerts.append("⚠️ HIGH TURBIDITY DETECTED!")

    elif sid.startswith("SEN0257"):  # Water pressure
        pressure = packet.get("pressure")
        if pressure is not None and (pressure < 1.0 or pressure > 2.5):
            alerts.append("⚠️ WATER PRESSURE OUT OF RANGE!")

    elif sid.startswith("BME280"):
        temp = packet.get("temp")
        humidity = packet.get("humidity")
        pressure = packet.get("pressure")
        if temp is not None and (temp < 18 or temp > 28):
            alerts.append("⚠️ TEMPERATURE OUT OF RANGE!")
        if humidity is not None and (humidity < 30 or humidity > 70):
            alerts.append("⚠️ HUMIDITY OUT OF RANGE!")
        if pressure is not None and (pressure < 990 or pressure > 1030):
            alerts.append("⚠️ AIR PRESSURE OUT OF RANGE!")

    elif sid.startswith("BNO055"):
        orientation = packet.get("orientation")
        if orientation is not None and (orientation < 0 or orientation > 360):
            alerts.append("⚠️ INVALID ORIENTATION VALUE!")

    elif sid.startswith("SEN0169"):  # pH
        ph = packet.get("pH")
        if ph is not None and (ph < 6.5 or ph > 8.5):
            alerts.append("⚠️ UNSAFE WATER pH LEVEL!")

    elif sid.startswith("DO2") or sid.startswith("SEN0322"):  # O2
        oxygen = packet.get("oxygen")
        if oxygen is not None and oxygen < 19.5:
            alerts.append("⚠️ LOW OXYGEN LEVEL!")

    elif sid.startswith("DS18B20"):  # Water temperature
        wtemp = packet.get("water_temp")
        if wtemp is not None and (wtemp < 5 or wtemp > 30):
            alerts.append("⚠️ WATER TEMPERATURE OUT OF RANGE!")

    elif sid.startswith("MQ9"):
        co = packet.get("co")
        if co is not None and co > 50:
            alerts.append("⚠️ HIGH CO LEVEL!")

    elif sid.startswith("MQ135"):
        aq = packet.get("air_quality")
        if aq is not None and aq > 800:
            alerts.append("⚠️ POOR AIR QUALITY DETECTED!")

    elif sid.startswith("BF350"):
        strain = packet.get("strain")
        if strain is not None and strain > 800:
            alerts.append("⚠️ HIGH STRUCTURAL STRAIN!")

    elif sid.startswith("FS300A"):
        flow = packet.get("flow")
        if flow is not None and flow < 0.5:
            alerts.append("⚠️ LOW WATER FLOW!")

    elif sid.startswith("SEN0463"):
        rad = packet.get("radiation")
        if rad is not None and rad > 0.3:
            alerts.append("⚠️ RADIATION LEVEL TOO HIGH!")

    elif sid.startswith("SCD40"):  # CO2
        co2 = packet.get("co2")
        if co2 is not None and co2 > 5000:
            alerts.append("⚠️ HIGH CO2 LEVEL!")

    elif sid.startswith("Anemometer"):
        wind = packet.get("windspeed")
        if wind is not None and wind > 15:
            alerts.append("⚠️ HIGH WINDSPEED DETECTED!")

    elif sid.startswith("NPN"):
        level = packet.get("level")
        if level is not None and level < 10:
            alerts.append("⚠️ LIQUID LEVEL CRITICALLY LOW!")

    elif sid.startswith("RC0603JR"):
        leak = packet.get("leak")
        if leak == 1:
            alerts.append("⚠️ WATER LEAK DETECTED!")

    elif sid.startswith("EZO_ORP"):
        orp = packet.get("orp")
        if orp is not None and (orp < 250 or orp > 500):
            alerts.append("⚠️ ORP OUT OF RANGE!")

    # --------------------
    # Biometric Sensors
    # --------------------
    elif sid.startswith("MAX30100"):
        spo2 = packet.get("spo2")
        if spo2 is not None and spo2 < 90:
            alerts.append("⚠️ LOW SpO₂ LEVEL!")

    elif sid.startswith("AD8232"):
        ecg = packet.get("ecg")
        if ecg is not None and (ecg < -0.8 or ecg > 0.8):
            alerts.append("⚠️ ECG SIGNAL OUT OF RANGE!")

    elif sid.startswith("Grove_GSR"):
        gsr = packet.get("gsr")
        if gsr is not None and gsr > 80:
            alerts.append("⚠️ HIGH STRESS RESPONSE DETECTED!")

    elif sid.startswith("BG03"):
        glucose = packet.get("glucose")
        if glucose is not None and (glucose < 70 or glucose > 180):
            alerts.append("⚠️ BLOOD GLUCOSE OUT OF SAFE RANGE!")

    elif sid.startswith("Fitbit_Sense2"):
        hr = packet.get("heart_rate")
        if hr is not None and (hr < 40 or hr > 180):
            alerts.append("⚠️ ABNORMAL HEART RATE!")

    # --------------------
    # Positioning / Comms
    # --------------------
    elif sid.startswith("TEL0157"):
        lat = packet.get("lat")
        lon = packet.get("lon")
        if lat is None or lon is None:
            alerts.append("⚠️ GPS SIGNAL LOST!")

    elif sid.startswith("Hikvision_Cam"):
        # Just placeholder — real video stream anomaly detection would be separate
        fr = packet.get("frame_rate")
        if fr is not None and fr < 15:
            alerts.append("⚠️ CAMERA FRAME RATE TOO LOW!")

    return alerts
