from fastapi import APIRouter, HTTPException
from config import CHAT_ID
from database import get_conn
from schemas import PartMasterPayload, MachinePayload, EmployeeModel, OTPVerifyModel, RejectionReasonPayload, ShortfallReasonPayload
import random
from services.telegram_notifier import send_telegram_message

router = APIRouter()

admin_otp_store = {}

# ==========================================
# MACHINE MASTER ROUTES
# ==========================================


@router.get("/api/machine_init")
def init_machines():
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 Added machine_process to the SELECT statement
        cur.execute(
            "SELECT machine_code, machine_name, machine_process FROM machine_master ORDER BY machine_code"
        )
        machines = [
            {"machine_code": row[0], "machine_name": row[1], "machine_process": row[2]}
            for row in cur.fetchall()
        ]
        return {"machines": machines}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/api/machine/{machine_code}")
def get_machine(machine_code: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 Added machine_process to the SELECT statement
        cur.execute(
            "SELECT machine_code, machine_name, is_active, machine_process FROM machine_master WHERE machine_code = %s",
            (machine_code,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Machine not found")

        return {
            "machine_code": row[0],
            "machine_name": row[1],
            "is_active": row[2],
            "machine_process": row[3],  # 🚨 Map the new column
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/api/machine/save")
def save_machine(payload: MachinePayload):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Check if machine already exists
        cur.execute(
            "SELECT id FROM machine_master WHERE machine_code = %s",
            (payload.machine_code,),
        )
        exists = cur.fetchone()

        if exists:
            # Update existing machine (🚨 Added machine_process)
            cur.execute(
                "UPDATE machine_master SET machine_name = %s, is_active = %s, machine_process = %s WHERE machine_code = %s",
                (
                    payload.machine_name,
                    payload.is_active,
                    payload.machine_process,
                    payload.machine_code,
                ),
            )
        else:
            # Insert new machine (🚨 Added machine_process)
            cur.execute(
                "INSERT INTO machine_master (machine_code, machine_name, is_active, machine_process) VALUES (%s, %s, %s, %s)",
                (
                    payload.machine_code,
                    payload.machine_name,
                    payload.is_active,
                    payload.machine_process,
                ),
            )
        conn.commit()
        return {"message": "Machine saved successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/api/machine/{machine_code}")
def delete_machine(machine_code: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM machine_master WHERE machine_code = %s", (machine_code,)
        )
        conn.commit()
        return {"message": "Machine deleted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ==========================================
# PART / BOM MASTER ROUTES
# ==========================================


@router.get("/api/part/{part_no}")
def get_part_master(part_no: str):
    """Fetches a part and its unified routing sequence."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT part_no, part_name, customer_name FROM part_master WHERE part_no = %s",
            (part_no,),
        )
        part_row = cur.fetchone()

        if not part_row:
            raise HTTPException(status_code=404, detail="Part not found")

        payload = {
            "part_no": part_row[0],
            "part_name": part_row[1],
            "customer_name": part_row[2],
            "routing": [],
        }

        # Reverted SELECT statement (no erp_code)
        cur.execute(
            """
            SELECT sequence_no, process_name, mold_no, mold_name, cavity, active_cavities, 
                   hourly_target, target_temp, target_pressure, target_setting 
            FROM part_routing 
            WHERE part_no = %s 
            ORDER BY sequence_no ASC
        """,
            (part_no,),
        )

        for r in cur.fetchall():
            payload["routing"].append(
                {
                    "sequence": r[0],
                    "process_name": r[1],
                    "mold_no": r[2] if r[2] else "-",
                    "mold_name": r[3] if r[3] else "-",
                    "cavities": float(r[4] or 1.0),
                    "active_cavities": float(r[5] or 1.0),
                    "hourly_target": r[6] or 0,
                    "target_temp": float(r[7] or 0),
                    "target_pressure": float(r[8] or 0),
                    "target_setting": float(r[9] or 0),
                }
            )

        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/api/part/save")
def save_part_master(payload: PartMasterPayload):
    """Creates or updates a part and its unified routing."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO part_master (part_no, part_name, customer_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (part_no) DO UPDATE SET
                part_name = EXCLUDED.part_name,
                customer_name = EXCLUDED.customer_name,
                updated_at = CURRENT_TIMESTAMP;
        """,
            (payload.part_no, payload.part_name, payload.customer_name),
        )

        cur.execute("DELETE FROM part_routing WHERE part_no = %s", (payload.part_no,))

        for process in payload.routing:
            cycle_time_mins = (
                round((60.0 / process.hourly_target), 2)
                if process.hourly_target > 0
                else 0.0
            )

            # Reverted INSERT statement (no erp_code)
            cur.execute(
                """
                INSERT INTO part_routing (
                    part_no, sequence_no, process_name, mold_no, mold_name, 
                    cavity, active_cavities, cycle_time, hourly_target, 
                    target_temp, target_pressure, target_setting
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    payload.part_no,
                    process.sequence,
                    process.process_name,
                    process.mold_no,
                    process.mold_name,
                    process.cavities,
                    process.active_cavities,
                    cycle_time_mins,
                    process.hourly_target,
                    process.target_temp,
                    process.target_pressure,
                    process.target_setting,
                ),
            )

        conn.commit()
        return {"message": f"Part {payload.part_no} saved successfully."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# 🚨 RESTORED: The Delete Endpoint
@router.delete("/api/part/{part_no}")
def delete_part_master(part_no: str):
    """Deletes a part. Postgres ON DELETE CASCADE handles molds and routing."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM part_master WHERE part_no = %s", (part_no,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Part not found")

        conn.commit()
        return {"message": "Part deleted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# 🚨 RESTORED: The Dropdown List Endpoint
@router.get("/api/part_list")
def get_part_list_dropdown():
    """Fetches a lightweight list of parts for the search dropdown."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT part_no, part_name FROM part_master ORDER BY part_no ASC")
        return [{"part_no": r[0], "part_name": r[1]} for r in cur.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# ==========================================
# EMPLOYEE MASTER ROUTES
# ==========================================
# 1. FETCH ALL EMPLOYEES
# ==========================================
@router.get("/api/employees")
def get_employees():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, emp_code, full_name, job_role, username, password_hash, is_active 
            FROM employee_master 
            ORDER BY id ASC
        """)
        rows = cur.fetchall()
        
        employees = []
        for r in rows:
            employees.append({
                "id": r[0],
                "emp_code": r[1],
                "full_name": r[2],
                "job_role": r[3],
                "username": r[4],
                "password_hash": r[5],
                "is_active": r[6]
            })
        return {"status": "success", "employees": employees}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# ==========================================
# 2. CREATE NEW EMPLOYEE
# ==========================================
@router.post("/api/employees")
def create_employee(emp: EmployeeModel):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            INSERT INTO employee_master 
            (emp_code, full_name, job_role, username, password_hash, is_active, created_at, updated_at) 
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        cur.execute(query, (emp.emp_code, emp.full_name, emp.job_role, emp.username, emp.password_hash, emp.is_active))
        conn.commit()
        return {"status": "success", "message": "Employee created successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# ==========================================
# 3. UPDATE EXISTING EMPLOYEE
# ==========================================
@router.put("/api/employees/{emp_id}")
def update_employee(emp_id: int, emp: EmployeeModel):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            UPDATE employee_master 
            SET emp_code=%s, full_name=%s, job_role=%s, username=%s, password_hash=%s, 
                is_active=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """
        cur.execute(query, (emp.emp_code, emp.full_name, emp.job_role, emp.username, emp.password_hash, emp.is_active, emp_id))
        conn.commit()
        return {"status": "success", "message": "Employee updated successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# ==========================================
# OTP AUTHORIZATION LOGIC
# ==========================================
@router.post("/api/employees/request-otp")
def request_otp():
    # 1. Generate a random 6-digit OTP
    otp = str(random.randint(100000, 999999))
    admin_otp_store['admin'] = otp
    
    # 2. Use HTML tags (<b> for bold, <code> for monospace)
    message = (
        "🔐 <b>System Admin Authorization</b>\n\n"
        "A request was made to change an employee's password.\n\n"
        f"🔑 <b>Your OTP:</b> <code>{otp}</code>\n\n"
        "<i>This code will expire shortly. Do not share it.</i>"
    )
    
    # 3. Send strictly to CHAT_ID (Admin), NOT the Factory Group!
    success = send_telegram_message(message, target_chat=CHAT_ID)
    
    if success:
        return {"status": "success", "message": "OTP sent via Telegram"}
    else:
        # Fallback print to console if internet drops
        print(f"\n⚠️ [TELEGRAM FAILED] -> Fallback OTP: {otp}\n")
        return {"status": "warning", "message": "Telegram failed, check server console for OTP."}

@router.post("/api/employees/verify-otp")
def verify_otp(payload: OTPVerifyModel):
    stored_otp = admin_otp_store.get('admin')
    
    if stored_otp and stored_otp == payload.otp:
        # Clear the OTP after successful use so it can't be reused
        admin_otp_store['admin'] = None 
        return {"status": "success", "valid": True}
    
    return {"status": "error", "valid": False}

# ==========================================
# REJECTION REASON MASTER ROUTES
# ==========================================

@router.get("/api/rejection_list")
def get_rejection_list():
    """Fetches all rejection reasons for the master overview table."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, reason_code, reason_name, category, oee_impact, is_active 
            FROM rejection_reason_master 
            ORDER BY reason_code ASC
            """
        )
        reasons = []
        for row in cur.fetchall():
            reasons.append({
                "id": row[0],
                "reason_code": row[1],
                "reason_name": row[2],
                "category": row[3],
                "oee_impact": row[4],
                "is_active": row[5]
            })
        return reasons
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/api/rejection/{reason_code}")
def get_rejection_reason(reason_code: str):
    """Fetches a single rejection reason by its code."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, reason_code, reason_name, category, oee_impact, is_active 
            FROM rejection_reason_master 
            WHERE reason_code = %s
            """,
            (reason_code,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reason not found")

        return {
            "id": row[0],
            "reason_code": row[1],
            "reason_name": row[2],
            "category": row[3],
            "oee_impact": row[4],
            "is_active": row[5]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/api/rejection/save")
def save_rejection_reason(payload: RejectionReasonPayload):
    """Creates or updates a rejection reason using an Upsert (ON CONFLICT)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Assuming reason_code has a UNIQUE constraint in your database
        cur.execute(
            """
            INSERT INTO rejection_reason_master 
                (reason_code, reason_name, category, oee_impact, is_active, created_at, updated_at)
            VALUES 
                (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (reason_code) DO UPDATE SET
                reason_name = EXCLUDED.reason_name,
                category = EXCLUDED.category,
                oee_impact = EXCLUDED.oee_impact,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                payload.reason_code, 
                payload.reason_name, 
                payload.category, 
                payload.oee_impact, 
                payload.is_active
            )
        )
        conn.commit()
        return {"message": f"Reason {payload.reason_code} saved successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/api/rejection/{reason_code}")
def delete_rejection_reason(reason_code: str):
    """Deletes a rejection reason permanently."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM rejection_reason_master WHERE reason_code = %s", (reason_code,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Reason not found")
            
        conn.commit()
        return {"message": "Reason deleted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# ==========================================
# SHORTFALL REASON MASTER ROUTES
# ==========================================

@router.get("/api/shortfall_list")
def get_shortfall_list():
    """Fetches all shortfall reasons for the master overview table."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, reason_code, reason_name, category, oee_impact, valid_processes, is_active 
            FROM shortfall_reason_master 
            ORDER BY reason_code ASC
            """
        )
        reasons = []
        for row in cur.fetchall():
            reasons.append({
                "id": row[0],
                "reason_code": row[1],
                "reason_name": row[2],
                "category": row[3],
                "oee_impact": row[4],
                # Safely return an empty list if valid_processes is NULL in the database
                "valid_processes": row[5] if row[5] else [], 
                "is_active": row[6]
            })
        return reasons
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/api/shortfall/{reason_code}")
def get_shortfall_reason(reason_code: str):
    """Fetches a single shortfall reason by its code."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, reason_code, reason_name, category, oee_impact, valid_processes, is_active 
            FROM shortfall_reason_master 
            WHERE reason_code = %s
            """,
            (reason_code,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reason not found")

        return {
            "id": row[0],
            "reason_code": row[1],
            "reason_name": row[2],
            "category": row[3],
            "oee_impact": row[4],
            "valid_processes": row[5] if row[5] else [],
            "is_active": row[6]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/api/shortfall/save")
def save_shortfall_reason(payload: ShortfallReasonPayload):
    """Creates or updates a shortfall reason using an Upsert (ON CONFLICT)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Psycopg2 automatically converts Python lists to PostgreSQL Arrays!
        cur.execute(
            """
            INSERT INTO shortfall_reason_master 
                (reason_code, reason_name, category, oee_impact, valid_processes, is_active, created_at, updated_at)
            VALUES 
                (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (reason_code) DO UPDATE SET
                reason_name = EXCLUDED.reason_name,
                category = EXCLUDED.category,
                oee_impact = EXCLUDED.oee_impact,
                valid_processes = EXCLUDED.valid_processes,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                payload.reason_code, 
                payload.reason_name, 
                payload.category,
                payload.oee_impact,
                payload.valid_processes,
                payload.is_active
            )
        )
        conn.commit()
        return {"message": f"Shortfall reason {payload.reason_code} saved successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/api/shortfall/{reason_code}")
def delete_shortfall_reason(reason_code: str):
    """Deletes a shortfall reason permanently."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM shortfall_reason_master WHERE reason_code = %s", (reason_code,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Reason not found")
            
        conn.commit()
        return {"message": "Reason deleted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()