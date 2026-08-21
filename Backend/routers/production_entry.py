from fastapi import APIRouter, HTTPException, Query
from database import get_conn
from schemas import Stage1BlockSubmit, FinalizeBatchPayload, ActiveMachineState
from datetime import datetime, timedelta
from fastapi.responses import StreamingResponse
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.image.pil import PilImage
from utils import check_license

router = APIRouter()

@router.get("/init_stage1")
def init_stage1():
    """
    Fetches all master data required to initialize the dropdowns 
    and calculation parameters for the Stage 1 Production Entry page.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        payload = {
            "machines": [],
            "parts": {},
            "moulds": {},
            "operators": [],
            "supervisors": [],
            "rejections": [],
            "shortfalls": []
        }
        
        # 1. Fetch Parts, specific Processes, and target data including MOLD_NO
        cur.execute("""
            SELECT part_no, process_name, target_temp, target_pressure, target_setting, hourly_target, mold_no 
            FROM part_routing 
        """)
        for row in cur.fetchall():
            part_no = row[0]
            proc_name = str(row[1] or "").upper().strip()
            # Default to "-" if no mold is assigned (e.g., Assembly process)
            mold_no = str(row[6] or "-").strip()
            if not mold_no: mold_no = "-"
            
            if part_no not in payload["parts"]:
                payload["parts"][part_no] = {
                    "valid_processes": [],
                    "targets": {}
                }
            
            # Map the process to this part
            if proc_name not in payload["parts"][part_no]["valid_processes"]:
                payload["parts"][part_no]["valid_processes"].append(proc_name)
                
            # Ensure the process dictionary exists inside targets
            if proc_name not in payload["parts"][part_no]["targets"]:
                payload["parts"][part_no]["targets"][proc_name] = {}
                
            # 🚨 FIX 1: Map the specific target to the specific MOLD NO!
            payload["parts"][part_no]["targets"][proc_name][mold_no] = {
                "tgtTemp": float(row[2] if row[2] is not None else 0), 
                "tgtPressure": float(row[3] if row[3] is not None else 0), 
                "tgtSetting": float(row[4] if row[4] is not None else 0),
                "tgtHourly": int(row[5] if row[5] is not None else 0)  
            }

        # 🚨 FIX 2: Fetch Molds from part_routing for ALL applicable processes!
        cur.execute("""
            SELECT mold_no, cavity, active_cavities, hourly_target, part_no 
            FROM part_routing 
            WHERE UPPER(process_name) IN ('MOULDING', 'PRESS CUT', 'THERMOWELDING') 
              AND mold_no IS NOT NULL 
              AND mold_no != '-'
        """)
        for row in cur.fetchall():
            mold_no = row[0]
            if mold_no not in payload["moulds"]:
                 payload["moulds"][mold_no] = {
                     "cavities": float(row[1] if row[1] is not None else 1.0), 
                     "active_cavities": float(row[2] if row[2] is not None else 1.0), 
                     "hourlyShots": int(row[3] if row[3] is not None else 0), 
                     "linked_parts": []
                 }
            
            if row[4] not in payload["moulds"][mold_no]["linked_parts"]:
                payload["moulds"][mold_no]["linked_parts"].append(row[4])

        # 3. Fetch Machines (Now includes machine_process)
        cur.execute("SELECT machine_code, machine_process FROM machine_master WHERE is_active=true ORDER BY machine_code ASC")
        payload["machines"] = [
            {"code": row[0], "process": str(row[1] or "").upper().strip()} 
            for row in cur.fetchall()
        ]

        # 4. Fetch Employees
        cur.execute("SELECT emp_code, full_name, job_role FROM employee_master WHERE is_active=true ORDER BY full_name ASC")
        for row in cur.fetchall():
            emp_string = f"{row[0]} - {row[1]}"
            job_role = str(row[2] or "").lower()
            if job_role == "operator":
                payload["operators"].append(emp_string)
            elif job_role == "supervisor":
                payload["supervisors"].append(emp_string)

        # 5. Fetch Defect/Downtime Codes
        cur.execute("SELECT reason_name FROM rejection_reason_master WHERE is_active=true ORDER BY reason_name ASC")
        payload["rejections"] = [row[0] for row in cur.fetchall()]
        
        cur.execute("SELECT reason_name FROM shortfall_reason_master WHERE is_active=true ORDER BY reason_name ASC")
        payload["shortfalls"] = [row[0] for row in cur.fetchall()]

        return payload

    except Exception as e:
        print(f"CRITICAL ERROR IN INIT_STAGE1: {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/init_moulding_stage")
def init_moulding_stage():
    """
    Dedicated initialization for the Moulding Stage. 
    Strictly filters machines and shortfalls to MOULDING processes.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        payload = {
            "machines": [],
            "parts": {},
            "moulds": {},
            "operators": [],
            "supervisors": [],
            "rejections": [],
            "shortfalls": []
        }
        
        # 1. Fetch Parts and Target Data
        cur.execute("""
            SELECT part_no, process_name, target_temp, target_pressure, target_setting, hourly_target, mold_no 
            FROM part_routing 
        """)
        for row in cur.fetchall():
            part_no = row[0]
            proc_name = str(row[1] or "").upper().strip()
            mold_no = str(row[6] or "-").strip()
            if not mold_no: mold_no = "-"
            
            if part_no not in payload["parts"]:
                payload["parts"][part_no] = {"valid_processes": [], "targets": {}}
            
            if proc_name not in payload["parts"][part_no]["valid_processes"]:
                payload["parts"][part_no]["valid_processes"].append(proc_name)
                
            if proc_name not in payload["parts"][part_no]["targets"]:
                payload["parts"][part_no]["targets"][proc_name] = {}
                
            payload["parts"][part_no]["targets"][proc_name][mold_no] = {
                "tgtTemp": float(row[2] if row[2] is not None else 0), 
                "tgtPressure": float(row[3] if row[3] is not None else 0), 
                "tgtSetting": float(row[4] if row[4] is not None else 0),
                "tgtHourly": int(row[5] if row[5] is not None else 0)  
            }

        # 2. Fetch Moulds
        cur.execute("""
            SELECT mold_no, cavity, active_cavities, hourly_target, part_no 
            FROM part_routing 
            WHERE UPPER(process_name) IN ('MOULDING', 'PRESS CUT', 'THERMOWELDING') 
              AND mold_no IS NOT NULL 
              AND mold_no != '-'
        """)
        for row in cur.fetchall():
            mold_no = row[0]
            if mold_no not in payload["moulds"]:
                 payload["moulds"][mold_no] = {
                     "cavities": float(row[1] if row[1] is not None else 1.0), 
                     "active_cavities": float(row[2] if row[2] is not None else 1.0), 
                     "hourlyShots": int(row[3] if row[3] is not None else 0), 
                     "linked_parts": []
                 }
            if row[4] not in payload["moulds"][mold_no]["linked_parts"]:
                payload["moulds"][mold_no]["linked_parts"].append(row[4])

        # 3. 🚨 FILTER: Fetch ONLY Moulding Machines
        cur.execute("""
            SELECT machine_code, machine_process 
            FROM machine_master 
            WHERE is_active = true 
              AND UPPER(machine_process) = 'MOULDING'
            ORDER BY machine_code ASC
        """)
        payload["machines"] = [
            {"code": row[0], "process": str(row[1] or "").upper().strip()} 
            for row in cur.fetchall()
        ]

        # 4. Fetch Employees
        cur.execute("SELECT emp_code, full_name, job_role FROM employee_master WHERE is_active=true ORDER BY full_name ASC")
        for row in cur.fetchall():
            emp_string = f"{row[0]} - {row[1]}"
            job_role = str(row[2] or "").lower()
            if job_role == "operator":
                payload["operators"].append(emp_string)
            elif job_role == "supervisor":
                payload["supervisors"].append(emp_string)

        # 5. 🚨 FILTER: Fetch Rejections and strictly Moulding Shortfalls
        cur.execute("SELECT reason_name FROM rejection_reason_master WHERE is_active=true ORDER BY reason_name ASC")
        payload["rejections"] = [row[0] for row in cur.fetchall()]
        
        cur.execute("""
            SELECT reason_name 
            FROM shortfall_reason_master 
            WHERE is_active = true 
              AND 'MOULDING' = ANY(valid_processes)
            ORDER BY reason_name ASC
        """)
        payload["shortfalls"] = [row[0] for row in cur.fetchall()]

        return payload

    except Exception as e:
        print(f"CRITICAL ERROR IN INIT_MOULDING_STAGE: {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_batch_logs")
def get_batch_logs(date: str, shift: str, machine_code: str):
    """Fetches previously saved hour blocks, setup info, live IoT counts, AND last known setup."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 1. Fetch the automated IoT counts for this machine and date
        cur.execute("""
            SELECT hour_no, part_count 
            FROM machine_hourly_summary 
            WHERE machine_code = %s AND summary_date = %s
        """, (machine_code, date))
        
        # Format as a dictionary: {"8": 120, "9": 145}
        iot_counts = {str(row[0]): row[1] for row in cur.fetchall()}

        # 2. Existing query to fetch manual logs for the CURRENT day/shift
        cur.execute("""
            SELECT id, production_date, start_time, end_time, target_shots, actual_shots, ok_parts, ng_parts, 
                   actual_temp, actual_pressure, actual_setting, internal_batch_number, created_at,
                   part_number, mould_code, operator_code, supervisor_code, batch_id, is_no_plan 
            FROM production_hourly_log
            WHERE production_date = %s AND shift = %s AND machine_code = %s
            ORDER BY start_time ASC
        """, (date, shift, machine_code))
        
        rows = cur.fetchall()
        
        if not rows:
            # 🚨 NEW: Fetch the Last Known Setup if there are no logs for today!
            # We filter out 'is_no_plan = TRUE' so it only remembers real setups.
            cur.execute("""
                SELECT part_number, mould_code, operator_code, supervisor_code
                FROM production_hourly_log
                WHERE machine_code = %s AND is_no_plan = FALSE
                ORDER BY production_date DESC, start_time DESC
                LIMIT 1
            """, (machine_code,))
            
            last_setup_row = cur.fetchone()
            last_known_setup = None
            
            if last_setup_row:
                last_known_setup = {
                    "part_number": last_setup_row[0],
                    "mould_code": last_setup_row[1],
                    "operator_code": last_setup_row[2],
                    "supervisor_code": last_setup_row[3]
                }
            
            return {
                "exists": False, 
                "logs": [], 
                "is_finalized": False, 
                "iot_counts": iot_counts,
                "last_known_setup": last_known_setup # 🚨 Pass the setup to the frontend
            }
            
        last_row = rows[-1]
        current_batch_id = last_row[17] 
        
        cur.execute("SELECT 1 FROM batch_master WHERE batch_id = %s", (current_batch_id,))
        is_finalized = bool(cur.fetchone())
        
        setup = {
            "internal_batch_number": last_row[11],
            "part_number": last_row[13],
            "mould_code": last_row[14],
            "operator_code": last_row[15],
            "supervisor_code": last_row[16]
        }
        
        logs = []
        for row in rows:
            log_id = row[0]
            cur.execute("SELECT reason_name, quantity FROM production_rejections WHERE log_id = %s", (log_id,))
            rejections = [{"reason": r[0], "qty": r[1]} for r in cur.fetchall()]
            
            cur.execute("SELECT reason_name, quantity FROM production_shortfalls WHERE log_id = %s", (log_id,))
            shortfalls = [{"reason": r[0], "qty": r[1]} for r in cur.fetchall()]
            
            logs.append({
                "id": log_id,
                "production_date": str(row[1]),
                "start_time": str(row[2])[:5] if row[2] else "",
                "end_time": str(row[3])[:5] if row[3] else "",  
                "target_shots": row[4],
                "actual_shots": row[5],
                "ok_parts": row[6],
                "ng_parts": row[7],
                "actual_temp": row[8],
                "actual_pressure": row[9],
                "actual_setting": row[10],
                "internal_batch_number": row[11],
                "created_at": row[12].strftime("%H:%M:%S") if row[12] else "Unknown",
                "rejections": rejections,
                "shortfalls": shortfalls,
                "is_no_plan": row[18] 
            })
            
        return {
            "exists": True, 
            "setup": setup, 
            "logs": logs, 
            "is_finalized": is_finalized, 
            "iot_counts": iot_counts,
            "last_known_setup": None
        }
        
    except Exception as e:
        print(f"ERROR FETCHING LOGS: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch history logs.")
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_live_iot_count")
def get_live_iot_count(date: str, machine_code: str, shift: str = "A"):
    """Ultra-fast endpoint to ping IoT counts every 15 seconds."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Calculate the next calendar day for Shift B's after-midnight hours
        start_date_obj = datetime.strptime(date, "%Y-%m-%d")
        next_day_str = (start_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

        if shift == "A":
            # Shift A is entirely within the same physical calendar day (07:00 to 18:59)
            cur.execute("""
                SELECT hour_no, part_count 
                FROM machine_hourly_summary 
                WHERE machine_code = %s 
                  AND summary_date = %s 
                  AND hour_no >= 7 AND hour_no <= 18
            """, (machine_code, date))
        else:
            # 🚨 SMART QUERY: Shift B bridges across two physical calendar days!
            # Fetch 19:00 to 23:59 from Day 1, and 00:00 to 06:59 from Day 2
            cur.execute("""
                SELECT hour_no, part_count 
                FROM machine_hourly_summary 
                WHERE machine_code = %s 
                  AND (
                      (summary_date = %s AND hour_no >= 19 AND hour_no <= 23)
                      OR 
                      (summary_date = %s AND hour_no >= 0 AND hour_no <= 6)
                  )
            """, (machine_code, date, next_day_str))
        
        # Format dictionary with integer keys so the frontend maps them correctly
        iot_counts = {int(row[0]): row[1] for row in cur.fetchall()}
        return {"iot_counts": iot_counts}

    except Exception as e:
        print(f"BACKGROUND SYNC ERROR: {e}")
        return {"iot_counts": {}}
    finally:
        cur.close()
        conn.close()

import json
from fastapi import APIRouter, HTTPException
from database import get_conn
# ... (keep your existing imports and Pydantic models)

@router.post("/api/submit_stage1_block")
def submit_stage1_block(payload: Stage1BlockSubmit):
    check_license()
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # ==========================================
        # 1. SAVE HOURLY DATA (Your Existing Logic)
        # ==========================================
        cur.execute("""
            INSERT INTO production_hourly_log
            (batch_id, internal_batch_number, production_date, shift, start_time, end_time, machine_code, mould_code, part_number,
             operator_code, supervisor_code, target_shots, actual_shots, active_cavities,
             ok_parts, ng_parts, actual_temp, actual_pressure, actual_setting, is_no_plan)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            payload.batch_id, payload.internal_batch_number, payload.production_date, payload.shift, 
            payload.start_time, payload.end_time, payload.machine_code, payload.mould_code, payload.part_number,
            payload.operator_code, payload.supervisor_code, payload.target_shots, payload.actual_shots, 
            payload.active_cavities, payload.ok_parts, payload.ng_parts, payload.actual_temp, 
            payload.actual_pressure, payload.actual_setting, payload.is_no_plan
        ))
        
        result = cur.fetchone()
        log_id = result[0] if result else None

        if payload.rejections:
            for rej in payload.rejections:
                cur.execute("""
                    INSERT INTO production_rejections 
                    (log_id, batch_id, process_name, start_time, end_time, reason_name, quantity, emp_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    log_id, payload.batch_id, "MOULDING", payload.start_time, payload.end_time, 
                    rej.reason, rej.qty, payload.operator_code     
                ))

        if payload.shortfalls:
            for sf in payload.shortfalls:
                cur.execute(
                    "INSERT INTO production_shortfalls (log_id, reason_name, quantity) VALUES (%s, %s, %s)",
                    (log_id, sf.reason, sf.qty) 
                )


        # ==========================================
        # 2. ERP STAGING AGGREGATION & TRANSLATION
        # ==========================================
        
        # A. Calculate totals for the ENTIRE batch so far
        cur.execute("""
            SELECT 
                MIN(start_time), MAX(end_time),
                COALESCE(SUM(ok_parts), 0), COALESCE(SUM(ng_parts), 0)
            FROM production_hourly_log
            WHERE batch_id = %s
        """, (payload.batch_id,))
        agg_start, agg_end, agg_ok, agg_ng = cur.fetchone()

        # B. Group and Translate Rejections to JSON
        cur.execute("""
            SELECT COALESCE(e.finsys_code, r.reason_name), SUM(r.quantity)
            FROM production_rejections r
            LEFT JOIN erp_mapping_master e ON e.internal_name = r.reason_name AND e.category = 'rejection_reason_code'
            WHERE r.batch_id = %s
            GROUP BY 1
        """, (payload.batch_id,))
        rej_dict = {str(row[0]): int(row[1]) for row in cur.fetchall()}
        rej_json = json.dumps(rej_dict)

        # C. Fetch Cycle Time from Routing Master
        # 🚨 FIX 1: Removed the hardcoded 'MOULDING' constraint so it finds Thermowelding/Assembly parts too!
        cur.execute("""
            SELECT cycle_time FROM part_routing 
            WHERE part_no = %s AND mold_no = %s
            LIMIT 1
        """, (payload.part_number, payload.mould_code))
        cycle_res = cur.fetchone()
        cycle_time = float(cycle_res[0]) if cycle_res and cycle_res[0] else 0.0

        # D. Calculate Downtime Minutes & Create JSON
        cur.execute("""
            SELECT COALESCE(e.finsys_code, s.reason_name), SUM(s.quantity)
            FROM production_shortfalls s
            JOIN production_hourly_log l ON l.id = s.log_id
            LEFT JOIN erp_mapping_master e ON e.internal_name = s.reason_name AND e.category = 'short_reason_code'
            WHERE l.batch_id = %s
            GROUP BY 1
        """, (payload.batch_id,))
        
        dt_dict = {}
        total_dt_mins = 0.0
        
        for row in cur.fetchall():
            reason_code = str(row[0])
            missing_shots = int(row[1])
            
            # Formula: (Missing Shots * Cycle Time) / 60 to get Minutes
            dt_mins = round((missing_shots * cycle_time) / 60.0, 2)
            
            # 🚨 FIX 2: Even if cycle time is 0.0, STILL log the reason in the JSON so data is never lost!
            dt_dict[reason_code] = dt_mins
            total_dt_mins += dt_mins
                
        dt_json = json.dumps(dt_dict)

        # E. Translate Master Data Headers
        def get_erp_code(category, internal_name):
            cur.execute("SELECT finsys_code FROM erp_mapping_master WHERE category = %s AND internal_name = %s", (category, internal_name))
            res = cur.fetchone()
            return res[0] if res else internal_name

        mac_erp = get_erp_code('machine_code', payload.machine_code)
        mld_erp = get_erp_code('mold_no', payload.mould_code)
        sup_erp = get_erp_code('emp_code', payload.supervisor_code)
        shift_erp = get_erp_code('SHIFT', payload.shift)
        
        # 🚨 FIX 3: Dynamically find the machine's actual process to create the correct Part Mapping string
        cur.execute("SELECT UPPER(machine_process) FROM machine_master WHERE machine_code = %s", (payload.machine_code,))
        proc_res = cur.fetchone()
        actual_process = proc_res[0] if proc_res else "MOULDING"

        part_composite = f"{payload.part_number}-{actual_process}"
        part_erp = get_erp_code('part_no', part_composite)

        # F. Upsert (Delete Old, Insert New) Staging Row
        cur.execute("DELETE FROM erp_production_staging WHERE batch_id = %s", (payload.batch_id,))
        
        cur.execute("""
            INSERT INTO erp_production_staging (
                batch_id, shop_floor, section_code, shift_name,
                prd_start_time, prd_end_time, machine_erp_code, mould_erp_code,
                supervisor_erp_code, operator_count, helper_count, part_erp_code,
                job_no, job_dt, ok_qty, rej_qty, lumps, rejections_json,
                dt_type, total_downtime_mins, downtime_json, is_pushed
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, false
            )
        """, (
            payload.batch_id, "SW0102", "61", shift_erp,
            f"{payload.production_date} {agg_start}", f"{payload.production_date} {agg_end}", 
            mac_erp, mld_erp, sup_erp, "001", "001", part_erp,
            "-", payload.production_date, agg_ok, agg_ng, 0, rej_json,
            "simple", total_dt_mins, dt_json
        ))

        conn.commit()
        return {"message": "Block saved successfully", "log_id": log_id}

    except Exception as e:
        conn.rollback()
        print(f"Submission Error: {str(e)}") # Prints error to server terminal
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/api/finalize_batch")
def finalize_batch(payload: FinalizeBatchPayload):
    """Saves to WIP. (RM consumption logic permanently removed)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO batch_master 
            (batch_id, sequence_no, process_name, input_qty, ok_qty, ng_qty, emp_code, is_outsourced, remarks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (batch_id, sequence_no) DO UPDATE SET
                ok_qty = EXCLUDED.ok_qty,
                ng_qty = EXCLUDED.ng_qty,
                emp_code = EXCLUDED.emp_code,
                remarks = EXCLUDED.remarks
        """, (
            payload.batch_id, payload.sequence_no, payload.process_name,
            payload.input_qty, payload.ok_qty, payload.ng_qty, 
            payload.emp_code, payload.is_outsourced, payload.remarks
        ))

        conn.commit()
        return {"message": "Batch Master updated successfully", "batch_id": payload.batch_id}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_batch_ledger")
def get_batch_ledger(search: str = Query(""), start_date: str = Query(""), end_date: str = Query(""), machine: str = Query("")):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT 
                bm.id,
                bm.batch_id,
                bm.sequence_no,
                bm.process_name,
                bm.input_qty,
                bm.ok_qty,
                bm.ng_qty,
                bm.emp_code,
                bm.is_outsourced,
                bm.created_at,
                pm.part_name,
                pm.part_no,
                phl.internal_batch_number
            FROM batch_master bm
            LEFT JOIN part_master pm ON SPLIT_PART(bm.batch_id, '_', 5) = pm.part_no
            LEFT JOIN (
                SELECT DISTINCT ON (batch_id) batch_id, internal_batch_number
                FROM production_hourly_log
                ORDER BY batch_id, created_at ASC
            ) phl ON bm.batch_id = phl.batch_id
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND bm.batch_id ILIKE %s"
            params.append(f"%{search}%")
        if start_date:
            query += " AND DATE(bm.created_at) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(bm.created_at) <= %s"
            params.append(end_date)
        if machine:
            query += " AND bm.batch_id LIKE %s"
            params.append(f"%_{machine}_%")
            
        query += " ORDER BY bm.created_at ASC"
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        
        batches = {}
        for r in rows:
            bid = r[1]
            if bid not in batches:
                batches[bid] = {"batch_id": bid, "stages": []}
            
            batches[bid]["stages"].append({
                "id": r[0],
                "sequence_no": r[2],
                "process_name": r[3],
                "input_qty": r[4],
                "ok_qty": r[5],
                "ng_qty": r[6],
                "emp_code": r[7],
                "is_outsourced": r[8],
                "timestamp": r[9].strftime("%Y-%m-%d %H:%M:%S") if r[9] and hasattr(r[9], 'strftime') else str(r[9]) if r[9] else "",
                "part_name": r[10] or "Unknown Part",
                "part_no": r[11] or bid.split('_')[-1],
                "internal_batch_number": r[12] or "N/A"
            })
            
        ledger_list = list(batches.values())
        ledger_list.sort(key=lambda x: x["stages"][0]["timestamp"] if x["stages"] and len(x["stages"]) > 0 else "", reverse=True)
        
        return {"ledger": ledger_list}
        
    except Exception as e:
        print(f"LEDGER ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/download_label/{batch_id}")
def download_label(batch_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT bm.batch_id, pm.part_no, pm.part_name, phl.internal_batch_number
            FROM batch_master bm
            LEFT JOIN part_master pm ON SPLIT_PART(bm.batch_id, '_', 5) = pm.part_no
            LEFT JOIN production_hourly_log phl ON bm.batch_id = phl.batch_id
            WHERE bm.batch_id = %s LIMIT 1
        """, (batch_id,))
        
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Batch not found")
            
        full_batch, part_no, part_name, internal_batch = row
        
        parts = full_batch.split('_')
        date_str = parts[0] if len(parts) > 0 else "N/A"
        shift_str = parts[1] if len(parts) > 1 else "N/A"

        process_stages = []
        try:
            cur.execute("""
                SELECT 
                    pr.process_name,
                    bm.ok_qty,
                    bm.ng_qty,
                    bm.emp_code
                FROM part_routing pr
                LEFT JOIN batch_master bm 
                    ON pr.process_name = bm.process_name 
                    AND bm.batch_id = %s
                WHERE pr.part_no = %s
                ORDER BY pr.sequence_no ASC
            """, (batch_id, part_no))
            
            db_stages = cur.fetchall()
            
            for row in db_stages:
                proc_name, ok_qty, ng_qty, emp_code = row
                if ok_qty is None:
                    process_stages.append((proc_name, "", "", "", ""))
                else:
                    total_qty = ok_qty + (ng_qty or 0)
                    operator = emp_code if emp_code else ""
                    if operator and " - " in operator:
                        operator = operator.split(" - ")[1]
                        
                    process_stages.append((
                        proc_name, 
                        str(total_qty), 
                        str(ok_qty), 
                        str(ng_qty), 
                        operator
                    ))
        except Exception as db_err:
            print("Could not fetch routing from DB, using fallback data.", db_err)
            
        if not process_stages:
            process_stages = [("Moulding", "50", "45", "5", "Prakash")]

        img = Image.new('RGB', (709, 709), color='white')
        draw = ImageDraw.Draw(img)

        try:
            font_title = ImageFont.truetype("arialbd.ttf", 32) 
            font_bold = ImageFont.truetype("arialbd.ttf", 22)
            font_normal = ImageFont.truetype("arial.ttf", 22)
            font_table_hdr = ImageFont.truetype("arialbd.ttf", 16) 
            font_table_val = ImageFont.truetype("arial.ttf", 16)   
            font_small = ImageFont.truetype("cour.ttf", 14)
        except IOError:
            font_title = font_bold = font_normal = font_table_hdr = font_table_val = font_small = ImageFont.load_default()

        draw.rectangle([(10, 10), (699, 699)], outline="black", width=4) 
        draw.line([(10, 60), (699, 60)], fill="black", width=3) 
        draw.text((354, 35), "Jayashree Polymers", font=font_title, fill="black", anchor="mm")

        draw.line([(450, 60), (450, 350)], fill="black", width=3)
        y_positions_top = [118, 176, 234, 292] 
        for y in y_positions_top:
            draw.line([(10, y), (450, y)], fill="black", width=2)

        draw.line([(10, 350), (699, 350)], fill="black", width=3)

        draw.text((20, 75), "Part no:", font=font_normal, fill="black")
        draw.text((150, 75), str(part_no), font=font_bold, fill="black")
        draw.text((20, 133), "Part name:", font=font_normal, fill="black")
        draw.text((150, 133), str(part_name)[:16], font=font_bold, fill="black") 
        draw.text((20, 191), "Batch no:", font=font_normal, fill="black")
        draw.text((150, 191), str(internal_batch), font=font_normal, fill="black")
        draw.text((20, 249), "Date:", font=font_normal, fill="black")
        draw.text((150, 249), date_str, font=font_normal, fill="black")
        draw.text((20, 307), "Shift:", font=font_normal, fill="black")
        draw.text((150, 307), shift_str, font=font_normal, fill="black")

        qr = qrcode.QRCode(box_size=10, border=1)
        qr.add_data(full_batch)
        qr.make(fit=True)
        # 🚨 FIX: Explicitly cast to an RGB image to satisfy Pylance's resize check
        qr_wrapper = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
        qr_img = qr_wrapper.get_image().convert('RGB') 
        qr_img = qr_img.resize((230, 230)) 
        
        img.paste(qr_img, (460, 85))

        col_x = [10, 180, 280, 380, 480, 699] 
        for x in col_x:
            draw.line([(x, 350), (x, 640)], fill="black", width=2)
            
        headers = ["Process", "Total", "OK", "NG", "Operator"]
        for i, header_text in enumerate(headers):
            center_x = col_x[i] + ((col_x[i+1] - col_x[i]) / 2)
            draw.text((center_x, 370), header_text, font=font_table_hdr, fill="black", anchor="mm")
            
        draw.line([(10, 390), (699, 390)], fill="black", width=2)

        current_y = 390
        row_height = 40
        for idx, stage in enumerate(process_stages):
            if idx >= 6: break 
            
            proc_name, total_qty, ok_qty, ng_qty, opr_name = stage
            row_data = [str(proc_name)[:15], str(total_qty), str(ok_qty), str(ng_qty), str(opr_name)[:15]]
            
            for i, text in enumerate(row_data):
                center_x = col_x[i] + ((col_x[i+1] - col_x[i]) / 2)
                draw.text((center_x, current_y + 20), text, font=font_table_val, fill="black", anchor="mm")
            
            current_y += row_height
            draw.line([(10, current_y), (699, current_y)], fill="black", width=1)

        draw.line([(10, 640), (699, 640)], fill="black", width=3) 
        draw.text((354, 670), full_batch, font=font_small, fill="black", anchor="mm")

        buf = BytesIO()
        img.save(buf, format="PDF", resolution=300.0) 
        buf.seek(0)
        
        return StreamingResponse(
            buf, 
            media_type="application/pdf", 
            headers={"Content-Disposition": f"inline; filename={full_batch}.pdf"}
        )

    except Exception as e:
        print(f"IMAGE GEN ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_batch_route/{batch_id}")
def get_batch_route(batch_id: str):
    """Fetches full routing plan and WIP history. (Outsource parsing removed)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM batch_master WHERE batch_id = %s", (batch_id,))
        result = cur.fetchone()
        if not result or result[0] == 0:
            raise HTTPException(status_code=404, detail="BATCH NOT FOUND: This ID has no Stage 1 (Moulding) record.")
        
        part_no = batch_id.split('_')[-1]

        cur.execute("SELECT process_name FROM part_routing WHERE part_no = %s ORDER BY sequence_no ASC", (part_no,))
        routing_rows = cur.fetchall()
        if not routing_rows:
            raise HTTPException(status_code=404, detail=f"No routing defined in Master Data for part {part_no}.")
        routing_plan = [row[0] for row in routing_rows]

        cur.execute("""
            SELECT sequence_no, process_name, input_qty, ok_qty, ng_qty, emp_code, is_outsourced
            FROM batch_master 
            WHERE batch_id = %s
            ORDER BY sequence_no ASC
        """, (batch_id,))
        history = [{"sequence_no": r[0], "process_name": r[1], "input_qty": r[2], "ok_qty": r[3], "ng_qty": r[4], "emp_code": r[5], "is_outsourced": r[6]} for r in cur.fetchall()]

        return {
            "batch_id": batch_id, 
            "part_no": part_no, 
            "routing": routing_plan, 
            "history": history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ROUTE ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_machines")
def get_machines():
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 Make sure machine_process is included in the SELECT query!
        cur.execute("SELECT machine_code, machine_name, machine_process FROM machine_master WHERE is_active = true ORDER BY machine_code ASC")
        
        machines = []
        for row in cur.fetchall():
            machines.append({
                "code": row[0],
                "name": row[1],
                "process": row[2] # 🚨 This is the missing link!
            })
            
        return {"machines": machines}
    except Exception as e:
        print(f"Error fetching machines: {e}")
        return {"machines": []}
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_employees")
def get_employees():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT emp_code, full_name FROM employee_master WHERE is_active = true")
        rows = cur.fetchall()
        employees = [f"{row[0]} - {row[1]}" for row in rows]
        return {"employees": employees}
    except Exception as e:
        print(f"EMPLOYEE FETCH ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/api/active_machine")
def update_active_machine(state: ActiveMachineState):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            INSERT INTO active_machine_status 
            (machine_code, internal_batch_number, part_number, mould_code, operator_code, supervisor_code, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (machine_code) 
            DO UPDATE SET 
                internal_batch_number = EXCLUDED.internal_batch_number,
                part_number = EXCLUDED.part_number,
                mould_code = EXCLUDED.mould_code,
                operator_code = EXCLUDED.operator_code,
                supervisor_code = EXCLUDED.supervisor_code,
                updated_at = CURRENT_TIMESTAMP;
        """
        cur.execute(query, (
            state.machine_code, state.internal_batch_number, state.part_number, 
            state.mould_code, state.operator_code, state.supervisor_code
        ))
        conn.commit()
        return {"status": "success", "message": "Active machine state updated."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/active_machine/{machine_code}")
def get_active_machine(machine_code: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT internal_batch_number, part_number, mould_code, operator_code, supervisor_code 
            FROM active_machine_status 
            WHERE machine_code = %s
        """
        cur.execute(query, (machine_code,))
        row = cur.fetchone()
        
        if row:
            return {
                "exists": True,
                "internal_batch_number": row[0],
                "part_number": row[1],
                "mould_code": row[2],
                "operator_code": row[3],
                "supervisor_code": row[4]
            }
        return {"exists": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_shift_history")
def get_shift_history(date: str, shift: str, machine: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, start_time, end_time, target_shots, actual_shots, ok_parts, ng_parts, 
                   actual_temp, actual_pressure, actual_setting, created_at,
                   part_number, mould_code, internal_batch_number, operator_code, supervisor_code
            FROM production_hourly_log
            WHERE production_date = %s AND shift = %s AND machine_code = %s
            ORDER BY start_time ASC
        """, (date, shift, machine))
        
        rows = cur.fetchall()
        
        if not rows:
            return {"exists": False}

        first_row = rows[0]
        
        setup = {
            "part_number": first_row[10],
            "mould_code": first_row[11],
            "internal_batch_number": first_row[12],
            "operator_code": first_row[13],
            "supervisor_code": first_row[14]
        }
        
        logs = []
        for r in rows:
            log_id = r[0]
            
            cur.execute("SELECT reason_name, quantity FROM production_rejections WHERE log_id = %s", (log_id,))
            rejections = [{"reason": rej[0], "qty": rej[1]} for rej in cur.fetchall()]
            
            cur.execute("SELECT reason_name, quantity FROM production_shortfalls WHERE log_id = %s", (log_id,))
            shortfalls = [{"reason": sf[0], "qty": sf[1]} for sf in cur.fetchall()]
            
            logs.append({
                "start_time": str(r[1])[:5] if r[1] else "",
                "end_time": str(r[2])[:5] if r[2] else "",
                "target_shots": r[3],
                "actual_shots": r[4],
                "ok_parts": r[5],
                "ng_parts": r[6],
                "actual_temp": r[7],
                "actual_pressure": r[8],
                "actual_setting": r[9],
                "created_at": r[10].strftime("%H:%M:%S") if r[10] else "Unknown",
                "rejections": rejections,
                "shortfalls": shortfalls
            })
            
        return {"exists": True, "setup": setup, "logs": logs}
        
    except Exception as e:
        print(f"ERROR FETCHING SHIFT HISTORY: {str(e)}")
        return {"exists": False}
    finally:
        cur.close()
        conn.close()