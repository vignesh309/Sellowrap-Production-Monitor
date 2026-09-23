from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from database import get_conn

router = APIRouter()

# ==========================================
# 1. LIST DISTINCT METERS (for the dropdown)
# ==========================================
@router.get("/api/energy_meters/list")
def list_energy_meters():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT meter_name FROM energy_meter_readings ORDER BY meter_name ASC")
        rows = cur.fetchall()
        return {"meters": [r[0] for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ==========================================
# 2. SUMMARY CARDS
# ==========================================
@router.get("/api/energy_reports/summary")
def get_energy_summary(meter_name: str, from_date: str, to_date: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                MIN(kwh_received) as min_kwh,
                MAX(kwh_received) as max_kwh,
                AVG(watts_total) as avg_watts,
                AVG(ABS(pf_average)) as avg_pf
            FROM energy_meter_readings
            WHERE meter_name = %s AND record_date BETWEEN %s AND %s
        """, (meter_name, from_date, to_date))
        row = cur.fetchone()

        cur.execute("""
            SELECT watts_total, record_date, record_time
            FROM energy_meter_readings
            WHERE meter_name = %s AND record_date BETWEEN %s AND %s
            ORDER BY watts_total DESC NULLS LAST
            LIMIT 1
        """, (meter_name, from_date, to_date))
        peak_row = cur.fetchone()

        total_kwh = float(row[1] - row[0]) if row and row[0] is not None and row[1] is not None else 0
        avg_kw = float(row[2]) / 1000 if row and row[2] is not None else 0
        avg_pf = float(row[3]) if row and row[3] is not None else 0
        peak_kw = float(peak_row[0]) / 1000 if peak_row and peak_row[0] is not None else 0
        peak_time = f"{peak_row[1]} {str(peak_row[2])[:5]}" if peak_row else "-"

        return {
            "total_kwh": round(total_kwh, 2),
            "avg_kw": round(avg_kw, 2),
            "avg_pf": round(avg_pf, 3),
            "peak_kw": round(peak_kw, 2),
            "peak_time": peak_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ==========================================
# 3. TREND CHART (auto-aggregated)
# ==========================================
@router.get("/api/energy_reports/trend")
def get_energy_trend(meter_name: str, from_date: str, to_date: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        d1 = datetime.strptime(from_date, "%Y-%m-%d")
        d2 = datetime.strptime(to_date, "%Y-%m-%d")
        span_days = (d2 - d1).days

        # Bucket size scales with the selected range so the chart stays readable
        bucket = "hour" if span_days <= 3 else "day"

        cur.execute(f"""
            SELECT date_trunc('{bucket}', recorded_at) as bucket_time, AVG(watts_total) / 1000 as avg_kw
            FROM energy_meter_readings
            WHERE meter_name = %s AND record_date BETWEEN %s AND %s
            GROUP BY bucket_time
            ORDER BY bucket_time ASC
        """, (meter_name, from_date, to_date))
        rows = cur.fetchall()

        points = []
        for r in rows:
            label = r[0].strftime("%Y-%m-%d %H:%M") if bucket == "hour" else r[0].strftime("%Y-%m-%d")
            points.append({"time": label, "kw": round(float(r[1]), 2) if r[1] is not None else 0})

        return {"granularity": bucket, "points": points}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ==========================================
# 4. DATA TABLE (headline columns, raw rows)
# ==========================================
@router.get("/api/energy_reports/table")
def get_energy_table(meter_name: str, from_date: str, to_date: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT record_date, record_time, watts_total, pf_average, vll_average, current_total, kwh_received
            FROM energy_meter_readings
            WHERE meter_name = %s AND record_date BETWEEN %s AND %s
            ORDER BY record_date DESC, record_time DESC
            LIMIT 500
        """, (meter_name, from_date, to_date))
        rows = cur.fetchall()

        records = []
        for r in rows:
            records.append({
                "date": str(r[0]),
                "time": str(r[1])[:8] if r[1] else "",
                "watts_total": float(r[2]) if r[2] is not None else 0,
                "pf_average": float(r[3]) if r[3] is not None else 0,
                "vll_average": float(r[4]) if r[4] is not None else 0,
                "current_total": float(r[5]) if r[5] is not None else 0,
                "kwh_received": float(r[6]) if r[6] is not None else 0
            })

        return {"records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# ==========================================
# 5. LIVE METER STATUS (latest reading per meter, for the tree/flowchart view)
# ==========================================
@router.get("/api/energy_reports/live_status")
def get_live_meter_status():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT ON (meter_id) 
                meter_id, meter_name, watts_total, pf_average, vll_average, current_total, kwh_received, recorded_at
            FROM energy_meter_readings
            ORDER BY meter_id, recorded_at DESC
        """)
        rows = cur.fetchall()

        result = {}
        for r in rows:
            result[r[1]] = {
                "meter_id": r[0],
                "watts_total": float(r[2]) if r[2] is not None else 0,
                "pf_average": float(r[3]) if r[3] is not None else 0,
                "vll_average": float(r[4]) if r[4] is not None else 0,
                "current_total": float(r[5]) if r[5] is not None else 0,
                "kwh_received": float(r[6]) if r[6] is not None else 0,
                "recorded_at": r[7].strftime("%Y-%m-%d %H:%M:%S") if r[7] else None
            }
        return {"meters": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()