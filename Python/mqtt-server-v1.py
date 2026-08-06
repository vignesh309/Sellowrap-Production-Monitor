import json
import psycopg2
import paho.mqtt.client as mqtt
from datetime import datetime

IDLE_THRESHOLD = 30

# --------------------------------------------------
# ESTABLISH BOTH DATABASE CONNECTIONS
# --------------------------------------------------

# Connection 1: Sellowrap_Database
conn_sellowrap = psycopg2.connect(
    host="localhost",
    database="Sellowrap_Database",
    user="postgres",
    password="Password123"
)
cursor_sellowrap = conn_sellowrap.cursor()

# Connection 2: ADS_Database
conn_ads = psycopg2.connect(
    host="localhost",
    database="ADS_Database",
    user="postgres",
    password="Password123"
)
cursor_ads = conn_ads.cursor()

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        machine_code = data["machine_code"]
        event_time = datetime.strptime(
            data["timestamp"],
            "%Y-%m-%d %H:%M:%S"
        )

        print("\n================================")
        print("Machine :", machine_code)
        print("Time    :", event_time)
        print("================================")

        # --------------------------------------------------
        # SAVE RAW EVENT TO BOTH DATABASES
        # --------------------------------------------------
        sql_insert_event = """
        INSERT INTO machine_events (machine_code, event_time)
        VALUES (%s, %s)
        """

        cursor_sellowrap.execute(sql_insert_event, (machine_code, event_time))
        cursor_ads.execute(sql_insert_event, (machine_code, event_time))

        # --------------------------------------------------
        # GET PREVIOUS EVENT (From Sellowrap to calculate cycle)
        # --------------------------------------------------
        cursor_sellowrap.execute("""
        SELECT event_time
        FROM machine_events
        WHERE machine_code=%s
        ORDER BY event_time DESC
        LIMIT 2
        """, (machine_code,))

        rows = cursor_sellowrap.fetchall()
        cycle_sec = 0

        if len(rows) >= 2:
            latest = rows[0][0]
            previous = rows[1][0]
            cycle_sec = (latest - previous).total_seconds()

        # --------------------------------------------------
        # RUNTIME / IDLE CALCULATIONS
        # --------------------------------------------------
        runtime_add = 0
        idle_add = 0

        if cycle_sec > 0:
            if cycle_sec <= IDLE_THRESHOLD:
                runtime_add = cycle_sec
            else:
                idle_add = cycle_sec

        summary_date = event_time.date()
        hour_no = event_time.hour

        # --------------------------------------------------
        # UPSERT SUMMARY RECORD IN BOTH DATABASES
        # --------------------------------------------------
        sql_upsert_summary = """
        INSERT INTO machine_hourly_summary
        (
            machine_code, summary_date, hour_no,
            start_time, stop_time, part_count,
            avg_cycle_sec, min_cycle_sec, max_cycle_sec,
            runtime_sec, idle_sec, machine_status
        )
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, 'RUNNING')
        ON CONFLICT (machine_code, summary_date, hour_no)
        DO UPDATE SET
            stop_time = EXCLUDED.stop_time,
            part_count = machine_hourly_summary.part_count + 1,
            min_cycle_sec = LEAST(machine_hourly_summary.min_cycle_sec, EXCLUDED.min_cycle_sec),
            max_cycle_sec = GREATEST(machine_hourly_summary.max_cycle_sec, EXCLUDED.max_cycle_sec),
            runtime_sec = machine_hourly_summary.runtime_sec + EXCLUDED.runtime_sec,
            idle_sec = machine_hourly_summary.idle_sec + EXCLUDED.idle_sec,
            updated_time = CURRENT_TIMESTAMP
        """

        summary_args = (
            machine_code, summary_date, hour_no,
            event_time, event_time,
            cycle_sec, cycle_sec, cycle_sec,
            runtime_add, idle_add
        )

        cursor_sellowrap.execute(sql_upsert_summary, summary_args)
        cursor_ads.execute(sql_upsert_summary, summary_args)

        # --------------------------------------------------
        # UPDATE AVERAGE CYCLE IN BOTH DATABASES
        # --------------------------------------------------
        sql_update_avg = """
        UPDATE machine_hourly_summary
        SET avg_cycle_sec =
        CASE
            WHEN part_count > 1
            THEN (runtime_sec + idle_sec)::numeric / (part_count - 1)
            ELSE 0
        END
        WHERE machine_code=%s AND summary_date=%s AND hour_no=%s
        """

        update_args = (machine_code, summary_date, hour_no)

        cursor_sellowrap.execute(sql_update_avg, update_args)
        cursor_ads.execute(sql_update_avg, update_args)

        # --------------------------------------------------
        # COMMIT BOTH TRANSACTIONS
        # --------------------------------------------------
        conn_sellowrap.commit()
        conn_ads.commit()

        print(f"Part Saved to Both DBs | Cycle={cycle_sec}s")

    except Exception as e:
        # Rollback both in case of failure to keep data synced
        conn_sellowrap.rollback()
        conn_ads.rollback()
        print("ERROR:", e)

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
)
client.on_message = on_message
client.connect("localhost", 1883, 60)
client.subscribe("Sellowrap_Database/button", qos=1)

print("MQTT Dual-Database Listener Started")
client.loop_forever()