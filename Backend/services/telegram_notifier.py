import threading
import telebot
import os
import re
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

# 🚨 Import credentials securely from config.py
from config import BOT_TOKEN, CHAT_ID, GROUP_ID
from database import get_conn 

# ==========================================
# TELEGRAM BOT CONFIGURATION
# ==========================================
# Initialize the Bot Listener using the config token
bot = telebot.TeleBot(BOT_TOKEN)

def send_telegram_message(message: str, target_chat=GROUP_ID):
    """Sends a text message to the specified Telegram chat (Defaults to Group)."""
    try:
        print(f"Attempting to send Telegram message to {target_chat}...")
        bot.send_message(target_chat, message, parse_mode="HTML")
        print("✅ Telegram message sent successfully!")
        return True # 🚨 Added this so the API knows it worked
    except Exception as e:
        print(f"❌ Failed to send Telegram alert: {str(e)}")
        return False # 🚨 Added this for error handling

def send_cloudflare_link():
    """Extracts the Cloudflare link from cf_log.txt and sends it to the Personal Chat."""
    try:
        if not os.path.exists("cf_log.txt"):
            print("❌ cf_log.txt not found. Is Cloudflare running?")
            return

        with open("cf_log.txt", "r", encoding="utf-8") as f:
            log_content = f.read()

        # Regex to find the live Cloudflare URL
        match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', log_content)
        
        if match:
            cf_url = match.group(0)
            message = f"🌐 <b>Cloudflare Tunnel Active:</b>\n{cf_url}"
            # Send STRICTLY to the personal CHAT_ID
            bot.send_message(CHAT_ID, message, parse_mode="HTML")
            print("✅ Personal Cloudflare link sent for ADS Testing Server!")
        else:
            print("⚠️ Cloudflare URL not found in logs yet.")
            bot.send_message(CHAT_ID, "⚠️ Cloudflare URL not generated yet. Wait a moment and try /getlink again.")
    except Exception as e:
        print(f"❌ Error sending Cloudflare link: {str(e)}")


def generate_hourly_report():
    """Runs the DB queries and compiles the Hourly Floor Manager exception report."""
    now = datetime.now()
    
    # Calculate the exact 1-hour block we are auditing (1 hour grace period)
    target_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    target_end = target_start + timedelta(hours=1)

    target_date = target_start.date()
    start_str = target_start.strftime("%H:%M:%S")
    end_str = target_end.strftime("%H:%M:%S")
    target_hour_int = target_start.hour

    print(f"[{now}] Running Hourly Exception Report for block: {start_str} to {end_str}")

    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # MASTER QUERY: Pulls targets and calculates total production for percentage math
        cur.execute("""
            WITH HourlyLogs AS (
                SELECT 
                    machine_code,
                    SUM(ng_parts) as total_ng,
                    SUM(actual_shots * COALESCE(active_cavities, 1)) as total_produced,
                    SUM(target_shots) as total_target,
                    BOOL_OR(is_no_plan) as has_no_plan
                FROM production_hourly_log
                WHERE production_date = %s 
                  AND start_time >= %s 
                  AND start_time < %s
                GROUP BY machine_code
            ),
            ShortfallTotals AS (
                SELECT 
                    phl.machine_code,
                    SUM(ps.quantity) as total_sf
                FROM production_shortfalls ps
                JOIN production_hourly_log phl ON ps.log_id = phl.id
                WHERE phl.production_date = %s 
                  AND phl.start_time >= %s 
                  AND phl.start_time < %s
                GROUP BY phl.machine_code
            )
            SELECT 
                m.machine_code,
                COALESCE(hl.total_ng, 0) AS total_ng,
                COALESCE(hl.total_produced, 0) AS total_produced,
                COALESCE(hl.total_target, 0) AS total_target,
                COALESCE(sf.total_sf, 0) AS total_shortfalls,
                COALESCE(mhs.part_count, 0) AS iot_count,
                hl.machine_code IS NOT NULL AS is_submitted,
                COALESCE(hl.has_no_plan, FALSE) AS has_no_plan
            FROM machine_master m
            LEFT JOIN HourlyLogs hl ON m.machine_code = hl.machine_code
            LEFT JOIN ShortfallTotals sf ON m.machine_code = sf.machine_code
            LEFT JOIN machine_hourly_summary mhs 
                ON m.machine_code = mhs.machine_code 
                AND mhs.summary_date = %s 
                AND mhs.hour_no = %s
            WHERE m.is_active = TRUE
            ORDER BY m.machine_code;
        """, (
            target_date, start_str, end_str,       # For HourlyLogs
            target_date, start_str, end_str,       # For ShortfallTotals
            target_date, target_hour_int           # For IoT MHS Table
        ))
        
        machine_status_rows = cur.fetchall()

        # Group alerts into specific categories
        missing_alerts = []
        ng_alerts = []
        sf_alerts = []

        for row in machine_status_rows:
            machine = row[0]
            total_ng = float(row[1])
            total_produced = float(row[2])
            total_target = float(row[3])
            total_sf = float(row[4])
            iot_count = row[5]
            is_submitted = row[6]
            has_no_plan = row[7]

            # 1. Missing Data Alert
            if not is_submitted:
                missing_alerts.append(f"⚠️ <b>{machine}</b>: Data Not Entered (IoT Count: {iot_count})")
                continue # Skip further math if no data

            # Ignore No Plan machines entirely
            if has_no_plan:
                continue 

            # 2. Quality Alert (NG > 10% of Produced)
            if total_produced > 0:
                ng_percent = (total_ng / total_produced) * 100
                if ng_percent > 10:
                    ng_alerts.append(f"🔴 <b>{machine}</b>: Rejection Spike ({ng_percent:.1f}%) | NG: {int(total_ng)} / Prod: {int(total_produced)}")

            # 3. Shortfall Alert (SF > 10% of Target)
            if total_target > 0:
                sf_percent = (total_sf / total_target) * 100
                if sf_percent > 10:
                    sf_alerts.append(f"🟡 <b>{machine}</b>: High Shortfall ({sf_percent:.1f}%) | SF: {int(total_sf)} / Tgt: {int(total_target)}")

        # Construct final output message
        header = f"📊 <b>Hourly Exception Audit</b>\n<i>Block: {target_start.strftime('%I:%M %p')} - {target_end.strftime('%I:%M %p')}</i>\n\n"
        
        if not missing_alerts and not ng_alerts and not sf_alerts:
            final_message = header + "✅ <b>All clear!</b> All machines submitted, rejection rates < 10%, and shortfalls < 10%."
        else:
            blocks = []
            if missing_alerts:
                blocks.append("<b>— MISSING LOGS —</b>\n" + "\n".join(missing_alerts))
            if ng_alerts:
                blocks.append("<b>— QUALITY ALERTS (>10%) —</b>\n" + "\n".join(ng_alerts))
            if sf_alerts:
                blocks.append("<b>— SHORTFALL ALERTS (>10%) —</b>\n" + "\n".join(sf_alerts))
            
            final_message = header + "\n\n".join(blocks)

        # Send factory reports to the GROUP_ID
        send_telegram_message(final_message, target_chat=GROUP_ID)

    except Exception as e:
        print(f"Telegram Report Error: {str(e)}")
    finally:
        cur.close()
        conn.close()


# ==========================================
# COMMAND LISTENERS
# ==========================================
@bot.message_handler(commands=['hourlysummary', 'hourly_summary'])
def handle_hourly_summary_command(message):
    print(f"User {message.from_user.first_name} requested a manual summary via Telegram!")
    bot.reply_to(message, "⏳ <i>Gathering the latest factory data. Please wait...</i>", parse_mode="HTML")
    generate_hourly_report()

@bot.message_handler(commands=['getlink', 'link'])
def handle_get_link_command(message):
    """Allows you to request the Cloudflare link at any time."""
    # Ensure only authorized people can fetch the link
    if str(message.chat.id) == str(CHAT_ID):
        print(f"Admin requested Cloudflare link.")
        send_cloudflare_link()
    else:
        bot.reply_to(message, "⛔ Unauthorized.")


def run_bot_listener():
    """Runs the bot polling in a loop so it constantly listens for commands."""
    print("🎧 Telegram Bot Command Listener Started...")
    bot.infinity_polling()


# ==========================================
# SCHEDULER SETUP
# ==========================================
def start_scheduler():
    """Starts both the background timer AND the command listener."""
    scheduler = BackgroundScheduler()
    
    # 1. Start the Automatic Hourly Timer
    scheduler.add_job(generate_hourly_report, 'cron', minute=0)
    scheduler.start()
    print("🤖 Telegram Bot Scheduler Started. Running EXACTLY on the hour, every hour.")

    # 2. Start the Command Listener in a background thread
    listener_thread = threading.Thread(target=run_bot_listener)
    listener_thread.daemon = True
    listener_thread.start()