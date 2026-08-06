from datetime import datetime
from fastapi import HTTPException

# =========================
# SECURITY CONFIG
# =========================
EXPIRATION_DATE = datetime(2027, 7, 25)

def check_license():
    """Stops the request if the trial is expired."""
    if datetime.now() > EXPIRATION_DATE:
        raise HTTPException(
            status_code=403, 
            detail="TRIAL EXPIRED. Please contact administrator to renew."
        )