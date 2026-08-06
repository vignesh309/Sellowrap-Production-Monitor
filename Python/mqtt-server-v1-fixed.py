import json
import logging
from datetime import datetime

import psycopg2
import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

IDLE_THRESHOLD = 30
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
MQTT_TOPIC = 'Sellowrap_Database/button'
DB_CONFIG = {
    'host': 'localhost',
    'user': 'postgres',
    'password': 'Password123',
}


def connect_db(database_name):
    return psycopg2.connect(database=database_name, **DB_CONFIG)


conn_sellowrap = connect_db('Sellowrap_Database')
cursor_sellowrap = conn_sellowrap.cursor()
conn_ads = connect_db('ADS_Database')
cursor_ads = conn_ads.cursor()


def on_connect(client, userdata, flags, rc):
    logging.info('Connected to MQTT broker with result code %s', rc)
    client.subscribe(MQTT_TOPIC, qos=1)
    logging.info('Subscribed to topic %s', MQTT_TOPIC)


def parse_event(payload):
    data = json.loads(payload.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('MQTT payload is not a JSON object')

    machine_code = data.get('machine_code')
    timestamp = data.get('timestamp')
    if not machine_code or not timestamp:
        raise ValueError('Missing required fields: machine_code or timestamp')

    event_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    return machine_code, event_time


def calculate_cycle_seconds(cursor, machine_code):
    cursor.execute(
        '''
        SELECT event_time
        FROM machine_events
        WHERE machine_code = %s
        ORDER BY event_time DESC
        LIMIT 2
        ''',
        (machine_code,),
    )
    rows = cursor.fetchall()
    if len(rows) < 2:
        return 0

    latest, previous = rows[0][0], rows[1][0]
    return max(0, (latest - previous).total_seconds())


def on_message(client, userdata, msg):
    try:
        machine_code, event_time = parse_event(msg.payload)
        logging.info('Received event for machine %s at %s', machine_code, event_time)

        sql_insert_event = '''
        INSERT INTO machine_events (machine_code, event_time)
        VALUES (%s, %s)
        '''
        cursor_sellowrap.execute(sql_insert_event, (machine_code, event_time))
        cursor_ads.execute(sql_insert_event, (machine_code, event_time))

        cycle_sec = calculate_cycle_seconds(cursor_sellowrap, machine_code)
        runtime_add = cycle_sec if 0 < cycle_sec <= IDLE_THRESHOLD else 0
        idle_add = cycle_sec if cycle_sec > IDLE_THRESHOLD else 0

        summary_date = event_time.date()
        hour_no = event_time.hour

        sql_upsert_summary = '''
        INSERT INTO machine_hourly_summary (
            machine_code,
            summary_date,
            hour_no,
            start_time,
            stop_time,
            part_count,
            avg_cycle_sec,
            min_cycle_sec,
            max_cycle_sec,
            runtime_sec,
            idle_sec,
            machine_status
        ) VALUES (
            %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, 'RUNNING'
        )
        ON CONFLICT (machine_code, summary_date, hour_no)
        DO UPDATE SET
            stop_time = EXCLUDED.stop_time,
            part_count = machine_hourly_summary.part_count + 1,
            min_cycle_sec = LEAST(machine_hourly_summary.min_cycle_sec, EXCLUDED.min_cycle_sec),
            max_cycle_sec = GREATEST(machine_hourly_summary.max_cycle_sec, EXCLUDED.max_cycle_sec),
            runtime_sec = machine_hourly_summary.runtime_sec + EXCLUDED.runtime_sec,
            idle_sec = machine_hourly_summary.idle_sec + EXCLUDED.idle_sec,
            updated_time = CURRENT_TIMESTAMP
        '''

        summary_args = (
            machine_code,
            summary_date,
            hour_no,
            event_time,
            event_time,
            cycle_sec,
            cycle_sec,
            cycle_sec,
            runtime_add,
            idle_add,
        )

        cursor_sellowrap.execute(sql_upsert_summary, summary_args)
        cursor_ads.execute(sql_upsert_summary, summary_args)

        sql_update_avg = '''
        UPDATE machine_hourly_summary
        SET avg_cycle_sec = CASE
            WHEN part_count > 1 THEN (runtime_sec + idle_sec)::numeric / (part_count - 1)
            ELSE 0
        END
        WHERE machine_code = %s AND summary_date = %s AND hour_no = %s
        '''

        cursor_sellowrap.execute(sql_update_avg, (machine_code, summary_date, hour_no))
        cursor_ads.execute(sql_update_avg, (machine_code, summary_date, hour_no))

        conn_sellowrap.commit()
        conn_ads.commit()

        logging.info('Saved event to both databases | cycle=%s seconds', cycle_sec)

    except Exception:
        conn_sellowrap.rollback()
        conn_ads.rollback()
        logging.exception('Failed to process MQTT message')


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    logging.info('MQTT listener started and connecting to %s:%s', MQTT_BROKER, MQTT_PORT)
    client.loop_forever()


if __name__ == '__main__':
    main()
