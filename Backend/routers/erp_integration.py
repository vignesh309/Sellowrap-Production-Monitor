import json
import os
from fastapi import APIRouter, HTTPException
from database import get_conn
from pydantic import BaseModel
from datetime import datetime
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/api/erp_mapping",
    tags=["ERP Integration"]
)

@router.get("/options")
def get_erp_mapping_options():
    """Fetches all valid internal codes from master tables for the ERP Mapping dropdowns."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        options = {
            "machines": [],
            "processes": [],
            "parts": [],
            "moulds": [],
            "employees": [],
            "rejections": [],
            "downtimes": []
        }

        cur.execute("SELECT machine_code FROM machine_master WHERE is_active = true ORDER BY machine_code")
        options["machines"] = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT process FROM process_master ORDER BY process")
        options["processes"] = [row[0] for row in cur.fetchall()]

        # 🚨 UPDATED: Concatenates Part No and Process Name directly in the database!
        cur.execute("SELECT DISTINCT CONCAT(part_no, '-', UPPER(process_name)) FROM part_routing WHERE part_no IS NOT NULL ORDER BY 1")
        options["parts"] = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT DISTINCT mold_no FROM part_routing WHERE mold_no IS NOT NULL AND mold_no != '-' ORDER BY mold_no")
        options["moulds"] = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT emp_code FROM employee_master WHERE is_active = true ORDER BY emp_code")
        options["employees"] = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT reason_code FROM rejection_reason_master WHERE is_active = true ORDER BY reason_code")
        options["rejections"] = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT reason_code FROM shortfall_reason_master WHERE is_active = true ORDER BY reason_code")
        options["downtimes"] = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT DISTINCT internal_name FROM erp_mapping_master WHERE category = 'SHIFT' ORDER BY internal_name")
        options["shifts"] = [row[0] for row in cur.fetchall()]

        return options

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

class MappingCreate(BaseModel):
    category: str
    internal_name: str
    finsys_code: str
    description: str = ""

@router.get("/")
def get_all_mappings():
    """Fetches all saved ERP mappings from the database."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, category, internal_name, finsys_code, description FROM erp_mapping_master")
        rows = cur.fetchall()
        
        # 🚨 UPDATED: Organized data by your NEW category names
        mappings = {
            'machine_code': [], 
            'part_no': [], 
            'mold_no': [], 
            'emp_code': [], 
            'rejection_reason_code': [], 
            'short_reason_code': [], 
            'SHIFT': []
        }
        
        for row in rows:
            cat = row[1]
            
            # Failsafe: if an unexpected category is in the DB, create a list for it
            if cat not in mappings:
                mappings[cat] = []
                
            mappings[cat].append({
                "id": row[0],
                "internal": row[2],
                "erp": row[3],
                "desc": row[4]
            })
            
        return mappings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/")
def create_mapping(mapping: MappingCreate):
    """Saves a new ERP mapping to the database."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO erp_mapping_master (category, internal_name, finsys_code, description)
            VALUES (%s, %s, %s, %s)
        """, (mapping.category, mapping.internal_name, mapping.finsys_code, mapping.description))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        # Handle unique constraint violations gracefully
        if "unique constraint" in str(e).lower():
            raise HTTPException(status_code=400, detail="This Internal Name is already mapped.")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{mapping_id}")
def delete_mapping(mapping_id: int):
    """Deletes an ERP mapping by its ID."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM erp_mapping_master WHERE id = %s", (mapping_id,))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/auto_sync")
def auto_sync_erp_mappings():
    """
    Auto-fetches master data and populates missing mappings in erp_mapping_master.
    Defaults the finsys_code to the internal_name.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # The CONCAT logic to merge part_no and process_name
        queries = {
            "machine_code": "SELECT machine_code FROM machine_master WHERE is_active = true",
            "process_code": "SELECT process FROM process_master", # 🚨 NEW: Auto-sync process table
            "part_no": "SELECT DISTINCT CONCAT(part_no, '-', UPPER(process_name)) FROM part_routing WHERE part_no IS NOT NULL",
            "mold_no": "SELECT DISTINCT mold_no FROM part_routing WHERE mold_no IS NOT NULL AND mold_no != '-'",
            "emp_code": "SELECT emp_code FROM employee_master WHERE is_active = true",
            "rejection_reason_code": "SELECT reason_code FROM rejection_reason_master WHERE is_active = true",
            "short_reason_code": "SELECT reason_code FROM shortfall_reason_master WHERE is_active = true"
        }

        total_added = 0

        for category, query in queries.items():
            # Get all valid codes currently in the Master Tables
            cur.execute(query)
            master_codes = [row[0] for row in cur.fetchall()]

            # 🚨 FIXED: Now targeting 'erp_mapping_master'
            cur.execute("SELECT internal_name FROM erp_mapping_master WHERE category = %s", (category,))
            existing_codes = {row[0] for row in cur.fetchall()}

            # Find the ones that haven't been mapped yet
            missing_codes = [code for code in master_codes if code not in existing_codes]

            # Insert the missing ones
            for code in missing_codes:
                # 🚨 FIXED: Now targeting 'erp_mapping_master'
                cur.execute("""
                    INSERT INTO erp_mapping_master (category, internal_name, finsys_code, description)
                    VALUES (%s, %s, %s, %s)
                """, (category, code, code, "Auto-synced from Master Tables"))
                total_added += 1

        conn.commit()
        return {"status": "success", "message": f"Auto-sync complete. Added {total_added} new mappings.", "added_count": total_added}

    except Exception as e:
        conn.rollback()
        # This will print the exact database error to your terminal if it ever fails again!
        print(f"CRITICAL AUTO-SYNC ERROR: {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/staging_data")
def get_erp_staging_data(from_date: str = None, to_date: str = None):
    """Fetches staging table data, separated by push status, with optional date filtering."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 NEW: Dynamic query building for Date Filters
        query = """
            SELECT id, batch_id, shift_name, prd_start_time, prd_end_time, machine_erp_code, 
                   part_erp_code, ok_qty, rej_qty, total_downtime_mins, is_pushed, pushed_at, api_error_log
            FROM erp_production_staging
            WHERE 1=1
        """
        params = []
        
        if from_date:
            query += " AND DATE(prd_start_time) >= %s"
            params.append(from_date)
        if to_date:
            query += " AND DATE(prd_start_time) <= %s"
            params.append(to_date)
            
        query += " ORDER BY created_at DESC"
        
        cur.execute(query, tuple(params))
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        
        pending = []
        pushed = []
        
        for row in rows:
            data_dict = dict(zip(columns, row))
            if data_dict['prd_start_time']: data_dict['prd_start_time'] = str(data_dict['prd_start_time'])
            if data_dict['prd_end_time']: data_dict['prd_end_time'] = str(data_dict['prd_end_time'])
            if data_dict['pushed_at']: data_dict['pushed_at'] = str(data_dict['pushed_at'])
            
            if data_dict['total_downtime_mins'] is not None:
                data_dict['total_downtime_mins'] = float(data_dict['total_downtime_mins'])
            
            if data_dict['is_pushed']:
                pushed.append(data_dict)
            else:
                pending.append(data_dict)
                
        return {"pending": pending, "pushed": pushed}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/push_mock")
def mock_erp_push():
    """Fetches pending rows, formats them exactly to FINSYS specs, and SAVES them locally."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 FIX: Added 'batch_id' to the SELECT query!
        cur.execute("""
            SELECT batch_id, shop_floor, shift_name, prd_start_time, prd_end_time, section_code, 
                   mould_erp_code, supervisor_erp_code, helper_count, operator_count, 
                   machine_erp_code, part_erp_code, job_no, job_dt, ok_qty, rej_qty, lumps, 
                   rejections_json, dt_type, total_downtime_mins, downtime_json
            FROM erp_production_staging
            WHERE is_pushed = false
        """)
        
        columns = [desc[0] for desc in cur.description]
        pending_rows = cur.fetchall()
        
        if not pending_rows:
            return JSONResponse(status_code=400, content={"detail": "No pending records to push."})
            
        # 🚨 NEW: Grouping dictionary to build the exact nested structure FINSYS expects
        grouped_payload = {}

        for row in pending_rows:
            row_dict = dict(zip(columns, row))
            
            # --- FIX: psycopg2 automatically parses JSONB into dicts. 
            # We just need to ensure it's not None.
            rej_cat = row_dict['rejections_json'] if isinstance(row_dict['rejections_json'], dict) else {}
            dt_cat = row_dict['downtime_json'] if isinstance(row_dict['downtime_json'], dict) else {}
            
            # --- DATE FORMATTING ---
            def format_iso(dt_val):
                if not dt_val: return ""
                # Converts to FINSYS format: "2026-07-24T14:30:00.000Z"
                return dt_val.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                
            def format_job_dt(dt_val):
                if not dt_val: return ""
                # Converts to FINSYS format: "24/07/2026"
                return dt_val.strftime("%d/%m/%Y")

            shop_floor = row_dict['shop_floor'] or "SW0102"
            shift = f"Shift {row_dict['shift_name']}" if row_dict['shift_name'] else "Unknown"
            start_time = format_iso(row_dict['prd_start_time'])
            end_time = format_iso(row_dict['prd_end_time'])
            section = row_dict['section_code'] or "61"
            
            # Create a unique group key for the top-level FINSYS header
            group_key = (shop_floor, shift, start_time, end_time, section)
            
            if group_key not in grouped_payload:
                grouped_payload[group_key] = {
                    "shop_floor": shop_floor,
                    "shift": shift,
                    "prd_start_time": start_time,
                    "prd_end_time": end_time,
                    "Section": section,
                    "data": []
                }
            
            # --- NESTED MACHINE & PART DATA ---
            part_code_val = row_dict['part_erp_code'] or "UNKNOWN_PART"
            
            machine_data = {
                "Mould_id": row_dict['mould_erp_code'] or "-",
                "Line_superv": row_dict['supervisor_erp_code'] or "001",
                "no_help": row_dict['helper_count'] or "001",
                "no_opr": row_dict['operator_count'] or "001",
                "machine_id": row_dict['machine_erp_code'] or "-",
                "part_code": {
                    part_code_val: {
                        "Job_no": row_dict['job_no'] or "-",
                        "Job_dt": format_job_dt(row_dict['job_dt']),
                        "ok_qty": int(row_dict['ok_qty'] or 0),
                        "rej_qty": int(row_dict['rej_qty'] or 0),
                        "Lumps": int(row_dict['lumps'] or 0),
                        "uid": row_dict['batch_id'],
                        "rej_category": rej_cat
                    }
                },
                "type": row_dict['dt_type'] or "simple",
                "total_downtime": float(row_dict['total_downtime_mins'] or 0.0),
                "dt_category": dt_cat
            }
            
            grouped_payload[group_key]["data"].append(machine_data)
            
        # Convert the grouped dictionary back into the final list
        final_payload = list(grouped_payload.values())
        
        # --- FILE CREATION ---
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        filename = f"FINSYS_Payload_{timestamp}.json"
        
        # Navigate up one folder from 'routers' to the 'Backend' root directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, filename)
        
        with open(file_path, "w") as json_file:
            json.dump(final_payload, json_file, indent=4)
            
        # 2. Update the rows in the database to mark them as pushed
        cur.execute("""
            UPDATE erp_production_staging 
            SET is_pushed = true, pushed_at = %s 
            WHERE is_pushed = false
        """, (now,))
        conn.commit()
        
        return {"status": "success", "message": f"Successfully created {filename} formatted for FINSYS!"}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()