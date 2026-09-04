from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date
from datetime import datetime
from database import get_conn
from services.telegram_notifier import generate_hourly_report
import math

router = APIRouter()


def format_time(minutes: float) -> str:
    """Return a human-readable duration from a number of minutes."""
    total_minutes = max(0, int(round(minutes or 0)))
    hours, remaining_minutes = divmod(total_minutes, 60)
    return f"{hours}h {remaining_minutes}m"

@router.get("/api/get_processes")
def get_processes():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT process FROM process_master ORDER BY process ASC")
        processes = [row[0] for row in cur.fetchall()]
        return {"processes": processes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_live_machine_status")
def get_live_machine_status(prod_date: str, time_block: str):
    # Split "08:00 - 09:00" into "08:00:00" and "09:00:00" for the database
    start_t_str, end_t_str = time_block.split(" - ")
    start_time = start_t_str.strip() + ":00"
    end_time = end_t_str.strip() + ":00"

    conn = get_conn()
    cur = conn.cursor()
    try:
        # We group by machine to handle "Split Cards" automatically!
        query = """
            SELECT 
                m.machine_code,
                MAX(p.part_number) as part_number,
                MAX(p.operator_code) as operator_code,
                COALESCE(SUM(p.target_shots), 0) as target_shots,
                COALESCE(SUM(p.actual_shots), 0) as actual_shots,
                COALESCE(SUM(p.ok_parts), 0) as ok_parts,
                COALESCE(SUM(p.ng_parts), 0) as ng_parts,
                BOOL_OR(p.is_no_plan) as is_no_plan
            FROM machine_master m
            LEFT JOIN production_hourly_log p 
                ON m.machine_code = p.machine_code 
                AND p.production_date = %s 
                AND p.start_time >= %s::time 
                AND p.end_time <= %s::time
            WHERE m.is_active = true
            GROUP BY m.machine_code
            ORDER BY m.machine_code ASC
        """
        cur.execute(query, (prod_date, start_time, end_time))
        rows = cur.fetchall()

        machines = []
        for row in rows:
            code, part, op, tgt, act, ok, ng, is_no_plan = row
            
            # Format display text based on No Plan status
            display_part = "Awaiting Data"
            if is_no_plan:
                display_part = "NO PLAN"
            elif part:
                display_part = part
            
            machines.append({
                "code": code,
                "target": int(tgt),
                "actual": int(act),
                "ok": int(ok),
                "ng": int(ng),
                "part": display_part,
                "operator": op if op else "--",
                "is_no_plan": bool(is_no_plan)
            })

        return {"machines": machines}
    except Exception as e:
        print(f"DASHBOARD ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/pending_finalization")
def get_pending_finalizations(from_date: Optional[str] = None, to_date: Optional[str] = None):
    """
    Acts as a Strict Compliance Checklist.
    Cross-references ALL active machines against the selected dates/shifts to find any 
    machine that lacks a finalized batch (even if 0 hours have been logged).
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Prevent massive database lookups by defaulting to today if cleared
        if not from_date:
            from_date = datetime.now().strftime("%Y-%m-%d")
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")

        query = """
            WITH date_range AS (
                SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS prod_date
            ),
            shifts AS (
                SELECT 'A' AS shift_name UNION ALL SELECT 'B'
            ),
            
            -- Step 1: Create the Master Matrix (Every Date x Every Shift x Every Active Machine)
            matrix AS (
                SELECT d.prod_date, s.shift_name, m.machine_code, m.machine_process
                FROM date_range d
                CROSS JOIN shifts s
                CROSS JOIN machine_master m
                WHERE m.is_active = true
            ),
            
            -- Step 2: Grab all production logs within the date range
            logged_data AS (
                SELECT 
                    h.production_date, 
                    h.shift, 
                    h.machine_code,
                    COUNT(h.id) as hours_logged,
                    SUM(h.ok_parts) as total_ok,
                    SUM(h.ng_parts) as total_ng,
                    STRING_AGG(DISTINCT h.part_number, ', ') as parts_run,
                    MAX(h.operator_code) as operator,
                    COUNT(b.batch_id) as finalized_batches
                FROM production_hourly_log h
                LEFT JOIN batch_master b ON h.batch_id = b.batch_id
                WHERE h.production_date >= %s::date AND h.production_date <= %s::date
                GROUP BY h.production_date, h.shift, h.machine_code
            )
            
            -- Step 3: Match the logs to the matrix, keeping ONLY those with 0 finalized batches
            SELECT 
                mx.prod_date,
                mx.shift_name,
                mx.machine_code,
                COALESCE(ld.parts_run, '-') as parts_run,
                COALESCE(ld.operator, '-') as operator,
                COALESCE(ld.total_ok, 0) as total_ok,
                COALESCE(ld.total_ng, 0) as total_ng,
                COALESCE(ld.hours_logged, 0) as hours_logged,
                UPPER(mx.machine_process) as process_name
            FROM matrix mx
            LEFT JOIN logged_data ld 
                ON mx.prod_date = ld.production_date 
                AND mx.shift_name = ld.shift 
                AND mx.machine_code = ld.machine_code
            WHERE COALESCE(ld.finalized_batches, 0) = 0
            ORDER BY mx.prod_date DESC, mx.shift_name ASC, mx.machine_code ASC
        """
        
        # We pass the dates twice: once for the Matrix generation, and once for filtering the logs
        cur.execute(query, (from_date, to_date, from_date, to_date))
        rows = cur.fetchall()
        
        pending_batches = []
        for r in rows:
            pending_batches.append({
                "date": str(r[0]),
                "shift": r[1],
                "machine": r[2],
                "part": r[3],
                "operator": r[4],
                "total_ok": int(r[5]),
                "total_ng": int(r[6]),
                "hours_logged": int(r[7]),
                "process": r[8] or "UNKNOWN" 
            })
            
        return {"records": pending_batches}
        
    except Exception as e:
        print(f"Error fetching pending finalizations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_rm_consumption_report")
def get_rm_consumption_report(start_date: str = Query(""), end_date: str = Query("")):
    """Fetches RM consumption records with optional date filtering."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT 
                batch_id, 
                rm_batch_id, 
                starting_rm_weight, 
                consumed_weight, 
                remaining_balance, 
                created_at
            FROM rm_consumption
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND DATE(created_at) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(created_at) <= %s"
            params.append(end_date)

        query += " ORDER BY created_at DESC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            # Rebuild the QR parts to show a cleaner view of the RM info
            rm_full = r[1]
            rm_parts = rm_full.split("$") if "$" in rm_full else []
            rm_clean = rm_parts[2] if len(rm_parts) > 2 else rm_full

            records.append(
                {
                    "batch_id": r[0],
                    "rm_barcode_full": rm_full,
                    "rm_code": rm_clean,
                    "starting_weight": float(r[2]),
                    "consumed": float(r[3]),
                    "remaining": float(r[4]),
                    "timestamp": r[5].strftime("%Y-%m-%d %H:%M:%S") if r[5] else "",
                }
            )

        return {"records": records}

    except Exception as e:
        print(f"RM REPORT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/api/get_production_hourly_report")
def get_production_hourly_report(
    start_date: str = Query(""),
    end_date: str = Query(""),
    machine: str = Query(""),
    shift: str = Query("")
):
    """Fetches every single raw Hourly Production row exactly as saved."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 NO GROUPING: We select EVERY single row directly.
        # We include p.id to ensure overlapping split times are kept distinct.
        # We also include p.active_cavities!
        query = """
            SELECT 
                p.id, p.production_date, p.shift, p.start_time, p.end_time, 
                p.machine_code, p.mould_code, p.part_number, p.operator_code, 
                p.target_shots, p.actual_shots, p.ok_parts, p.ng_parts, 
                p.internal_batch_number, p.is_no_plan, m.machine_process,
                p.active_cavities
            FROM production_hourly_log p
            LEFT JOIN machine_master m ON p.machine_code = m.machine_code
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND p.production_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND p.production_date <= %s"
            params.append(end_date)
        if machine:
            query += " AND p.machine_code = %s"
            params.append(machine)
        if shift:
            query += " AND p.shift = %s"
            params.append(shift)

        # Order exactly by Date -> Shift -> Start Time -> ID to keep split runs perfectly sequential
        query += " ORDER BY p.production_date DESC, p.shift ASC, p.start_time ASC, p.id ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            # Clean up the operator string (e.g., "EMP-001 - John Doe" -> "EMP-001")
            operator_full = r[8] if r[8] else ""
            operator_short = operator_full.split(" - ")[0] if " - " in operator_full else operator_full

            # Format start_time and end_time into the exact split times (e.g., "09:00 - 09:30")
            start_str = str(r[3])[:5] if r[3] else "00:00"
            end_str = str(r[4])[:5] if r[4] else "00:00"
            
            # Math values
            target_shots = int(r[9] or 0)
            actual_shots = int(r[10] or 0)
            active_cavities = int(r[16] or 1)

            records.append({
                "log_id": r[0],
                "date": str(r[1]),
                "shift": r[2],
                "time_block": f"{start_str} - {end_str}",
                "machine": r[5],
                "mould": r[6],
                "part_no": r[7],
                "operator": operator_short,
                "target": target_shots * active_cavities, # Show Total Target Parts
                "actual": actual_shots * active_cavities, # Show Total Actual Parts
                "ok": int(r[11] or 0),
                "ng": int(r[12] or 0),
                "batch": r[13] or "-",
                "is_no_plan": bool(r[14]),
                "process": r[15] or "Moulding",
                "active_cavities": active_cavities,
                "rm_lot": "-"
            })

        return {"records": records}

    except Exception as e:
        print(f"HOURLY REPORT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/api/get_loss_analysis")
def get_loss_analysis(
    start_date: str = Query(""),
    end_date: str = Query(""),
    machine: str = Query(""),
    shift: str = Query(""),
):
    """Fetches aggregated Rejections and Shortfalls for the Pareto charts."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Base WHERE clause to apply to both queries
        where_sql = "WHERE 1=1"
        params = []

        if start_date:
            where_sql += " AND phl.production_date >= %s"
            params.append(start_date)
        if end_date:
            where_sql += " AND phl.production_date <= %s"
            params.append(end_date)
        if machine:
            where_sql += " AND phl.machine_code = %s"
            params.append(machine)
        if shift:
            where_sql += " AND phl.shift = %s"
            params.append(shift)

        # 1. Query for Top Rejections
        rejection_query = f"""
            SELECT pr.reason_name, SUM(pr.quantity) as total
            FROM production_rejections pr
            JOIN production_hourly_log phl ON pr.log_id = phl.id
            {where_sql}
            GROUP BY pr.reason_name
            ORDER BY total DESC
        """
        cur.execute(rejection_query, tuple(params))
        rejections_data = [
            {"reason": row[0], "count": int(row[1])} for row in cur.fetchall()
        ]

        # 2. Query for Top Shortfalls
        shortfall_query = f"""
            SELECT ps.reason_name, SUM(ps.quantity) as total
            FROM production_shortfalls ps
            JOIN production_hourly_log phl ON ps.log_id = phl.id
            {where_sql}
            GROUP BY ps.reason_name
            ORDER BY total DESC
        """
        cur.execute(shortfall_query, tuple(params))
        shortfalls_data = [
            {"reason": row[0], "count": int(row[1])} for row in cur.fetchall()
        ]

        return {"rejections": rejections_data, "shortfalls": shortfalls_data}

    except Exception as e:
        print(f"LOSS ANALYSIS ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# --- NEW API ENDPOINTS FOR DETAILED SHORTFALLS REPORT ---

@router.get("/api/get_master_dropdowns")
def get_master_dropdowns():
    """Fetches machines and parts for frontend dropdowns."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Fetch Active Machines
        cur.execute("""
            SELECT machine_code, machine_name 
            FROM machine_master 
            WHERE is_active = true 
            ORDER BY machine_code
        """)
        machines = [{"machine_code": row[0], "machine_name": row[1]} for row in cur.fetchall()]

        # 🚨 UPDATED: Changed part_number to part_no to match the new part_master schema
        cur.execute("""
            SELECT part_no, part_name 
            FROM part_master 
            ORDER BY part_no
        """)
        # We still output "part_number" in the JSON so your JS doesn't break!
        parts = [{"part_number": row[0], "part_name": row[1]} for row in cur.fetchall()]

        return {
            "machines": machines,
            "parts": parts
        }

    except Exception as e:
        print(f"Master Dropdown Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load dropdowns")
    finally:
        cur.close()
        conn.close()


@router.get("/api/report/detailed_shortfalls")
def get_detailed_shortfalls(
    start_date: str, end_date: str, 
    shift: Optional[str] = None, 
    machine: Optional[str] = None, 
    part_no: Optional[str] = None
):
    """Fetches dynamic pivot matrix of Shortfall reasons."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        where_clause = "h.production_date >= %s AND h.production_date <= %s"
        params = [start_date, end_date]

        if shift and shift != "ALL":
            where_clause += " AND h.shift = %s"
            params.append(shift)
        if machine and machine != "ALL":
            where_clause += " AND h.machine_code = %s"
            params.append(machine)
        if part_no and part_no != "ALL":
            where_clause += " AND h.part_number = %s"
            params.append(part_no)

        # 1. Fetch relevant Shortfall Reasons (Dynamic Columns)
        cur.execute(f"""
            SELECT DISTINCT s.reason_name
            FROM production_shortfalls s
            JOIN production_hourly_log h ON s.log_id = h.id
            WHERE {where_clause}
            ORDER BY s.reason_name
        """, tuple(params))
        
        dynamic_reasons = [row[0] for row in cur.fetchall()]

        # 2. Fetch the actual data
        # 🚨 UPDATED: Added SPLIT_PART to keep the supervisor/operator names clean!
        cur.execute(f"""
            SELECT 
                h.production_date, 
                h.shift, 
                h.machine_code, 
                h.part_number, 
                SPLIT_PART(h.supervisor_code, ' - ', 1) as supervisor, 
                SPLIT_PART(h.operator_code, ' - ', 1) as operator, 
                s.reason_name, 
                SUM(s.quantity)
            FROM production_hourly_log h
            JOIN production_shortfalls s ON h.id = s.log_id
            WHERE {where_clause}
            GROUP BY 
                h.production_date, h.shift, h.machine_code, h.part_number, 
                supervisor, operator, s.reason_name
            ORDER BY 
                h.production_date DESC, h.shift, h.machine_code
        """, tuple(params))
        
        rows = cur.fetchall()

        # 3. Pivot Grouping in Python
        report_data = {}
        for r in rows:
            row_key = f"{r[0]}_{r[1]}_{r[2]}_{r[3]}_{r[4]}_{r[5]}"
            
            if row_key not in report_data:
                report_data[row_key] = {
                    "date": str(r[0]), 
                    "shift": r[1], 
                    "machine": r[2], 
                    "part_no": r[3],
                    "supervisor": r[4] or "-", 
                    "operator": r[5] or "-",
                    "reasons": {reason: 0 for reason in dynamic_reasons},
                    "total_shortfalls": 0
                }
            
            reason_name = r[6]
            qty = int(r[7])
            report_data[row_key]["reasons"][reason_name] = qty
            report_data[row_key]["total_shortfalls"] += qty

        final_rows = list(report_data.values())

        return {
            "dynamic_columns": dynamic_reasons,
            "rows": final_rows
        }

    except Exception as e:
        print(f"Shortfall Matrix Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/report/detailed_rejections")
def get_detailed_rejections(
    start_date: str, end_date: str, 
    shift: Optional[str] = None, 
    machine: Optional[str] = None, 
    part_no: Optional[str] = None
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Build dynamic WHERE clause
        where_clause = "h.production_date >= %s AND h.production_date <= %s"
        params = [start_date, end_date]

        if shift and shift != "ALL":
            where_clause += " AND h.shift = %s"
            params.append(shift)
        if machine and machine != "ALL":
            where_clause += " AND h.machine_code = %s"
            params.append(machine)
        if part_no and part_no != "ALL":
            where_clause += " AND h.part_number = %s"
            params.append(part_no)

        # 1. Fetch all RELEVANT Rejection Reasons
        cur.execute(f"""
            SELECT DISTINCT r.reason_name
            FROM production_rejections r
            JOIN production_hourly_log h ON r.log_id = h.id
            WHERE {where_clause}
            ORDER BY r.reason_name
        """, tuple(params))
        dynamic_reasons = [row[0] for row in cur.fetchall()]

        # 2. Fetch the actual data
        # 🚨 UPDATED: Added SPLIT_PART to keep names clean!
        cur.execute(f"""
            SELECT 
                h.production_date, 
                h.shift, 
                h.machine_code, 
                h.part_number, 
                SPLIT_PART(h.supervisor_code, ' - ', 1) as supervisor, 
                SPLIT_PART(h.operator_code, ' - ', 1) as operator, 
                r.reason_name, 
                SUM(r.quantity)
            FROM production_hourly_log h
            JOIN production_rejections r ON h.id = r.log_id
            WHERE {where_clause}
            GROUP BY 
                h.production_date, h.shift, h.machine_code, h.part_number, 
                supervisor, operator, r.reason_name
            ORDER BY 
                h.production_date DESC, h.shift, h.machine_code
        """, tuple(params))
        
        rows = cur.fetchall()

        # 3. Python Pivot Magic
        report_data = {}
        for r in rows:
            row_key = f"{r[0]}_{r[1]}_{r[2]}_{r[3]}_{r[4]}_{r[5]}"
            
            if row_key not in report_data:
                report_data[row_key] = {
                    "date": str(r[0]), # 🚨 UPDATED: Cast to string to prevent JSON errors
                    "shift": r[1], 
                    "machine": r[2], 
                    "part_no": r[3],
                    "supervisor": r[4] or "-", 
                    "operator": r[5] or "-",
                    "reasons": {reason: 0 for reason in dynamic_reasons},
                    "total_rejections": 0
                }
            
            reason_name = r[6]
            qty = int(r[7])
            report_data[row_key]["reasons"][reason_name] = qty
            report_data[row_key]["total_rejections"] += qty

        final_rows = list(report_data.values())

        return {
            "dynamic_columns": dynamic_reasons,
            "rows": final_rows
        }

    except Exception as e:
        print(f"Rejection Matrix Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/reports/rejections")
def get_rejections_report(
    part_no: str, 
    from_date: Optional[str] = "",
    to_date: Optional[str] = ""
):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # 1. Parse parts
        part_list = [p.strip() for p in part_no.split(',') if p.strip()]
        if not part_list and part_no != "ALL":
            raise ValueError("No parts provided for the report.")

        # 2. Build Query
        # We group by batch and reason to sum up the quantities cleanly
        query = """
            SELECT 
                batch_id, 
                time_slot, 
                process_name, 
                reason_name, 
                emp_id, 
                SUM(quantity) as total_qty
            FROM production_rejections
        """
        
        conditions = []
        params = []

        # Filter by parts (using LIKE since part_no is inside the batch_id string)
        if part_no != "ALL":
            part_conditions = []
            for p in part_list:
                part_conditions.append("batch_id LIKE %s")
                params.append(f"%{p}%")
            
            # Combine part conditions with OR, wrapped in parentheses
            conditions.append(f"({' OR '.join(part_conditions)})")

        if from_date:
            conditions.append("DATE(created_at) >= %s")
            params.append(from_date)
        if to_date:
            conditions.append("DATE(created_at) <= %s")
            params.append(to_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Group and Order
        query += """
            GROUP BY batch_id, time_slot, process_name, reason_name, emp_id
            ORDER BY batch_id DESC, time_slot ASC
        """

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        # 3. Process Data & Calculate KPIs
        details = []
        total_ng = 0
        
        # Dictionaries to track what the worst defects/processes are
        defect_counts = {}
        process_counts = {}

        for row in rows:
            batch = row[0]
            t_slot = row[1]
            process = row[2] or "N/A"
            reason = row[3] or "Unknown"
            emp = row[4] or "N/A"
            qty = int(row[5] or 0)

            total_ng += qty
            
            # Tally defects
            defect_counts[reason] = defect_counts.get(reason, 0) + qty
            # Tally processes
            process_counts[process] = process_counts.get(process, 0) + qty

            details.append({
                "batch_id": batch,
                "time_slot": t_slot,
                "process_name": process,
                "reason_name": reason,
                "emp_id": emp,
                "quantity": qty
            })

        # Find the top defect and process
        top_defect = max(defect_counts, key=lambda k: defect_counts[k]) if defect_counts else "-"
        top_process = max(process_counts, key=lambda k: process_counts[k]) if process_counts else "-"

        # 4. Ship it!
        return {
            "summary": {
                "total_ng": total_ng,
                "top_defect": top_defect,
                "top_process": top_process
            },
            "details": details
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/reports/partwise")
def get_partwise_report(
    from_date: str, 
    to_date: str, 
    machine: str = "ALL", 
    shift: str = "ALL",
    page: int = 1,
    page_size: int = 500
):
    """Fetches paginated data for the Partwise Report."""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        offset = (page - 1) * page_size
        shift_condition = "AND l.shift = %s" if shift != "ALL" else ""

        # The core query logic without ORDER BY or LIMIT
        base_query = f"""
            WITH ShortfallAgg AS (
                SELECT
                    l.production_date, l.machine_code, l.mould_code, l.part_number,
                    sf.reason_name, SUM(sf.quantity) as total_qty,
                    ROW_NUMBER() OVER(PARTITION BY l.production_date, l.machine_code, l.mould_code, l.part_number ORDER BY SUM(sf.quantity) DESC) as rn
                FROM production_hourly_log l
                JOIN production_shortfalls sf ON sf.log_id = l.id
                WHERE l.production_date BETWEEN %s AND %s {shift_condition}
                GROUP BY l.production_date, l.machine_code, l.mould_code, l.part_number, sf.reason_name
            ),
            TopShortfall AS (
                SELECT production_date, machine_code, mould_code, part_number, reason_name AS major_shortfall
                FROM ShortfallAgg WHERE rn = 1
            ),
            RejectionAgg AS (
                SELECT
                    l.production_date, l.machine_code, l.mould_code, l.part_number,
                    rj.reason_name, SUM(rj.quantity) as total_qty,
                    ROW_NUMBER() OVER(PARTITION BY l.production_date, l.machine_code, l.mould_code, l.part_number ORDER BY SUM(rj.quantity) DESC) as rn
                FROM production_hourly_log l
                JOIN production_rejections rj ON rj.log_id = l.id
                WHERE l.production_date BETWEEN %s AND %s {shift_condition}
                GROUP BY l.production_date, l.machine_code, l.mould_code, l.part_number, rj.reason_name
            ),
            TopRejection AS (
                SELECT production_date, machine_code, mould_code, part_number, reason_name AS major_ng
                FROM RejectionAgg WHERE rn = 1
            )
            
            SELECT
                l.production_date, MAX(l.shift) AS shift, l.machine_code, l.mould_code,
                l.part_number, pr.cavity AS no_of_cavities, MAX(l.supervisor_code) AS supervisor,
                MAX(l.operator_code) AS operator, SUM(l.target_shots) AS target_qty,
                
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 7 THEN l.actual_shots END) AS h07,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 8 THEN l.actual_shots END) AS h08,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 9 THEN l.actual_shots END) AS h09,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 10 THEN l.actual_shots END) AS h10,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 11 THEN l.actual_shots END) AS h11,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 12 THEN l.actual_shots END) AS h12,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 13 THEN l.actual_shots END) AS h13,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 14 THEN l.actual_shots END) AS h14,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 15 THEN l.actual_shots END) AS h15,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 16 THEN l.actual_shots END) AS h16,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 17 THEN l.actual_shots END) AS h17,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 18 THEN l.actual_shots END) AS h18,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 19 THEN l.actual_shots END) AS h19,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 20 THEN l.actual_shots END) AS h20,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 21 THEN l.actual_shots END) AS h21,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 22 THEN l.actual_shots END) AS h22,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 23 THEN l.actual_shots END) AS h23,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 0 THEN l.actual_shots END) AS h00,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 1 THEN l.actual_shots END) AS h01,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 2 THEN l.actual_shots END) AS h02,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 3 THEN l.actual_shots END) AS h03,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 4 THEN l.actual_shots END) AS h04,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 5 THEN l.actual_shots END) AS h05,
                SUM(CASE WHEN EXTRACT(HOUR FROM l.start_time::time) = 6 THEN l.actual_shots END) AS h06,

                SUM(l.actual_shots) AS total_actual, SUM(l.ok_parts) AS ok_qty, SUM(l.ng_parts) AS rej_qty,
                MAX(ts.major_shortfall) AS major_shortfall, MAX(tr.major_ng) AS major_ng,
                MAX(bm.remarks) AS remarks, MAX(mm.machine_process) AS process
            FROM production_hourly_log l
            LEFT JOIN part_routing pr ON pr.part_no = l.part_number AND pr.mold_no = l.mould_code
            LEFT JOIN TopShortfall ts ON ts.production_date = l.production_date AND ts.machine_code = l.machine_code AND ts.mould_code = l.mould_code AND ts.part_number = l.part_number
            LEFT JOIN TopRejection tr ON tr.production_date = l.production_date AND tr.machine_code = l.machine_code AND tr.mould_code = l.mould_code AND tr.part_number = l.part_number
            LEFT JOIN batch_master bm ON bm.batch_id = l.batch_id
            LEFT JOIN machine_master mm ON mm.machine_code = l.machine_code
            WHERE l.production_date BETWEEN %s AND %s {shift_condition}
        """
        
        # Build Parameters
        params = []
        params.extend([from_date, to_date])
        if shift != "ALL": params.append(shift)
        params.extend([from_date, to_date])
        if shift != "ALL": params.append(shift)
        params.extend([from_date, to_date])
        if shift != "ALL": params.append(shift)
        
        if machine != "ALL":
            base_query += " AND l.machine_code = %s"
            params.append(machine)

        base_query += " GROUP BY l.production_date, l.machine_code, l.mould_code, l.part_number, pr.cavity"

        # 🚨 1. Get Total Rows (For UI Pagination Math)
        count_query = f"SELECT COUNT(*) FROM ({base_query}) as total"
        cur.execute(count_query, tuple(params))
        count_row = cur.fetchone()
        total_rows = count_row[0] if count_row else 0

        # 🚨 2. Get the specific 500 rows for this page
        data_query = base_query + " ORDER BY l.production_date ASC, l.machine_code ASC LIMIT %s OFFSET %s"
        data_params = params.copy()
        data_params.extend([page_size, offset])
        
        cur.execute(data_query, tuple(data_params))
        rows = cur.fetchall()

        formatted_rows = []
        for r in rows:
            formatted_rows.append({
                "date": str(r[0]), "shift": r[1] or "-", "machine": r[2], "mould": r[3],
                "part_no": r[4], "cavities": r[5] or 1, "supervisor": r[6] or "-", "operator": r[7] or "-",
                "target_qty": r[8] or 0, "hours": [r[i] for i in range(9, 33)],
                "total_actual": r[33] or 0, "ok_qty": r[34] or 0, "rej_qty": r[35] or 0,
                "total_qty": (r[33] or 0) * (r[5] or 1), "major_shortfall": r[36] or "", 
                "major_ng": r[37] or "", "remarks": r[38] or "", "process": r[39] or ""
            })

        return {
            "rows": formatted_rows,
            "total_rows": total_rows,
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        print(f"REPORT FETCH ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/report/shift_summary")
def get_shift_summary(date: str, shift: str):
    """Fetches aggregated production quantities for the Shift Summary Report."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 
                h.machine_code,
                h.part_number,
                COALESCE(p.part_name, 'Unknown') as part_name,
                COALESCE(p.customer_name, 'Unknown') as customer_name,
                
                -- 🚨 UPDATED: Multiplies shots by active cavities for true part quantity
                SUM(h.target_shots * COALESCE(h.active_cavities, 1)) as target_qty,
                SUM(h.actual_shots * COALESCE(h.active_cavities, 1)) as total_qty,
                
                SUM(h.ok_parts) as ok_qty,
                SUM(h.ng_parts) as ng_qty,
                
                -- 🚨 UPDATED: Slices "EMP-001 - John Doe" down to just "EMP-001"
                STRING_AGG(DISTINCT SPLIT_PART(h.operator_code, ' - ', 1), ' / ') as operator_names
                
            FROM production_hourly_log h
            LEFT JOIN part_master p ON h.part_number = p.part_no
            
            WHERE h.production_date = %s 
              AND h.shift = %s
              AND h.is_no_plan = FALSE
              AND h.part_number IS NOT NULL
              AND h.part_number != 'NO PLAN'
              
            GROUP BY 
                h.machine_code,
                h.part_number,
                p.part_name,
                p.customer_name
            ORDER BY 
                h.machine_code ASC;
        """,
            (date, shift),
        )

        rows = cur.fetchall()

        report_data = []
        for r in rows:
            report_data.append(
                {
                    "machine_code": r[0],
                    "part_number": r[1],
                    "part_name": r[2],
                    "customer": r[3],
                    "target_qty": int(r[4] or 0),  
                    "total_qty": int(r[5] or 0),  
                    "ok_qty": int(r[6] or 0),
                    "ng_qty": int(r[7] or 0),
                    "operators": r[8] or "-",
                }
            )

        return report_data

    except Exception as e:
        print(f"Shift Summary Report Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

from fastapi import APIRouter, Query, HTTPException

@router.get("/api/report/moulding_machines_history")
def get_moulding_machine_history(
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
    machine: str = Query("ALL", description="Machine ID or ALL"),
    page: int = Query(1, description="Page number"),
    limit: int = Query(500, description="Items per page")
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        
        start_time_str = f"{start} 00:00:00"
        end_time_str = f"{end} 23:59:59"

        suffixes = []
        curr = start_dt.replace(day=1)
        while curr <= end_dt:
            suffixes.append(curr.strftime("%b_%Y").lower())
            if curr.month == 12:
                curr = curr.replace(year=curr.year + 1, month=1)
            else:
                curr = curr.replace(month=curr.month + 1)

        valid_tables = []
        for suffix in suffixes:
            table_name = f"moulding_machines_history1_{suffix}"
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s)", 
                (table_name,)
            )
            if cur.fetchone()[0]:
                valid_tables.append(table_name)

        if not valid_tables:
            return {"data": [], "total_rows": 0, "total_pages": 1, "current_page": 1}

        query_parts = []
        params = []
        
        for table in valid_tables:
            base_query = f"""
                SELECT history_timestamp, machine_id, parameter_name, unit, old_value, new_value, changed_by 
                FROM {table}
                WHERE history_timestamp >= %s AND history_timestamp <= %s
            """
            table_params = [start_time_str, end_time_str]
            
            if machine != "ALL":
                base_query += " AND machine_id = %s"
                table_params.append(machine)
                
            query_parts.append(base_query)
            params.extend(table_params)

        # 1. Combine queries
        combined_query = " UNION ALL ".join(query_parts)

        # 2. Get Total Row Count
        count_query = f"SELECT COUNT(*) FROM ({combined_query}) AS total_results"
        cur.execute(count_query, tuple(params))
        total_rows = cur.fetchone()[0]

        # 3. Get Paginated Data
        offset = (page - 1) * limit
        final_query = f"{combined_query} ORDER BY history_timestamp DESC LIMIT %s OFFSET %s"
        
        data_params = list(params) + [limit, offset]
        cur.execute(final_query, tuple(data_params))
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "history_timestamp": row[0],
                "machine_id": row[1],
                "parameter_name": row[2],
                "unit": row[3],
                "old_value": row[4],
                "new_value": row[5],
                "changed_by": row[6]
            })
            
        total_pages = math.ceil(total_rows / limit) if total_rows > 0 else 1

        return {
            "data": results,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "current_page": page
        }

    except Exception as e:
        print(f"History API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/report/moulding_machines_alarms")
def get_moulding_machine_alarms(
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
    machine: str = Query("ALL", description="Machine ID or ALL"),
    page: int = Query(1, description="Page number"),
    limit: int = Query(500, description="Items per page")
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        
        start_time_str = f"{start} 00:00:00"
        end_time_str = f"{end} 23:59:59"

        suffixes = []
        curr = start_dt.replace(day=1)
        while curr <= end_dt:
            suffixes.append(curr.strftime("%b_%Y").lower())
            if curr.month == 12:
                curr = curr.replace(year=curr.year + 1, month=1)
            else:
                curr = curr.replace(month=curr.month + 1)

        valid_tables = []
        for suffix in suffixes:
            table_name = f"moulding_machines_alarms_{suffix}"
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s)", 
                (table_name,)
            )
            if cur.fetchone()[0]:
                valid_tables.append(table_name)

        if not valid_tables:
            return {"data": [], "total_rows": 0, "total_pages": 1, "current_page": 1}

        query_parts = []
        params = []
        
        for table in valid_tables:
            base_query = f"""
                SELECT alarm_timestamp, machine_id, alarm_code, alarm_message, alarm_status 
                FROM {table}
                WHERE alarm_timestamp >= %s AND alarm_timestamp <= %s
            """
            table_params = [start_time_str, end_time_str]
            
            if machine != "ALL":
                base_query += " AND machine_id = %s"
                table_params.append(machine)
                
            query_parts.append(base_query)
            params.extend(table_params)

        # 1. Combine queries into a single subquery string
        combined_query = " UNION ALL ".join(query_parts)

        # 2. Get Total Row Count (to calculate total pages)
        count_query = f"SELECT COUNT(*) FROM ({combined_query}) AS total_results"
        cur.execute(count_query, tuple(params))
        total_rows = cur.fetchone()[0]

        # 3. Get Paginated Data
        offset = (page - 1) * limit
        final_query = f"{combined_query} ORDER BY alarm_timestamp DESC LIMIT %s OFFSET %s"
        
        data_params = list(params) + [limit, offset]
        cur.execute(final_query, tuple(data_params))
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "alarm_timestamp": row[0],
                "machine_id": row[1],
                "alarm_code": row[2],
                "alarm_message": row[3],
                "alarm_status": row[4]
            })
            
        total_pages = math.ceil(total_rows / limit) if total_rows > 0 else 1

        return {
            "data": results,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "current_page": page
        }

    except Exception as e:
        print(f"Alarms API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_oee_summary")
def get_oee_summary(
    start_date: str = Query(""),
    end_date: str = Query(""),
    process_name: str = Query(""),
    shift: str = Query("")
):
    """Fetches True OEE Summary by calculating dynamic shift time and precise cycle-time downtime."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            WITH BaseLogs AS (
                SELECT 
                    id as log_id,
                    split_part(batch_id, '_', 1) as b_date,
                    split_part(batch_id, '_', 2) as b_shift,
                    split_part(batch_id, '_', 3) as b_machine,
                    split_part(batch_id, '_', 5) as b_part,
                    split_part(batch_id, '_', 4) as b_process,
                    batch_id,
                    (target_shots * COALESCE(active_cavities, 1)) as target_qty,
                    (actual_shots * COALESCE(active_cavities, 1)) as actual_qty,
                    operator_code,
                    supervisor_code,
                    ((EXTRACT(EPOCH FROM end_time) - EXTRACT(EPOCH FROM start_time) + 
                      CASE WHEN end_time < start_time THEN 86400 ELSE 0 END) / 60.0) as logged_mins
                FROM production_hourly_log
                WHERE is_no_plan = false AND split_part(batch_id, '_', 5) != 'NO PLAN'
            ),
            ShiftAgg AS (
                SELECT 
                    b_date, b_shift, b_machine, b_part,
                    MAX(b_process) as process_name,
                    SUM(target_qty) as target_qty,
                    SUM(actual_qty) as total_qty,
                    SUM(logged_mins) as total_logged_mins,
                    MAX(operator_code) as operator,
                    MAX(supervisor_code) as supervisor,
                    MAX(batch_id) as max_batch_id
                FROM BaseLogs
                GROUP BY b_date, b_shift, b_machine, b_part
            ),
            DowntimeAgg AS (
                SELECT 
                    b.b_date, b.b_shift, b.b_machine, b.b_part,
                    SUM(CASE WHEN sm.oee_impact = 'None' THEN COALESCE(ps.quantity, 0) ELSE 0 END) as planned_dt_qty,
                    SUM(CASE WHEN sm.oee_impact = 'Availability' THEN COALESCE(ps.quantity, 0) ELSE 0 END) as unplanned_dt_qty,
                    (
                        SELECT ps_inner.reason_name
                        FROM production_shortfalls ps_inner
                        JOIN BaseLogs b_inner ON ps_inner.log_id = b_inner.log_id
                        WHERE b_inner.b_date = b.b_date 
                          AND b_inner.b_shift = b.b_shift 
                          AND b_inner.b_machine = b.b_machine 
                          AND b_inner.b_part = b.b_part
                          AND ps_inner.reason_name != 'Break Time' 
                        GROUP BY ps_inner.reason_name
                        ORDER BY SUM(ps_inner.quantity) DESC
                        LIMIT 1
                    ) as major_shortfall
                FROM production_shortfalls ps
                JOIN BaseLogs b ON ps.log_id = b.log_id
                LEFT JOIN shortfall_reason_master sm ON ps.reason_name = sm.reason_name
                GROUP BY b.b_date, b.b_shift, b.b_machine, b.b_part
            ),
            RejectionAgg AS (
                SELECT 
                    b.b_date, b.b_shift, b.b_machine, b.b_part,
                    SUM(pr.quantity) as total_ng_qty,
                    (
                        SELECT pr_inner.reason_name
                        FROM production_rejections pr_inner
                        JOIN BaseLogs b_inner ON pr_inner.log_id = b_inner.log_id
                        WHERE b_inner.b_date = b.b_date 
                          AND b_inner.b_shift = b.b_shift 
                          AND b_inner.b_machine = b.b_machine 
                          AND b_inner.b_part = b.b_part
                        GROUP BY pr_inner.reason_name
                        ORDER BY SUM(pr_inner.quantity) DESC
                        LIMIT 1
                    ) as major_ng
                FROM production_rejections pr
                JOIN BaseLogs b ON pr.log_id = b.log_id
                WHERE pr.quantity > 0
                GROUP BY b.b_date, b.b_shift, b.b_machine, b.b_part
            )
            SELECT 
                sa.b_date,       -- 0
                sa.b_shift,      -- 1
                sa.b_machine,    -- 2
                sa.b_part,       -- 3
                COALESCE(pm.part_name, 'Unknown') as part_name,  -- 4
                COALESCE(pm.customer_name, 'Unknown') as customer_name, -- 5
                CASE 
                    WHEN sa.b_part = 'AUTO-PART' THEN COALESCE(mm.machine_process, 'Unknown')
                    ELSE COALESCE(bm.process_name, prt.process_name, mm.machine_process, 'Unknown') 
                END as process_name,   -- 6
                
                COALESCE(sa.target_qty, 0) as target_qty,        -- 7
                COALESCE(sa.total_qty, 0) as total_qty,          -- 8
                (COALESCE(sa.total_qty, 0) - COALESCE(ra.total_ng_qty, 0)) as ok_qty, -- 9
                COALESCE(ra.total_ng_qty, 0) as ng_qty,          -- 10
                
                SPLIT_PART(sa.operator, ' - ', 1) as operator,   -- 11
                SPLIT_PART(sa.supervisor, ' - ', 1) as supervisor,-- 12
                COALESCE(bm.remarks, '-') as remarks,            -- 13 
                
                COALESCE(dt.planned_dt_qty, 0) as planned_dt_qty,      -- 14
                COALESCE(dt.unplanned_dt_qty, 0) as unplanned_dt_qty,  -- 15
                COALESCE(dt.major_shortfall, '-') as major_shortfall,  -- 16
                COALESCE(ra.major_ng, '-') as major_ng,                -- 17
                
                COALESCE(sa.total_logged_mins, 720) as total_logged_mins, -- 18
                COALESCE(prt.cycle_time, 0) as cycle_time_sec,         -- 19
                COALESCE(prt.hourly_target, 0) as hourly_target        -- 20

            FROM ShiftAgg sa
            LEFT JOIN batch_master bm ON sa.max_batch_id = bm.batch_id
            LEFT JOIN DowntimeAgg dt 
                ON sa.b_date = dt.b_date AND sa.b_shift = dt.b_shift AND sa.b_machine = dt.b_machine AND sa.b_part = dt.b_part
            LEFT JOIN RejectionAgg ra 
                ON sa.b_date = ra.b_date AND sa.b_shift = ra.b_shift AND sa.b_machine = ra.b_machine AND sa.b_part = ra.b_part
            LEFT JOIN part_master pm ON sa.b_part = pm.part_no
            LEFT JOIN machine_master mm ON sa.b_machine = mm.machine_code
            LEFT JOIN part_routing prt 
                ON sa.b_part = prt.part_no 
                AND prt.process_name = mm.machine_process
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND sa.b_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND sa.b_date <= %s"
            params.append(end_date)
        if process_name:
            query += " AND mm.machine_process = %s"
            params.append(process_name)
        if shift:
            query += " AND sa.b_shift = %s"
            params.append(shift)

        query += " ORDER BY sa.b_date DESC, sa.b_shift ASC, sa.b_machine ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            target_qty = int(r[7])
            total_qty = int(r[8])
            ok_qty = int(r[9])
            ng_qty = int(r[10])
            
            planned_dt_qty = int(r[14])
            unplanned_dt_qty = int(r[15])
            major_shortfall = r[16]
            major_ng = r[17]
            
            total_shift_time = float(r[18])  
            cycle_time_from_db = float(r[19]) 
            hourly_target = int(r[20])

            if cycle_time_from_db > 0:
                std_cycle_time_mins = cycle_time_from_db
            elif hourly_target > 0:
                std_cycle_time_mins = 60.0 / hourly_target
            else:
                std_cycle_time_mins = 0.0

            actual_math_mins = std_cycle_time_mins
            if actual_math_mins == 0.0 and target_qty > 0 and total_shift_time > 0:
                actual_math_mins = total_shift_time / target_qty

            planned_dt_mins = planned_dt_qty * actual_math_mins
            unplanned_dt_mins = unplanned_dt_qty * actual_math_mins

            # 🚨 NEW TARGET ADJUSTMENT: Synchronized with Machinewise Report logic!
            target_per_min = (target_qty / total_shift_time) if total_shift_time > 0 else 0
            
            # We ONLY subtract the target that would have been made during Availability & Planned Downtime
            adj_tgt = target_qty - ((planned_dt_mins + unplanned_dt_mins) * target_per_min)
            if adj_tgt < 0: adj_tgt = 0
            target_qty = adj_tgt

            planned_prod_time = total_shift_time - planned_dt_mins
            if planned_prod_time < 0: planned_prod_time = 0
                
            operating_time = planned_prod_time - unplanned_dt_mins
            if operating_time < 0: operating_time = 0

            # 1. Availability Math
            if planned_prod_time > 0:
                avail_pct = (operating_time / planned_prod_time) * 100
            else:
                avail_pct = 0.0

            # 2. Performance Math
            if target_qty > 0:
                perf_pct = (total_qty / target_qty) * 100
            else:
                perf_pct = 0.0
            if perf_pct > 100: perf_pct = 100.0  

            # 3. Quality Math
            if total_qty > 0:
                qual_pct = (ok_qty / total_qty) * 100
            else:
                qual_pct = 0.0

            # Overall OEE Compound Formula
            oee_pct = (avail_pct / 100) * (perf_pct / 100) * (qual_pct / 100) * 100

            records.append({
                "date": r[0],
                "shift": r[1],
                "machine": r[2],
                "part_no": r[3],
                "part_name": r[4],
                "customer_name": r[5],
                "process_name": r[6],
                "target_qty": int(target_qty), # Showing adjusted target
                "total_qty": total_qty,
                "ok_qty": ok_qty,
                "ng_qty": ng_qty,
                
                "major_ng": major_ng,
                "major_shortfall": major_shortfall,
                "planned_time": round(planned_prod_time),
                "actual_time": round(operating_time),
                "unplanned_dt_mins": round(unplanned_dt_mins),
                
                "std_cycle_time": round(std_cycle_time_mins, 2) if std_cycle_time_mins > 0 else 0.0,
                
                "avail_pct": round(avail_pct, 2),
                "perf_pct": round(perf_pct, 2),
                "qual_pct": round(qual_pct, 2),
                "oee_pct": round(oee_pct, 2),
                "op_perf_pct": round(perf_pct, 2), 
                
                "operator": r[11] or "-",
                "supervisor": r[12] or "-",
                "remarks": r[13] or ""
            })

        return {"records": records}
        
    except Exception as e:
        print("OEE Summary Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_teep_summary")
def get_teep_summary(
    start_date: str = Query(""),
    end_date: str = Query(""),
    machine: str = Query(""),
    shift: str = Query("")
):
    """Fetches TEEP (Asset OEE) Summary. Uses Total Shift Time for Availability."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            WITH BatchTargets AS (
                SELECT 
                    batch_id,
                    MAX(operator_code) as operator,
                    MAX(supervisor_code) as supervisor,
                    SUM(target_shots * COALESCE(active_cavities, 1)) as target_qty,
                    SUM(((EXTRACT(EPOCH FROM end_time) - EXTRACT(EPOCH FROM start_time) + CASE WHEN end_time < start_time THEN 86400 ELSE 0 END) / 60.0)) as logged_mins
                FROM production_hourly_log
                GROUP BY batch_id
            ),
            DowntimeAgg AS (
                SELECT 
                    hl.batch_id,
                    SUM(CASE WHEN sm.oee_impact = 'None' THEN COALESCE(ps.quantity, 0) ELSE 0 END) as planned_dt_qty,
                    SUM(CASE WHEN sm.oee_impact = 'Availability' THEN COALESCE(ps.quantity, 0) ELSE 0 END) as unplanned_dt_qty,
                    MAX(ps.reason_name) as major_shortfall
                FROM production_shortfalls ps
                JOIN production_hourly_log hl ON ps.log_id = hl.id
                LEFT JOIN shortfall_reason_master sm ON ps.reason_name = sm.reason_name
                GROUP BY hl.batch_id
            ),
            RejectionAgg AS (
                SELECT 
                    pr.batch_id,
                    MAX(pr.reason_name) as major_ng
                FROM production_rejections pr
                WHERE pr.quantity > 0
                GROUP BY pr.batch_id
            )
            SELECT 
                split_part(bm.batch_id, '_', 1) as b_date,
                split_part(bm.batch_id, '_', 2) as b_shift,
                split_part(bm.batch_id, '_', 3) as b_machine,
                split_part(bm.batch_id, '_', 5) as b_part,
                COALESCE(pm.part_name, 'Unknown') as part_name,
                COALESCE(pm.customer_name, 'Unknown') as customer_name,
                bm.process_name,
                
                COALESCE(bt.target_qty, 0) as target_qty,
                (COALESCE(bm.ok_qty, 0) + COALESCE(bm.ng_qty, 0)) as total_qty,
                COALESCE(bm.ok_qty, 0) as ok_qty,
                COALESCE(bm.ng_qty, 0) as ng_qty,
                
                SPLIT_PART(bt.operator, ' - ', 1) as operator,
                SPLIT_PART(bt.supervisor, ' - ', 1) as supervisor,
                bm.remarks,
                
                COALESCE(dt.planned_dt_qty, 0) as planned_dt_qty,
                COALESCE(dt.unplanned_dt_qty, 0) as unplanned_dt_qty,
                COALESCE(dt.major_shortfall, '-') as major_shortfall,
                COALESCE(ra.major_ng, '-') as major_ng,
                
                -- 🚨 Fetch routing data to convert parts to minutes correctly
                COALESCE(bt.logged_mins, 720) as total_logged_mins,
                COALESCE(prt.cycle_time, 0) as cycle_time_sec,
                COALESCE(prt.hourly_target, 0) as hourly_target

            FROM batch_master bm
            LEFT JOIN BatchTargets bt ON bm.batch_id = bt.batch_id
            LEFT JOIN DowntimeAgg dt ON bm.batch_id = dt.batch_id
            LEFT JOIN RejectionAgg ra ON bm.batch_id = ra.batch_id
            LEFT JOIN part_master pm ON split_part(bm.batch_id, '_', 5) = pm.part_no
            LEFT JOIN part_routing prt ON split_part(bm.batch_id, '_', 5) = prt.part_no AND bm.process_name = prt.process_name
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND split_part(bm.batch_id, '_', 1) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND split_part(bm.batch_id, '_', 1) <= %s"
            params.append(end_date)
        if machine:
            query += " AND split_part(bm.batch_id, '_', 3) = %s"
            params.append(machine)
        if shift:
            query += " AND split_part(bm.batch_id, '_', 2) = %s"
            params.append(shift)

        query += " ORDER BY split_part(bm.batch_id, '_', 1) DESC, split_part(bm.batch_id, '_', 2) ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            target_qty = int(r[7])
            total_qty = int(r[8])
            ok_qty = int(r[9])
            ng_qty = int(r[10])
            
            planned_dt_qty = int(r[14])
            unplanned_dt_qty = int(r[15])
            major_shortfall = r[16]
            major_ng = r[17]

            total_logged_mins = float(r[18])
            cycle_time_from_db = float(r[19]) 
            hourly_target = int(r[20])

            # 🚨 NEW: Calculate actual math mins to convert DT Quantity to Minutes
            if cycle_time_from_db > 0:
                std_cycle_time_mins = cycle_time_from_db
            elif hourly_target > 0:
                std_cycle_time_mins = 60.0 / hourly_target
            else:
                std_cycle_time_mins = 0.0

            actual_math_mins = std_cycle_time_mins
            if actual_math_mins == 0.0 and target_qty > 0 and total_logged_mins > 0:
                actual_math_mins = total_logged_mins / target_qty

            planned_dt_mins = planned_dt_qty * actual_math_mins
            unplanned_dt_mins = unplanned_dt_qty * actual_math_mins

            # 🚨 TARGET ADJUSTMENT
            target_per_min = (target_qty / total_logged_mins) if total_logged_mins > 0 else 0
            adj_tgt = target_qty - ((planned_dt_mins + unplanned_dt_mins) * target_per_min)
            if adj_tgt < 0: adj_tgt = 0
            target_qty = adj_tgt

            # 🚨 NEW TEEP MATH LOGIC 🚨
            total_shift_time = 720.0 
            
            # Operating time deducts all stops from the LOGGED time to find true running time
            operating_time = total_logged_mins - planned_dt_mins - unplanned_dt_mins
            if operating_time < 0: operating_time = 0

            # 1. TEEP Availability (Operating Time / TOTAL CALENDAR TIME)
            if total_shift_time > 0:
                avail_pct = (operating_time / total_shift_time) * 100
            else:
                avail_pct = 0.0

            # 2. Performance (Same as OEE, using Adjusted Target)
            if target_qty > 0:
                perf_pct = (total_qty / target_qty) * 100
            else:
                perf_pct = 0.0
            if perf_pct > 100: perf_pct = 100.0 

            # 3. Quality (Same as OEE)
            if total_qty > 0:
                qual_pct = (ok_qty / total_qty) * 100
            else:
                qual_pct = 0.0

            # TEEP Compound Formula
            teep_pct = (avail_pct / 100) * (perf_pct / 100) * (qual_pct / 100) * 100

            records.append({
                "date": r[0],
                "shift": r[1],
                "machine": r[2],
                "part_no": r[3],
                "part_name": r[4],
                "customer_name": r[5],
                "process_name": r[6],
                "target_qty": int(target_qty),
                "total_qty": total_qty,
                "ok_qty": ok_qty,
                "ng_qty": ng_qty,
                "major_ng": major_ng,
                "major_shortfall": major_shortfall,
                
                # Expose the specific times for the executive view
                "total_time": round(total_shift_time),
                "planned_dt": round(planned_dt_mins),
                "unplanned_dt": round(unplanned_dt_mins),
                "actual_run_time": round(operating_time),
                
                "avail_pct": round(avail_pct, 2),
                "perf_pct": round(perf_pct, 2),
                "qual_pct": round(qual_pct, 2),
                "teep_pct": round(teep_pct, 2),
                
                "operator": r[11] or "-",
                "supervisor": r[12] or "-",
                "remarks": r[13] or ""
            })

        return {"records": records}
        
    except Exception as e:
        print("TEEP Summary Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_teep_summary_idle_machines")
def get_teep_summary_idle_machines(
    start_date: str = Query(""),
    end_date: str = Query(""),
    machine: str = Query(""),
    shift: str = Query("")
):
    """Fetches TEEP (Asset OEE) Summary. Drives from hourly_log to include Idle machines."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Base query on production_hourly_log to capture auto-logged idle time
        query = """
            WITH HourlyAgg AS (
                SELECT 
                    batch_id,
                    production_date,
                    shift,
                    machine_code,
                    MAX(part_number) as part_number,
                    MAX(operator_code) as operator,
                    MAX(supervisor_code) as supervisor,
                    SUM(target_shots * COALESCE(active_cavities, 1)) as target_qty,
                    SUM(ok_parts + ng_parts) as total_qty,
                    SUM(ok_parts) as ok_qty,
                    SUM(ng_parts) as ng_qty
                FROM production_hourly_log
                WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND production_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND production_date <= %s"
            params.append(end_date)
        if machine:
            query += " AND machine_code = %s"
            params.append(machine)
        if shift:
            query += " AND shift = %s"
            params.append(shift)

        query += """
                GROUP BY batch_id, production_date, shift, machine_code
            ),
            DowntimeAgg AS (
                SELECT 
                    hl.batch_id,
                    -- Convert Missing Shots to Minutes: (Shots * Cycle Time) / 60
                    SUM(CASE WHEN sm.oee_impact = 'None' 
                             THEN (COALESCE(ps.quantity, 0) * COALESCE(pr.cycle_time, 0)) 
                             ELSE 0 END) as planned_dt_mins,
                    SUM(CASE WHEN sm.oee_impact = 'Availability' 
                             THEN (COALESCE(ps.quantity, 0) * COALESCE(pr.cycle_time, 0))
                             ELSE 0 END) as unplanned_dt_mins,
                    MAX(ps.reason_name) as major_shortfall
                FROM production_shortfalls ps
                JOIN production_hourly_log hl ON ps.log_id = hl.id
                LEFT JOIN shortfall_reason_master sm ON ps.reason_name = sm.reason_name
                -- Join part_routing to fetch the correct cycle time for the math
                LEFT JOIN part_routing pr ON hl.part_number = pr.part_no AND hl.mould_code = pr.mold_no
                GROUP BY hl.batch_id
            ),
            RejectionAgg AS (
                SELECT 
                    pr.batch_id,
                    MAX(pr.reason_name) as major_ng
                FROM production_rejections pr
                WHERE pr.quantity > 0
                GROUP BY pr.batch_id
            )
            SELECT 
                ha.production_date as b_date,
                ha.shift as b_shift,
                ha.machine_code as b_machine,
                ha.part_number as b_part,
                COALESCE(pm.part_name, CASE WHEN ha.part_number = 'AUTO-PART' THEN 'IDLE / NO PLAN' ELSE 'Unknown' END) as part_name,
                COALESCE(pm.customer_name, '-') as customer_name,
                COALESCE(mm.machine_process, 'UNKNOWN') as process_name,
                
                COALESCE(ha.target_qty, 0) as target_qty,
                COALESCE(ha.total_qty, 0) as total_qty,
                COALESCE(ha.ok_qty, 0) as ok_qty,
                COALESCE(ha.ng_qty, 0) as ng_qty,
                
                SPLIT_PART(ha.operator, ' - ', 1) as operator,
                SPLIT_PART(ha.supervisor, ' - ', 1) as supervisor,
                COALESCE(bm.remarks, CASE WHEN ha.part_number = 'AUTO-PART' THEN 'Auto-Logged Idle Time' ELSE '' END) as remarks,
                
                COALESCE(dt.planned_dt_mins, CASE WHEN ha.part_number = 'AUTO-PART' THEN 720 ELSE 0 END) as planned_dt_mins,
                COALESCE(dt.unplanned_dt_mins, 0) as unplanned_dt_mins,
                COALESCE(dt.major_shortfall, CASE WHEN ha.part_number = 'AUTO-PART' THEN 'No Plan' ELSE '-' END) as major_shortfall,
                COALESCE(ra.major_ng, '-') as major_ng

            FROM HourlyAgg ha
            LEFT JOIN machine_master mm ON ha.machine_code = mm.machine_code
            LEFT JOIN DowntimeAgg dt ON ha.batch_id = dt.batch_id
            LEFT JOIN RejectionAgg ra ON ha.batch_id = ra.batch_id
            LEFT JOIN part_master pm ON ha.part_number = pm.part_no
            LEFT JOIN batch_master bm ON ha.batch_id = bm.batch_id
            ORDER BY ha.production_date DESC, ha.shift ASC, mm.machine_process ASC, ha.machine_code ASC
        """
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            target_qty = int(r[7])
            total_qty = int(r[8])
            ok_qty = int(r[9])
            ng_qty = int(r[10])
            
            planned_dt_mins = float(r[14])
            unplanned_dt_mins = float(r[15])
            major_shortfall = r[16]
            major_ng = r[17]

            # 🚨 TEEP MATH LOGIC 🚨
            total_shift_time = 720.0 
            operating_time = total_shift_time - planned_dt_mins - unplanned_dt_mins
            if operating_time < 0: operating_time = 0.0

            if total_shift_time > 0:
                avail_pct = (operating_time / total_shift_time) * 100
            else:
                avail_pct = 0.0

            if target_qty > 0:
                perf_pct = (total_qty / target_qty) * 100
            else:
                perf_pct = 0.0
            if perf_pct > 100: perf_pct = 100.0 

            if total_qty > 0:
                qual_pct = (ok_qty / total_qty) * 100
            else:
                qual_pct = 0.0

            teep_pct = (avail_pct / 100) * (perf_pct / 100) * (qual_pct / 100) * 100

            records.append({
                "date": str(r[0]),
                "shift": r[1],
                "machine": r[2],
                "part_no": r[3],
                "part_name": r[4],
                "customer_name": r[5],
                "process_name": r[6],
                "target_qty": target_qty,
                "total_qty": total_qty,
                "ok_qty": ok_qty,
                "ng_qty": ng_qty,
                "major_ng": major_ng,
                "major_shortfall": major_shortfall,
                
                "total_time": round(total_shift_time),
                "planned_dt": round(planned_dt_mins),
                "unplanned_dt": round(unplanned_dt_mins),
                "actual_run_time": round(operating_time),
                
                "avail_pct": round(avail_pct, 2),
                "perf_pct": round(perf_pct, 2),
                "qual_pct": round(qual_pct, 2),
                "teep_pct": round(teep_pct, 2),
                
                "operator": r[11] or "-",
                "supervisor": r[12] or "-",
                "remarks": r[13] or ""
            })

        return {"records": records}
        
    except Exception as e:
        print("TEEP Summary Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_iot_summary")
def get_iot_summary(
    summary_date: str = Query(...), 
    machine_code: str = Query("")
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # ==========================================
        # 1. FETCH IOT AUTOMATED DATA
        # ==========================================
        query = """
            SELECT 
                machine_code, hour_no, start_time, stop_time, 
                part_count, avg_cycle_sec, min_cycle_sec, max_cycle_sec, 
                runtime_sec, idle_sec, machine_status
            FROM machine_hourly_summary
            WHERE summary_date = %s
        """
        params = [summary_date]

        if machine_code:
            query += " AND machine_code = %s"
            params.append(machine_code)

        query += " ORDER BY machine_code ASC, hour_no ASC"
        cur.execute(query, tuple(params))
        iot_rows = cur.fetchall()

        # ==========================================
        # 2. FETCH MANUAL OPERATOR DATA (For Discrepancy Check)
        # ==========================================
        manual_query = """
            SELECT 
                machine_code, 
                EXTRACT(HOUR FROM start_time::time) as hr, 
                SUM(actual_shots) as total_manual
            FROM production_hourly_log
            WHERE production_date = %s
        """
        manual_params = [summary_date]
        
        if machine_code:
            manual_query += " AND machine_code = %s"
            manual_params.append(machine_code)
            
        manual_query += " GROUP BY machine_code, EXTRACT(HOUR FROM start_time::time)"
        cur.execute(manual_query, tuple(manual_params))
        manual_rows = cur.fetchall()

        # Build a fast dictionary to look up manual quantities: dict[machine][hour]
        manual_dict = {}
        for m_row in manual_rows:
            mc, hr, total = m_row
            if mc not in manual_dict:
                manual_dict[mc] = {}
            manual_dict[mc][int(hr)] = int(total)

        # ==========================================
        # 3. MERGE AND FORMAT
        # ==========================================
        records = []
        total_parts = 0
        total_runtime = 0
        total_idle = 0

        for r in iot_rows:
            mc, hr, st_time, sp_time, count, avg_cyc, min_cyc, max_cyc, run_s, idle_s, status = r
            
            total_parts += count
            total_runtime += run_s
            total_idle += idle_s

            # Grab the matching manual quantity from our dictionary
            manual_qty = manual_dict.get(mc, {}).get(int(hr), 0)

            records.append({
                "machine_code": mc,
                "hour_no": hr,
                "start_time": str(st_time)[11:19] if st_time else "-",
                "stop_time": str(sp_time)[11:19] if sp_time else "-",
                "part_count": count,
                "manual_qty": manual_qty, # <--- NEW FIELD FOR DISCREPANCY TABLE
                "avg_cycle": round(avg_cyc, 1) if avg_cyc else 0.0,
                "min_cycle": round(min_cyc, 1) if min_cyc else 0.0,
                "max_cycle": round(max_cyc, 1) if max_cyc else 0.0,
                "runtime_min": round(run_s / 60, 1),
                "idle_min": round(idle_s / 60, 1),
                "status": status
            })

        total_time = total_runtime + total_idle
        availability = round((total_runtime / total_time) * 100, 1) if total_time > 0 else 0.0

        return {
            "records": records,
            "summary": {
                "total_parts": total_parts,
                "total_runtime_hrs": round(total_runtime / 3600, 2),
                "total_idle_hrs": round(total_idle / 3600, 2),
                "hardware_availability": availability
            }
        }

    except Exception as e:
        print(f"IOT SUMMARY ERROR: {str(e)}")
        # If running FastAPI, ensure HTTPException is imported
        # raise HTTPException(status_code=500, detail="Failed to fetch IoT data")
        return {"error": "Failed to fetch IoT data", "details": str(e)}
    finally:
        cur.close()
        conn.close()

@router.get("/api/report/historical_iot")
def get_historical_iot(
    start_date: str = Query(...), 
    end_date: str = Query(...), 
    machine_code: str = Query("ALL")
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Step 1: Base query using CTEs (Common Table Expressions) for clean merging
        query = """
        WITH ManualData AS (
            SELECT 
                production_date, machine_code, 
                EXTRACT(HOUR FROM start_time::time) as hr, 
                SUM(actual_shots) as total_manual, 
                MAX(operator_code) as operator_name
            FROM production_hourly_log
            WHERE production_date BETWEEN %s AND %s
            GROUP BY production_date, machine_code, EXTRACT(HOUR FROM start_time::time)
        ),
        IoTData AS (
            SELECT 
                summary_date, machine_code, hour_no, part_count, 
                runtime_sec, idle_sec, avg_cycle_sec
            FROM machine_hourly_summary
            WHERE summary_date BETWEEN %s AND %s
        )
        SELECT
            COALESCE(I.summary_date, M.production_date) as report_date,
            COALESCE(I.machine_code, M.machine_code) as machine,
            COALESCE(I.hour_no, M.hr) as hour_block,
            COALESCE(I.part_count, 0) as iot_qty,
            COALESCE(M.total_manual, 0) as manual_qty,
            COALESCE(I.runtime_sec, 0) as run_sec,
            COALESCE(I.idle_sec, 0) as idle_sec,
            COALESCE(I.avg_cycle_sec, 0) as avg_cycle,
            COALESCE(M.operator_name, 'No Operator Logged') as operator
        FROM IoTData I
        FULL OUTER JOIN ManualData M
            ON I.summary_date = M.production_date 
            AND I.machine_code = M.machine_code 
            AND I.hour_no = M.hr
        """
        
        # Parameters for the BETWEEN clauses (used twice)
        params = [start_date, end_date, start_date, end_date]

        if machine_code and machine_code != "ALL":
            query += " WHERE COALESCE(I.machine_code, M.machine_code) = %s"
            params.append(machine_code)

        query += " ORDER BY report_date DESC, machine ASC, hour_block ASC"
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            rep_date, mc, hr, iot_q, man_q, run_s, idle_s, avg_cyc, op = r
            
            # Math calculations for the frontend
            missing = iot_q - man_q
            status = "Match"
            if missing > 0: status = "Under-Reported"
            elif missing < 0: status = "Over-Reported"

            records.append({
                "date": str(rep_date),
                "machine": mc,
                "hour": f"{int(hr):02d}:00",
                "iot_qty": iot_q,
                "manual_qty": int(man_q),
                "variance": missing,
                "status": status,
                "runtime_min": round(run_s / 60, 1),
                "idle_min": round(idle_s / 60, 1),
                "avg_cycle": round(float(avg_cyc), 1),
                "operator": op
            })

        return {"status": "success", "records": records}

    except Exception as e:
        print(f"Historical IoT Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database Error")
    finally:
        cur.close()
        conn.close()
        
@router.get("/api/test-telegram")
def test_telegram_alert():
    """Instantly triggers the hourly report for testing purposes."""
    try:
        generate_hourly_report()
        return {"status": "success", "message": "Test report sent to Telegram!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/api/get_oeeteep_process_summary")
def get_oeeteep_process_summary(
    start_date: str = Query(""),
    end_date: str = Query(""),
    process: str = Query(""),
    machine: str = Query("")
):
    """Fetches highly aggregated OEE and TEEP data grouped entirely by Process."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            WITH BatchTargets AS (
                SELECT 
                    batch_id,
                    SUM(target_shots * COALESCE(active_cavities, 1)) as target_qty
                FROM production_hourly_log
                GROUP BY batch_id
            ),
            DowntimeAgg AS (
                SELECT 
                    hl.batch_id,
                    SUM(CASE WHEN sm.oee_impact = 'None' THEN COALESCE(ps.quantity, 0) ELSE 0 END) as planned_dt_mins,
                    SUM(CASE WHEN sm.oee_impact = 'Availability' THEN COALESCE(ps.quantity, 0) ELSE 0 END) as unplanned_dt_mins
                FROM production_shortfalls ps
                JOIN production_hourly_log hl ON ps.log_id = hl.id
                LEFT JOIN shortfall_reason_master sm ON ps.reason_name = sm.reason_name
                GROUP BY hl.batch_id
            )
            SELECT 
                bm.process_name,
                COUNT(DISTINCT bm.batch_id) as total_batches,
                SUM(COALESCE(bt.target_qty, 0)) as total_target_qty,
                SUM(COALESCE(bm.ok_qty, 0) + COALESCE(bm.ng_qty, 0)) as total_produced_qty,
                SUM(COALESCE(bm.ok_qty, 0)) as total_ok_qty,
                SUM(COALESCE(dt.planned_dt_mins, 0)) as total_planned_dt,
                SUM(COALESCE(dt.unplanned_dt_mins, 0)) as total_unplanned_dt
            FROM batch_master bm
            LEFT JOIN BatchTargets bt ON bm.batch_id = bt.batch_id
            LEFT JOIN DowntimeAgg dt ON bm.batch_id = dt.batch_id
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND split_part(bm.batch_id, '_', 1) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND split_part(bm.batch_id, '_', 1) <= %s"
            params.append(end_date)
        if process:
            query += " AND UPPER(bm.process_name) = UPPER(%s)"
            params.append(process)
        if machine:
            query += " AND split_part(bm.batch_id, '_', 3) = %s"
            params.append(machine)

        query += " GROUP BY bm.process_name"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            process_name = r[0] or "Unknown"
            total_batches = int(r[1])
            
            target_qty = int(r[2])
            total_qty = int(r[3])
            ok_qty = int(r[4])
            
            planned_dt_mins = float(r[5])
            unplanned_dt_mins = float(r[6])

            # --- AGGREGATED TIME MATH ---
            # If 10 batches ran, the total maximum asset time is 10 * 720 mins
            total_shift_time = total_batches * 720.0 
            planned_prod_time = total_shift_time - planned_dt_mins
            operating_time = planned_prod_time - unplanned_dt_mins

            # --- SHARED MATH ---
            perf_pct = (total_qty / target_qty * 100) if target_qty > 0 else 0.0
            if perf_pct > 100: perf_pct = 100.0 
            
            qual_pct = (ok_qty / total_qty * 100) if total_qty > 0 else 0.0

            # --- OEE (EQUIPMENT) MATH ---
            oee_avail_pct = (operating_time / planned_prod_time * 100) if planned_prod_time > 0 else 0.0
            oee_pct = (oee_avail_pct / 100) * (perf_pct / 100) * (qual_pct / 100) * 100

            # --- TEEP (ASSET) MATH ---
            teep_avail_pct = (operating_time / total_shift_time * 100) if total_shift_time > 0 else 0.0
            teep_pct = (teep_avail_pct / 100) * (perf_pct / 100) * (qual_pct / 100) * 100

            records.append({
                "process_name": process_name.upper(),
                "total_batches": total_batches,
                
                # Times
                "total_shift_time": round(total_shift_time),
                "planned_prod_time": round(planned_prod_time),
                "operating_time": round(operating_time),
                
                # OEE Metrics
                "oee_avail_pct": round(oee_avail_pct, 2),
                "perf_pct": round(perf_pct, 2),
                "qual_pct": round(qual_pct, 2),
                "oee_pct": round(oee_pct, 2),
                
                # TEEP Metrics
                "teep_avail_pct": round(teep_avail_pct, 2),
                "teep_pct": round(teep_pct, 2)
            })

        return {"records": records}
        
    except Exception as e:
        print("OEE/TEEP Process Summary Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/cycle_time_variance")
def get_cycle_time_variance(
    start_date: str = Query(""),
    end_date: str = Query(""),
    machine: str = Query("")
):
    """Fetches IoT cycle time data, joins it with production logs, and calculates variance dynamically per month."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 1. Dynamically figure out the table name based on the start_date
        # Expecting format "YYYY-MM-DD"
        if start_date:
            dt_obj = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            dt_obj = datetime.now()
            
        month_abbr = dt_obj.strftime("%b").lower()  # e.g., 'aug', 'sep', 'oct'
        year_str = dt_obj.strftime("%Y")            # e.g., '2026'
        
        # Constructs: "moulding_machines_monitor1_sep_2026"
        iot_table_name = f"moulding_machines_monitor1_{month_abbr}_{year_str}"

        # 2. Inject the dynamic table name into the query using an f-string
        query = f"""
            WITH ShiftBounds AS (
                SELECT 
                    machine_code,
                    part_number,
                    'MOULDING' as process_name,
                    (production_date + start_time) as actual_start,
                    (production_date + end_time + 
                        (CASE WHEN end_time < start_time THEN INTERVAL '1 day' ELSE INTERVAL '0' END)
                    ) as actual_end
                FROM production_hourly_log
                WHERE production_date >= %s AND production_date <= %s
                  AND is_no_plan = false
            ),
            MatchedIoT AS (
                SELECT 
                    sb.machine_code,
                    sb.part_number,
                    sb.process_name,
                    iot.cycle_time
                FROM ShiftBounds sb
                JOIN {iot_table_name} iot
                  ON iot.machine_id = sb.machine_code
                 AND iot.monitor_timestamp >= sb.actual_start
                 AND iot.monitor_timestamp < sb.actual_end
                 AND iot.cycle_time > 0
            )
            SELECT 
                m.machine_code,
                m.part_number,
                m.process_name,
                MIN(m.cycle_time) as min_ct,
                MAX(m.cycle_time) as max_ct,
                AVG(m.cycle_time) as avg_ct,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.cycle_time) as median_ct,
                COALESCE(pr.hourly_target, 0) as hourly_target,
                COALESCE(pr.cycle_time, 0) as routing_ct_mins
            FROM MatchedIoT m
            LEFT JOIN part_routing pr 
              ON pr.part_no = m.part_number 
             AND pr.process_name = 'MOULDING'
            WHERE 1=1
        """
        params = [start_date, end_date]

        if machine:
            query += " AND m.machine_code = %s"
            params.append(machine)

        query += " GROUP BY m.machine_code, m.part_number, m.process_name, pr.hourly_target, pr.cycle_time"
        query += " ORDER BY m.machine_code ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            machine_code = r[0]
            part_no = r[1]
            process = r[2]
            min_ct = float(r[3]) if r[3] else 0.0
            max_ct = float(r[4]) if r[4] else 0.0
            avg_ct = float(r[5]) if r[5] else 0.0
            median_ct = float(r[6]) if r[6] else 0.0
            
            hourly_target = int(r[7])
            routing_ct_mins = float(r[8])

            # Convert Standard CT to SECONDS mathematically
            std_ct_sec = 0.0
            if hourly_target > 0:
                std_ct_sec = 3600.0 / hourly_target
            elif routing_ct_mins > 0:
                std_ct_sec = routing_ct_mins * 60.0

            # Calculate Variance % 
            variance_pct = 0.0
            if std_ct_sec > 0 and avg_ct > 0:
                variance_pct = ((avg_ct - std_ct_sec) / std_ct_sec) * 100

            records.append({
                "machine_code": machine_code,
                "part_no": part_no,
                "process_name": process,
                "min_ct": round(min_ct, 1),
                "max_ct": round(max_ct, 1),
                "avg_ct": round(avg_ct, 1),
                "std_ct": round(std_ct_sec, 1),
                "median_ct": round(median_ct, 1),
                "variance_pct": round(variance_pct, 1)
            })
        # 🚨 NEW: Sort the records by variance_pct in ascending order
        # Negative (Top) -> Zero (Middle) -> Positive (Bottom)
        records.sort(key=lambda x: x["variance_pct"])
        return {"records": records}
    except Exception as e:
        print("Cycle Time Variance Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/machine_list")
def get_machine_list():
    """Fetches active machines, processes, and lines for 3-tier cascading dropdowns."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 NEW: LEFT JOIN links the machine's process to the process_master table to find the line
        cur.execute("""
            SELECT m.machine_code, m.machine_name, m.machine_process, p.production_line 
            FROM machine_master m
            LEFT JOIN process_master p ON m.machine_process = p.process
            WHERE m.is_active = true 
            ORDER BY m.machine_code ASC
        """)
        
        machines = [
            {
                "machine_code": row[0], 
                "machine_name": row[1], 
                "machine_process": row[2],
                "production_line": row[3] if row[3] else "Unassigned" # Handles missing maps safely
            } 
            for row in cur.fetchall()
        ]
        
        return {"machines": machines}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/machinewise_oee_report")
def get_machinewise_oee_report(
    start_date: str = Query(""),
    end_date: str = Query(""),
    machine: str = Query("")
):
    """Calculates Machine-wise OEE and Downtime Breakdown dynamically per machine."""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # NEW: Fetch OEE Impact rules from the master table
        cur.execute("SELECT DISTINCT category, oee_impact FROM shortfall_reason_master WHERE is_active = true")
        impact_map = {row[0]: row[1] for row in cur.fetchall()}
        
        def get_impact(category_name):
            # Default to Availability if someone creates a category without setting the impact
            return impact_map.get(category_name, 'Availability')
            
        query = """
        WITH BaseLogs AS (
            SELECT 
                log.id as log_id,
                split_part(log.batch_id, '_', 3) as machine_code,
                
                -- 🚨 Extract active cavities to correctly calculate downtime minutes later
                COALESCE(log.active_cavities, 1) as active_cavities,
                
                -- Extracting and multiplying quantities directly from the log
                log.target_shots * COALESCE(log.active_cavities, 1) as target_qty,
                log.actual_shots * COALESCE(log.active_cavities, 1) as actual_qty,
                log.ng_parts as ng_qty,
                
                ((EXTRACT(EPOCH FROM log.end_time) - EXTRACT(EPOCH FROM log.start_time) + CASE WHEN log.end_time < log.start_time THEN 86400 ELSE 0 END) / 60.0) as logged_mins,
                CASE WHEN pr.cycle_time > 0 THEN pr.cycle_time 
                     WHEN pr.hourly_target > 0 THEN 60.0 / pr.hourly_target 
                     ELSE 0 END as ct_mins,
                CASE WHEN log.is_no_plan = true THEN 1 ELSE 0 END as is_no_plan
            FROM production_hourly_log log
            LEFT JOIN part_routing pr ON pr.part_no = split_part(log.batch_id, '_', 5) AND pr.process_name = split_part(log.batch_id, '_', 4)
            WHERE split_part(log.batch_id, '_', 1) >= %s AND split_part(log.batch_id, '_', 1) <= %s
        ),
        AggLogs AS (
            SELECT 
                b.log_id,
                b.machine_code,
                b.active_cavities, -- 🚨 Pass cavities down to the final select
                b.target_qty,
                b.actual_qty,
                b.ng_qty,
                b.logged_mins,
                b.is_no_plan,
                CASE WHEN b.ct_mins > 0 THEN b.ct_mins 
                     WHEN b.target_qty > 0 THEN b.logged_mins / b.target_qty
                     ELSE 0 END as final_ct_mins,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Mould Changeover'), 0) as dt_mould,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Planning / Management'), 0) as dt_plan,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Machine Breakdown'), 0) as dt_machine,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Tooling Issue'), 0) as dt_tooling,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Material Shortage'), 0) as dt_material,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Utility Failure'), 0) as dt_utility,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Operator Efficiency'), 0) as dt_operator,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Manpower Shortage'), 0) as dt_manpower,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Process & Quality'), 0) as dt_process,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Planned Maintenance'), 0) as dt_maint,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Break Time'), 0) as dt_break
            FROM BaseLogs b
        )
        SELECT 
            machine_code,
            SUM(target_qty), 
            SUM(actual_qty),
            SUM(ng_qty),
            SUM(logged_mins),
            SUM(CASE WHEN is_no_plan = 1 THEN logged_mins ELSE 0 END),
            
            -- 🚨 Missing shots multiplied by cavities before calculating minutes
            SUM(dt_mould * active_cavities * final_ct_mins),
            SUM(dt_plan * active_cavities * final_ct_mins),
            SUM(dt_machine * active_cavities * final_ct_mins),
            SUM(dt_tooling * active_cavities * final_ct_mins),
            SUM(dt_material * active_cavities * final_ct_mins),
            SUM(dt_utility * active_cavities * final_ct_mins),
            SUM(dt_operator * active_cavities * final_ct_mins),
            SUM(dt_manpower * active_cavities * final_ct_mins),
            SUM(dt_process * active_cavities * final_ct_mins),
            SUM(dt_maint * active_cavities * final_ct_mins),
            SUM(dt_break * active_cavities * final_ct_mins)
        FROM AggLogs
        WHERE 1=1
        """
        
        params = [start_date, end_date]
        if machine and machine != "ALL":
            # Split the comma-separated string into a tuple for the SQL 'IN' clause
            machine_list = tuple(machine.split(','))
            query += " AND machine_code IN %s"
            params.append(machine_list)
            
        query += " GROUP BY machine_code ORDER BY machine_code ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        # Calculate total theoretical minutes in the selected date range
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (d2 - d1).days + 1
        total_range_mins = total_days * 24 * 60

        # Helper function to format minutes into y, mo, w, d, h, m
        def format_time(mins):
            if mins <= 0: return "0"
            mins = int(mins) 
            y = mins // 525600       
            mins %= 525600
            mo = mins // 43200       
            mins %= 43200
            w = mins // 10080        
            mins %= 10080
            d = mins // 1440         
            mins %= 1440
            h = mins // 60
            m = mins % 60
            parts = []
            if y > 0: parts.append(f"{y}y")
            if mo > 0: parts.append(f"{mo}mo")
            if w > 0: parts.append(f"{w}w")
            if d > 0: parts.append(f"{d}d")
            if h > 0: parts.append(f"{h}h")
            if m > 0 or not parts: parts.append(f"{m}m")
            return " ".join(parts)

        # 🚨 NEW: Helper function to format downtime with percentages
        def format_dt(mins, total_mins):
            if mins <= 0: return "0"
            pct = round((mins / total_mins * 100), 1) if total_mins > 0 else 0.0
            return f"{format_time(mins)} ({pct}%)"

        # 🚨 1. Setup running totals for the "Consolidated Summary" column
        tot_tgt = 0; tot_act = 0; tot_ng = 0
        tot_plan_prod = 0; tot_no_plan = 0; tot_op_time = 0
        tot_dt = { "mould": 0, "plan": 0, "machine": 0, "tooling": 0, "material": 0, "utility": 0, "operator": 0, "manpower": 0, "process": 0, "maint": 0, "break": 0 }

        records = []
        for row in rows:
            tgt = float(row[1])
            act = float(row[2])
            ng = float(row[3])
            logged_mins = float(row[4])
            no_plan_mins = float(row[5])
            
            # 1. Extract the raw minutes
            dt_mould = float(row[6]); dt_plan = float(row[7]); dt_machine = float(row[8]); dt_tooling = float(row[9])
            dt_material = float(row[10]); dt_utility = float(row[11]); dt_operator = float(row[12]); dt_manpower = float(row[13])
            dt_process = float(row[14]); dt_maint = float(row[15]); dt_break = float(row[16])
            
            # 2. Map minutes to their UI categories to dynamically check their OEE Impact
            dt_dict = {
                "Mould Changeover": dt_mould,
                "Planning / Management": dt_plan,
                "Machine Breakdown": dt_machine,
                "Tooling Issue": dt_tooling,
                "Material Shortage": dt_material,
                "Utility Failure": dt_utility,
                "Operator Efficiency": dt_operator,
                "Manpower Shortage": dt_manpower,
                "Process & Quality": dt_process,
                "Planned Maintenance": dt_maint,
                "Break Time": dt_break
            }
            
            # 3. Sort the minutes into the correct OEE buckets dynamically
            avail_loss_mins = sum(mins for cat, mins in dt_dict.items() if get_impact(cat) == 'Availability')
            perf_loss_mins = sum(mins for cat, mins in dt_dict.items() if get_impact(cat) == 'Performance')

            # Math
            planned_prod_time = total_range_mins - no_plan_mins
            if planned_prod_time < 0: planned_prod_time = 0
                
            logged_prod_mins = logged_mins - no_plan_mins
            if logged_prod_mins < 0: logged_prod_mins = 0
                
            # UPDATE: Operating time is now reduced by BOTH Availability and Performance Losses
            operating_time = logged_prod_mins - avail_loss_mins - perf_loss_mins
            if operating_time < 0: operating_time = 0
                
            # RECALCULATE TARGET QUANTITY
            target_per_min = (tgt / logged_prod_mins) if logged_prod_mins > 0 else 0
            
            # UPDATE: Target is reduced by BOTH Availability and Performance Downtime
            adj_tgt = tgt - ((avail_loss_mins + perf_loss_mins) * target_per_min)
            if adj_tgt < 0: adj_tgt = 0
            
            tgt = adj_tgt
            
            # 🚨 2. Calculate percentages based on the total available calendar time
            pct_planned = round((planned_prod_time / total_range_mins * 100), 1) if total_range_mins > 0 else 0.0
            pct_no_plan = round((no_plan_mins / total_range_mins * 100), 1) if total_range_mins > 0 else 0.0
            pct_actual = round((operating_time / total_range_mins * 100), 1) if total_range_mins > 0 else 0.0
            
            # Add to running totals
            tot_tgt += tgt; tot_act += act; tot_ng += ng
            tot_plan_prod += planned_prod_time; tot_no_plan += no_plan_mins; tot_op_time += operating_time
            tot_dt["mould"] += dt_mould; tot_dt["plan"] += dt_plan; tot_dt["machine"] += dt_machine
            tot_dt["tooling"] += dt_tooling; tot_dt["material"] += dt_material; tot_dt["utility"] += dt_utility
            tot_dt["operator"] += dt_operator; tot_dt["manpower"] += dt_manpower; tot_dt["process"] += dt_process
            tot_dt["maint"] += dt_maint; tot_dt["break"] += dt_break

            # OEE Percentages 
            avail_pct = (operating_time / planned_prod_time * 100) if planned_prod_time > 0 else 0.0
            perf_pct = (act / tgt * 100) if tgt > 0 else 0.0
            if perf_pct > 100: perf_pct = 100.0
            qual_pct = ((act - ng) / act * 100) if act > 0 else 0.0
            oee_pct = (avail_pct / 100) * (perf_pct / 100) * (qual_pct / 100) * 100
            
            records.append({
                "machine": row[0],
                "oee": round(oee_pct, 2), "availability": round(avail_pct, 2),
                "performance": round(perf_pct, 2), "quality": round(qual_pct, 2),
                "target": int(tgt), "actual": int(act), "rejection": int(ng),
                
                # 🚨 3. Inject the percentage string dynamically
                "planned_prod_time": f"{format_time(planned_prod_time)} ({pct_planned}%)",
                "no_plan_time": f"{format_time(no_plan_mins)} ({pct_no_plan}%)",
                "actual_op_time": f"{format_time(operating_time)} ({pct_actual}%)",
                
                # 🚨 UPDATED: Apply format_dt to inject percentages dynamically
                "mould_changeover": format_dt(dt_mould, total_range_mins),
                "planning_management": format_dt(dt_plan, total_range_mins),
                "machine_breakdown": format_dt(dt_machine, total_range_mins),
                "tooling_issue": format_dt(dt_tooling, total_range_mins),
                "material_shortage": format_dt(dt_material, total_range_mins),
                "utility_failure": format_dt(dt_utility, total_range_mins),
                "operator_efficiency": format_dt(dt_operator, total_range_mins),
                "manpower_shortage": format_dt(dt_manpower, total_range_mins),
                "process_quality": format_dt(dt_process, total_range_mins),
                "planned_maintenance": format_dt(dt_maint, total_range_mins),
                "break_time": format_dt(dt_break, total_range_mins)
            })

        # 🚨 4. Append the Summary column with Plant-Wide Percentages
        if (not machine or machine == "ALL") and len(records) > 0:
            overall_avail = (tot_op_time / tot_plan_prod * 100) if tot_plan_prod > 0 else 0.0
            overall_perf = (tot_act / tot_tgt * 100) if tot_tgt > 0 else 0.0
            if overall_perf > 100: overall_perf = 100.0
            overall_qual = ((tot_act - tot_ng) / tot_act * 100) if tot_act > 0 else 0.0
            overall_oee = (overall_avail / 100) * (overall_perf / 100) * (overall_qual / 100) * 100
            
            # Plant-wide total calendar capacity
            tot_calendar_mins = tot_plan_prod + tot_no_plan
            
            tot_pct_planned = round((tot_plan_prod / tot_calendar_mins * 100), 1) if tot_calendar_mins > 0 else 0.0
            tot_pct_no_plan = round((tot_no_plan / tot_calendar_mins * 100), 1) if tot_calendar_mins > 0 else 0.0
            tot_pct_actual = round((tot_op_time / tot_calendar_mins * 100), 1) if tot_calendar_mins > 0 else 0.0

            records.append({
                "machine": "Consolidated Summary",
                "oee": round(overall_oee, 2), "availability": round(overall_avail, 2),
                "performance": round(overall_perf, 2), "quality": round(overall_qual, 2),
                "target": int(tot_tgt), "actual": int(tot_act), "rejection": int(tot_ng),
                
                # Plant-wide formatted strings
                "planned_prod_time": f"{format_time(tot_plan_prod)} ({tot_pct_planned}%)",
                "no_plan_time": f"{format_time(tot_no_plan)} ({tot_pct_no_plan}%)",
                "actual_op_time": f"{format_time(tot_op_time)} ({tot_pct_actual}%)",
                
                # 🚨 UPDATED: Apply format_dt for the Plant-wide Consolidated Summary
                "mould_changeover": format_dt(tot_dt["mould"], tot_calendar_mins), 
                "planning_management": format_dt(tot_dt["plan"], tot_calendar_mins),
                "machine_breakdown": format_dt(tot_dt["machine"], tot_calendar_mins), 
                "tooling_issue": format_dt(tot_dt["tooling"], tot_calendar_mins),
                "material_shortage": format_dt(tot_dt["material"], tot_calendar_mins), 
                "utility_failure": format_dt(tot_dt["utility"], tot_calendar_mins),
                "operator_efficiency": format_dt(tot_dt["operator"], tot_calendar_mins), 
                "manpower_shortage": format_dt(tot_dt["manpower"], tot_calendar_mins),
                "process_quality": format_dt(tot_dt["process"], tot_calendar_mins), 
                "planned_maintenance": format_dt(tot_dt["maint"], tot_calendar_mins),
                "break_time": format_dt(tot_dt["break"], tot_calendar_mins)
            })

        return {"records": records}
    except Exception as e:
        print("Machinewise OEE Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/lineprocesswise_oee_report")
def get_lineprocesswise_oee_report(
    start_date: str = Query(""), 
    end_date: str = Query(""), 
    view_mode: str = Query("line"), 
    entities: str = Query("")
):
    """Calculates OEE dynamically grouped by either Line or Process with accurate Availability/Performance scaling."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 NEW: Fetch OEE Impact rules from the master table for dynamic sorting
        cur.execute("SELECT DISTINCT category, oee_impact FROM shortfall_reason_master WHERE is_active = true")
        impact_map = {row[0]: row[1] for row in cur.fetchall()}
        
        def get_impact(category_name):
            # Default to Availability if the mapping is missing for any reason
            return impact_map.get(category_name, 'Availability')

        # Determine the grouping column based on the view_mode
        if view_mode == "line":
            group_col_sql = "COALESCE(p.production_line, 'Unknown Line')"
        else:
            group_col_sql = "COALESCE(m.machine_process, 'Unknown Process')"

        query = f"""
        WITH BaseLogs AS (
            SELECT 
                log.id as log_id,
                {group_col_sql} as group_key,
                COALESCE(log.active_cavities, 1) as active_cavities,
                log.target_shots * COALESCE(log.active_cavities, 1) as target_qty,
                log.actual_shots * COALESCE(log.active_cavities, 1) as actual_qty,
                log.ng_parts as ng_qty,
                ((EXTRACT(EPOCH FROM log.end_time) - EXTRACT(EPOCH FROM log.start_time) + 
                  CASE WHEN log.end_time < log.start_time THEN 86400 ELSE 0 END) / 60.0) as logged_mins,
                CASE WHEN pr.cycle_time > 0 THEN pr.cycle_time
                     WHEN pr.hourly_target > 0 THEN 60.0 / pr.hourly_target
                     ELSE 0 END as ct_mins,
                CASE WHEN log.is_no_plan = true THEN 1 ELSE 0 END as is_no_plan
            FROM production_hourly_log log
            LEFT JOIN part_routing pr ON pr.part_no = split_part(log.batch_id, '_', 5) AND pr.process_name = split_part(log.batch_id, '_', 4)
            LEFT JOIN machine_master m ON log.machine_code = m.machine_code
            LEFT JOIN process_master p ON m.machine_process = p.process
            WHERE split_part(log.batch_id, '_', 1) >= %s AND split_part(log.batch_id, '_', 1) <= %s
        ),
        AggLogs AS (
            SELECT 
                b.log_id,
                b.group_key,
                b.active_cavities,
                b.target_qty,
                b.actual_qty,
                b.ng_qty,
                b.logged_mins,
                b.is_no_plan,
                CASE WHEN b.ct_mins > 0 THEN b.ct_mins
                     WHEN b.target_qty > 0 THEN b.logged_mins / b.target_qty
                     ELSE 0 END as final_ct_mins,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Mould Changeover'), 0) as dt_mould,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Planning / Management'), 0) as dt_plan,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Machine Breakdown'), 0) as dt_machine,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Tooling Issue'), 0) as dt_tooling,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Material Shortage'), 0) as dt_material,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Utility Failure'), 0) as dt_utility,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Operator Efficiency'), 0) as dt_operator,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Manpower Shortage'), 0) as dt_manpower,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Process & Quality'), 0) as dt_process,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Planned Maintenance'), 0) as dt_maint,
                COALESCE((SELECT SUM(s.quantity) FROM production_shortfalls s JOIN shortfall_reason_master srm ON s.reason_name = srm.reason_name WHERE s.log_id = b.log_id AND srm.category = 'Break Time'), 0) as dt_break
            FROM BaseLogs b
        )
        SELECT 
            group_key,
            SUM(target_qty),
            SUM(actual_qty),
            SUM(ng_qty),
            SUM(logged_mins),
            SUM(CASE WHEN is_no_plan = 1 THEN logged_mins ELSE 0 END),
            SUM(dt_mould * active_cavities * final_ct_mins),
            SUM(dt_plan * active_cavities * final_ct_mins),
            SUM(dt_machine * active_cavities * final_ct_mins),
            SUM(dt_tooling * active_cavities * final_ct_mins),
            SUM(dt_material * active_cavities * final_ct_mins),
            SUM(dt_utility * active_cavities * final_ct_mins),
            SUM(dt_operator * active_cavities * final_ct_mins),
            SUM(dt_manpower * active_cavities * final_ct_mins),
            SUM(dt_process * active_cavities * final_ct_mins),
            SUM(dt_maint * active_cavities * final_ct_mins),
            SUM(dt_break * active_cavities * final_ct_mins)
        FROM AggLogs
        WHERE 1=1
        """
        
        params = [start_date, end_date]
        
        if entities and entities != "ALL":
            entity_list = tuple(entities.split(','))
            query += " AND group_key IN %s"
            params.append(entity_list)
            
        query += " GROUP BY group_key ORDER BY group_key ASC"
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (d2 - d1).days + 1
        
        def format_time(mins):
            if mins <= 0: return "0"
            mins = int(mins)
            y = mins // 525600; mins %= 525600
            mo = mins // 43200; mins %= 43200
            w = mins // 10080; mins %= 10080
            d = mins // 1440; mins %= 1440
            h = mins // 60
            m = mins % 60
            parts = []
            if y > 0: parts.append(f"{y}y")
            if mo > 0: parts.append(f"{mo}mo")
            if w > 0: parts.append(f"{w}w")
            if d > 0: parts.append(f"{d}d")
            if h > 0: parts.append(f"{h}h")
            if m > 0 or not parts: parts.append(f"{m}m")
            return " ".join(parts)
            
        # 🚨 NEW: Helper function to format downtime with percentages
        def format_dt(mins, total_mins):
            if mins <= 0: return "0"
            pct = round((mins / total_mins * 100), 1) if total_mins > 0 else 0.0
            return f"{format_time(mins)} ({pct}%)"
            
        tot_tgt = 0; tot_act = 0; tot_ng = 0
        tot_plan_prod = 0; tot_no_plan = 0; tot_op_time = 0
        tot_dt = {k: 0 for k in ["mould", "plan", "machine", "tooling", "material", "utility", "operator", "manpower", "process", "maint", "break"]}
        
        records = []
        for row in rows:
            cur.execute(f"SELECT COUNT(*) FROM machine_master m LEFT JOIN process_master p ON m.machine_process = p.process WHERE {group_col_sql} = %s AND m.is_active = true", (row[0],))
            machine_count = cur.fetchone()[0] or 1
            total_range_mins = (total_days * 24 * 60) * machine_count
            
            tgt = float(row[1])
            act = float(row[2])
            ng = float(row[3])
            logged_mins = float(row[4])
            no_plan_mins = float(row[5])
            
            dt_mould = float(row[6]); dt_plan = float(row[7]); dt_machine = float(row[8]); dt_tooling = float(row[9])
            dt_material = float(row[10]); dt_utility = float(row[11]); dt_operator = float(row[12]); dt_manpower = float(row[13])
            dt_process = float(row[14]); dt_maint = float(row[15]); dt_break = float(row[16])
            
            dt_dict = {
                "Mould Changeover": dt_mould, "Planning / Management": dt_plan, "Machine Breakdown": dt_machine,
                "Tooling Issue": dt_tooling, "Material Shortage": dt_material, "Utility Failure": dt_utility,
                "Operator Efficiency": dt_operator, "Manpower Shortage": dt_manpower, "Process & Quality": dt_process,
                "Planned Maintenance": dt_maint, "Break Time": dt_break
            }
            
            avail_loss_mins = sum(mins for cat, mins in dt_dict.items() if get_impact(cat) == 'Availability')
            perf_loss_mins = sum(mins for cat, mins in dt_dict.items() if get_impact(cat) == 'Performance')
            
            planned_prod_time = total_range_mins - no_plan_mins
            if planned_prod_time < 0: planned_prod_time = 0
                
            logged_prod_mins = logged_mins - no_plan_mins
            if logged_prod_mins < 0: logged_prod_mins = 0
                
            operating_time = logged_prod_mins - avail_loss_mins
            if operating_time < 0: operating_time = 0
                
            target_per_min = (tgt / logged_prod_mins) if logged_prod_mins > 0 else 0
            adj_tgt = tgt - (avail_loss_mins * target_per_min)
            if adj_tgt < 0: adj_tgt = 0
            tgt = adj_tgt
            
            pct_planned = round((planned_prod_time / total_range_mins * 100), 1) if total_range_mins > 0 else 0.0
            pct_no_plan = round((no_plan_mins / total_range_mins * 100), 1) if total_range_mins > 0 else 0.0
            pct_actual = round((operating_time / total_range_mins * 100), 1) if total_range_mins > 0 else 0.0
            
            tot_tgt += tgt; tot_act += act; tot_ng += ng
            tot_plan_prod += planned_prod_time; tot_no_plan += no_plan_mins; tot_op_time += operating_time
            tot_dt["mould"] += dt_mould; tot_dt["plan"] += dt_plan; tot_dt["machine"] += dt_machine; tot_dt["tooling"] += dt_tooling
            tot_dt["material"] += dt_material; tot_dt["utility"] += dt_utility; tot_dt["operator"] += dt_operator; tot_dt["manpower"] += dt_manpower
            tot_dt["process"] += dt_process; tot_dt["maint"] += dt_maint; tot_dt["break"] += dt_break
            
            avail_pct = (operating_time / planned_prod_time * 100) if planned_prod_time > 0 else 0.0
            perf_pct = (act / tgt * 100) if tgt > 0 else 0.0
            if perf_pct > 100: perf_pct = 100.0
            qual_pct = ((act - ng) / act * 100) if act > 0 else 0.0
            oee_pct = (avail_pct / 100) * (perf_pct / 100) * (qual_pct / 100) * 100
            
            records.append({
                "machine": row[0],
                "oee": round(oee_pct, 2), "availability": round(avail_pct, 2),
                "performance": round(perf_pct, 2), "quality": round(qual_pct, 2),
                "target": int(tgt), "actual": int(act), "rejection": int(ng),
                "planned_prod_time": f"{format_time(planned_prod_time)} ({pct_planned}%)",
                "no_plan_time": f"{format_time(no_plan_mins)} ({pct_no_plan}%)",
                "actual_op_time": f"{format_time(operating_time)} ({pct_actual}%)",
                
                # 🚨 UPDATED: Apply format_dt to inject percentages dynamically
                "mould_changeover": format_dt(dt_mould, total_range_mins),
                "planning_management": format_dt(dt_plan, total_range_mins),
                "machine_breakdown": format_dt(dt_machine, total_range_mins),
                "tooling_issue": format_dt(dt_tooling, total_range_mins),
                "material_shortage": format_dt(dt_material, total_range_mins),
                "utility_failure": format_dt(dt_utility, total_range_mins),
                "operator_efficiency": format_dt(dt_operator, total_range_mins),
                "manpower_shortage": format_dt(dt_manpower, total_range_mins),
                "process_quality": format_dt(dt_process, total_range_mins),
                "planned_maintenance": format_dt(dt_maint, total_range_mins),
                "break_time": format_dt(dt_break, total_range_mins)
            })
            
        if len(records) > 0:
            overall_avail = (tot_op_time / tot_plan_prod * 100) if tot_plan_prod > 0 else 0.0
            overall_perf = (tot_act / tot_tgt * 100) if tot_tgt > 0 else 0.0
            if overall_perf > 100: overall_perf = 100.0
            overall_qual = ((tot_act - tot_ng) / tot_act * 100) if tot_act > 0 else 0.0
            overall_oee = (overall_avail / 100) * (overall_perf / 100) * (overall_qual / 100) * 100
            
            tot_calendar_mins = tot_plan_prod + tot_no_plan
            tot_pct_planned = round((tot_plan_prod / tot_calendar_mins * 100), 1) if tot_calendar_mins > 0 else 0.0
            tot_pct_no_plan = round((tot_no_plan / tot_calendar_mins * 100), 1) if tot_calendar_mins > 0 else 0.0
            tot_pct_actual = round((tot_op_time / tot_calendar_mins * 100), 1) if tot_calendar_mins > 0 else 0.0
            
            records.append({
                "machine": "Consolidated Summary",
                "oee": round(overall_oee, 2), "availability": round(overall_avail, 2),
                "performance": round(overall_perf, 2), "quality": round(overall_qual, 2),
                "target": int(tot_tgt), "actual": int(tot_act), "rejection": int(tot_ng),
                "planned_prod_time": f"{format_time(tot_plan_prod)} ({tot_pct_planned}%)",
                "no_plan_time": f"{format_time(tot_no_plan)} ({tot_pct_no_plan}%)",
                "actual_op_time": f"{format_time(tot_op_time)} ({tot_pct_actual}%)",
                
                # 🚨 UPDATED: Apply format_dt for the Plant-wide Consolidated Summary
                "mould_changeover": format_dt(tot_dt["mould"], tot_calendar_mins), 
                "planning_management": format_dt(tot_dt["plan"], tot_calendar_mins),
                "machine_breakdown": format_dt(tot_dt["machine"], tot_calendar_mins), 
                "tooling_issue": format_dt(tot_dt["tooling"], tot_calendar_mins),
                "material_shortage": format_dt(tot_dt["material"], tot_calendar_mins), 
                "utility_failure": format_dt(tot_dt["utility"], tot_calendar_mins),
                "operator_efficiency": format_dt(tot_dt["operator"], tot_calendar_mins), 
                "manpower_shortage": format_dt(tot_dt["manpower"], tot_calendar_mins),
                "process_quality": format_dt(tot_dt["process"], tot_calendar_mins), 
                "planned_maintenance": format_dt(tot_dt["maint"], tot_calendar_mins),
                "break_time": format_dt(tot_dt["break"], tot_calendar_mins)
            })
            
        return {"records": records}
    except Exception as e:
        print("Line/Process OEE Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()