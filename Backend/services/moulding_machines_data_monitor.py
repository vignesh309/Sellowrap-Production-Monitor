#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import queue
import time
import csv
import os
import re
from datetime import datetime
import subprocess
import sys

# =========================================================
# PATH FIX: Allow importing config from parent Backend folder
# =========================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from services.logging_setup import configure_service_logging

configure_service_logging("moulding")

import psycopg2
from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, CHAT_ID
from services.telegram_notifier import send_telegram_message

# =========================================================
# DYNAMIC DATABASE CONFIGURATION
# =========================================================
DB_CONFIG = {
    "host": DB_HOST,
    "database": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD
}

KNOWN_TABLES = set()
DB_LOCK = threading.Lock()

# Cache to store both mold_no and part_number from Factor 46
MACHINE_MOLD_CACHE = {}

# =========================
# MACHINE CONFIGURATION
# =========================
MACHINES = [
    {"ip": "192.168.3.157", "port": 8200, "name": "IM01-850T"},
    {"ip": "192.168.3.153", "port": 8200, "name": "IM02-350T-1"},
    {"ip": "192.168.3.163", "port": 8200, "name": "IM03-280T-1"},
    {"ip": "200.200.210.239", "port": 8200, "name": "IM04-130T"},
    {"ip": "192.168.3.155", "port": 8200, "name": "IM05-100T-1"},
    {"ip": "192.168.3.164", "port": 8200, "name": "IM06-80T-1"},
    {"ip": "192.168.3.156", "port": 8200, "name": "IM07-550T"},
    {"ip": "192.168.3.161", "port": 8200, "name": "IM08-80T-2"},
    {"ip": "192.168.3.162", "port": 8200, "name": "IM09-80T-3"},
    {"ip": "192.168.3.154", "port": 8200, "name": "IM10-180T-1"},
    {"ip": "192.168.3.150", "port": 8200, "name": "IM11-100T-2"},
    {"ip": "192.168.3.165", "port": 8200, "name": "IM12-350T-2"},
    {"ip": "192.168.3.169", "port": 8200, "name": "IM13-280T-2"},
    {"ip": "192.168.3.168", "port": 8200, "name": "IM14-180T-2"},
    {"ip": "192.168.3.167", "port": 8200, "name": "IM15-50T"},
    {"ip": "192.168.3.166", "port": 8200, "name": "IM16-280T-3"},
    {"ip": "192.168.3.170", "port": 8200, "name": "IM19-350T-5"}
]

ENCODING = "shift_jis"
CONNECT_TIMEOUT = 10
SOCKET_TIMEOUT = 1
XON_INTERVAL = 60.0
STATUS_INTERVAL = 900.0  # 15 minutes

XON = b'\x11'
CR = b'\r'
ANSWER = {35: 36, 37: 38, 45: 46, 47: 48, 48: 48, 50: 51}

# =========================
# COLORS & UTILS
# =========================
try:
    subprocess.run("", shell=True, check=False)
except Exception:
    pass

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

def checksum(data: bytes):
    total = 0
    started = False
    for b in data:
        if started:
            total += b
        elif b == ord(','):
            total += b
            started = True
    total &= 0xFF
    hi = (total >> 4) & 0x0F
    lo = total & 0x0F

    def asc(v):
        return chr(v + 55) if v > 9 else chr(v + 48)

    return asc(hi) + asc(lo)

def make_packet(body):
    cs = checksum(body.encode(ENCODING))
    return (body + cs + "\r").encode(ENCODING)

def get_factor(text):
    try:
        reader = csv.reader([text.strip()])
        fields = next(reader)
        return int(fields[1])
    except Exception:
        return -1

def safe_float(val):
    try:
        if val is None:
            return None
        return float(str(val).strip())
    except Exception:
        return None

def safe_int(val):
    try:
        if val is None:
            return None
        return int(str(val).strip())
    except Exception:
        return None

# =========================
# CONNECTION ALERTS (Telegram)
# =========================
DEBOUNCE_SECONDS = 60
STALE_SECONDS = 1200
BATCH_WINDOW = 10
RETRY_SECONDS = 30


class ConnectionAlertManager:
    def __init__(self, machines):
        now = time.time()
        self.lock = threading.Lock()
        self.states = {
            machine["name"]: {
                "ip": machine["ip"],
                "last_seen": now,
                "down_since": now,
                "outage_start": now,
                "queued_down": False,
                "notified_down": False,
            }
            for machine in machines
        }
        self.pending_down = set()
        self.pending_up = {}
        self.batch_started = None
        self.retry_after = 0
        self.started = False

    def mark_alive(self, name):
        with self.lock:
            state = self.states.get(name)
            if state is not None:
                state["last_seen"] = time.time()
                state["down_since"] = None

    def mark_down(self, name):
        with self.lock:
            state = self.states.get(name)
            if state is not None and state["down_since"] is None:
                now = time.time()
                state["down_since"] = now
                state["outage_start"] = now

    def start(self):
        with self.lock:
            if self.started:
                return
            self.started = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                self._evaluate()
                self._flush()
            except Exception as e:
                print(RED + f"[ALERT] Connection tracker error: {e}" + RESET)
            time.sleep(5)

    def _evaluate(self):
        now = time.time()
        with self.lock:
            for name, state in self.states.items():
                if (state["down_since"] is None
                        and now - state["last_seen"] > STALE_SECONDS):
                    state["down_since"] = now
                    state["outage_start"] = state["last_seen"]

                if state["down_since"] is not None:
                    if name in self.pending_up:
                        self.pending_up.pop(name, None)
                        state["notified_down"] = True
                    if (not state["queued_down"]
                            and not state["notified_down"]
                            and now - state["down_since"] >= DEBOUNCE_SECONDS):
                        state["queued_down"] = True
                        self.pending_down.add(name)
                else:
                    if state["queued_down"]:
                        state["queued_down"] = False
                        self.pending_down.discard(name)
                    elif state["notified_down"]:
                        state["notified_down"] = False
                        self.pending_up[name] = max(0, now - state["outage_start"])

    def _flush(self):
        now = time.time()
        with self.lock:
            if not self.pending_down and not self.pending_up:
                self.batch_started = None
                return
            if self.batch_started is None:
                self.batch_started = now
            if now - self.batch_started < BATCH_WINDOW or now < self.retry_after:
                return
            down = [
                (name, self.states[name]["ip"], self.states[name]["outage_start"])
                for name in sorted(self.pending_down)
            ]
            up = sorted(self.pending_up.items())

        failed = False
        if down:
            lines = [
                f"• <b>{name}</b> ({ip}) - since {datetime.fromtimestamp(started).strftime('%d-%b %H:%M:%S')}"
                for name, ip, started in down
            ]
            message = "🔴 <b>Moulding machine(s) DISCONNECTED</b>\n\n" + "\n".join(lines)
            if self._send(message):
                with self.lock:
                    for name, _, _ in down:
                        self.pending_down.discard(name)
                        self.states[name]["queued_down"] = False
                        self.states[name]["notified_down"] = True
            else:
                failed = True

        if up:
            lines = [
                f"• <b>{name}</b> - was down {self._format_duration(duration)}"
                for name, duration in up
            ]
            message = "🟢 <b>Moulding machine(s) RECONNECTED</b>\n\n" + "\n".join(lines)
            if self._send(message):
                with self.lock:
                    for name, _ in up:
                        self.pending_up.pop(name, None)
            else:
                failed = True

        with self.lock:
            if failed:
                self.retry_after = time.time() + RETRY_SECONDS
            else:
                self.retry_after = 0
                if not self.pending_down and not self.pending_up:
                    self.batch_started = None

    @staticmethod
    def _send(message):
        if not CHAT_ID:
            print(RED + "[ALERT] CHAT_ID is empty; cannot send personal Telegram alert" + RESET)
            return False
        try:
            return bool(send_telegram_message(message, target_chat=CHAT_ID))
        except Exception as e:
            print(RED + f"[ALERT] Telegram send failed: {e}" + RESET)
            return False

    @staticmethod
    def _format_duration(seconds):
        hours, remainder = divmod(int(seconds // 60), 60)
        return f"{hours}h {remainder}m" if hours else f"{remainder}m"


alerts = ConnectionAlertManager(MACHINES)

# =========================
# DYNAMIC TABLE LOGIC
# =========================
def get_dynamic_table_name(base_name):
    suffix = datetime.now().strftime("%b_%Y").lower()
    return f"{base_name}_{suffix}"

def ensure_dynamic_table_exists(conn, cursor, base_name, dynamic_table_name):
    with DB_LOCK:
        if dynamic_table_name in KNOWN_TABLES:
            return

        schemas = {
            "moulding_machines_mode": """
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    machine_id VARCHAR(50) NOT NULL,
                    mode_timestamp TIMESTAMP NOT NULL,
                    mode_status VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            "moulding_machines_monitor1": """
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    machine_id VARCHAR(50) NOT NULL,
                    monitor_timestamp TIMESTAMP NOT NULL,
                    shot_count INTEGER,
                    cycle_time NUMERIC,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            "moulding_machines_status": """
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    machine_id VARCHAR(50) NOT NULL,
                    status_timestamp TIMESTAMP NOT NULL,
                    mold_name VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            "moulding_machines_history1": """
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    machine_id VARCHAR(50) NOT NULL,
                    history_timestamp TIMESTAMP NOT NULL,
                    parameter_name VARCHAR(150),
                    unit VARCHAR(20),
                    old_value VARCHAR(50),
                    new_value VARCHAR(50),
                    changed_by VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            "moulding_machines_alarms": """
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    machine_id VARCHAR(50) NOT NULL,
                    alarm_timestamp TIMESTAMP NOT NULL,
                    alarm_code VARCHAR(20),
                    alarm_message TEXT,
                    alarm_status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            "moulding_machines_parameters": """
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    machine_id VARCHAR(50) NOT NULL,
                    parameter_timestamp TIMESTAMP NOT NULL,
                    part_number VARCHAR(100),
                    mold_no VARCHAR(100),
                    barrel_temp_z1 NUMERIC(6,2),
                    barrel_temp_z2 NUMERIC(6,2),
                    barrel_temp_z3 NUMERIC(6,2),
                    barrel_temp_z4 NUMERIC(6,2),
                    barrel_temp_z5 NUMERIC(6,2),
                    injection_position NUMERIC(8,2),
                    cushion NUMERIC(8,2),
                    revolution NUMERIC(8,2),
                    max_pressure NUMERIC(8,2),
                    hold_on_pressure_1 NUMERIC(8,2),
                    hold_on_pressure_2 NUMERIC(8,2),
                    back_pressure NUMERIC(8,2),
                    injection_speed NUMERIC(8,2),
                    injection_time NUMERIC(8,2),
                    hold_on_time NUMERIC(8,2),
                    hold_on_speed NUMERIC(8,2),
                    suck_back_position NUMERIC(8,2),
                    suck_back_speed NUMERIC(8,2),
                    plast_position NUMERIC(8,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """
        }

        if base_name in schemas:
            query = schemas[base_name].format(table_name=dynamic_table_name)
            cursor.execute(query)
            conn.commit()
            KNOWN_TABLES.add(dynamic_table_name)

# =========================
# DATABASE FUNCTIONS
# =========================
def save_mode_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        base_name = "moulding_machines_mode"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(conn, cursor, base_name, table_name)

        insert_query = f"""
            INSERT INTO {table_name} (machine_id, mode_timestamp, mode_status)
            VALUES (%s, %s, %s);
        """
        cursor.execute(insert_query, (machine_id, data_dict['timestamp'], data_dict['mode_status']))
        conn.commit()
        print(YELLOW + f"[DB SUCCESS] Logged MODE ({data_dict['mode_status']}) for {machine_id} -> {table_name}" + RESET)
    except Exception as e:
        print(RED + f"[DB ERROR] Failed to insert mode data: {e}" + RESET)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_monitor_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        base_name = "moulding_machines_monitor1"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(conn, cursor, base_name, table_name)

        insert_query = f"""
            INSERT INTO {table_name} (machine_id, monitor_timestamp, shot_count, cycle_time)
            VALUES (%s, %s, %s, %s);
        """
        cursor.execute(insert_query, (
            machine_id, data_dict['timestamp'], data_dict['shot_count'], data_dict['cycle_time']
        ))
        conn.commit()
        print(CYAN + f"[DB SUCCESS] Cycle {data_dict['shot_count']} saved for {machine_id} -> {table_name}" + RESET)
    except Exception as e:
        print(RED + f"[DB ERROR] Failed to insert monitor data: {e}" + RESET)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_parameters_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        base_name = "moulding_machines_parameters"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(conn, cursor, base_name, table_name)

        insert_query = f"""
            INSERT INTO {table_name} (
                machine_id, parameter_timestamp, part_number, mold_no,
                barrel_temp_z1, barrel_temp_z2, barrel_temp_z3, barrel_temp_z4, barrel_temp_z5,
                injection_position, cushion, revolution, max_pressure,
                hold_on_pressure_1, hold_on_pressure_2, back_pressure,
                injection_speed, injection_time, hold_on_time, hold_on_speed,
                suck_back_position, suck_back_speed, plast_position
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            );
        """
        cursor.execute(insert_query, (
            machine_id, data_dict['timestamp'], data_dict['part_number'], data_dict['mold_no'],
            data_dict['barrel_temp_z1'], data_dict['barrel_temp_z2'], data_dict['barrel_temp_z3'],
            data_dict['barrel_temp_z4'], data_dict['barrel_temp_z5'],
            data_dict['injection_position'], data_dict['cushion'], data_dict['revolution'], data_dict['max_pressure'],
            data_dict['hold_on_pressure_1'], data_dict['hold_on_pressure_2'], data_dict['back_pressure'],
            data_dict['injection_speed'], data_dict['injection_time'],
            data_dict['hold_on_time'], data_dict['hold_on_speed'],
            data_dict['suck_back_position'], data_dict['suck_back_speed'], data_dict['plast_position']
        ))
        conn.commit()
        print(CYAN + f"[DB SUCCESS] Parameters saved for {machine_id} -> {table_name}" + RESET)
    except Exception as e:
        print(RED + f"[DB ERROR] Failed to insert parameter data: {e}" + RESET)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_status_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        base_name = "moulding_machines_status"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(conn, cursor, base_name, table_name)

        insert_query = f"""
            INSERT INTO {table_name} (machine_id, status_timestamp, mold_name)
            VALUES (%s, %s, %s);
        """
        cursor.execute(insert_query, (machine_id, data_dict['timestamp'], data_dict['mold_name']))
        conn.commit()
        print(GREEN + f"[DB SUCCESS] STATUS Logged for {machine_id} -> {table_name} | Mold: {data_dict['mold_name']}" + RESET)
    except Exception as e:
        print(RED + f"[DB ERROR] Failed to insert status data: {e}" + RESET)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_history1_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        base_name = "moulding_machines_history1"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(conn, cursor, base_name, table_name)

        insert_query = f"""
            INSERT INTO {table_name} (
                machine_id, history_timestamp, parameter_name,
                unit, old_value, new_value, changed_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        cursor.execute(insert_query, (
            machine_id, data_dict['timestamp'], data_dict['parameter_name'],
            data_dict['unit'], data_dict['old_value'], data_dict['new_value'], data_dict['changed_by']
        ))
        conn.commit()
        print(MAGENTA + f"[DB SUCCESS] HISTORY Logged for {machine_id} -> {table_name}" + RESET)
    except Exception as e:
        print(RED + f"[DB ERROR] Failed to insert history1 data: {e}" + RESET)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_alarm_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        base_name = "moulding_machines_alarms"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(conn, cursor, base_name, table_name)

        insert_query = f"""
            INSERT INTO {table_name} (
                machine_id, alarm_timestamp, alarm_code, alarm_message, alarm_status
            ) VALUES (%s, %s, %s, %s, %s);
        """
        cursor.execute(insert_query, (
            machine_id, data_dict['timestamp'], data_dict['alarm_code'],
            data_dict['alarm_message'], data_dict['alarm_status']
        ))
        conn.commit()
        color = RED if data_dict['alarm_status'] == "TRIGGERED" else GREEN
        print(color + f"[DB SUCCESS] ALARM {data_dict['alarm_status']} Logged for {machine_id} -> {table_name}" + RESET)
    except Exception as e:
        print(RED + f"[DB ERROR] Failed to insert alarm data: {e}" + RESET)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# TOYO MACHINE CLASS
# =========================
class ToyoMachine:
    def __init__(self, ip, port, name):
        self.ip = ip
        self.port = port
        self.name = name
        self.sock = None
        self.reply_queue = queue.Queue()
        self.is_running = True
        self.last_parameter_save_time = 0
        self.receiver_thread = None

    def receiver(self):
        sock = self.sock
        if sock is None:
            return

        buffer = b""
        while self.is_running:
            try:
                data = sock.recv(4096)
                if not data:
                    print(RED + f"[{self.name}] Disconnected by machine" + RESET)
                    alerts.mark_down(self.name)
                    break

                buffer += data

                while b"\r" in buffer:
                    packet, buffer = buffer.split(b"\r", 1)
                    packet += b"\r"

                    try:
                        txt = packet.decode(ENCODING, errors="ignore")
                        factor = get_factor(txt)
                        if factor != -1:
                            alerts.mark_alive(self.name)

                        if factor in (36, 38, 46, 48, 51):
                            self.reply_queue.put((factor, txt))

                        if factor == 32:
                            fields = next(csv.reader([txt.strip()]))
                            mode_data = {
                                "timestamp": f"{fields[2].strip()} {fields[3].strip()}",
                                "mode_status": fields[5].strip('" ')
                            }
                            save_mode_to_db(self.name, mode_data)

                        elif factor in (30, 31):
                            fields = next(csv.reader([txt.strip()]))
                            alarm_code = fields[4].strip()

                            if alarm_code in ["160", "108", "138", "106", "193", "264"]:
                                continue

                            alarm_data = {
                                "timestamp": f"{fields[2].strip()} {fields[3].strip()}",
                                "alarm_code": alarm_code,
                                "alarm_message": fields[7].strip('" '),
                                "alarm_status": "TRIGGERED" if factor == 30 else "RESET"
                            }
                            save_alarm_to_db(self.name, alarm_data)

                        elif factor == 33:
                            fields = next(csv.reader([txt.strip()]))
                            timestamp_str = f"{fields[2].strip()}-{fields[3].strip()}-{fields[4].strip()} {fields[5].strip()}:{fields[6].strip()}:{fields[7].strip()}"

                            monitor_data = {
                                "timestamp": timestamp_str,
                                "shot_count": safe_int(fields[8]),
                                "cycle_time": safe_float(fields[57])
                            }
                            save_monitor_to_db(self.name, monitor_data)

                            current_time = time.time()
                            if current_time - self.last_parameter_save_time >= 3600:
                                cache_data = MACHINE_MOLD_CACHE.get(self.name, {"mold_no": "M-1", "part_number": None})

                                param_data = {
                                    "timestamp": timestamp_str,
                                    "part_number": cache_data.get("part_number"),
                                    "mold_no": cache_data.get("mold_no"),
                                    "barrel_temp_z1": safe_float(fields[9]),
                                    "barrel_temp_z2": safe_float(fields[10]),
                                    "barrel_temp_z3": safe_float(fields[11]),
                                    "barrel_temp_z4": safe_float(fields[12]),
                                    "barrel_temp_z5": safe_float(fields[13]),
                                    "injection_position": safe_float(fields[15]),
                                    "cushion": safe_float(fields[20]),
                                    "revolution": safe_float(fields[23]),
                                    "max_pressure": safe_float(fields[27]),
                                    "hold_on_pressure_1": safe_float(fields[28]),
                                    "hold_on_pressure_2": safe_float(fields[29]),
                                    "back_pressure": safe_float(fields[33]),
                                    "injection_speed": safe_float(fields[37]),
                                    "injection_time": safe_float(fields[58]),
                                    "hold_on_time": None,
                                    "hold_on_speed": None,
                                    "suck_back_position": None,
                                    "suck_back_speed": None,
                                    "plast_position": None
                                }
                                save_parameters_to_db(self.name, param_data)
                                self.last_parameter_save_time = current_time

                        elif factor == 46:
                            fields = next(csv.reader([txt.strip()]))
                            raw_mold_name = fields[7].strip()

                            match = re.search(r'^(.*?)\s*\((.*?)\)\s*$', raw_mold_name)
                            if match:
                                clean_mold_no = match.group(1).strip()
                                part_num = match.group(2).strip()
                            else:
                                clean_mold_no = raw_mold_name
                                part_num = None

                            MACHINE_MOLD_CACHE[self.name] = {
                                "mold_no": clean_mold_no,
                                "part_number": part_num
                            }

                            status_data = {
                                "timestamp": f"{fields[2].strip()} {fields[3].strip()}",
                                "mold_name": raw_mold_name
                            }
                            save_status_to_db(self.name, status_data)

                        elif factor == 54:
                            fields = next(csv.reader([txt.strip()]))
                            history_data = {
                                "timestamp": fields[2].strip(),
                                "parameter_name": fields[3].strip(),
                                "unit": fields[4].strip(),
                                "old_value": fields[5].strip(),
                                "new_value": fields[6].strip(),
                                "changed_by": fields[8].strip()
                            }
                            save_history1_to_db(self.name, history_data)

                    except Exception as inner_e:
                        print(RED + f"[{self.name}] Data Parsing Error (Skipping Packet): {inner_e}" + RESET)

            except socket.timeout:
                continue
            except Exception as e:
                print(RED + f"[{self.name}] Critical Socket Error (Triggering Reconnect): {e}" + RESET)
                alerts.mark_down(self.name)
                break

    def request(self, factor):
        if self.sock is None:
            return None

        body = f'":",{factor},'
        packet = make_packet(body)
        try:
            self.sock.sendall(packet)
        except Exception:
            return None

        start = time.time()
        expected = ANSWER.get(factor, factor + 1)
        while time.time() - start < 10:
            try:
                fid, ans_txt = self.reply_queue.get(timeout=1)
                if fid == expected:
                    if expected == 46:
                        self.reply_queue.put((fid, ans_txt))
                    return ans_txt
            except queue.Empty:
                pass
        return None

    def start_polling(self):
        while self.is_running:
            try:
                print(CYAN + f"[{self.name}] Connecting..." + RESET)
                try:
                    temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    temp_sock.settimeout(2)
                    temp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b'\x01\x00\x00\x00\x00\x00\x00\x00')
                    temp_sock.connect((self.ip, self.port))
                    temp_sock.close()
                    time.sleep(1)
                except Exception:
                    pass

                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self.sock.settimeout(SOCKET_TIMEOUT)
                self.sock.connect((self.ip, self.port))

                self.sock.sendall(XON)
                time.sleep(3)
                self.receiver_thread = threading.Thread(target=self.receiver, daemon=True)
                self.receiver_thread.start()

                self.request(45)
                try:
                    self.sock.sendall(make_packet('":",32,'))
                except Exception:
                    pass

                last_xon = time.time()
                last_status = time.time()

                while self.is_running:
                    if not self.receiver_thread.is_alive():
                        print(RED + f"[{self.name}] Receiver stopped - reconnecting" + RESET)
                        alerts.mark_down(self.name)
                        break

                    now = time.time()
                    if now - last_status >= STATUS_INTERVAL:
                        self.request(45)
                        try:
                            self.sock.sendall(make_packet('":",32,'))
                        except Exception:
                            pass
                        last_status = now

                    if now - last_xon >= XON_INTERVAL:
                        self.sock.sendall(XON)
                        last_xon = now

                    time.sleep(0.5)

            except Exception as e:
                print(RED + f"[{self.name}] Polling Error: {e}" + RESET)
                alerts.mark_down(self.name)
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                time.sleep(5)

# =========================
# MAIN ORCHESTRATOR
# =========================
def main():
    alerts.start()
    threads = []
    for m_conf in MACHINES:
        machine_obj = ToyoMachine(m_conf["ip"], m_conf["port"], m_conf["name"])
        t = threading.Thread(target=machine_obj.start_polling, daemon=True)
        threads.append(t)
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping all monitors...")

if __name__ == "__main__":
    main()