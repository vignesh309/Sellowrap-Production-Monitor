#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Energy meter monitor: ELMEASURE LG+ 5310 behind a Waveshare RS485-to-Ethernet gateway.
Polls the meter every POLL_SECONDS and stores ONE reading per SAVE_INTERVAL_MINUTES
slot into energy_meter_readings. Sends a personal Telegram alert if the meter goes silent.
"""

import os
import sys
import time
import math
import struct
from datetime import datetime

import psycopg2
from pymodbus.client import ModbusTcpClient

# =========================================================
# PATH FIX: allow importing config / services from Backend
# =========================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, CHAT_ID
from services.telegram_notifier import send_telegram_message

DB_CONFIG = {
    "host": DB_HOST,
    "database": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD
}

# =========================================================
# METER CONFIGURATION
# =========================================================
METER_ID = 11                          # unique key stored in the table (test data already uses 1-10)
METER_NAME = "Hydraulic Press 1"       # reports filter by this name - don't rename it later
GATEWAY_IP = "192.168.3.51"
GATEWAY_PORT = 502
SLAVE_ID = 1                           # Modbus slave id on the RS-485 bus

START_ADDRESS = 100                    # meter register 40101 = PyModbus address 100
REGISTER_COUNT = 60                    # 30 float values x 2 registers

POLL_SECONDS = 60                      # how often the meter is read (health check + data)
SAVE_INTERVAL_MINUTES = 30             # one DB row per slot (must divide 60 evenly)
FAIL_ALERT_THRESHOLD = 3               # consecutive failed reads before the Telegram alert

# Order of the 30 floats in the meter's register block (2 registers each)
FIELDS = [
    "watts_total", "watts_r_phase", "watts_y_phase", "watts_b_phase",
    "var_total", "var_r_phase", "var_y_phase", "var_b_phase",
    "pf_average", "pf_r_phase", "pf_y_phase", "pf_b_phase",
    "va_total", "va_r_phase", "va_y_phase", "va_b_phase",
    "vll_average", "vry", "vyb", "vbr",
    "vln_average", "voltage_r_phase", "voltage_y_phase", "voltage_b_phase",
    "current_total", "current_r_phase", "current_y_phase", "current_b_phase",
    "frequency", "wh_received"
]

INSERT_COLUMNS = (
    ["meter_id", "meter_name", "gateway_ip", "record_date", "record_time", "recorded_at"]
    + FIELDS
    + ["kwh_received"]
)
INSERT_SQL = (
    f"INSERT INTO energy_meter_readings ({', '.join(INSERT_COLUMNS)}) "
    f"VALUES ({', '.join(['%s'] * len(INSERT_COLUMNS))})"
)


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# =========================================================
# MODBUS
# =========================================================
def decode_float(r1, r2):
    """LG+ 5310 uses word-swapped 32-bit floats."""
    raw = struct.pack(">HH", r2, r1)
    return struct.unpack(">f", raw)[0]


def connect():
    client = ModbusTcpClient(host=GATEWAY_IP, port=GATEWAY_PORT, timeout=3)
    if client.connect():
        return client
    client.close()
    return None


def read_meter(client):
    """Returns {field: value} or None if the read failed or returned bad data."""
    try:
        result = client.read_holding_registers(
            address=START_ADDRESS,
            count=REGISTER_COUNT,
            device_id=SLAVE_ID
        )
        if result.isError():
            log(f"Modbus error response: {result}")
            return None

        regs = result.registers
        if len(regs) < REGISTER_COUNT:
            log(f"Short response: {len(regs)} registers")
            return None

        values = {name: decode_float(regs[2 * i], regs[2 * i + 1]) for i, name in enumerate(FIELDS)}
    except Exception as e:
        log(f"Modbus read exception: {type(e).__name__}: {e}")
        return None

    if not all(math.isfinite(v) for v in values.values()):
        log("Meter returned NaN/Inf values - reading discarded")
        return None

    return values


# =========================================================
# DATABASE
# =========================================================
def slot_of(dt):
    """Start of the 30-minute slot a timestamp belongs to (e.g. 10:42 -> 10:30)."""
    return dt.replace(
        minute=(dt.minute // SAVE_INTERVAL_MINUTES) * SAVE_INTERVAL_MINUTES,
        second=0,
        microsecond=0
    )


def get_last_saved_slot():
    """On startup, find which slot was saved last so a restart doesn't duplicate it."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT MAX(recorded_at) FROM energy_meter_readings
            WHERE meter_id = %s AND meter_name = %s AND gateway_ip = %s
            """,
            (METER_ID, METER_NAME, GATEWAY_IP)
        )
        row = cur.fetchone()
        return slot_of(row[0]) if row and row[0] else None
    except Exception as e:
        log(f"Could not read last saved slot: {e}")
        return None
    finally:
        if conn:
            conn.close()


def save_reading(values, now):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        now = now.replace(microsecond=0)
        params = (
            [METER_ID, METER_NAME, GATEWAY_IP, now.date(), now.time(), now]
            + [values[f] for f in FIELDS]
            + [values["wh_received"] / 1000.0]
        )
        cur.execute(INSERT_SQL, params)
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        log(f"DB insert failed: {e}")
        return False
    finally:
        if conn:
            conn.close()


# =========================================================
# TELEGRAM ALERTS (personal chat)
# =========================================================
def send_alert(message):
    if not CHAT_ID:
        log("CHAT_ID is empty in .env - cannot send personal alert")
        return False
    try:
        return bool(send_telegram_message(message, target_chat=CHAT_ID))
    except Exception as e:
        log(f"Telegram send failed: {e}")
        return False


def fmt_duration(seconds):
    h, m = divmod(int(seconds // 60), 60)
    return f"{h}h {m}m" if h else f"{m}m"


# =========================================================
# MAIN LOOP
# =========================================================
def main():
    log(f"Energy meter monitor started: {METER_NAME} (meter_id {METER_ID}) "
        f"via {GATEWAY_IP}:{GATEWAY_PORT}, slave {SLAVE_ID}")

    last_slot = get_last_saved_slot()
    client = None
    fail_count = 0
    down_since = None
    alert_sent = False

    try:
        while True:
            if client is None:
                client = connect()

            values = read_meter(client) if client else None

            if values is None:
                fail_count += 1
                if fail_count == 1:
                    down_since = datetime.now()
                log(f"Meter read failed ({fail_count} in a row)")

                # Drop the connection so the next cycle reconnects cleanly
                if client is not None:
                    client.close()
                    client = None

                if fail_count >= FAIL_ALERT_THRESHOLD and not alert_sent:
                    alert_sent = send_alert(
                        f"🔴 <b>Energy meter OFFLINE</b>\n\n"
                        f"• <b>{METER_NAME}</b> ({GATEWAY_IP}, slave {SLAVE_ID})\n"
                        f"• No response since {down_since.strftime('%d-%b %H:%M:%S')}"
                    )
            else:
                if alert_sent:
                    send_alert(
                        f"🟢 <b>Energy meter ONLINE</b>\n\n"
                        f"• <b>{METER_NAME}</b> is responding again "
                        f"(was down {fmt_duration((datetime.now() - down_since).total_seconds())})"
                    )
                fail_count = 0
                down_since = None
                alert_sent = False

                now = datetime.now()
                slot = slot_of(now)
                if slot != last_slot:
                    if save_reading(values, now):
                        last_slot = slot
                        log(f"Saved reading for slot {slot.strftime('%H:%M')} | "
                            f"{values['watts_total'] / 1000:.2f} kW | "
                            f"{values['wh_received'] / 1000:,.1f} kWh")

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        log("Stopping energy meter monitor...")
    finally:
        if client is not None:
            client.close()
        log("Connection closed.")


if __name__ == "__main__":
    main()