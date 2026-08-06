import json
import sqlite3
import time
from datetime import datetime
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

# ==========================
# CONFIGURATION
# ==========================
MACHINE_CODE = "MC002"

BUTTON_PIN = 27

MQTT_BROKER = "192.168.5.10"
MQTT_PORT = 1883
MQTT_TOPIC = "ADS_Database/button"

# ==========================
# DEBOUNCE CONFIG
# ==========================
DEBOUNCE_TIME = 0.8
last_trigger_time = 0

# ==========================
# SQLITE SETUP
# ==========================
db = sqlite3.connect("machine.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_name TEXT,
    timestamp TEXT,
    sent INTEGER DEFAULT 0
)
""")
db.commit()

# ==========================
# MQTT CLIENT SETUP
# ==========================
client = mqtt.Client()

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    print("Connected to MQTT Broker")
except Exception as e:
    print(f"MQTT Initial Connection Failed (Will retry in background): {e}")

# ==========================
# GPIO SETUP
# ==========================
try:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(
        BUTTON_PIN,
        GPIO.IN,
        pull_up_down=GPIO.PUD_UP
    )

    print("================================")
    print("GPIO Trigger Logger Started")
    print("Machine Code :", MACHINE_CODE)
    print("GPIO Pin     :", BUTTON_PIN)
    print("================================")

except Exception as e:
    print("GPIO Setup Error:", e)
    db.close()
    exit()

# Read initial state
last_state = GPIO.input(BUTTON_PIN)

print("Initial State =", last_state)

# ==========================
# MAIN LOOP
# ==========================
try:
    while True:

        state = GPIO.input(BUTTON_PIN)

        if state != last_state:
            print(f"GPIO Changed: {last_state} -> {state}")

        # Falling Edge Detection
        # PUD_UP means:
        # Released = 1
        # Pressed  = 0
        if state == 0 and last_state == 1:

            now = time.time()

            # Debounce
            if now - last_trigger_time < DEBOUNCE_TIME:
                last_state = state
                time.sleep(0.05)
                continue

            last_trigger_time = now

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Save locally
            cursor.execute("""
                INSERT INTO events
                (machine_name, timestamp, sent)
                VALUES (?, ?, 0)
            """, (MACHINE_CODE, ts))

            db.commit()
            row_id = cursor.lastrowid

            print("================================")
            print("TRIGGER RECEIVED")
            print("Machine Code :", MACHINE_CODE)
            print("Time         :", ts)
            print("Saved to SQLite")

            payload = {
                "machine_code": MACHINE_CODE,
                "timestamp": ts
            }

            # Publish MQTT
            try:
                result = client.publish(
                    MQTT_TOPIC,
                    json.dumps(payload),
                    qos=1
                )

                result.wait_for_publish()

                cursor.execute(
                    "UPDATE events SET sent = 1 WHERE id = ?",
                    (row_id,)
                )
                db.commit()

                print("Published to MQTT successfully")

            except Exception as mqtt_error:
                print(
                    f"MQTT Publish Failed "
                    f"(Stored locally instead): {mqtt_error}"
                )

            print("================================")

        last_state = state
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nProgram Stopped")

finally:
    GPIO.cleanup()
    client.loop_stop()
    client.disconnect()
    db.close()