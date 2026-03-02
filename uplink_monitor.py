# uplink_monitor.py
# Publishes VM network uplink health to MQTT every 10s (online + RTT).
# Optional: enable periodic speedtest (disabled by default).
#
# Topic: hab/network/uplink
# Payload example:
# {
#   "online": true,
#   "rtt_ms": 34.2,
#   "down_mbps": null,
#   "up_mbps": null,
#   "ip": "35.xx.xx.xx",
#   "ts": "2026-01-19T12:10:00Z",
#   "source": "vm"
# }

import json
import os
import socket
import subprocess
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "essie-mosquitto")  # in docker-compose network: service/container name
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "hab/network/uplink")

PING_HOST = os.getenv("PING_HOST", "1.1.1.1")  # Cloudflare DNS (fast + stable)
PING_TIMEOUT_S = int(os.getenv("PING_TIMEOUT_S", "2"))
INTERVAL_S = int(os.getenv("INTERVAL_S", "10"))

# Speedtest is optional (uses bandwidth). Disabled by default.
ENABLE_SPEEDTEST = os.getenv("ENABLE_SPEEDTEST", "0") == "1"
SPEEDTEST_EVERY_S = int(os.getenv("SPEEDTEST_EVERY_S", "1800"))  # 30 min

# If your environment doesn't have `ping`, you can swap to a TCP connect check (see below).


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_public_ip():
    # Avoid external web calls. Best effort: return VM hostname/IP if resolvable.
    # (Public IP would need an external service; keeping this local.)
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return None


def ping_rtt_ms(host: str, timeout_s: int):
    """
    Returns (online: bool, rtt_ms: float|None)
    Uses system ping (linux). For alpine, you may need `apk add iputils`.
    """
    # Linux ping: -c 1 (one packet), -W timeout (seconds)
    cmd = ["ping", "-c", "1", "-W", str(timeout_s), host]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        # Parse "... time=12.3 ms"
        # Works for typical ping output.
        marker = "time="
        if marker in out:
            tail = out.split(marker, 1)[1]
            num = ""
            for ch in tail:
                if ch.isdigit() or ch == ".":
                    num += ch
                else:
                    break
            rtt = float(num) if num else None
            return True, rtt
        return True, None
    except Exception:
        return False, None


def speedtest_mbps():
    """
    Optional: Uses Ookla `speedtest` CLI if installed.
    Returns (down_mbps, up_mbps) or (None, None) if unavailable.
    """
    # Requires speedtest CLI available in container.
    # Command: speedtest -f json
    try:
        out = subprocess.check_output(["speedtest", "-f", "json"], stderr=subprocess.STDOUT, text=True)
        data = json.loads(out)
        # Ookla json gives bandwidth in bits/s under download.bandwidth? (varies by version)
        # We'll handle common formats robustly.
        down_bps = None
        up_bps = None

        # Newer format often includes:
        # data["download"]["bandwidth"] in bytes/s, and upload same
        if isinstance(data, dict):
            if "download" in data and isinstance(data["download"], dict):
                bw = data["download"].get("bandwidth")
                if isinstance(bw, (int, float)):
                    down_bps = float(bw) * 8.0  # bytes/s -> bits/s
            if "upload" in data and isinstance(data["upload"], dict):
                bw = data["upload"].get("bandwidth")
                if isinstance(bw, (int, float)):
                    up_bps = float(bw) * 8.0

        down_mbps = round(down_bps / 1_000_000, 2) if down_bps else None
        up_mbps = round(up_bps / 1_000_000, 2) if up_bps else None
        return down_mbps, up_mbps
    except Exception:
        return None, None


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    last_speedtest_ts = 0

    while True:
        online, rtt = ping_rtt_ms(PING_HOST, PING_TIMEOUT_S)

        down_mbps = None
        up_mbps = None
        now = time.time()

        if ENABLE_SPEEDTEST and (now - last_speedtest_ts) >= SPEEDTEST_EVERY_S:
            down_mbps, up_mbps = speedtest_mbps()
            last_speedtest_ts = now

        payload = {
            "online": bool(online),
            "rtt_ms": round(rtt, 1) if isinstance(rtt, (int, float)) else None,
            "down_mbps": down_mbps,
            "up_mbps": up_mbps,
            "ip": get_public_ip(),
            "ts": utc_now_iso(),
            "source": "vm",
            "ping_host": PING_HOST,
        }

        client.publish(TOPIC, json.dumps(payload), qos=0, retain=True)
        print("📡 uplink published:", payload, flush=True)

        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
