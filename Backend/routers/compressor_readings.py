from fastapi import APIRouter, Query, HTTPException
from database import get_conn
from datetime import datetime

router = APIRouter()

@router.get("/api/compressor/list")
def get_compressor_list():
    """Fetch distinct compressor codes for the dropdown menu."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT compressor_code FROM compressor_readings ORDER BY compressor_code;")
        rows = cur.fetchall()
        compressors = [row[0] for row in rows]
        return {"compressors": compressors}
    except Exception as e:
        print("Compressor List Error:", str(e))
        raise HTTPException(status_code=500, detail="Database error retrieving compressors.")
    finally:
        cur.close()
        conn.close()

@router.get("/api/compressor/readings")
def get_compressor_readings(
    start_date: str = Query(""), 
    end_date: str = Query(""), 
    compressor_code: str = Query("ALL")
):
    """Fetch analog sensor data filtered by date and compressor."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT 
                compressor_code, 
                TO_CHAR(record_date, 'YYYY-MM-DD') as record_date, 
                TO_CHAR(record_time, 'HH24:MI:SS') as record_time, 
                discharge_pressure_bar, 
                discharge_temp_c, 
                ambient_temp_c
            FROM compressor_readings
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND record_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND record_date <= %s"
            params.append(end_date)
        if compressor_code and compressor_code != "ALL":
            query += " AND compressor_code = %s"
            params.append(compressor_code)

        query += " ORDER BY record_date ASC, record_time ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        records = []
        for r in rows:
            records.append({
                "compressor_code": r[0],
                "record_date": r[1],
                "record_time": r[2],
                "discharge_pressure_bar": float(r[3]) if r[3] is not None else None,
                "discharge_temp_c": float(r[4]) if r[4] is not None else None,
                "ambient_temp_c": float(r[5]) if r[5] is not None else None
            })

        return {"records": records}
        
    except Exception as e:
        print("Compressor Readings Error:", str(e))
        raise HTTPException(status_code=500, detail="Database error retrieving readings.")
    finally:
        cur.close()
        conn.close()