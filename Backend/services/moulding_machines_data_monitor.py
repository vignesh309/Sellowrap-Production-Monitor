#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import queue
import time
import csv
import os
import psycopg2
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

# Now safely import your database configuration variables
from config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD

# =========================================================
# DYNAMIC DATABASE CONFIGURATION
# =========================================================
DB_CONFIG = {
    "host": DB_HOST,
    "database": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD
}

# Cache to prevent running "CREATE TABLE" queries unnecessarily
KNOWN_TABLES = set()
DB_LOCK = threading.Lock()

# =========================
# MACHINE CONFIGURATION
# =========================
# 🚨 CHANGED: The 'name' is now exactly what will be stored in machine_id
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
        return float(val.strip())
    except ValueError:
        return None

def safe_int(val):
    try:
        return int(val.strip())
    except ValueError:
        return None

# =========================
# DYNAMIC TABLE LOGIC
# =========================
def get_dynamic_table_name(base_name):
    """Generates the table name based on the current month and year."""
    suffix = datetime.now().strftime("%b_%Y").lower() 
    return f"{base_name}_{suffix}"

def ensure_dynamic_table_exists(cursor, base_name, dynamic_table_name):
    """Creates the month-specific table if it does not already exist."""
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
            """
        }

        if base_name in schemas:
            query = schemas[base_name].format(table_name=dynamic_table_name)
            cursor.execute(query)
            KNOWN_TABLES.add(dynamic_table_name)

# =========================
# DATABASE FUNCTIONS
# =========================
def save_mode_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
        )
        cursor = conn.cursor()
        base_name = "moulding_machines_mode"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(cursor, base_name, table_name)
        
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
        conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
        )
        cursor = conn.cursor()
        base_name = "moulding_machines_monitor1"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(cursor, base_name, table_name)
        
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

def save_status_to_db(machine_id, data_dict):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
            )
        cursor = conn.cursor()
        base_name = "moulding_machines_status"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(cursor, base_name, table_name)
        
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
        conn = psycopg2.connect(
                    host=DB_CONFIG["host"],
                    database=DB_CONFIG["database"],
                    user=DB_CONFIG["user"],
                    password=DB_CONFIG["password"]
                )
        cursor = conn.cursor()
        base_name = "moulding_machines_history1"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(cursor, base_name, table_name)
        
        insert_query = f"""
            INSERT INTO {table_name} (
                machine_id, history_timestamp, parameter_name, 
                unit, old_value, new_value, changed_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        cursor.execute(insert_query, (
            machine_id, data_dict['timestamp'], data_dict['parameter_name'],
            data_dict['unit'], data_dict['old_value'], data_dict['new_value'],
            data_dict['changed_by']
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
        conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
        )
        cursor = conn.cursor()
        base_name = "moulding_machines_alarms"
        table_name = get_dynamic_table_name(base_name)
        ensure_dynamic_table_exists(cursor, base_name, table_name)
        
        insert_query = f"""
            INSERT INTO {table_name} (
                machine_id, alarm_timestamp, alarm_code, 
                alarm_message, alarm_status
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

    def receiver(self):
        if self.sock is None:
            return
        buffer = b""
        while self.is_running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    print(RED + f"[{self.name}] Disconnected by machine" + RESET)
                    break

                buffer += data

                while b"\r" in buffer:
                    packet, buffer = buffer.split(b"\r", 1)
                    packet += b"\r"
                    txt = packet.decode(ENCODING, errors="ignore")

                    factor = get_factor(txt)

                    if factor in (36, 38, 46, 48, 51):
                        self.reply_queue.put((factor, txt))

                    if factor == 32:
                        try:
                            fields = next(csv.reader([txt.strip()]))
                            mode_data = {
                                "timestamp": f"{fields[2].strip()} {fields[3].strip()}",
                                "mode_status": fields[5].strip('" ')
                            }
                            save_mode_to_db(self.name, mode_data)
                        except Exception as e:
                            print(RED + f"[{self.name}] Parse Error for Factor 32: {e}" + RESET)

                    elif factor in (30, 31):
                        try:
                            fields = next(csv.reader([txt.strip()]))
                            alarm_data = {
                                "timestamp": f"{fields[2].strip()} {fields[3].strip()}",
                                "alarm_code": fields[4].strip(),
                                "alarm_message": fields[7].strip('" '),
                                "alarm_status": "TRIGGERED" if factor == 30 else "RESET"
                            }
                            save_alarm_to_db(self.name, alarm_data)
                        except Exception as e:
                            print(RED + f"[{self.name}] Parse Error for Factor {factor}: {e}" + RESET)

                    elif factor == 33:
                        try:
                            fields = next(csv.reader([txt.strip()]))
                            monitor_data = {
                                "timestamp": f"{fields[2].strip()}-{fields[3].strip()}-{fields[4].strip()} {fields[5].strip()}:{fields[6].strip()}:{fields[7].strip()}",
                                "shot_count": safe_int(fields[8]),
                                "cycle_time": safe_float(fields[57])
                            }
                            save_monitor_to_db(self.name, monitor_data)
                        except Exception as e:
                            print(RED + f"[{self.name}] Parse Error for Factor 33: {e}" + RESET)

                    elif factor == 46:
                        try:
                            fields = next(csv.reader([txt.strip()]))
                            status_data = {
                                "timestamp": f"{fields[2].strip()} {fields[3].strip()}",
                                "mold_name": fields[7].strip()
                            }
                            save_status_to_db(self.name, status_data)
                        except Exception as e:
                            print(RED + f"[{self.name}] Parse Error for Factor 46: {e}" + RESET)

                    elif factor == 54:
                        try:
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
                        except Exception as e:
                            print(RED + f"[{self.name}] Parse Error for Factor 54: {e}" + RESET)

            except socket.timeout:
                continue
            except Exception as e:
                print(RED + f"[{self.name}] Receiver error: {e}" + RESET)
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
                print(CYAN + f"[{self.name}] Connecting to {self.ip}:{self.port} ..." + RESET)
                
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
                
                print(GREEN + f"[{self.name}] Connected. Sending XON..." + RESET)
                self.sock.sendall(XON)
                time.sleep(3)

                threading.Thread(target=self.receiver, daemon=True).start()

                # 1. Request Status (Factor 45)
                self.request(45)
                
                # 2. 🚨 NEW: Trigger Machine Mode (Factor 32) immediately on startup
                try:
                    self.sock.sendall(make_packet('":",32,'))
                except Exception:
                    pass

                last_xon = time.time()
                last_status = time.time()

                while self.is_running:
                    now = time.time()

                    if now - last_status >= STATUS_INTERVAL:
                        # Request Status every 15 mins
                        self.request(45)
                        
                        # 🚨 NEW: Trigger Machine Mode every 15 mins as well
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
                print(RED + f"[{self.name}] Connection lost: {e}" + RESET)
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass
                print(YELLOW + f"[{self.name}] Reconnecting in 5 seconds..." + RESET)
                time.sleep(5)

# =========================
# MAIN ORCHESTRATOR
# =========================
def main():
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