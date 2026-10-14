from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from database import get_conn

router = APIRouter()

@router.get("/api/moulding_parameters")
def get_moulding_parameters(
    month: str = Query(..., description="YYYY-MM format"),
    machine: str = Query(..., description="Machine Code"),
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0)
):
    """
    Fetches parameter history from a dynamically named monthly table.
    Safely validates the date input to prevent SQL injection before string formatting.
    """
    # 1. Strict Input Validation & Table Name Construction
    try:
        target_date = datetime.strptime(month, "%Y-%m")
        month_abbr = target_date.strftime("%b").lower()  # e.g., 'oct'
        year_str = target_date.strftime("%Y")            # e.g., '2026'
        
        table_name = f"moulding_machines_parameters_{month_abbr}_{year_str}"
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Expected YYYY-MM.")

    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # 2. Check if the dynamic table actually exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            )
        """, (table_name,))
        
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            return {
                "records": [],
                "snapshot": None,
                "total_rows": 0
            }

        # 3. Get Total Rows for Pagination using actual column 'machine_id'
        cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE machine_id = %s", (machine,))
        total_rows = cur.fetchone()[0]

        if total_rows == 0:
            return {
                "records": [],
                "snapshot": None,
                "total_rows": 0
            }

        # The core query matching your exact database columns
        query_cols = f"""
            SELECT parameter_timestamp, part_number, mold_no, 
                   barrel_temp_z1, barrel_temp_z2, barrel_temp_z3, barrel_temp_z4, barrel_temp_z5,
                   max_pressure, injection_speed, injection_time, cushion
            FROM {table_name}
            WHERE machine_id = %s
            ORDER BY parameter_timestamp DESC
        """

        # 4. Fetch the absolute latest snapshot for the top cards
        cur.execute(query_cols + " LIMIT 1", (machine,))
        
        snap_row = cur.fetchone()
        snapshot = {
            "timestamp": snap_row[0].strftime("%Y-%m-%d %H:%M:%S") if snap_row[0] else None,
            "part_no": snap_row[1],
            "mold_no": snap_row[2],
            "barrel_temp_z1": snap_row[3],
            "barrel_temp_z2": snap_row[4],
            "barrel_temp_z3": snap_row[5],
            "barrel_temp_z4": snap_row[6],
            "barrel_temp_z5": snap_row[7],
            "max_injection_pressure": snap_row[8],
            "injection_speed": snap_row[9],
            "injection_time": snap_row[10],
            "cushion_position": snap_row[11]
        } if snap_row else None

        # 5. Fetch Paginated Records for the Table and Chart
        cur.execute(query_cols + " LIMIT %s OFFSET %s", (machine, limit, offset))

        records = []
        for r in cur.fetchall():
            records.append({
                "timestamp": r[0].strftime("%Y-%m-%d %H:%M:%S") if r[0] else "-",
                "part_no": r[1] or "-",
                "mold_no": r[2] or "-",
                "barrel_temp_z1": r[3] if r[3] is not None else None,
                "barrel_temp_z2": r[4] if r[4] is not None else None,
                "barrel_temp_z3": r[5] if r[5] is not None else None,
                "barrel_temp_z4": r[6] if r[6] is not None else None,
                "barrel_temp_z5": r[7] if r[7] is not None else None,
                "max_injection_pressure": r[8] if r[8] is not None else None,
                "injection_speed": r[9] if r[9] is not None else None,
                "injection_time": r[10] if r[10] is not None else None,
                "cushion_position": r[11] if r[11] is not None else None
            })

        return {
            "records": records,
            "snapshot": snapshot,
            "total_rows": total_rows
        }

    except Exception as e:
        print(f"Moulding Parameters Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error retrieving parameters.")
    finally:
        cur.close()
        conn.close()