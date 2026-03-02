import sys
from redundancy_manager import choose_channel

def run_router():
    for line in sys.stdin:
        encrypted_packet = line.strip()
        if not encrypted_packet:
            continue

        channel = choose_channel()
        # Send logs to stderr (so console shows them, but packets stay clean)
        print(f"[COMMS] Sending packet via {channel.upper()}", file=sys.stderr)
        # Forward only the encrypted packet downstream
        sys.stdout.write(encrypted_packet + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    run_router()
