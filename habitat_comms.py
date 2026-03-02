import socket
import threading
import time
import json
import random
import sounddevice as sd
import numpy as np
import argparse
import sys
import queue
import os
import wave
import base64
from datetime import datetime

# ----------------------------
# CONFIG
# ----------------------------
TELEMETRY_PORT = 5000
VOICE_PORT = 6000
EFN_PORT = 7000

DELAY = 5           # telemetry delay
MARS_DELAY = 1200   # 20 minutes
HOST = "127.0.0.1"

AUDIO_DIR = "audio_logs"
os.makedirs(AUDIO_DIR, exist_ok=True)


# ----------------------------
# UTILS
# ----------------------------
def save_audio_file(data: np.ndarray, role: str) -> str:
    """Save audio chunk to WAV and return file path (base64 inline optional)."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{AUDIO_DIR}/efn_{role}_{ts}.wav"

    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(44100)
        wf.writeframes(data.tobytes())

    return filename


# ----------------------------
# TELEMETRY
# ----------------------------
def telemetry_send(sock, role):
    while True:
        telemetry = {
            "sensor_id": f"EFN_Comms_{role}",
            "box": "EFN",
            "timestamp": time.time(),
            "O2_level": round(random.uniform(19, 21), 2),
            "CO2_level": round(random.uniform(0.03, 0.07), 3),
            "Temperature": round(random.uniform(20, 24), 1),
            "voice_status": "connected"
        }
        msg = json.dumps(telemetry).encode()
        time.sleep(DELAY)
        try:
            sock.sendall(msg + b"\n")
            print(json.dumps(telemetry), flush=True)
            print(f"[Telemetry-{role}] Sent:", telemetry)
        except Exception as e:
            print(f"[Telemetry-{role}] Error sending: {e}", file=sys.stderr)
            break


def telemetry_receive(sock, role):
    buffer = ""
    while True:
        try:
            data = sock.recv(1024).decode()
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    telemetry = json.loads(line.strip())
                    telemetry["sensor_id"] = f"EFN_Comms_{role}"
                    telemetry["box"] = "EFN"
                    print(json.dumps(telemetry), flush=True)
                    print(f"[Telemetry-{role}] Received:", telemetry)
                except json.JSONDecodeError:
                    print(f"[Telemetry-{role}] Malformed data:", line.strip())
        except Exception as e:
            print(f"[Telemetry-{role}] Error receiving: {e}", file=sys.stderr)
            break


# ----------------------------
# EFN TEXT + AUDIO
# ----------------------------
def efn_send(sock, role):
    """Send EFN text or audio memos with Mars delay."""
    while True:
        choice = input(f"[EFN-{role}] (T)ext or (A)udio? ").strip().lower()
        if choice == "t":
            note = input(f"[EFN-{role}] Enter note: ").strip()
            if not note:
                continue

            packet = {
                "sensor_id": f"EFN_Log_{role}",
                "box": "EFN",
                "timestamp": time.time(),
                "from": role,
                "type": "text",
                "note": note,
                "status": "Pending"
            }

        elif choice == "a":
            print(f"[EFN-{role}] Recording 5s audio memo...")
            duration = 5
            audio = sd.rec(int(duration * 44100), samplerate=44100, channels=1, dtype='int16')
            sd.wait()
            filename = save_audio_file(audio, role)

            packet = {
                "sensor_id": f"EFN_Log_{role}",
                "box": "EFN",
                "timestamp": time.time(),
                "from": role,
                "type": "audio",
                "note": "Audio memo",
                "file": filename,
                "status": "Pending"
            }

        else:
            continue

        def delayed_send(p):
            time.sleep(MARS_DELAY)
            p["status"] = "Delivered"
            try:
                sock.sendall((json.dumps(p) + "\n").encode())
                print(json.dumps(p), flush=True)
                print(f"[EFN-{role}] Delivered after {MARS_DELAY}s:", p)
            except Exception as e:
                print(f"[EFN-{role}] Send error: {e}", file=sys.stderr)

        threading.Thread(target=delayed_send, args=(packet,), daemon=True).start()
        print(f"[EFN-{role}] Queued with delay:", packet)


def efn_receive(sock, role):
    buffer = ""
    while True:
        try:
            data = sock.recv(4096).decode()
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    efn = json.loads(line.strip())
                    print(json.dumps(efn), flush=True)

                    if efn.get("type") == "audio" and "file" in efn:
                        print(f"[EFN-{role}] Received Audio Memo -> {efn['file']}")
                    else:
                        print(f"[EFN-{role}] Received:", efn)

                except json.JSONDecodeError:
                    print(f"[EFN-{role}] Malformed EFN:", line.strip())
        except Exception as e:
            print(f"[EFN-{role}] Error receiving: {e}", file=sys.stderr)
            break


# ----------------------------
# CONNECTION HANDLERS
# ----------------------------
def run_server(mic_index, speaker_index):
    telem_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    telem_srv.bind((HOST, TELEMETRY_PORT))
    telem_srv.listen(1)
    telem_conn, _ = telem_srv.accept()
    print("[Telemetry] Connected")

    voice_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    voice_srv.bind((HOST, VOICE_PORT))
    voice_srv.listen(1)
    voice_conn, _ = voice_srv.accept()
    print("[Voice] Connected")

    efn_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    efn_srv.bind((HOST, EFN_PORT))
    efn_srv.listen(1)
    efn_conn, _ = efn_srv.accept()
    print("[EFN] Connected")

    threading.Thread(target=telemetry_send, args=(telem_conn, "Server"), daemon=True).start()
    threading.Thread(target=telemetry_receive, args=(telem_conn, "Server"), daemon=True).start()
    threading.Thread(target=efn_send, args=(efn_conn, "Server"), daemon=True).start()
    threading.Thread(target=efn_receive, args=(efn_conn, "Server"), daemon=True).start()

    while True:
        time.sleep(1)


def run_client(mic_index, speaker_index):
    telem_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    telem_conn.connect((HOST, TELEMETRY_PORT))
    print("[Telemetry] Connected to server")

    voice_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    voice_conn.connect((HOST, VOICE_PORT))
    print("[Voice] Connected to server")

    efn_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    efn_conn.connect((HOST, EFN_PORT))
    print("[EFN] Connected to server")

    threading.Thread(target=telemetry_send, args=(telem_conn, "Client"), daemon=True).start()
    threading.Thread(target=telemetry_receive, args=(telem_conn, "Client"), daemon=True).start()
    threading.Thread(target=efn_send, args=(efn_conn, "Client"), daemon=True).start()
    threading.Thread(target=efn_receive, args=(efn_conn, "Client"), daemon=True).start()

    while True:
        time.sleep(1)


# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Habitat Analog Mission Comms + EFN with Mars Delay")
    parser.add_argument("mode", choices=["server", "client"], help="Run as server (ground) or client (crew)")
    args = parser.parse_args()

    print("\n[Audio Devices] Available devices:")
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        io = []
        if dev['max_input_channels'] > 0:
            io.append("Input")
        if dev['max_output_channels'] > 0:
            io.append("Output")
        print(f"  {idx}: {dev['name']} ({'/'.join(io)})")

    try:
        mic_index = input("\nSelect Microphone device index (Enter for default): ")
        mic_index = int(mic_index) if mic_index.strip() != "" else None
    except:
        mic_index = None

    try:
        spk_index = input("Select Speaker device index (Enter for default): ")
        spk_index = int(spk_index) if spk_index.strip() != "" else None
    except:
        spk_index = None

    if args.mode == "server":
        run_server(mic_index, spk_index)
    elif args.mode == "client":
        run_client(mic_index, spk_index)
