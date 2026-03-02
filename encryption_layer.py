import sys
import json
from cryptography.fernet import Fernet

KEY_FILE = "encryption_key.key"

def load_or_create_key():
    """Load existing key or generate a new one if not found."""
    try:
        with open(KEY_FILE, "rb") as f:
            return f.read()
    except FileNotFoundError:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key

def run_encryption():
    key = load_or_create_key()
    cipher = Fernet(key)

    for line in sys.stdin:
        try:
            packet = json.loads(line.strip())
            raw_data = json.dumps(packet).encode("utf-8")

            # Encrypt telemetry (Fernet output is already base64-safe bytes)
            encrypted_data = cipher.encrypt(raw_data)

            # Forward as UTF-8 string
            sys.stdout.write(encrypted_data.decode("utf-8") + "\n")
            sys.stdout.flush()
        except Exception as e:
            print(f"[ENCRYPTION] Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    run_encryption()
