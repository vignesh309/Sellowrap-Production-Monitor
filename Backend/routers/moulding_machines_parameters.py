from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from database import get_conn

router = APIRouter()

@router.get("/api/moulding_parameters")
def get_moulding_parameters(
    month: str = Query(..., description="YYYY-MM format"),
    machine: str = Query(..., description="Comma-separated Machine IDs"),
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

        # 🚨 FIX 1: Parse the comma-separated machines into a SQL-friendly tuple
        if machine and machine != "ALL":
            machine_list = tuple(machine.split(','))
            where_clause = "WHERE machine_id IN %s"
            base_params = (machine_list,)
        else:
            where_clause = "WHERE 1=1"
            base_params = ()

        # 3. Get Total Rows for Pagination
        cur.execute(f"SELECT COUNT(*) FROM {table_name} {where_clause}", base_params)
        total_rows = cur.fetchone()[0]

        if total_rows == 0:
            return {
                "records": [],
                "snapshot": None,
                "total_rows": 0
            }

        # 🚨 FIX 2: Added 'machine_id' directly after 'parameter_timestamp'
        query_cols = f"""
            SELECT parameter_timestamp, machine_id, part_number, mold_no, 
                   barrel_temp_z1, barrel_temp_z2, barrel_temp_z3, barrel_temp_z4, barrel_temp_z5,
                   max_pressure, injection_speed, injection_time, cushion
            FROM {table_name}
            {where_clause}
            ORDER BY parameter_timestamp DESC
        """

        # 4. Fetch the absolute latest snapshot for the top cards
        cur.execute(query_cols + " LIMIT 1", base_params)
        
        snap_row = cur.fetchone()
        snapshot = {
            "timestamp": snap_row[0].strftime("%Y-%m-%d %H:%M:%S") if snap_row[0] else None,
            "machine": snap_row[1] or "-",
            "part_no": snap_row[2] or "-",
            "mold_no": snap_row[3] or "-",
            "barrel_temp_z1": snap_row[4],
            "barrel_temp_z2": snap_row[5],
            "barrel_temp_z3": snap_row[6],
            "barrel_temp_z4": snap_row[7],
            "barrel_temp_z5": snap_row[8],
            "max_injection_pressure": snap_row[9],
            "injection_speed": snap_row[10],
            "injection_time": snap_row[11],
            "cushion_position": snap_row[12]
        } if snap_row else None

        # 5. Fetch Paginated Records for the Table and Chart
        cur.execute(query_cols + " LIMIT %s OFFSET %s", base_params + (limit, offset))

        records = []
        for r in cur.fetchall():
            records.append({
                "timestamp": r[0].strftime("%Y-%m-%d %H:%M:%S") if r[0] else "-",
                "machine": r[1] or "-",
                "part_no": r[2] or "-",
                "mold_no": r[3] or "-",
                "barrel_temp_z1": r[4] if r[4] is not None else None,
                "barrel_temp_z2": r[5] if r[5] is not None else None,
                "barrel_temp_z3": r[6] if r[6] is not None else None,
                "barrel_temp_z4": r[7] if r[7] is not None else None,
                "barrel_temp_z5": r[8] if r[8] is not None else None,
                "max_injection_pressure": r[9] if r[9] is not None else None,
                "injection_speed": r[10] if r[10] is not None else None,
                "injection_time": r[11] if r[11] is not None else None,
                "cushion_position": r[12] if r[12] is not None else None
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