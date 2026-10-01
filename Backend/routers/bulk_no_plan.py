from fastapi import APIRouter, HTTPException
from database import get_conn

router = APIRouter()

@router.get("/api/bulk_no_plan/status")
def get_bulk_no_plan_status(date: str):
    """
    Returns every active machine's hour-by-hour status (both shifts) for the given date,
    so the Bulk No Plan tool can render saved/selectable/blocked states in one page load.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 1. All active machines
        cur.execute("SELECT machine_code, machine_process FROM machine_master WHERE is_active = true ORDER BY machine_code ASC")
        machines = {}
        for code, process in cur.fetchall():
            proc = (process or "UNKNOWN").upper().strip()
            machines[code] = {
                "process": proc,
                "A": {"is_finalized": False, "batch_id": None, "hours": {}},
                "B": {"is_finalized": False, "batch_id": None, "hours": {}}
            }

        # 2. All hourly logs for that date
        cur.execute("""
            SELECT machine_code, shift, start_time, created_at, is_no_plan, batch_id
            FROM production_hourly_log
            WHERE production_date = %s
            ORDER BY machine_code, shift, start_time ASC
        """, (date,))

        batch_ids_seen = set()
        for machine_code, shift, start_time, created_at, is_no_plan, batch_id in cur.fetchall():
            if machine_code not in machines:
                continue
            start_str = str(start_time)[:5] if start_time else ""
            machines[machine_code][shift]["hours"][start_str] = {
                "saved": True,
                "created_at": created_at.strftime("%H:%M:%S") if created_at else "",
                "is_no_plan": bool(is_no_plan)
            }
            machines[machine_code][shift]["batch_id"] = batch_id
            
            # FIXED: Prevent 'None' from entering the set and crashing the ANY() query
            if batch_id:
                batch_ids_seen.add(batch_id)

        # 3. Which of those batch_ids are finalized
        finalized_ids = set()
        if batch_ids_seen:
            cur.execute("SELECT DISTINCT batch_id FROM batch_master WHERE batch_id = ANY(%s)", (list(batch_ids_seen),))
            finalized_ids = {r[0] for r in cur.fetchall()}

        for machine_code, data in machines.items():
            for shift in ["A", "B"]:
                bid = data[shift]["batch_id"]
                if bid and bid in finalized_ids:
                    data[shift]["is_finalized"] = True

        return {"machines": machines, "date": date}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()