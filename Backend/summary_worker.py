import psycopg2
import time
from datetime import datetime

# 🚨 Import the database variables from your config.py file
from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD

IDLE_THRESHOLD = 120

def calculate_hourly_summary():
    # 🚨 Pylance Fix: Declare variables as None before the try block
    conn = None
    cursor = None
    
    # --------------------------------------------------
    # ESTABLISH DATABASE CONNECTION
    # --------------------------------------------------
    try:
        # 🚨 Replaced hardcoded credentials with config variables
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()

        now = datetime.now()
        today_date = now.date()
        month_suffix = now.strftime("%m_%Y")
        table_name = f"machine_events_{month_suffix}"

        # --------------------------------------------------
        # CHECK IF TABLE EXISTS 
        # --------------------------------------------------
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, (table_name,))
        
        # 🚨 Pylance Fix: Safely fetch the result 
        result = cursor.fetchone()
        
        if result is None or not result[0]:
            print(f"[{now.strftime('%H:%M:%S')}] Table {table_name} does not exist yet. Waiting...")
            return

        # --------------------------------------------------
        # THE "FULL-DAY" OFFLINE CATCH-UP QUERY
        # --------------------------------------------------
        sql_batch_process = f"""
        WITH EventDifferences AS (
            SELECT
                machine_code,
                event_time,
                EXTRACT(EPOCH FROM (event_time - LAG(event_time) OVER (PARTITION BY machine_code ORDER BY event_time))) AS cycle_sec
            FROM {table_name}
            WHERE DATE(event_time) = %s 
        ),
        DailyHourlyData AS (
            SELECT
                machine_code,
                EXTRACT(HOUR FROM event_time) AS hour_no,
                MIN(event_time) AS start_time,
                MAX(event_time) AS stop_time,
                COUNT(event_time) AS part_count,
                COALESCE(MIN(cycle_sec), 0) AS min_cycle_sec,
                COALESCE(MAX(cycle_sec), 0) AS max_cycle_sec,
                COALESCE(SUM(CASE WHEN cycle_sec <= {IDLE_THRESHOLD} THEN cycle_sec ELSE 0 END), 0) AS runtime_sec,
                COALESCE(SUM(CASE WHEN cycle_sec > {IDLE_THRESHOLD} THEN cycle_sec ELSE 0 END), 0) AS idle_sec
            FROM EventDifferences
            GROUP BY machine_code, EXTRACT(HOUR FROM event_time)
        )
        INSERT INTO machine_hourly_summary (
            machine_code, summary_date, hour_no,
            start_time, stop_time, part_count,
            min_cycle_sec, max_cycle_sec, runtime_sec, idle_sec, machine_status, avg_cycle_sec
        )
        SELECT
            machine_code, %s, hour_no,
            start_time, stop_time, part_count,
            min_cycle_sec, max_cycle_sec, runtime_sec, idle_sec, 'RUNNING',
            CASE WHEN (part_count - 1) > 0 THEN (runtime_sec + idle_sec) / (part_count - 1) ELSE 0 END
        FROM DailyHourlyData
        ON CONFLICT (machine_code, summary_date, hour_no)
        DO UPDATE SET
            stop_time = EXCLUDED.stop_time,
            part_count = EXCLUDED.part_count,
            min_cycle_sec = EXCLUDED.min_cycle_sec,
            max_cycle_sec = EXCLUDED.max_cycle_sec,
            runtime_sec = EXCLUDED.runtime_sec,
            idle_sec = EXCLUDED.idle_sec,
            avg_cycle_sec = EXCLUDED.avg_cycle_sec,
            updated_time = CURRENT_TIMESTAMP;
        """

        cursor.execute(sql_batch_process, (today_date, today_date))
        conn.commit()

    except Exception as e:
        print(f"❌ Worker Error: {e}")
        
    finally:
        # 🚨 Pylance Fix: Safely close connections
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

# --------------------------------------------------
# INFINITE 15-SECOND LOOP
# --------------------------------------------------
def start_summary_worker():
    """Runs the infinite 15-second loop safely in the background."""
    print("⚙️ Full-Day Sync Worker Started in Background...")
    while True:
        calculate_hourly_summary()
        time.sleep(15)

if __name__ == "__main__":
    start_summary_worker()