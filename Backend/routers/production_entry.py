from fastapi import APIRouter, HTTPException, Query
from database import get_conn
from schemas import ActiveMachineState, DeleteLogsPayload
from fastapi.responses import StreamingResponse
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.image.pil import PilImage

router = APIRouter()

@router.get("/api/init_moulding_stage")
def init_moulding_stage():
    """
    Dedicated initialization for the Moulding Stage. 
    Strictly filters machines and shortfalls to MOULDING processes.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        payload = {
            "machines": [],
            "parts": {},
            "moulds": {},
            "operators": [],
            "supervisors": [],
            "rejections": [],
            "shortfalls": []
        }
        
        # 1. Fetch Parts and Target Data
        cur.execute("""
            SELECT part_no, process_name, target_temp, target_pressure, target_setting, hourly_target, mold_no 
            FROM part_routing 
        """)
        for row in cur.fetchall():
            part_no = row[0]
            proc_name = str(row[1] or "").upper().strip()
            mold_no = str(row[6] or "-").strip()
            if not mold_no: mold_no = "-"
            
            if part_no not in payload["parts"]:
                payload["parts"][part_no] = {"valid_processes": [], "targets": {}}
            
            if proc_name not in payload["parts"][part_no]["valid_processes"]:
                payload["parts"][part_no]["valid_processes"].append(proc_name)
                
            if proc_name not in payload["parts"][part_no]["targets"]:
                payload["parts"][part_no]["targets"][proc_name] = {}
                
            payload["parts"][part_no]["targets"][proc_name][mold_no] = {
                "tgtTemp": float(row[2] if row[2] is not None else 0), 
                "tgtPressure": float(row[3] if row[3] is not None else 0), 
                "tgtSetting": float(row[4] if row[4] is not None else 0),
                "tgtHourly": int(row[5] if row[5] is not None else 0)  
            }

        # 2. Fetch Moulds
        cur.execute("""
            SELECT mold_no, cavity, active_cavities, hourly_target, part_no 
            FROM part_routing 
            WHERE UPPER(process_name) IN ('MOULDING', 'PRESS CUT', 'THERMOWELDING') 
              AND mold_no IS NOT NULL 
              AND mold_no != '-'
        """)
        for row in cur.fetchall():
            mold_no = row[0]
            if mold_no not in payload["moulds"]:
                 payload["moulds"][mold_no] = {
                     "cavities": float(row[1] if row[1] is not None else 1.0), 
                     "active_cavities": float(row[2] if row[2] is not None else 1.0), 
                     "hourlyShots": int(row[3] if row[3] is not None else 0), 
                     "linked_parts": []
                 }
            if row[4] not in payload["moulds"][mold_no]["linked_parts"]:
                payload["moulds"][mold_no]["linked_parts"].append(row[4])

        # 3. 🚨 FILTER: Fetch ONLY Moulding Machines
        cur.execute("""
            SELECT machine_code, machine_process 
            FROM machine_master 
            WHERE is_active = true 
              AND UPPER(machine_process) = 'MOULDING'
            ORDER BY machine_code ASC
        """)
        payload["machines"] = [
            {"code": row[0], "process": str(row[1] or "").upper().strip()} 
            for row in cur.fetchall()
        ]

        # 4. Fetch Employees
        cur.execute("SELECT emp_code, full_name, job_role FROM employee_master WHERE is_active=true ORDER BY full_name ASC")
        for row in cur.fetchall():
            emp_string = f"{row[0]} - {row[1]}"
            job_role = str(row[2] or "").lower()
            if job_role == "operator":
                payload["operators"].append(emp_string)
            elif job_role == "supervisor":
                payload["supervisors"].append(emp_string)

        # 5. 🚨 FILTER: Fetch Rejections and strictly Moulding Shortfalls
        cur.execute("SELECT reason_name FROM rejection_reason_master WHERE is_active=true ORDER BY reason_name ASC")
        payload["rejections"] = [row[0] for row in cur.fetchall()]
        
        cur.execute("""
            SELECT reason_name 
            FROM shortfall_reason_master 
            WHERE is_active = true 
              AND 'MOULDING' = ANY(valid_processes)
            ORDER BY reason_name ASC
        """)
        payload["shortfalls"] = [row[0] for row in cur.fetchall()]

        return payload

    except Exception as e:
        print(f"CRITICAL ERROR IN INIT_MOULDING_STAGE: {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_batch_ledger")
def get_batch_ledger(search: str = Query(""), start_date: str = Query(""), end_date: str = Query(""), machine: str = Query("")):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT 
                bm.id,
                bm.batch_id,
                bm.sequence_no,
                bm.process_name,
                bm.input_qty,
                bm.ok_qty,
                bm.ng_qty,
                bm.emp_code,
                bm.is_outsourced,
                bm.created_at,
                pm.part_name,
                pm.part_no,
                phl.internal_batch_number
            FROM batch_master bm
            LEFT JOIN part_master pm ON SPLIT_PART(bm.batch_id, '_', 5) = pm.part_no
            LEFT JOIN (
                SELECT DISTINCT ON (batch_id) batch_id, internal_batch_number
                FROM production_hourly_log
                ORDER BY batch_id, created_at ASC
            ) phl ON bm.batch_id = phl.batch_id
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND bm.batch_id ILIKE %s"
            params.append(f"%{search}%")
        if start_date:
            query += " AND DATE(bm.created_at) >= %s"
            params.append(start_date)
        if end_date:
            query += " AND DATE(bm.created_at) <= %s"
            params.append(end_date)
        if machine:
            query += " AND bm.batch_id LIKE %s"
            params.append(f"%_{machine}_%")
            
        query += " ORDER BY bm.created_at ASC"
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        
        batches = {}
        for r in rows:
            bid = r[1]
            if bid not in batches:
                batches[bid] = {"batch_id": bid, "stages": []}
            
            batches[bid]["stages"].append({
                "id": r[0],
                "sequence_no": r[2],
                "process_name": r[3],
                "input_qty": r[4],
                "ok_qty": r[5],
                "ng_qty": r[6],
                "emp_code": r[7],
                "is_outsourced": r[8],
                "timestamp": r[9].strftime("%Y-%m-%d %H:%M:%S") if r[9] and hasattr(r[9], 'strftime') else str(r[9]) if r[9] else "",
                "part_name": r[10] or "Unknown Part",
                "part_no": r[11] or bid.split('_')[-1],
                "internal_batch_number": r[12] or "N/A"
            })
            
        ledger_list = list(batches.values())
        ledger_list.sort(key=lambda x: x["stages"][0]["timestamp"] if x["stages"] and len(x["stages"]) > 0 else "", reverse=True)
        
        return {"ledger": ledger_list}
        
    except Exception as e:
        print(f"LEDGER ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/download_label/{batch_id}")
def download_label(batch_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT bm.batch_id, pm.part_no, pm.part_name, phl.internal_batch_number
            FROM batch_master bm
            LEFT JOIN part_master pm ON SPLIT_PART(bm.batch_id, '_', 5) = pm.part_no
            LEFT JOIN production_hourly_log phl ON bm.batch_id = phl.batch_id
            WHERE bm.batch_id = %s LIMIT 1
        """, (batch_id,))
        
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Batch not found")
            
        full_batch, part_no, part_name, internal_batch = row
        
        parts = full_batch.split('_')
        date_str = parts[0] if len(parts) > 0 else "N/A"
        shift_str = parts[1] if len(parts) > 1 else "N/A"

        process_stages = []
        try:
            cur.execute("""
                SELECT 
                    pr.process_name,
                    bm.ok_qty,
                    bm.ng_qty,
                    bm.emp_code
                FROM part_routing pr
                LEFT JOIN batch_master bm 
                    ON pr.process_name = bm.process_name 
                    AND bm.batch_id = %s
                WHERE pr.part_no = %s
                ORDER BY pr.sequence_no ASC
            """, (batch_id, part_no))
            
            db_stages = cur.fetchall()
            
            for row in db_stages:
                proc_name, ok_qty, ng_qty, emp_code = row
                if ok_qty is None:
                    process_stages.append((proc_name, "", "", "", ""))
                else:
                    total_qty = ok_qty + (ng_qty or 0)
                    operator = emp_code if emp_code else ""
                    if operator and " - " in operator:
                        operator = operator.split(" - ")[1]
                        
                    process_stages.append((
                        proc_name, 
                        str(total_qty), 
                        str(ok_qty), 
                        str(ng_qty), 
                        operator
                    ))
        except Exception as db_err:
            print("Could not fetch routing from DB, using fallback data.", db_err)
            
        if not process_stages:
            process_stages = [("Moulding", "50", "45", "5", "Prakash")]

        img = Image.new('RGB', (709, 709), color='white')
        draw = ImageDraw.Draw(img)

        try:
            font_title = ImageFont.truetype("arialbd.ttf", 32) 
            font_bold = ImageFont.truetype("arialbd.ttf", 22)
            font_normal = ImageFont.truetype("arial.ttf", 22)
            font_table_hdr = ImageFont.truetype("arialbd.ttf", 16) 
            font_table_val = ImageFont.truetype("arial.ttf", 16)   
            font_small = ImageFont.truetype("cour.ttf", 14)
        except IOError:
            font_title = font_bold = font_normal = font_table_hdr = font_table_val = font_small = ImageFont.load_default()

        draw.rectangle([(10, 10), (699, 699)], outline="black", width=4) 
        draw.line([(10, 60), (699, 60)], fill="black", width=3) 
        draw.text((354, 35), "Jayashree Polymers", font=font_title, fill="black", anchor="mm")

        draw.line([(450, 60), (450, 350)], fill="black", width=3)
        y_positions_top = [118, 176, 234, 292] 
        for y in y_positions_top:
            draw.line([(10, y), (450, y)], fill="black", width=2)

        draw.line([(10, 350), (699, 350)], fill="black", width=3)

        draw.text((20, 75), "Part no:", font=font_normal, fill="black")
        draw.text((150, 75), str(part_no), font=font_bold, fill="black")
        draw.text((20, 133), "Part name:", font=font_normal, fill="black")
        draw.text((150, 133), str(part_name)[:16], font=font_bold, fill="black") 
        draw.text((20, 191), "Batch no:", font=font_normal, fill="black")
        draw.text((150, 191), str(internal_batch), font=font_normal, fill="black")
        draw.text((20, 249), "Date:", font=font_normal, fill="black")
        draw.text((150, 249), date_str, font=font_normal, fill="black")
        draw.text((20, 307), "Shift:", font=font_normal, fill="black")
        draw.text((150, 307), shift_str, font=font_normal, fill="black")

        qr = qrcode.QRCode(box_size=10, border=1)
        qr.add_data(full_batch)
        qr.make(fit=True)
        # 🚨 FIX: Explicitly cast to an RGB image to satisfy Pylance's resize check
        qr_wrapper = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
        qr_img = qr_wrapper.get_image().convert('RGB') 
        qr_img = qr_img.resize((230, 230)) 
        
        img.paste(qr_img, (460, 85))

        col_x = [10, 180, 280, 380, 480, 699] 
        for x in col_x:
            draw.line([(x, 350), (x, 640)], fill="black", width=2)
            
        headers = ["Process", "Total", "OK", "NG", "Operator"]
        for i, header_text in enumerate(headers):
            center_x = col_x[i] + ((col_x[i+1] - col_x[i]) / 2)
            draw.text((center_x, 370), header_text, font=font_table_hdr, fill="black", anchor="mm")
            
        draw.line([(10, 390), (699, 390)], fill="black", width=2)

        current_y = 390
        row_height = 40
        for idx, stage in enumerate(process_stages):
            if idx >= 6: break 
            
            proc_name, total_qty, ok_qty, ng_qty, opr_name = stage
            row_data = [str(proc_name)[:15], str(total_qty), str(ok_qty), str(ng_qty), str(opr_name)[:15]]
            
            for i, text in enumerate(row_data):
                center_x = col_x[i] + ((col_x[i+1] - col_x[i]) / 2)
                draw.text((center_x, current_y + 20), text, font=font_table_val, fill="black", anchor="mm")
            
            current_y += row_height
            draw.line([(10, current_y), (699, current_y)], fill="black", width=1)

        draw.line([(10, 640), (699, 640)], fill="black", width=3) 
        draw.text((354, 670), full_batch, font=font_small, fill="black", anchor="mm")

        buf = BytesIO()
        img.save(buf, format="PDF", resolution=300.0) 
        buf.seek(0)
        
        return StreamingResponse(
            buf, 
            media_type="application/pdf", 
            headers={"Content-Disposition": f"inline; filename={full_batch}.pdf"}
        )

    except Exception as e:
        print(f"IMAGE GEN ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_batch_route/{batch_id}")
def get_batch_route(batch_id: str):
    """Fetches full routing plan and WIP history. (Outsource parsing removed)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM batch_master WHERE batch_id = %s", (batch_id,))
        result = cur.fetchone()
        if not result or result[0] == 0:
            raise HTTPException(status_code=404, detail="BATCH NOT FOUND: This ID has no Stage 1 (Moulding) record.")
        
        part_no = batch_id.split('_')[-1]

        cur.execute("SELECT process_name FROM part_routing WHERE part_no = %s ORDER BY sequence_no ASC", (part_no,))
        routing_rows = cur.fetchall()
        if not routing_rows:
            raise HTTPException(status_code=404, detail=f"No routing defined in Master Data for part {part_no}.")
        routing_plan = [row[0] for row in routing_rows]

        cur.execute("""
            SELECT sequence_no, process_name, input_qty, ok_qty, ng_qty, emp_code, is_outsourced
            FROM batch_master 
            WHERE batch_id = %s
            ORDER BY sequence_no ASC
        """, (batch_id,))
        history = [{"sequence_no": r[0], "process_name": r[1], "input_qty": r[2], "ok_qty": r[3], "ng_qty": r[4], "emp_code": r[5], "is_outsourced": r[6]} for r in cur.fetchall()]

        return {
            "batch_id": batch_id, 
            "part_no": part_no, 
            "routing": routing_plan, 
            "history": history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ROUTE ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_machines")
def get_machines():
    conn = get_conn()
    cur = conn.cursor()
    try:
        # 🚨 Make sure machine_process is included in the SELECT query!
        cur.execute("SELECT machine_code, machine_name, machine_process FROM machine_master WHERE is_active = true ORDER BY machine_code ASC")
        
        machines = []
        for row in cur.fetchall():
            machines.append({
                "code": row[0],
                "name": row[1],
                "process": row[2] # 🚨 This is the missing link!
            })
            
        return {"machines": machines}
    except Exception as e:
        print(f"Error fetching machines: {e}")
        return {"machines": []}
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_employees")
def get_employees():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT emp_code, full_name FROM employee_master WHERE is_active = true")
        rows = cur.fetchall()
        employees = [f"{row[0]} - {row[1]}" for row in rows]
        return {"employees": employees}
    except Exception as e:
        print(f"EMPLOYEE FETCH ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/api/active_machine")
def update_active_machine(state: ActiveMachineState):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            INSERT INTO active_machine_status 
            (machine_code, internal_batch_number, part_number, mould_code, operator_code, supervisor_code, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (machine_code) 
            DO UPDATE SET 
                internal_batch_number = EXCLUDED.internal_batch_number,
                part_number = EXCLUDED.part_number,
                mould_code = EXCLUDED.mould_code,
                operator_code = EXCLUDED.operator_code,
                supervisor_code = EXCLUDED.supervisor_code,
                updated_at = CURRENT_TIMESTAMP;
        """
        cur.execute(query, (
            state.machine_code, state.internal_batch_number, state.part_number, 
            state.mould_code, state.operator_code, state.supervisor_code
        ))
        conn.commit()
        return {"status": "success", "message": "Active machine state updated."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/active_machine/{machine_code}")
def get_active_machine(machine_code: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT internal_batch_number, part_number, mould_code, operator_code, supervisor_code 
            FROM active_machine_status 
            WHERE machine_code = %s
        """
        cur.execute(query, (machine_code,))
        row = cur.fetchone()
        
        if row:
            return {
                "exists": True,
                "internal_batch_number": row[0],
                "part_number": row[1],
                "mould_code": row[2],
                "operator_code": row[3],
                "supervisor_code": row[4]
            }
        return {"exists": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/api/get_shift_history")
def get_shift_history(date: str, shift: str, machine: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, start_time, end_time, target_shots, actual_shots, ok_parts, ng_parts, 
                   actual_temp, actual_pressure, actual_setting, created_at,
                   part_number, mould_code, internal_batch_number, operator_code, supervisor_code
            FROM production_hourly_log
            WHERE production_date = %s AND shift = %s AND machine_code = %s
            ORDER BY start_time ASC
        """, (date, shift, machine))
        
        rows = cur.fetchall()
        
        if not rows:
            return {"exists": False}

        first_row = rows[0]
        
        setup = {
            "part_number": first_row[10],
            "mould_code": first_row[11],
            "internal_batch_number": first_row[12],
            "operator_code": first_row[13],
            "supervisor_code": first_row[14]
        }
        
        logs = []
        for r in rows:
            log_id = r[0]
            
            cur.execute("SELECT reason_name, quantity FROM production_rejections WHERE log_id = %s", (log_id,))
            rejections = [{"reason": rej[0], "qty": rej[1]} for rej in cur.fetchall()]
            
            cur.execute("SELECT reason_name, quantity FROM production_shortfalls WHERE log_id = %s", (log_id,))
            shortfalls = [{"reason": sf[0], "qty": sf[1]} for sf in cur.fetchall()]
            
            logs.append({
                "start_time": str(r[1])[:5] if r[1] else "",
                "end_time": str(r[2])[:5] if r[2] else "",
                "target_shots": r[3],
                "actual_shots": r[4],
                "ok_parts": r[5],
                "ng_parts": r[6],
                "actual_temp": r[7],
                "actual_pressure": r[8],
                "actual_setting": r[9],
                "created_at": r[10].strftime("%H:%M:%S") if r[10] else "Unknown",
                "rejections": rejections,
                "shortfalls": shortfalls
            })
            
        return {"exists": True, "setup": setup, "logs": logs}
        
    except Exception as e:
        print(f"ERROR FETCHING SHIFT HISTORY: {str(e)}")
        return {"exists": False}
    finally:
        cur.close()
        conn.close()

@router.get("/api/production_logs")
def get_production_logs(
    filter_date: str = Query(""),
    filter_shift: str = Query("ALL"),
    filter_machine: str = Query("ALL")
):
    """Fetches hourly production logs for the Log Manager dashboard."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        query = """
            SELECT 
                id, 
                production_date, 
                shift, 
                machine_code, 
                part_number, 
                start_time, 
                end_time,
                (target_shots * COALESCE(active_cavities, 1)) as target_qty,
                (actual_shots * COALESCE(active_cavities, 1)) as actual_qty
            FROM production_hourly_log
            WHERE 1=1
        """
        params = []
        
        if filter_date:
            query += " AND production_date = %s"
            params.append(filter_date)
            
        if filter_shift and filter_shift != "ALL":
            query += " AND shift = %s"
            params.append(filter_shift)
            
        if filter_machine and filter_machine != "ALL":
            query += " AND machine_code = %s"
            params.append(filter_machine)
            
        # Order newest first, limit to 500 to prevent browser lag on broad searches
        query += " ORDER BY production_date DESC, start_time DESC LIMIT 500"
        
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        
        records = []
        for r in rows:
            records.append({
                "log_id": r[0],
                "date_shift": f"{r[1]} | Shift {r[2]}",
                "machine": r[3],
                "part_no": r[4],
                "time_block": f"{r[5]} - {r[6]}",
                "target": int(r[7]),
                "actual": int(r[8])
            })
            
        return {"records": records}
        
    except Exception as e:
        print("Fetch Logs Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/api/production_logs/delete")
def delete_production_logs(payload: DeleteLogsPayload):
    """Safely executes a cascading delete across all 4 production tables."""
    if not payload.log_ids:
        raise HTTPException(status_code=400, detail="No logs selected for deletion.")
        
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Convert list to tuple for SQL 'IN' clause
        log_ids_tuple = tuple(payload.log_ids)
        
        # 🚨 STEP 0: Fetch the batch_ids BEFORE deleting, so we can clean the ERP table
        cur.execute(
            "SELECT batch_id FROM production_hourly_log WHERE id IN %s", 
            (log_ids_tuple,)
        )
        batch_ids = [row[0] for row in cur.fetchall()]
        
        if not batch_ids:
            raise HTTPException(status_code=404, detail="Logs not found in database.")

        # 🚨 STEP 1: Delete Downtimes
        cur.execute("DELETE FROM production_shortfalls WHERE log_id IN %s", (log_ids_tuple,))
        
        # 🚨 STEP 2: Delete Rejections
        cur.execute("DELETE FROM production_rejections WHERE log_id IN %s", (log_ids_tuple,))
        
        # 🚨 STEP 3: Delete ERP Staging Payloads
        # We loop through and use LIKE so we catch the full FINSYS time-stamped strings
        for batch_id in batch_ids:
            cur.execute("DELETE FROM erp_production_staging WHERE batch_id LIKE %s", (f"{batch_id}%",))
            
        # 🚨 STEP 4: Delete the Main Hourly Logs
        cur.execute("DELETE FROM production_hourly_log WHERE id IN %s", (log_ids_tuple,))
        
        # Commit the transaction ONLY if all 4 steps succeed
        conn.commit()
        
        return {"message": f"Successfully wiped {len(payload.log_ids)} hourly blocks from all systems."}
        
    except Exception as e:
        conn.rollback() # Cancel all deletes if anything fails
        print("Delete Log Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()