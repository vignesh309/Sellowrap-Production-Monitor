import os
import smtplib
import io
import pandas as pd
import matplotlib
matplotlib.use('Agg') # 🚨 This forces Matplotlib to run headlessly without crashing Tkinter!
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from database import get_conn
from routers.reports import get_machinewise_oee_report, get_lineprocesswise_oee_report

def send_morning_digest():
    """Runs automatically at 10:00 AM. Generates the OEE HTML dashboard, Excel file, and emails it."""
    
    sender_email = "Sellowrap.rpt@gmail.com"
    sender_password = os.getenv("EMAIL_APP_PASSWORD")

    if not sender_password:
        print("Automated Email Failed: No app password found.")
        return

    recipients = [
        "karthik.j@sellowrap.com, maintenancesouth@sellowrap.com, "
        "productionsouth@sellowrap.com, durai.gopalan@sellowrap.com, "
        "qualitysouth1@sellowrap.com, padmanabha.pillai@sellowrap.com, "
        "bdtooling1@sellowrap.com, hrsouth@sellowrap.com, "
        "vijay.shankar@sellowrap.com, khush@sellowrap.com, "
        "partheban.manoharan@sellowrap.com", "tamilselvan@sellowrap.com"
    ]

    target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_conn()
    cur = conn.cursor()

    try:
        # ==========================================
        # 1. FETCH ACTION BOARD DATA
        # ==========================================
        oee_data = get_machinewise_oee_report(start_date=target_date, end_date=target_date, machine="ALL")
        records = oee_data.get("records", [])
        
        # ==========================================
        # 2. GENERATE EXCEL ATTACHMENT IN MEMORY
        # ==========================================
        excel_data = []
        for r in records:
            clean_row = {}
            for key, value in r.items():
                # Detect the Time/Percentage string format like "1d 2h (15.5%)"
                if isinstance(value, str) and '(' in value and '%)' in value:
                    # Extract just the "15.5" part
                    pct_str = value.split('(')[-1].replace('%)', '').strip()
                    try:
                        clean_row[key] = float(pct_str)
                    except ValueError:
                        clean_row[key] = value
                else:
                    clean_row[key] = value
            excel_data.append(clean_row)

        df = pd.DataFrame(excel_data)
        
        # Rename columns (these will become your row labels after we transpose)
        df.rename(columns={
            "machine": "Machine",
            "oee": "OEE (%)",
            "availability": "Availability (%)",
            "performance": "Performance (%)",
            "quality": "Quality (%)",
            "target": "Target Qty",
            "actual": "Actual Qty",
            "rejection": "Rejection Qty",
            "planned_prod_time": "Planned Prod (%)",
            "no_plan_time": "No Plan (%)",
            "actual_op_time": "Actual Op Time (%)",
            "mould_changeover": "Mould Changeover (%)",
            "planning_management": "Planning/Management (%)",
            "machine_breakdown": "Machine Breakdown (%)",
            "tooling_issue": "Tooling Issue (%)",
            "material_shortage": "Material Shortage (%)",
            "utility_failure": "Utility Failure (%)",
            "operator_efficiency": "Operator Efficiency (%)",
            "manpower_shortage": "Manpower Shortage (%)",
            "process_quality": "Process & Quality (%)",
            "planned_maintenance": "Planned Maint (%)",
            "break_time": "Break Time (%)"
        }, inplace=True)

        # 🚨 NEW: Transpose the Dataframe (Swap Rows and Columns)
        if "Machine" in df.columns:
            # Set the machines as the index so they become the column headers
            df.set_index("Machine", inplace=True)
            # Transpose
            df = df.T
            # Reset the index to turn the metric names back into a normal column
            df.reset_index(inplace=True)
            df.rename(columns={"index": "Metric / Category"}, inplace=True)

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Daily_OEE')
            
            # Optional: Auto-adjust the width of the first column so the metric names fit perfectly
            worksheet = writer.sheets['Daily_OEE']
            worksheet.column_dimensions['A'].width = 25
            
        excel_buffer.seek(0)

        # ==========================================
        # 3. PROCESS HTML DASHBOARD DATA
        # ==========================================
        consolidated = next((r for r in records if r["machine"] == "Consolidated Summary"), {})
        machines_only = sorted([r for r in records if r["machine"] != "Consolidated Summary"], key=lambda x: x["oee"], reverse=True)
        
        top_machine_text = "N/A"
        bottom_machine_text = "N/A"
        
        if machines_only:
            top_machine = machines_only[0]
            top_machine_text = f"{top_machine['machine']} (OEE: {top_machine['oee']}%)"
            bottom_machine = machines_only[-1]
            
            cur.execute("""
                SELECT s.reason_name, SUM(s.quantity) as qty FROM production_shortfalls s
                JOIN production_hourly_log h ON s.log_id = h.id
                WHERE h.production_date = %s AND h.machine_code = %s
                  AND s.reason_name NOT IN ('Break Time', 'No Plan')
                GROUP BY s.reason_name ORDER BY qty DESC LIMIT 1
            """, (target_date, bottom_machine["machine"]))
            worst_reason = cur.fetchone()
            worst_reason_text = f"{worst_reason[0]} ({worst_reason[1]} missing shots)" if worst_reason else "No shortfalls logged"
            bottom_machine_text = f"{bottom_machine['machine']} (OEE: {bottom_machine['oee']}% - Highest Loss: {worst_reason_text})"

        # Generate Chart
        process_oee_data = get_lineprocesswise_oee_report(start_date=target_date, end_date=target_date, view_mode="process", entities="ALL")
        process_records = process_oee_data.get("records", [])
        processes_only = sorted([r for r in process_records if r["machine"] != "Consolidated Summary"], key=lambda x: x["oee"], reverse=True)
        
        process_names = [p["machine"] for p in processes_only]
        process_oee_values = [p["oee"] for p in processes_only]
        
        plt.figure(figsize=(9, 4.5))
        colors = ['#00f076' if val >= 80 else '#ff2a7a' for val in process_oee_values]
        bars = plt.bar(process_names, process_oee_values, color=colors, edgecolor='#14172b', width=0.5)
        plt.axhline(y=80, color='#ffb12a', linestyle='--', linewidth=2, label='Target (80%)')
        plt.title(f"Process-wise OEE Performance ({target_date})", fontsize=14, fontweight='bold', color='#14172b')
        plt.ylabel("OEE %", fontsize=11, fontweight='bold')
        plt.ylim(0, 105)
        plt.xticks(rotation=0, fontsize=10, fontweight='bold')
        plt.grid(axis='y', linestyle='--', alpha=0.5)
        plt.tight_layout()

        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, yval + 1, f'{yval}%', ha='center', va='bottom', fontsize=9, fontweight='bold')

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150)
        img_buffer.seek(0)
        plt.close()

        # Fetch Top Losses (Ignoring Break Time and No Plan)
        cur.execute("""
            SELECT s.reason_name, SUM(s.quantity) as qty FROM production_shortfalls s
            JOIN production_hourly_log h ON s.log_id = h.id
            WHERE h.production_date = %s AND s.reason_name NOT IN ('Break Time', 'No Plan')
            GROUP BY s.reason_name ORDER BY qty DESC LIMIT 3
        """, (target_date,))
        dt_html = "".join([f"<li style='margin-bottom: 4px;'>{i+1}. {r[0]}: {r[1]} missing shots</li>" for i, r in enumerate(cur.fetchall())]) or "<li>No downtime recorded.</li>"

        cur.execute("""
            SELECT r.reason_name, SUM(r.quantity) as qty FROM production_rejections r
            JOIN production_hourly_log h ON r.log_id = h.id
            WHERE h.production_date = %s GROUP BY r.reason_name ORDER BY qty DESC LIMIT 3
        """, (target_date,))
        rej_html = "".join([f"<li style='margin-bottom: 4px;'>{i+1}. {r[0]}: {r[1]} pcs</li>" for i, r in enumerate(cur.fetchall())]) or "<li>No rejections recorded.</li>"

        # Fetch Pending
        cur.execute("""
            SELECT h.machine_code FROM production_hourly_log h
            LEFT JOIN batch_master b ON h.batch_id = b.batch_id
            WHERE h.production_date = %s GROUP BY h.machine_code HAVING COUNT(b.batch_id) = 0
        """, (target_date,))
        pending_html = "".join([f"<li>⚠️ {p[0]}</li>" for p in cur.fetchall()]) or "<li>✅ All shifts finalized successfully.</li>"

        # ==========================================
        # 4. BUILD & SEND EMAIL
        # ==========================================
        msg = EmailMessage()
        msg['Subject'] = f"Manufacturing Analytics: Daily OEE Report ({target_date})"
        msg['From'] = f"Production Monitor <{sender_email}>"
        msg['To'] = ", ".join(recipients)

        image_cid = make_msgid(domain='production-monitor.local')

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f4f4f9;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                    <td align="center" style="padding: 20px;">
                        <table width="650" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff; border: 1px solid #dddddd;">
                            <tr>
                                <td bgcolor="#0072ff" style="padding: 20px; color: #ffffff;">
                                    <h2 style="margin: 0; font-size: 24px;">Daily OEE Executive Summary</h2>
                                    <p style="margin: 5px 0 0 0; font-size: 14px;">Date: {target_date}</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 20px; line-height: 1.6; color: #333333;">
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
                                    
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 20px;">
                                        <tr>
                                            <td style="text-align: center; border: 1px solid #eeeeee; padding: 10px;">
                                                <img src="cid:{image_cid[1:-1]}" alt="Process-wise OEE Chart" width="600" style="display: block; width: 100%; max-width: 600px; height: auto; border: 0;" />
                                            </td>
                                        </tr>
                                    </table>

                                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 20px;">
                                        <tr>
                                            <td width="4" bgcolor="#ffb12a"></td>
                                            <td bgcolor="#f9f9f9" style="padding: 15px; border: 1px solid #eeeeee;">
                                                <h3 style="margin: 0 0 10px 0; color: #14172b;">3. Critical Losses</h3>
                                                <b>Top 3 Machine Downtime Reasons:</b>
                                                <ul style="margin-top: 5px; margin-bottom: 15px; padding-left: 20px;">{dt_html}</ul>
                                                <b>Top 3 Rejection Codes:</b>
                                                <ul style="margin-top: 5px; margin-bottom: 0; padding-left: 20px;">{rej_html}</ul>
                                            </td>
                                        </tr>
                                    </table>
                                    
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
                                                <ul style="margin: 0; padding-left: 20px; color: #ff2a7a; font-weight: bold;">{pending_html}</ul>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        msg.add_alternative(html_body, subtype='html')
        msg.get_payload()[0].add_related(img_buffer.read(), maintype='image', subtype='png', cid=image_cid)

        # Attach the pure-percentage Excel file
        msg.add_attachment(
            excel_buffer.read(),
            maintype='application',
            subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=f"Daily_OEE_Report_{target_date}.xlsx"
        )

        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        print(f"[{datetime.now()}] Automated Morning Email sent successfully with clean Excel attachment!")

    except Exception as e:
        print(f"[{datetime.now()}] Automated Morning Email Failed: {str(e)}")
    finally:
        cur.close()
        conn.close()