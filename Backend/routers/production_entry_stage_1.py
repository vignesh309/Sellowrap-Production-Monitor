from fastapi import APIRouter, HTTPException, Query
import json
from datetime import datetime, timedelta

from database import get_conn
from schemas import Stage1BlockSubmit, FinalizeBatchPayload
from utils import check_license

router = APIRouter()


# ==========================================
# 1. INIT MASTER DATA FOR STAGE 1 ENTRY PAGE
# ==========================================
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
            mold_no = str(row[6] or "-").strip()
            if not mold_no:
                mold_no = "-"

            if part_no not in payload["parts"]:
                payload["parts"][part_no] = {
                    "valid_processes": [],
                    "targets": {}
                }

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

        # 2. Fetch Molds from part_routing for applicable processes
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

        # 3. Fetch Machines
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


# ==========================================
# 2. FETCH SAVED HOUR BLOCKS + LAST SETUP
# ==========================================
@router.get("/api/get_batch_logs")
def get_batch_logs(date: str, shift: str, machine_code: str):
    """Fetches previously saved hour blocks, setup info, live IoT counts, AND last known setup."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        start_date_obj = datetime.strptime(date, "%Y-%m-%d")
        next_day_str = (start_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

        # 1. Fetch the automated IoT counts for this machine and date
        if shift == "A":
            cur.execute("""
                SELECT hour_no, part_count 
                FROM machine_hourly_summary 
                WHERE machine_code = %s 
                  AND summary_date = %s 
                  AND hour_no >= 7 AND hour_no <= 18
            """, (machine_code, date))
        else:
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

        iot_counts = {str(row[0]): row[1] for row in cur.fetchall()}

        # 2. Fetch manual logs for the CURRENT day/shift
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
                "last_known_setup": last_known_setup
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


# ==========================================
# 3. FAST IOT COUNT POLL (background sync, 15s)
# ==========================================
@router.get("/api/get_live_iot_count")
def get_live_iot_count(date: str, machine_code: str, shift: str = "A"):
    """Ultra-fast endpoint to ping IoT counts every 15 seconds."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        start_date_obj = datetime.strptime(date, "%Y-%m-%d")
        next_day_str = (start_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

        if shift == "A":
            cur.execute("""
                SELECT hour_no, part_count 
                FROM machine_hourly_summary 
                WHERE machine_code = %s 
                  AND summary_date = %s 
                  AND hour_no >= 7 AND hour_no <= 18
            """, (machine_code, date))
        else:
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

        iot_counts = {int(row[0]): row[1] for row in cur.fetchall()}
        return {"iot_counts": iot_counts}

    except Exception as e:
        print(f"BACKGROUND SYNC ERROR: {e}")
        return {"iot_counts": {}}
    finally:
        cur.close()
        conn.close()


# ==========================================
# 4. SUBMIT AN HOUR BLOCK (+ ERP staging translation)
# ==========================================
@router.post("/api/submit_stage1_block")
def submit_stage1_block(payload: Stage1BlockSubmit):
    check_license()
    conn = get_conn()
    cur = conn.cursor()

    try:
        # 0. TIME COLLISION FAILSAFE
        cur.execute("""
            SELECT id, part_number, batch_id 
            FROM production_hourly_log 
            WHERE machine_code = %s 
              AND production_date = %s 
              AND start_time = %s 
              AND end_time = %s
        """, (payload.machine_code, payload.production_date, payload.start_time, payload.end_time))

        existing_log = cur.fetchone()

        if existing_log:
            raise HTTPException(
                status_code=400,
                detail=f"Time conflict! {payload.machine_code} already has a log from {payload.start_time} to {payload.end_time} (Part: {existing_log[1]}). Please edit or delete the existing log first."
            )

        # 1. SAVE HOURLY DATA
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

        # 2. ERP STAGING TRANSLATION (HOURLY ROWS)
        clean_start = payload.start_time.replace(':', '')
        clean_end = payload.end_time.replace(':', '')
        erp_unique_id = f"{payload.batch_id}_{clean_start}-{clean_end}"

        cur.execute("""
            SELECT COALESCE(e.finsys_code, m.reason_code), SUM(r.quantity)
            FROM production_rejections r
            LEFT JOIN rejection_reason_master m ON r.reason_name = m.reason_name
            LEFT JOIN erp_mapping_master e ON e.internal_name = m.reason_code AND e.category = 'rejection_reason_code'
            WHERE r.log_id = %s
            GROUP BY 1
        """, (log_id,))
        rej_dict = {str(row[0]): int(row[1]) for row in cur.fetchall()}
        rej_json = json.dumps(rej_dict)

        cur.execute("""
            SELECT cycle_time FROM part_routing 
            WHERE part_no = %s AND mold_no = %s
            LIMIT 1
        """, (payload.part_number, payload.mould_code))
        cycle_res = cur.fetchone()
        cycle_time = float(cycle_res[0]) if cycle_res and cycle_res[0] else 0.0

        cur.execute("""
            SELECT COALESCE(e.finsys_code, m.reason_code), SUM(s.quantity)
            FROM production_shortfalls s
            LEFT JOIN shortfall_reason_master m ON s.reason_name = m.reason_name
            LEFT JOIN erp_mapping_master e ON e.internal_name = m.reason_code AND e.category = 'short_reason_code'
            WHERE s.log_id = %s
            GROUP BY 1
        """, (log_id,))

        dt_dict = {}
        total_dt_mins = 0.0
        cavities = payload.active_cavities if payload.active_cavities else 1

        for row in cur.fetchall():
            reason_code = str(row[0])
            missing_shots = int(row[1])
            missing_parts = missing_shots * cavities
            dt_mins = round((missing_parts * cycle_time), 2)
            dt_mins = round((missing_shots * cycle_time), 2)
            dt_dict[reason_code] = dt_mins
            total_dt_mins += dt_mins

        dt_json = json.dumps(dt_dict)

        def get_erp_code(category, internal_name):
            cur.execute("SELECT finsys_code FROM erp_mapping_master WHERE category = %s AND internal_name = %s", (category, internal_name))
            res = cur.fetchone()
            return res[0] if res else internal_name

        mac_erp = get_erp_code('machine_code', payload.machine_code)
        mld_erp = get_erp_code('mold_no', payload.mould_code)

        clean_supervisor = payload.supervisor_code.split(' - ')[0].strip() if payload.supervisor_code else "001"
        sup_erp = get_erp_code('emp_code', clean_supervisor)

        shift_erp = get_erp_code('SHIFT', payload.shift)

        cur.execute("SELECT UPPER(machine_process) FROM machine_master WHERE machine_code = %s", (payload.machine_code,))
        proc_res = cur.fetchone()
        actual_process = proc_res[0] if proc_res else "MOULDING"

        process_erp = get_erp_code('process_code', actual_process)

        part_composite = f"{payload.part_number}-{actual_process}"
        part_erp = get_erp_code('part_no', part_composite)

        cur.execute("DELETE FROM erp_production_staging WHERE batch_id = %s", (erp_unique_id,))

        if payload.ok_parts > 0 or payload.ng_parts > 0:
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
                erp_unique_id,
                "SW0103", process_erp, shift_erp,
                f"{payload.production_date} {payload.start_time}", f"{payload.production_date} {payload.end_time}",
                mac_erp, mld_erp, sup_erp, "001", "001", part_erp,
                "-", payload.production_date, payload.ok_parts, payload.ng_parts, 0, rej_json,
                "simple", total_dt_mins, dt_json
            ))

        conn.commit()
        return {"message": "Block saved successfully", "log_id": log_id}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        print(f"Submission Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ==========================================
# 5. FINALIZE BATCH
# ==========================================
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