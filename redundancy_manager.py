import random

def choose_channel():
    """
    Simulate channel availability.
    Fiber > Acoustic > LoRa
    """
    # Simulated link quality (random for demo)
    links = {
        "fiber": random.choice([True, True, True, False]),   # 75% uptime
        "acoustic": random.choice([True, False]),            # 50% uptime
        "lora": True                                         # Always available
    }

    if links["fiber"]:
        return "fiber"
    elif links["acoustic"]:
        return "acoustic"
    else:
        return "lora"
