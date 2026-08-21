from fastapi import APIRouter, HTTPException
from database import get_conn
from pydantic import BaseModel

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
            "parts": [],
            "moulds": [],
            "employees": [],
            "rejections": [],
            "downtimes": []
        }

        cur.execute("SELECT machine_code FROM machine_master WHERE is_active = true ORDER BY machine_code")
        options["machines"] = [row[0] for row in cur.fetchall()]

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
            INSERT INTO finsys_mapping_master (category, internal_name, finsys_code, description)
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
        cur.execute("DELETE FROM finsys_mapping_master WHERE id = %s", (mapping_id,))
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