import os
import sys
from datetime import datetime
import json
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import psycopg2
from typing import Optional
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_USER

# --------------------------------------------------
# DATABASE HELPER & TABLE CREATION
# --------------------------------------------------
def get_db_connection():
  """Creates a fresh database connection to avoid dropped connection errors."""
  return psycopg2.connect(
      host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
  )


def ensure_monthly_table_exists(dt: Optional[datetime] = None):
  """Proactively creates the monthly table and index if they don't exist."""
  if dt is None:
    dt = datetime.now()

  month_suffix = dt.strftime("%m_%Y")
  table_name = f"machine_events_{month_suffix}"

  conn = None
  try:
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Create Table
    create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            machine_code VARCHAR(50),
            event_time TIMESTAMP
        );
        """
    cursor.execute(create_table_sql)

    # 2. Create Index
    create_index_sql = f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_mc_et 
        ON {table_name}(machine_code, event_time DESC);
        """
    cursor.execute(create_index_sql)

    conn.commit()
    print(f"🛠️  Table structure verified: {table_name}")
    return table_name

  except Exception as e:
    if conn:
      conn.rollback()
    print(f"❌ Failed to ensure table {table_name}:", e)
    return table_name
  finally:
    if conn:
      conn.close()


# --------------------------------------------------
# MQTT CALLBACKS
# --------------------------------------------------
def on_message(client, userdata, msg):
  conn = None
  try:
    data = json.loads(msg.payload.decode())

    machine_code = data["machine_code"]
    event_time = datetime.strptime(data["timestamp"], "%Y-%m-%d %H:%M:%S")

    print("\n================================")
    print("Machine :", machine_code)
    print("Time    :", event_time)
    print("================================")

    # Ensure table exists for this event's month
    table_name = ensure_monthly_table_exists(event_time)

    # Insert event
    conn = get_db_connection()
    cursor = conn.cursor()

    sql_insert_event = f"""
        INSERT INTO {table_name} (machine_code, event_time)
        VALUES (%s, %s)
        """
    cursor.execute(sql_insert_event, (machine_code, event_time))
    conn.commit()

    print(f"✅ Trigger Saved | Table: {table_name}")

  except Exception as e:
    if conn:
      conn.rollback()
    print("❌ ERROR in on_message:", e)
  finally:
    if conn:
      conn.close()


# --------------------------------------------------
# INITIALIZATION & STARTUP
# --------------------------------------------------
# Ensure current month table exists right now when script starts
print("🚀 Initializing Sellowrap MQTT Listener...")
ensure_monthly_table_exists(datetime.now())

client = mqtt.Client(
    callback_api_version=CallbackAPIVersion.VERSION2,
    client_id="Sellowrap_Windows_Server",
    clean_session=False,
)
client.on_message = on_message
client.connect("200.200.210.249", 1883, 60)
client.subscribe("Sellowrap_Database/button", qos=1)

print("🔌 MQTT Sellowrap-Database Listener Started (Raw Events Only)")
client.loop_forever()