# bio_ingest.py
# Simple HTTP ingest -> MQTT publisher for biometric/activity telemetry
#
import os
import json
import time
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_BASE = os.getenv("MQTT_BASE", "hab/biometric")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")
SOURCE = os.getenv("SOURCE", "phone")
DEVICE_TTL_S = int(os.getenv("DEVICE_TTL_S", "1800"))  # 30 mins

app = FastAPI(title="Bio Ingest -> MQTT")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# MQTT (robust: never crash API)
# ----------------------------
mqtt_client = mqtt.Client()
_mqtt_connected = False
_mqtt_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_token(x_token: Optional[str]) -> None:
    if INGEST_TOKEN:
        if not x_token or x_token != INGEST_TOKEN:
            raise HTTPException(status_code=401, detail="Bad or missing X-Token")


def on_connect(client, userdata, flags, rc):
    global _mqtt_connected
    with _mqtt_lock:
        _mqtt_connected = (rc == 0)


def on_disconnect(client, userdata, rc):
    global _mqtt_connected
    with _mqtt_lock:
        _mqtt_connected = False


mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect


def mqtt_is_connected() -> bool:
    with _mqtt_lock:
        return bool(_mqtt_connected)


def mqtt_publish(topic: str, payload: str) -> bool:
    """Best-effort publish; returns True if queued, False if not connected."""
    if not mqtt_is_connected():
        return False
    try:
        mqtt_client.publish(topic, payload, qos=0, retain=False)
        return True
    except Exception:
        return False


def mqtt_connect_loop():
    """Reconnect forever in background; keeps API alive even if MQTT is down."""
    mqtt_client.loop_start()
    while True:
        if not mqtt_is_connected():
            try:
                mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
            except Exception:
                pass
        time.sleep(3)


@app.on_event("startup")
def startup():
    t = threading.Thread(target=mqtt_connect_loop, daemon=True)
    t.start()


# ----------------------------
# in-memory registry (ephemeral)
# ----------------------------
registry: Dict[str, Dict[str, Any]] = {}


def cleanup_registry() -> None:
    cutoff = time.time() - DEVICE_TTL_S
    dead = [k for k, v in registry.items() if float(v.get("last_seen", 0)) < cutoff]
    for k in dead:
        registry.pop(k, None)


def publish_connected_snapshot() -> None:
    cleanup_registry()
    snapshot = {
        "ts": now_iso(),
        "count": len(registry),
        "devices": [
            {
                "device_id": did,
                "astronaut": v.get("astronaut"),
                "device_name": v.get("device_name"),
                "last_seen": v.get("last_seen_iso"),
            }
            for did, v in registry.items()
        ],
    }
    mqtt_publish(f"{MQTT_BASE}/connected", json.dumps(snapshot))


def publish_bio(
    astronaut: str,
    device_id: str,
    device_name: Optional[str],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    ts = now_iso()

    registry[device_id] = {
        "astronaut": astronaut,
        "device_name": device_name,
        "last_seen": time.time(),
        "last_seen_iso": ts,
    }

    out = {
        "astronaut": astronaut,
        "device_id": device_id,
        "device_name": device_name,
        "metrics": metrics,
        "ts": ts,
        "source": SOURCE,
    }

    topic = f"{MQTT_BASE}/{astronaut}"
    ok = mqtt_publish(topic, json.dumps(out))
    publish_connected_snapshot()

    return {
        "ok": True,
        "topic": topic,
        "ts": ts,
        "mqtt_connected": mqtt_is_connected(),
        "mqtt_published": ok,
    }


# ----------------------------
# Helper: detect external base URL correctly behind nginx prefix (/bio)
# ----------------------------
def external_base(request: Request, server_override: str = "") -> str:
    """
    Returns base like:
      http://192.168.31.238:8088/bio
    so the connect page can always POST to /bio/ingest.
    """
    if server_override and server_override.strip():
        return server_override.strip().rstrip("/")

    # Respect reverse proxy headers (nginx sets these)
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc

    # We are mounted behind nginx at /bio/*
    return f"{proto}://{host}/bio"


# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    return {
        "ok": True,
        "ts": now_iso(),
        "mqtt": f"{MQTT_BROKER}:{MQTT_PORT}",
        "mqtt_connected": mqtt_is_connected(),
    }


@app.get("/devices")
def devices():
    publish_connected_snapshot()
    cleanup_registry()
    return {
        "ts": now_iso(),
        "count": len(registry),
        "devices": [
            {
                "device_id": did,
                "astronaut": v.get("astronaut"),
                "device_name": v.get("device_name"),
                "last_seen": v.get("last_seen_iso"),
            }
            for did, v in registry.items()
        ],
    }


@app.get("/template")
def template():
    return {
        "astronaut": "astro1",
        "device_id": "A1-EXAMPLE-001",
        "device_name": "Wearable",
        "metrics": {
            "pulse": 76,
            "o2": 97,
            "systolic": 110,
            "diastolic": 72,
            "cbt": 96.6,
            "glucometer": 82,
            "steps": 1200,
            "calories": 110.5,
            "sleep_hours": 6.3,
        },
        "ts": now_iso(),
    }


@app.post("/ingest")
async def ingest(payload: Dict[str, Any], x_token: Optional[str] = Header(default=None)):
    require_token(x_token)

    astronaut = str(payload.get("astronaut", "")).strip()
    device_id = str(payload.get("device_id", "")).strip()
    device_name = str(payload.get("device_name", "")).strip() or None
    metrics = payload.get("metrics", {})

    if not astronaut:
        raise HTTPException(status_code=400, detail="astronaut is required")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")
    if not isinstance(metrics, dict) or not metrics:
        raise HTTPException(status_code=400, detail="metrics must be a non-empty object")

    return publish_bio(astronaut, device_id, device_name, metrics)


@app.post("/ingest_simple")
async def ingest_simple(payload: Dict[str, Any], x_token: Optional[str] = Header(default=None)):
    require_token(x_token)

    astronaut = str(payload.get("astronaut", "")).strip()
    device_id = str(payload.get("device_id", "")).strip()
    device_name = str(payload.get("device_name", "")).strip() or None

    if not astronaut:
        raise HTTPException(status_code=400, detail="astronaut is required")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")

    allowed = [
        "pulse",
        "o2",
        "systolic",
        "diastolic",
        "cbt",
        "glucometer",
        "steps",
        "calories",
        "sleep_hours",
        "distance_km",
        "active_minutes",
    ]

    metrics: Dict[str, Any] = {}
    for k in allowed:
        if k in payload and payload[k] is not None:
            metrics[k] = payload[k]

    if not metrics:
        raise HTTPException(status_code=400, detail="No metrics provided")

    return publish_bio(astronaut, device_id, device_name, metrics)


@app.get("/connect.json")
def connect_json(
    request: Request,
    astronaut: str = Query("astro1"),
    device_name: str = Query("Wearable"),
    device_id: str = Query(""),
    server: str = Query("", description="Base server URL (optional)"),
):
    did = device_id.strip() or f"PHONE-{int(time.time())}"
    astro = astronaut.strip() or "astro1"
    dname = device_name.strip() or "Wearable"
    base = external_base(request, server)

    return {
        "astronaut": astro,
        "device_name": dname,
        "device_id": did,
        "server": base,
        "post_url": f"{base}/ingest",
        "mqtt_topic": f"{MQTT_BASE}/{astro}",
        "ts": now_iso(),
    }


@app.get("/connect", response_class=HTMLResponse)
def connect_page(
    request: Request,
    astronaut: str = Query("astro1"),
    device_name: str = Query("Wearable"),
    device_id: str = Query(""),
    server: str = Query("", description="Base server URL (optional)"),
):
    did = device_id.strip() or f"PHONE-{int(time.time())}"
    astro = astronaut.strip() or "astro1"
    dname = device_name.strip() or "Wearable"

    # ✅ Base will be like: http://<host>:8088/bio (or vm ip)
    base = external_base(request, server)

    # IMPORTANT: use safe .format() template (not f-string)
    # - All JS braces are literal, no Python interpolation confusion.
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Connect Wearable</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: #0b0b0f;
      color: #fff;
      margin: 0;
      padding: 18px;
    }}
    .card {{
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 16px;
      padding: 16px;
      max-width: 720px;
      margin: 0 auto;
      box-shadow: 0 12px 40px rgba(0,0,0,0.4);
    }}
    .row {{ display:flex; gap:10px; flex-wrap:wrap; }}
    .row > div {{ flex: 1; min-width: 160px; }}
    label {{ font-size: 12px; color: rgba(255,255,255,0.75); display:block; margin-bottom:6px; }}
    input {{
      width: 100%;
      padding: 10px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(0,0,0,0.25);
      color: #fff;
      font-size: 14px;
    }}
    button {{
      padding: 12px 14px;
      border-radius: 14px;
      border: 0;
      background: #ff4d00;
      color: #fff;
      font-weight: 800;
      cursor: pointer;
    }}
    button.secondary {{
      background: rgba(255,255,255,0.10);
      border: 1px solid rgba(255,255,255,0.15);
      color: #fff;
      font-weight: 700;
    }}
    .muted {{ color: rgba(255,255,255,0.68); font-size: 12px; line-height: 1.55; }}
    .ok {{ color: #00ff9c; }}
    .bad {{ color: #ff6666; }}
    .spacer {{ height: 12px; }}
    .title {{ font-size: 18px; font-weight: 900; margin-bottom: 8px; }}
    .pill {{
      display:inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.12);
      font-size: 12px;
      margin-bottom: 10px;
    }}
    .hr {{ height:1px; background:rgba(255,255,255,0.12); margin:14px 0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="title">Wearable Check-in</div>
    <div class="pill">Target: <b>{astro}</b> • MQTT: <b>{mqtt}/{astro}</b></div>

    <div class="muted">
      Fill a few fields and tap <b>SEND</b>. No setup required.<br/>
      Posting to: <b id="post_to"></b>
    </div>

    <div class="hr"></div>

    <div class="row">
      <div>
        <label>Astronaut</label>
        <input id="astronaut" value="{astro}" />
      </div>
      <div>
        <label>Device Name</label>
        <input id="device_name" value="{dname}" placeholder="e.g. My Watch" />
      </div>
      <div>
        <label>Device ID</label>
        <input id="device_id" value="{did}" />
      </div>
    </div>

    <div class="spacer"></div>

    <div class="row">
      <div>
        <label>Pulse (bpm)</label>
        <input id="pulse" value="" inputmode="numeric" placeholder="e.g. 76" />
      </div>
      <div>
        <label>O₂ (%)</label>
        <input id="o2" value="" inputmode="numeric" placeholder="e.g. 97" />
      </div>
      <div>
        <label>Steps</label>
        <input id="steps" value="" inputmode="numeric" placeholder="e.g. 1200" />
      </div>
    </div>

    <div class="spacer"></div>

    <div class="row">
      <button id="send_once">SEND</button>
      <button id="start" class="secondary">Auto Send (5s)</button>
      <button id="stop" class="secondary">Stop</button>
    </div>

    <div class="spacer"></div>
    <div id="status" class="muted">Status: idle</div>

    <div class="spacer"></div>
    <div class="muted">
      MQTT status: <span id="mqtt_status"></span>
    </div>
  </div>

<script>
(function() {{
  const statusEl = document.getElementById("status");
  const mqttEl = document.getElementById("mqtt_status");
  const postToEl = document.getElementById("post_to");

  const BASE = "{base}";
  const POST_URL = BASE + "/ingest";
  postToEl.textContent = POST_URL;

  let timer = null;

  function num(v) {{
    if (v === "" || v === null || v === undefined) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }}

  async function refreshHealth() {{
    try {{
      const res = await fetch(BASE + "/health", {{ cache: "no-store" }});
      const j = await res.json();
      mqttEl.textContent = j.mqtt_connected ? "CONNECTED" : "CONNECTING...";
    }} catch {{
      mqttEl.textContent = "UNKNOWN";
    }}
  }}

  async function postIngest() {{
    const astronaut = document.getElementById("astronaut").value.trim() || "astro1";
    const device_name = document.getElementById("device_name").value.trim() || "Wearable";
    const device_id = document.getElementById("device_id").value.trim() || ("PHONE-" + Math.floor(Date.now()/1000));

    const metrics = {{
      pulse: num(document.getElementById("pulse").value),
      o2: num(document.getElementById("o2").value),
      steps: num(document.getElementById("steps").value),
    }};
    Object.keys(metrics).forEach(k => {{ if (metrics[k] === null) delete metrics[k]; }});

    if (!metrics || Object.keys(metrics).length === 0) {{
      statusEl.innerHTML = 'Status: <span class="bad">enter at least 1 value</span>';
      return;
    }}

    const payload = {{ astronaut, device_id, device_name, metrics }};

    try {{
      const res = await fetch(POST_URL, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});

      const text = await res.text();
      if (!res.ok) {{
        statusEl.innerHTML = 'Status: <span class="bad">error</span> ' + text;
        return;
      }}

      statusEl.innerHTML = 'Status: <span class="ok">sent</span> ' + new Date().toLocaleTimeString();
      refreshHealth();
    }} catch (e) {{
      statusEl.innerHTML = 'Status: <span class="bad">network error</span> ' + (e && e.message ? e.message : "");
    }}
  }}

  document.getElementById("send_once").addEventListener("click", () => postIngest());

  document.getElementById("start").addEventListener("click", async () => {{
    if (timer) return;
    await postIngest();
    timer = setInterval(() => postIngest(), 5000);
    statusEl.innerHTML = 'Status: <span class="ok">running</span>';
  }});

  document.getElementById("stop").addEventListener("click", () => {{
    if (timer) clearInterval(timer);
    timer = null;
    statusEl.innerHTML = 'Status: idle';
  }});

  refreshHealth();
  setInterval(refreshHealth, 5000);
}})();
</script>

</body>
</html>
""".format(
        astro=astro,
        did=did,
        dname=dname,
        mqtt=MQTT_BASE,
        base=base,
    )

    return HTMLResponse(content=html)
