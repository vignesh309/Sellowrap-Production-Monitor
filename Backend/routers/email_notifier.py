import os
import smtplib
import io
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from database import get_conn

# Import BOTH endpoints
from routers.reports import get_machinewise_oee_report, get_lineprocesswise_oee_report

router = APIRouter()

@router.post("/api/email_oee_report")
async def email_oee_report(
    file: UploadFile = File(...),
    recipient: str = Form("srinivignesh1999@gmail.com")
):
    """Generates the Executive Summary, Process OEE Chart, and emails it."""
    sender_email = "Sellowrap.rpt@gmail.com"
    sender_password = os.getenv("EMAIL_APP_PASSWORD")

    if not sender_password:
        raise HTTPException(status_code=500, detail="Email App Password not configured in .env file.")

    target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_conn()
    cur = conn.cursor()

    try:
        # ==========================================
        # 1. FETCH OVERALL OEE & ACTION BOARD (Machine Level)
        # ==========================================
        oee_data = get_machinewise_oee_report(start_date=target_date, end_date=target_date, machine="ALL")
        records = oee_data.get("records", [])
        
        consolidated = {}
        machines_only = []
        
        for r in records:
            if r["machine"] == "Consolidated Summary":
                consolidated = r
            else:
                machines_only.append(r)
                
        machines_only.sort(key=lambda x: x["oee"], reverse=True)
        
        top_machine_text = "N/A"
        bottom_machine_text = "N/A"
        
        if machines_only:
            top_machine = machines_only[0]
            top_machine_text = f"{top_machine['machine']} (OEE: {top_machine['oee']}%)"
            bottom_machine = machines_only[-1]
            
            cur.execute("""
                SELECT s.reason_name, SUM(s.quantity) as qty
                FROM production_shortfalls s
                JOIN production_hourly_log h ON s.log_id = h.id
                WHERE h.production_date = %s AND h.machine_code = %s
                GROUP BY s.reason_name
                ORDER BY qty DESC LIMIT 1
            """, (target_date, bottom_machine["machine"]))
            worst_reason = cur.fetchone()
            
            worst_reason_text = f"{worst_reason[0]} ({worst_reason[1]} missing shots)" if worst_reason else "No shortfalls logged"
            bottom_machine_text = f"{bottom_machine['machine']} (OEE: {bottom_machine['oee']}% - Highest Loss: {worst_reason_text})"

        # ==========================================
        # 2. GENERATE PROCESS-WISE OEE BAR CHART
        # ==========================================
        # Fetch data grouped by process instead of individual machines
        process_oee_data = get_lineprocesswise_oee_report(start_date=target_date, end_date=target_date, view_mode="process", entities="ALL")
        process_records = process_oee_data.get("records", [])
        
        # Filter out the consolidated row and sort for a clean waterfall look
        processes_only = [r for r in process_records if r["machine"] != "Consolidated Summary"]
        processes_only.sort(key=lambda x: x["oee"], reverse=True)
        
        process_names = [p["machine"] for p in processes_only]
        process_oee_values = [p["oee"] for p in processes_only]
        
        plt.figure(figsize=(9, 4.5))
        
        # Color coding: Green if >= 80%, Red if < 80%
        colors = ['#00f076' if val >= 80 else '#ff2a7a' for val in process_oee_values]
        
        # Made bars slightly wider since there are fewer of them now
        bars = plt.bar(process_names, process_oee_values, color=colors, edgecolor='#14172b', width=0.5)
        
        # Add target line
        plt.axhline(y=80, color='#ffb12a', linestyle='--', linewidth=2, label='Target (80%)')
        
        # Chart formatting
        plt.title(f"Process-wise OEE Performance ({target_date})", fontsize=14, fontweight='bold', color='#14172b')
        plt.ylabel("OEE %", fontsize=11, fontweight='bold')
        plt.ylim(0, 105)
        
        # Set rotation to 0 so the process names render flat and clean
        plt.xticks(rotation=0, fontsize=10, fontweight='bold')
        plt.grid(axis='y', linestyle='--', alpha=0.5)
        plt.tight_layout()

        # Add data labels on top of bars
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, yval + 1, f'{yval}%', ha='center', va='bottom', fontsize=9, color='#14172b', fontweight='bold')

        # Save to memory buffer
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150)
        img_buffer.seek(0)
        plt.close()

        # ==========================================
        # 3. CRITICAL LOSSES (SPECIFIC SUB-REASONS)
        # ==========================================
        cur.execute("""
            SELECT s.reason_name, SUM(s.quantity) as qty
            FROM production_shortfalls s
            JOIN production_hourly_log h ON s.log_id = h.id
            WHERE h.production_date = %s
            GROUP BY s.reason_name
            ORDER BY qty DESC LIMIT 3
        """, (target_date,))
        top_downtimes = cur.fetchall()
        dt_html = "".join([f"<li style='margin-bottom: 4px;'>{i+1}. {r[0]}: {r[1]} missing shots</li>" for i, r in enumerate(top_downtimes)]) or "<li>No downtime recorded.</li>"

        cur.execute("""
            SELECT r.reason_name, SUM(r.quantity) as qty
            FROM production_rejections r
            JOIN production_hourly_log h ON r.log_id = h.id
            WHERE h.production_date = %s
            GROUP BY r.reason_name
            ORDER BY qty DESC LIMIT 3
        """, (target_date,))
        top_rejections = cur.fetchall()
        rej_html = "".join([f"<li style='margin-bottom: 4px;'>{i+1}. {r[0]}: {r[1]} pcs</li>" for i, r in enumerate(top_rejections)]) or "<li>No rejections recorded.</li>"

        # ==========================================
        # 4. PENDING FINALIZATIONS (COMPLIANCE)
        # ==========================================
        cur.execute("""
            SELECT h.machine_code
            FROM production_hourly_log h
            LEFT JOIN batch_master b ON h.batch_id = b.batch_id
            WHERE h.production_date = %s
            GROUP BY h.machine_code
            HAVING COUNT(b.batch_id) = 0
            ORDER BY h.machine_code ASC
        """, (target_date,))
        pending = cur.fetchall()
        pending_html = "".join([f"<li>⚠️ {p[0]}</li>" for p in pending]) or "<li>✅ All shifts finalized successfully.</li>"

        # ==========================================
        # 5. BUILD OUTLOOK-SAFE HTML & ATTACHMENTS
        # ==========================================
        file_content = await file.read()
        msg = EmailMessage()
        msg['Subject'] = f"Manufacturing Analytics: Daily OEE Report ({target_date})"
        msg['From'] = sender_email
        msg['To'] = recipient

        # Generate a unique Content-ID for the inline image
        image_cid = make_msgid(domain='sellowrap.com')
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f4f4f9;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                    <td align="center" style="padding: 20px;">
                        <table width="650" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; border: 1px solid #dddddd;">
                            
                            <!-- Header -->
                            <tr>
                                <td bgcolor="#0072ff" style="padding: 20px; color: #ffffff;">
                                    <h2 style="margin: 0; font-size: 24px;">Daily OEE Summary</h2>
                                    <p style="margin: 5px 0 0 0; font-size: 14px;">Date: {target_date}</p>
                                </td>
                            </tr>
                            
                            <!-- Body Content -->
                            <tr>
                                <td style="padding: 20px; line-height: 1.6; color: #333333;">
                                    <p style="margin-top: 0;">Good morning,</p>
                                    <p>The detailed machine-wise OEE breakdown is attached. Here is the executive snapshot for the previous day:</p>
                                    
                                    <!-- 1. Executive Snapshot & Volume -->
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 20px;">
                                        <tr>
                                            <td width="4" bgcolor="#00e5ff"></td>
                                            <td bgcolor="#f9f9f9" style="padding: 15px; border: 1px solid #eeeeee;">
                                                <h3 style="margin: 0 0 10px 0; color: #14172b;">1. The Executive Snapshot (Overall OEE)</h3>
                                                <ul style="padding-left: 20px; margin: 0 0 15px 0;">
                                                    <li style="margin-bottom: 6px;"><b>Average Plant OEE:</b> {consolidated.get('oee', 0)}%</li>
                                                    <li style="margin-bottom: 6px;"><b>Availability:</b> {consolidated.get('availability', 0)}%</li>
                                                    <li style="margin-bottom: 6px;"><b>Performance:</b> {consolidated.get('performance', 0)}%</li>
                                                    <li style="margin-bottom: 6px;"><b>Quality:</b> {consolidated.get('quality', 0)}%</li>
                                                </ul>
                                                
                                                <h3 style="margin: 0 0 10px 0; color: #14172b;">2. Production vs. Target (Volume)</h3>
                                                <ul style="padding-left: 20px; margin: 0;">
                                                    <li style="margin-bottom: 6px;"><b>Total Target Shots:</b> {consolidated.get('target', 0)}</li>
                                                    <li style="margin-bottom: 6px;"><b>Total Actual Produced:</b> {consolidated.get('actual', 0)}</li>
                                                    <li style="margin-bottom: 6px;"><b>Total NG (Rejected):</b> {consolidated.get('rejection', 0)}</li>
                                                </ul>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <!-- OEE Chart Section -->
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 20px;">
                                        <tr>
                                            <td style="text-align: center; border: 1px solid #eeeeee; padding: 10px;">
                                                <img src="cid:{image_cid[1:-1]}" alt="Process-wise OEE Chart" width="600" style="display: block; width: 100%; max-width: 600px; height: auto; border: 0;" />
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- 3. Critical Losses -->
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 20px;">
                                        <tr>
                                            <td width="4" bgcolor="#ffb12a"></td>
                                            <td bgcolor="#f9f9f9" style="padding: 15px; border: 1px solid #eeeeee;">
                                                <h3 style="margin: 0 0 10px 0; color: #14172b;">3. Critical Losses</h3>
                                                <b>Top 3 Machine Downtime Reasons:</b>
                                                <ul style="margin-top: 5px; margin-bottom: 15px; padding-left: 20px;">
                                                    {dt_html}
                                                </ul>
                                                <b>Top 3 Rejection Codes:</b>
                                                <ul style="margin-top: 5px; margin-bottom: 0; padding-left: 20px;">
                                                    {rej_html}
                                                </ul>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <!-- 4. Action Board & Compliance -->
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 20px;">
                                        <tr>
                                            <td width="4" bgcolor="#ff2a7a"></td>
                                            <td bgcolor="#f9f9f9" style="padding: 15px; border: 1px solid #eeeeee;">
                                                <h3 style="margin: 0 0 10px 0; color: #14172b;">4. The Action Board</h3>
                                                <ul style="padding-left: 20px; margin: 0 0 15px 0;">
                                                    <li style="margin-bottom: 6px;"><b>Top Performing Machine:</b> {top_machine_text}</li>
                                                    <li style="margin-bottom: 6px;"><b>Needs Attention:</b> {bottom_machine_text}</li>
                                                </ul>
                                                
                                                <h3 style="margin: 0 0 10px 0; color: #14172b;">Compliance Alert: Pending Finalizations</h3>
                                                <p style="margin: 0 0 5px 0; font-size: 13px; color: #666;"><i>The following machines have logged hours but have not been finalized:</i></p>
                                                <ul style="margin: 0; padding-left: 20px; color: #ff2a7a; font-weight: bold;">
                                                    {pending_html}
                                                </ul>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td bgcolor="#eeeeee" style="padding: 15px; text-align: center; color: #777777; font-size: 12px;">
                                    <p style="margin: 0;">&copy; Sellowrap Manufacturing System</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        # Add HTML to email
        msg.add_alternative(html_body, subtype='html')
        
        # Attach the image inline
        msg.get_payload()[0].add_related(
            img_buffer.read(), 
            maintype='image', 
            subtype='png', 
            cid=image_cid
        )

        # Attach the Excel file
        msg.add_attachment(
            file_content,
            maintype='application',
            subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=file.filename
        )

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        return {"message": "Email sent successfully with Process OEE chart!"}

    except Exception as e:
        print(f"Email Sending Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email.")
    finally:
        cur.close()
        conn.close()