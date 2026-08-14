import os
import psycopg2
import logging
from fastapi import HTTPException
from dotenv import load_dotenv

# 1. Load the variables first!
load_dotenv()

# 2. Read them securely
DB_HOST = os.getenv("DB_HOST", "") # The IP acts as a fallback if the env fails
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD") 

def get_conn():
    if not DB_PASS:
        logging.error("Database password environment variable not set.")
        raise HTTPException(status_code=500, detail="Server configuration error.")

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=503, detail="Database Service Unavailable.")
    except Exception as e:
        logging.error(f"Unexpected error during DB connection: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")