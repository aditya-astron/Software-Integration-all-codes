import os
import time
import json
import mimetypes
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import uvicorn

# ===============================
# 🔧 CONFIGURATION
# ===============================
INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-secret-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "essie_org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "essie_telemetry")

MARS_DELAY_MIN = int(os.getenv("MARS_DELAY_MIN", 1))  # One-way light delay (minutes)
AUDIO_DIR = "./audio_logs"
os.makedirs(AUDIO_DIR, exist_ok=True)

SERVER_ROLE = os.getenv("SERVER_ROLE", "hab")  # "hab" or "mcc"

# ✅ Force correct MIME for audio webm (important for <audio>)
mimetypes.add_type("audio/webm", ".webm")
mimetypes.add_type("audio/webm", ".weba")

# ===============================
# 🚀 FASTAPI APP
# ===============================
app = FastAPI(
    title="EFN Comms Server",
    description="Earth–Mars EFN Communication Relay",
    version="1.3.1",
    openapi_version="3.1.0",
)

# --- Enable CORS so Dashboard can call APIs ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Serve audio via StaticFiles (supports Range requests properly)
app.mount("/audio_logs", StaticFiles(directory=AUDIO_DIR), name="audio_logs")

# --- InfluxDB Client ---
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)
query_api = client.query_api()

# ===============================
# 📘 DATA MODELS
# ===============================
class LogEntry(BaseModel):
    from_: str  # "hab" or "mcc"
    text: str = ""
    audio: str = ""

# ===============================
# 🌐 API ROUTES
# ===============================
@app.get("/")
def root():
    return {
        "message": f"EFN server ({SERVER_ROLE}) online",
        "time": datetime.utcnow().isoformat(),
    }

@app.get("/health")
def health():
    return {
        "status": "online",
        "server": SERVER_ROLE,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.post("/efn/log/submit")
async def submit_log(entry: LogEntry):
    if not entry.text and not entry.audio:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Empty log not allowed"})

    if entry.from_ not in ["hab", "mcc"]:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid role"})

    now = datetime.utcnow()
    deliver_after = now + timedelta(minutes=MARS_DELAY_MIN)

    payload = {
        "from": entry.from_,
        "text": entry.text,
        "audio": entry.audio,
        "deliver_after": int(deliver_after.timestamp()),
    }

    point = Point("efn_log").field("payload", json.dumps(payload)).time(now)
    write_api.write(bucket=INFLUX_BUCKET, record=point)

    print(f"[EFN:{SERVER_ROLE}] Received message from {entry.from_} (deliver after {deliver_after.isoformat()})")
    return {"status": "ok", "deliver_after": deliver_after.isoformat()}

@app.post("/efn/log/upload_audio")
async def upload_audio(file: UploadFile):
    """
    Upload audio and store under ./audio_logs.
    We keep .webm as canonical extension for MediaRecorder.
    """
    # Default extension
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in [".webm", ".weba"]:
        ext = ".webm"

    filename = f"{int(time.time())}{ext}"
    filepath = os.path.join(AUDIO_DIR, filename)

    try:
        with open(filepath, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        size = os.path.getsize(filepath)
        print(f"[EFN:{SERVER_ROLE}] Uploaded audio: {filename} ({size} bytes)")

        if size < 2000:
            os.remove(filepath)
            return JSONResponse(status_code=400, content={"status": "error", "message": "Audio too short or invalid"})

        return {"status": "ok", "filename": filename}

    except Exception as e:
        print(f"[EFN:{SERVER_ROLE}] Upload error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/efn/log/list")
async def list_logs():
    flux = f"""
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "efn_log")
      |> filter(fn: (r) => r._field == "payload")
      |> sort(columns: ["_time"], desc: true)
    """

    tables = query_api.query(flux)
    entries = []
    now_ts = int(datetime.utcnow().timestamp())

    for table in tables:
        for record in table.records:
            try:
                payload = json.loads(record["_value"])
            except Exception:
                continue

            deliver_after = payload.get("deliver_after", 0)
            if now_ts >= deliver_after:
                entries.append(
                    {
                        "time": record["_time"].isoformat(),
                        "from": payload.get("from", "unknown"),
                        "text": payload.get("text", ""),
                        "audio": payload.get("audio", ""),
                    }
                )

    unique = {(e["time"], e["from"], e["text"], e["audio"]): e for e in entries}
    return sorted(unique.values(), key=lambda e: e["time"])

# ===============================
# ▶️ RUN SERVER
# ===============================
if __name__ == "__main__":
    uvicorn.run("efn_server:app", host="0.0.0.0", port=8000, reload=False)
