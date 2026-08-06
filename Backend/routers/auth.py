from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_conn
from utils import EXPIRATION_DATE

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.get("/api/get_license_info")
def get_license_info():
    """Returns the system license expiration date for the frontend badge."""
    try:
        # Formats the datetime object into "25-Jul-2026"
        formatted_date = EXPIRATION_DATE.strftime("%d-%b-%Y")
        return {"expiration": formatted_date}
    except Exception as e:
        return {"expiration": "Unknown"}
    
@router.post("/api/login")
def login(user_data: dict):
    conn = get_conn()
    cur = conn.cursor()
    try:
        username = user_data.get("username")
        password = user_data.get("password")

        # Query the employee_master table for the full_name and role
        cur.execute("""
            SELECT full_name, job_role 
            FROM employee_master 
            WHERE username = %s AND password_hash = %s AND is_active = true
        """, (username, password))
        
        row = cur.fetchone()

        if row:
            full_name, job_role = row
            return {
                "status": "success", 
                "full_name": full_name, 
                "role": job_role
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid username or password")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()