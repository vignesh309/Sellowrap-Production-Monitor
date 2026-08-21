from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date, datetime, timedelta

import psycopg2
from database import get_conn

router = APIRouter()

@router.get("/api/live_factory_status")
def live_factory_status(date: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 1. 🚨 SMART QUERY: Get the LATEST log from today for each active machine
        cur.execute("""
            WITH LatestLog AS (
                SELECT DISTINCT ON (machine_code)
                       machine_code, part_number, operator_code, is_no_plan
                FROM production_hourly_log
                WHERE production_date = %s
                -- 🚨 FIX: Order by the physical creation time, NOT the string text of the hour!
                ORDER BY machine_code, created_at DESC
            )
            SELECT m.machine_code, m.machine_name, 
                   l.part_number, l.operator_code, pm.part_name,
                   l.is_no_plan
            FROM machine_master m
            LEFT JOIN LatestLog l ON m.machine_code = l.machine_code
            LEFT JOIN part_master pm ON l.part_number = pm.part_no
            WHERE m.is_active = true
            ORDER BY m.machine_code ASC
        """, (date,))
        machines_db = cur.fetchall()
        
        machine_dict = {}
        for row in machines_db:
            mac_code = row[0]
            current_part = row[2]
            is_latest_no_plan = row[5]
            
            # Format the display text based on the latest log
            if not current_part:
                display_part_no = "Idle"
                display_part_name = "--"
            elif is_latest_no_plan:
                display_part_no = "NO PLAN"
                display_part_name = "No Plan Assigned"
            else:
                display_part_no = current_part
                display_part_name = row[4] or "--"
            
            machine_dict[mac_code] = {
                "machine": mac_code,
                "current_part_no": display_part_no,
                "current_part_name": display_part_name,
                "current_operator": row[3] or "--",
                "shift_target": 0,
                "shift_actual": 0,
                "shift_ok": 0,
                "shift_ng": 0,
                "hourly_data": {"A": {}, "B": {}}
            }

        # 2. Get and group all hourly logs for the selected date to build the tables
        cur.execute("""
            SELECT machine_code, shift, 
                   EXTRACT(HOUR FROM start_time::time) as start_hr,
                   SUM(target_shots), SUM(actual_shots), SUM(ok_parts), SUM(ng_parts), BOOL_OR(is_no_plan)
            FROM production_hourly_log
            WHERE production_date = %s
            GROUP BY machine_code, shift, start_hr
        """, (date,))
        
        logs = cur.fetchall()
        
        for log in logs:
            mac_code, shift, start_hr, tgt, act, ok, ng, is_no_plan = log
            if mac_code not in machine_dict:
                continue
                
            # Format start_hr to exactly match your JS mapping (e.g., "08:00 - 09:00")
            hr_int = int(start_hr)
            next_hr = (hr_int + 1) % 24
            time_slot = f"{hr_int:02d}:00 - {next_hr:02d}:00"
            
            # Map to Shift A or B
            shift_key = shift if shift in ["A", "B"] else "A"
            
            # Add to shift totals (Ignore No Plan blocks for the Grand Total Target)
            if not is_no_plan:
                machine_dict[mac_code]["shift_target"] += int(tgt or 0)
                
            machine_dict[mac_code]["shift_actual"] += int(act or 0)
            machine_dict[mac_code]["shift_ok"] += int(ok or 0)
            machine_dict[mac_code]["shift_ng"] += int(ng or 0)
            
            # Add to hourly data arrays for the tables
            machine_dict[mac_code]["hourly_data"][shift_key][time_slot] = {
                "target": "NP" if is_no_plan else int(tgt or 0),
                "actual": "NP" if is_no_plan else int(act or 0),
                "ok": "NP" if is_no_plan else int(ok or 0),
                "ng": "NP" if is_no_plan else int(ng or 0)
            }

        return {"data": list(machine_dict.values())}
        
    except Exception as e:
        print(f"FACTORY STATUS ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_live_moulding_data")
def get_live_moulding_data(machine_code: str, date: str = None, shift: str = None):
    conn = get_conn()
    cur = conn.cursor()
    
    # Determine the current month's table suffix (e.g., aug_2026)
    suffix = datetime.now().strftime("%b_%Y").lower()
    
    # Default response structure
    response_data = {
        "mode_status": "UNKNOWN",
        "cycle_time": None,
        "alarm_status": "NONE",
        "alarm_message": "",
        "mold_name": "--",
        "iot_counts": {}
    }
    
    try:
        # 1. Fetch Machine Mode
        cur.execute(f"""
            SELECT mode_status FROM moulding_machines_mode_{suffix}
            WHERE machine_id = %s ORDER BY mode_timestamp DESC LIMIT 1
        """, (machine_code,))
        mode_row = cur.fetchone()
        if mode_row:
            response_data["mode_status"] = mode_row[0]

        # 2. Fetch Cycle Time
        cur.execute(f"""
            SELECT cycle_time FROM moulding_machines_monitor1_{suffix}
            WHERE machine_id = %s ORDER BY monitor_timestamp DESC LIMIT 1
        """, (machine_code,))
        cycle_row = cur.fetchone()
        if cycle_row:
            response_data["cycle_time"] = cycle_row[0]

        # 3. Fetch Alarms
        cur.execute(f"""
            SELECT alarm_status, alarm_message FROM moulding_machines_alarms_{suffix}
            WHERE machine_id = %s ORDER BY alarm_timestamp DESC LIMIT 1
        """, (machine_code,))
        alarm_row = cur.fetchone()
        if alarm_row:
            response_data["alarm_status"] = alarm_row[0]
            response_data["alarm_message"] = alarm_row[1]

        # 4. Fetch Mold Name
        cur.execute(f"""
            SELECT mold_name FROM moulding_machines_status_{suffix}
            WHERE machine_id = %s ORDER BY status_timestamp DESC LIMIT 1
        """, (machine_code,))
        mold_row = cur.fetchone()
        if mold_row:
            response_data["mold_name"] = mold_row[0]
            
        # 5. 🚨 SMART QUERY: Calculate exact hourly shots using true Shift Window
        if date and shift:
            # Calculate physical start and end times for the shift
            start_date_obj = datetime.strptime(date, "%Y-%m-%d")
            
            if shift == "A":
                start_dt = start_date_obj.replace(hour=7, minute=0, second=0)
                end_dt = start_date_obj.replace(hour=18, minute=59, second=59)
            else: # Shift B
                start_dt = start_date_obj.replace(hour=19, minute=0, second=0)
                end_dt = (start_date_obj + timedelta(days=1)).replace(hour=6, minute=59, second=59)

            cur.execute(f"""
                WITH FirstShots AS (
                    -- Get the very first shot count recorded at the start of each hour within the shift window
                    SELECT DISTINCT ON (EXTRACT(HOUR FROM monitor_timestamp))
                        EXTRACT(HOUR FROM monitor_timestamp) AS hr,
                        shot_count
                    FROM moulding_machines_monitor1_{suffix}
                    WHERE machine_id = %s AND monitor_timestamp >= %s AND monitor_timestamp <= %s
                    ORDER BY EXTRACT(HOUR FROM monitor_timestamp), monitor_timestamp ASC
                )
                SELECT 
                    hr,
                    -- Subtract current hour's first shot from the next hour's first shot
                    -- If it is the current running hour, subtract from the absolute MAX shot count right now
                    COALESCE(
                        LEAD(shot_count) OVER (ORDER BY hr), 
                        (SELECT MAX(shot_count) FROM moulding_machines_monitor1_{suffix} 
                         WHERE machine_id = %s AND monitor_timestamp >= %s AND monitor_timestamp <= %s 
                         AND EXTRACT(HOUR FROM monitor_timestamp) = FirstShots.hr)
                    ) - shot_count AS hourly_shots
                FROM FirstShots;
            """, (machine_code, start_dt, end_dt, machine_code, start_dt, end_dt))
            
            for row in cur.fetchall():
                hour_no = int(row[0])
                shots = int(row[1])
                response_data["iot_counts"][hour_no] = shots

    except psycopg2.errors.UndefinedTable:
        # Safely ignore if the table doesn't exist yet for a new month
        conn.rollback()
    except Exception as e:
        conn.rollback()
        print(f"Error fetching live moulding data: {e}")
    finally:
        cur.close()
        conn.close()
        
    return response_data

@router.get("/api/live_moulding_dashboard")
def get_live_moulding_dashboard(date: str, shift: str):
    conn = get_conn()
    cur = conn.cursor()
    
    suffix = datetime.now().strftime("%b_%Y").lower()
    
    # Calculate exact physical time bounds based on the Logical Shift
    start_date_obj = datetime.strptime(date, "%Y-%m-%d")
    if shift == "A":
        start_dt = start_date_obj.replace(hour=7, minute=0, second=0)
        end_dt = start_date_obj.replace(hour=18, minute=59, second=59)
    else: # Shift B
        start_dt = start_date_obj.replace(hour=19, minute=0, second=0)
        end_dt = (start_date_obj + timedelta(days=1)).replace(hour=6, minute=59, second=59)

    response_data = []

    try:
        cur.execute("SELECT machine_code FROM machine_master WHERE is_active = true AND machine_process = 'MOULDING' ORDER BY machine_code ASC")
        active_machines = [row[0] for row in cur.fetchall()]

        for mac in active_machines:
            mac_data = {
                "machine": mac,
                "mode": "UNKNOWN",
                "cycle_time": "--",
                "mould_name": "--",
                "shot_count": 0,
                "alarm": "NONE",
                "is_idle": True # 🚨 NEW: Defaults to True (Red) until proven active
            }

            # 1. Fetch Mode
            cur.execute(f"SELECT mode_status FROM moulding_machines_mode_{suffix} WHERE machine_id = %s ORDER BY mode_timestamp DESC LIMIT 1", (mac,))
            mode_row = cur.fetchone()
            if mode_row: mac_data["mode"] = mode_row[0].strip().upper()

            # 2. Fetch Cycle Time AND check the 3-Minute Rule
            cur.execute(f"SELECT cycle_time, monitor_timestamp FROM moulding_machines_monitor1_{suffix} WHERE machine_id = %s ORDER BY monitor_timestamp DESC LIMIT 1", (mac,))
            cycle_row = cur.fetchone()
            if cycle_row: 
                mac_data["cycle_time"] = cycle_row[0]
                last_time = cycle_row[1]
                
                # Safely parse the timestamp whether the DB sends it as a string or a datetime object
                if isinstance(last_time, str):
                    try:
                        last_time = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass
                
                if isinstance(last_time, datetime):
                    # 🚨 3-MINUTE RULE CALCULATION (180 seconds)
                    if (datetime.now() - last_time).total_seconds() <= 300:
                        mac_data["is_idle"] = False

            # 3. Fetch Mould Name
            cur.execute(f"SELECT mold_name FROM moulding_machines_status_{suffix} WHERE machine_id = %s ORDER BY status_timestamp DESC LIMIT 1", (mac,))
            mold_row = cur.fetchone()
            if mold_row: mac_data["mould_name"] = mold_row[0]

            # 4. Fetch Last Alarm
            cur.execute(f"SELECT alarm_message, alarm_status FROM moulding_machines_alarms_{suffix} WHERE machine_id = %s ORDER BY alarm_timestamp DESC LIMIT 1", (mac,))
            alarm_row = cur.fetchone()
            if alarm_row and alarm_row[1].strip().upper() == "TRIGGERED":
                mac_data["alarm"] = alarm_row[0]

            # 5. Calculate exact Shot Count for the shift
            cur.execute(f"""
                SELECT COUNT(*) 
                FROM moulding_machines_monitor1_{suffix} 
                WHERE machine_id = %s AND monitor_timestamp >= %s AND monitor_timestamp <= %s
            """, (mac, start_dt, end_dt))
            act_row = cur.fetchone()
            if act_row: mac_data["shot_count"] = act_row[0]

            response_data.append(mac_data)

        return {"machines": response_data}

    except psycopg2.errors.UndefinedTable:
        conn.rollback()
        return {"machines": []}
    except Exception as e:
        conn.rollback()
        print(f"Error compiling Moulding Dashboard: {e}")
        return {"machines": []}
    finally:
        cur.close()
        conn.close()