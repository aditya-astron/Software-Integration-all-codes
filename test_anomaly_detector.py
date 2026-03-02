from anomaly_detector import detect_anomalies

def run_tests():
    test_packets = [
        # Environmental
        {"sensor_id": "SEN0189_Turbidity", "turbidity": 80},
        {"sensor_id": "SEN0257_Pressure", "pressure": 0.5},
        {"sensor_id": "BME280_1", "temp": 35, "humidity": 80, "pressure": 980},
        {"sensor_id": "BNO055_1", "orientation": 400},
        {"sensor_id": "SEN0169_pH", "pH": 5.0},
        {"sensor_id": "DO2_Oxygen", "oxygen": 18.0},
        {"sensor_id": "DS18B20_1", "water_temp": 40},
        {"sensor_id": "MQ9_1", "co": 100},
        {"sensor_id": "MQ135_1", "air_quality": 900},
        {"sensor_id": "BF350_1", "strain": 900},
        {"sensor_id": "FS300A_Flow", "flow": 0.1},
        {"sensor_id": "SEN0463_Radiation", "radiation": 0.5},
        {"sensor_id": "SEN0322_O2", "oxygen": 18.5},
        {"sensor_id": "SCD40_CO2", "co2": 6000},
        {"sensor_id": "Anemometer", "windspeed": 20},
        {"sensor_id": "NPN_LiquidLevel", "level": 5},
        {"sensor_id": "RC0603JR_1", "leak": 1},
        {"sensor_id": "EZO_ORP", "orp": 100},

        # Biometric
        {"sensor_id": "MAX30100_1", "spo2": 85},
        {"sensor_id": "AD8232_1", "ecg": 1.0},
        {"sensor_id": "Grove_GSR", "gsr": 90},
        {"sensor_id": "BG03_Glucose", "glucose": 200},
        {"sensor_id": "Fitbit_Sense2", "heart_rate": 30},

        # Positioning / Comms
        {"sensor_id": "TEL0157_GPS1"},  # missing lat/lon
        {"sensor_id": "Hikvision_Cam1", "frame_rate": 10},
    ]

    for packet in test_packets:
        alerts = detect_anomalies(packet)
        print(f"Sensor: {packet['sensor_id']} | Alerts: {alerts}")

if __name__ == "__main__":
    run_tests()
