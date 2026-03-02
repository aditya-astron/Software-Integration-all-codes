# local_weather.py (debug 10s)
import paho.mqtt.client as mqtt
import requests
import time
import json

API_KEY = "7aaf6f6629da3bd22bd55d48f36a9ab6"
CITY = "Ahmedabad"
BROKER = "mosquitto"   # service name from docker-compose
PORT = 1883
TOPIC = "hab/local_weather"


def fetch_weather_and_aqi():
    """Fetch current weather + AQI from OpenWeatherMap"""
    url_weather = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units=metric"
    r = requests.get(url_weather).json()

    temp = r["main"]["temp"]
    humidity = r["main"]["humidity"]
    pressure = r["main"]["pressure"]
    lat = r["coord"]["lat"]
    lon = r["coord"]["lon"]

    # Fetch AQI
    url_aqi = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={API_KEY}"
    r_aqi = requests.get(url_aqi).json()

    # AQI scale: 1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor
    aqi_val = r_aqi["list"][0]["main"]["aqi"]

    data = {
        "temp": temp,
        "humidity": humidity,
        "pressure": pressure,
        "aqi": aqi_val
    }
    return data


def main():
    client = mqtt.Client()
    client.connect(BROKER, PORT, 60)

    while True:
        try:
            weather = fetch_weather_and_aqi()
            client.publish(TOPIC, json.dumps(weather))
            print("📤 Published:", weather)
        except Exception as e:
            print("❌ Error fetching weather:", e)
        time.sleep(10)  # 🔹 update every 10 seconds for debug


if __name__ == "__main__":
    main()
