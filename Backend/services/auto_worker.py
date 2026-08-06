from datetime import datetime, timedelta
from database import get_conn

def run_auto_finalization(target_shift: str):
    """
    Runs 12 hours after a shift ends.
    If running at 07:05 AM -> Targets Shift A of the previous day.
    If running at 19:05 PM -> Targets Shift B of the previous day.
    """
    now = datetime.now()
    target_date = (now - timedelta(days=1)).date()
    
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Starting Auto-Finalization for Date: {target_date}, Shift: {target_shift}")

    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # 🚨 FIX 1: Fetch both the machine_code AND the machine_process from the database
        cur.execute("SELECT machine_code, machine_process FROM machine_master WHERE is_active = true")
        machines = cur.fetchall()

        # Determine the 12-hour block start times based on the shift
        if target_shift == 'A':
            shift_hours = [(7 + i, 8 + i) for i in range(12)] # 07:00 to 19:00
        else: # Shift B
            shift_hours = [((19 + i) % 24, (20 + i) % 24) for i in range(12)] # 19:00 to 07:00
            
        for machine_code, machine_process in machines:
            # 1. Determine the batch ID for this machine and shift
            # 2. Check if a batch already exists in batch_master for this shift/machine
            # We look for a batch ID matching our pattern or query existing logs
            cur.execute("""
                SELECT DISTINCT batch_id FROM production_hourly_log 
                WHERE production_date = %s AND shift = %s AND machine_code = %s
            """, (target_date, target_shift, machine_code))
            existing_logs = cur.fetchall()
            
            if existing_logs and existing_logs[0][0] is not None:
                batch_id = existing_logs[0][0]
            else:
                # Generate a synthetic batch ID if nothing was started by an operator
                batch_id = f"{target_date.strftime('%Y%m%d')}_{target_shift}_{machine_code}_AUTO"
                
            # 3. Check if this batch is already finalized
            cur.execute("SELECT 1 FROM batch_master WHERE batch_id = %s LIMIT 1", (batch_id,))
            if cur.fetchone():
                continue  # Already finalized, skip to next machine
                
            total_actual_shots = 0
            
            # 4. Loop through all 12 hours to fill missing gaps
            for start_h, end_h in shift_hours:
                start_time_str = f"{start_h:02d}:00:00"
                end_time_str = f"{end_h:02d}:00:00"
                
                # Handle calendar day roll-over for Shift B past midnight
                current_block_date = target_date
                if target_shift == 'B' and start_h < 19:
                    current_block_date = target_date + timedelta(days=1)
                
                # Check if a log exists for this specific hour block
                cur.execute("""
                    SELECT actual_shots FROM production_hourly_log 
                    WHERE production_date = %s AND shift = %s AND machine_code = %s AND start_time = %s
                """, (target_date, target_shift, machine_code, start_time_str))
                
                hour_log = cur.fetchone()
                
                if hour_log:
                    # Log exists, just add to our total for finalization
                    total_actual_shots += (hour_log[0] or 0)
                else:
                    # Log is missing! Check Luckfox Pico IoT data for this hour
                    cur.execute("""
                        SELECT part_count FROM machine_hourly_summary 
                        WHERE machine_code = %s AND summary_date = %s AND hour_no = %s
                    """, (machine_code, current_block_date, start_h))
                    
                    iot_data = cur.fetchone()
                    iot_count = iot_data[0] if iot_data else 0
                    
                    is_no_plan = True if iot_count == 0 else False
                    
                    # Insert the missing hour block automatically
                    cur.execute("""
                        INSERT INTO production_hourly_log 
                        (batch_id, internal_batch_number, production_date, shift, start_time, end_time, 
                         machine_code, mould_code, part_number, operator_code, supervisor_code, 
                         target_shots, actual_shots, ok_parts, ng_parts, is_no_plan)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        batch_id, "AUTO-GEN", target_date, target_shift, start_time_str, end_time_str,
                        machine_code, "AUTO-MOULD", "AUTO-PART", "AUTO-SYS", "AUTO-SYS",
                        0, iot_count, iot_count, 0, is_no_plan
                    ))
                    
                    total_actual_shots += iot_count

            # 5. Finalize the batch in batch_master
            cur.execute("""
                INSERT INTO batch_master 
                (batch_id, sequence_no, process_name, input_qty, ok_qty, ng_qty, emp_code, remarks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (batch_id, sequence_no) DO NOTHING
            """, (
                batch_id, 1, machine_process, 0, total_actual_shots, 0, "AUTO-SYS", "System Auto-Finalized"
            ))
            
            conn.commit()
            print(f"Successfully auto-finalized batch: {batch_id} for process: {machine_process}")

    except Exception as e:
        conn.rollback()
        print(f"CRITICAL ERROR IN AUTO-FINALIZATION: {str(e)}")
    finally:
        cur.close()
        conn.close()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Auto-Finalization Complete.")