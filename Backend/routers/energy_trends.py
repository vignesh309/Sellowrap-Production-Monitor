from fastapi import APIRouter, Query, HTTPException
from database import get_conn
from datetime import datetime

router = APIRouter()

@router.get("/api/energy_trends/meters")
def get_energy_meters():
    """Fetch distinct energy meter names for the dropdown filter."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT meter_name FROM energy_meter_readings ORDER BY meter_name;")
        rows = cur.fetchall()
        meters = [row[0] for row in rows]
        return {"meters": meters}
    except Exception as e:
        print("Energy Meters Fetch Error:", str(e))
        raise HTTPException(status_code=500, detail="Database error retrieving meters.")
    finally:
        cur.close()
        conn.close()

@router.get("/api/energy_trends/daily")
def get_daily_trends(
    month: str = Query(..., description="Format: YYYY-MM"), 
    meter_name: str = Query("ALL")
):
    try:
        target_date = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM.")
        
    # Calculate target comparison dates
    current_month_str = month
    prev_month_str = f"{target_date.year if target_date.month > 1 else target_date.year - 1}-{(target_date.month - 1) if target_date.month > 1 else 12:02d}"
    same_month_last_year_str = f"{target_date.year - 1}-{target_date.month:02d}"
    last_year_str = str(target_date.year - 1)
    current_year_str = str(target_date.year)

    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # ==========================================
        # 1. KPI Calculation (Expanded for Overall Consumption)
        # ==========================================
        kpi_query = """
            WITH DailyConsumption AS (
                SELECT 
                    TO_CHAR(record_date, 'YYYY-MM') AS month_str,
                    TO_CHAR(record_date, 'YYYY') AS year_str,
                    record_date,
                    meter_name,
                    (MAX(kwh_received) - MIN(kwh_received)) AS daily_kwh
                FROM energy_meter_readings
                WHERE TO_CHAR(record_date, 'YYYY-MM') IN (%s, %s, %s)
                   OR TO_CHAR(record_date, 'YYYY') IN (%s, %s)
        """
        kpi_params = [current_month_str, prev_month_str, same_month_last_year_str, last_year_str, current_year_str]
        
        if meter_name != "ALL":
            kpi_query += " AND meter_name = %s"
            kpi_params.append(meter_name)
            
        kpi_query += """
                GROUP BY TO_CHAR(record_date, 'YYYY-MM'), TO_CHAR(record_date, 'YYYY'), record_date, meter_name
            )
            SELECT 
                month_str, 
                year_str,
                SUM(daily_kwh) as total_kwh,
                COUNT(DISTINCT record_date) as active_days
            FROM DailyConsumption
            GROUP BY month_str, year_str;
        """
        
        cur.execute(kpi_query, tuple(kpi_params))
        kpi_rows = cur.fetchall()
        
        # Initialize metrics
        kpis = {
            "current_month": 0.0, "last_month": 0.0, "same_month_last_year": 0.0,
            "last_year_total": 0.0, "avg_daily": 0.0, "avg_monthly": 0.0
        }
        
        current_year_total = 0.0
        current_year_months = set()

        for r in kpi_rows:
            m_str, y_str, tot_kwh, act_days = r[0], r[1], float(r[2] or 0), int(r[3] or 0)
            
            # Match specific months
            if m_str == current_month_str:
                kpis["current_month"] = tot_kwh
                if act_days > 0:
                    kpis["avg_daily"] = tot_kwh / act_days
            elif m_str == prev_month_str:
                kpis["last_month"] = tot_kwh
            elif m_str == same_month_last_year_str:
                kpis["same_month_last_year"] = tot_kwh
                
            # Match years
            if y_str == last_year_str:
                kpis["last_year_total"] += tot_kwh
            elif y_str == current_year_str:
                current_year_total += tot_kwh
                current_year_months.add(m_str)

        # Calculate Average Monthly for the current year
        if len(current_year_months) > 0:
            kpis["avg_monthly"] = current_year_total / len(current_year_months)

        # ==========================================
        # 2. Daily Breakdown (Table & Chart Data)
        # ==========================================
        breakdown_query = """
            SELECT 
                TO_CHAR(record_date, 'YYYY-MM-DD') AS rec_date,
                meter_name,
                MIN(kwh_received) AS start_kwh,
                MAX(kwh_received) AS end_kwh,
                (MAX(kwh_received) - MIN(kwh_received)) AS daily_consumption
            FROM energy_meter_readings
            WHERE TO_CHAR(record_date, 'YYYY-MM') = %s
        """
        breakdown_params = [month]
        
        if meter_name != "ALL":
            breakdown_query += " AND meter_name = %s"
            breakdown_params.append(meter_name)
            
        breakdown_query += " GROUP BY record_date, meter_name ORDER BY record_date DESC, meter_name ASC;"
        
        cur.execute(breakdown_query, tuple(breakdown_params))
        b_rows = cur.fetchall()
        
        daily_records = [{"date": r[0], "meter_name": r[1], "start_reading": float(r[2] or 0), "end_reading": float(r[3] or 0), "total_consumption": float(r[4] or 0)} for r in b_rows]
            
        # Include the formatted date strings for the chart labels
        kpis["labels"] = {
            "same_month_last_year": same_month_last_year_str,
            "last_month": prev_month_str,
            "current_month": current_month_str
        }

        return {"kpis": kpis, "records": daily_records}
        
    except Exception as e:
        print("Energy Trends Error:", str(e))
        raise HTTPException(status_code=500, detail="Database error retrieving energy trends.")
    finally:
        cur.close()
        conn.close()

@router.get("/api/energy_trends/load")
def get_load_consumption(
    mode: str = Query(..., description="all_year, year, month, day"),
    val: str = Query(""),
    meter_name: str = Query("ALL")
):
    """
    Fetch load consumption deltas for dynamic time scales.
    Uses LAG() to accurately calculate the consumption between chronological readings.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Calculate the delta between each consecutive reading using LAG window function
        query = """
            WITH MeterDeltas AS (
                SELECT 
                    record_date,
                    record_time,
                    EXTRACT(YEAR FROM record_date) as yr,
                    EXTRACT(MONTH FROM record_date) as mo,
                    EXTRACT(DAY FROM record_date) as dy,
                    EXTRACT(HOUR FROM record_time) as hr,
                    kwh_received - LAG(kwh_received) OVER (PARTITION BY meter_id ORDER BY record_date, record_time) as delta
                FROM energy_meter_readings
                WHERE (%s = 'ALL' OR meter_name = %s)
            )
            SELECT 
        """
        params = [meter_name, meter_name]
        
        # Dynamically inject the grouping column based on the selected mode
        if mode == 'all_year':
            query += " yr as label, SUM(delta) as total FROM MeterDeltas WHERE delta >= 0 GROUP BY yr ORDER BY yr DESC LIMIT 12"
        elif mode == 'year':
            query += " mo as label, SUM(delta) as total FROM MeterDeltas WHERE yr = %s AND delta >= 0 GROUP BY mo ORDER BY mo"
            params.append(int(val))
        elif mode == 'month':
            y, m = val.split('-')
            query += " dy as label, SUM(delta) as total FROM MeterDeltas WHERE yr = %s AND mo = %s AND delta >= 0 GROUP BY dy ORDER BY dy"
            params.extend([int(y), int(m)])
        elif mode == 'day':
            y, m, d = val.split('-')
            query += " hr as label, SUM(delta) as total FROM MeterDeltas WHERE yr = %s AND mo = %s AND dy = %s AND delta >= 0 GROUP BY hr ORDER BY hr"
            params.extend([int(y), int(m), int(d)])
            
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        
        # Re-sort 'all_year' to chronological order (it was descending to get the most recent 12)
        if mode == 'all_year':
            rows = sorted(rows, key=lambda x: x[0])
            
        results = []
        for r in rows:
            lbl = int(r[0])
            tot = float(r[1]) if r[1] else 0.0
            
            # Format labels based on scale
            if mode == 'all_year':
                label_str = str(lbl)
            elif mode == 'year':
                label_str = f"{lbl:02d}" # '01', '02'
            elif mode == 'month':
                label_str = str(lbl) # '1', '2'
            elif mode == 'day':
                label_str = f"{lbl:02d}:00" # '08:00'
                
            results.append({"label": label_str, "value": tot})
            
        return {"data": results}
        
    except Exception as e:
        print("Load Consumption Error:", str(e))
        raise HTTPException(status_code=500, detail="Database error retrieving load consumption.")
    finally:
        cur.close()
        conn.close()