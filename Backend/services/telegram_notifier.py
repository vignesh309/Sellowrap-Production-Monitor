import threading
import telebot
import os
import re

# 🚨 Import credentials securely from config.py
from config import BOT_TOKEN, CHAT_ID, GROUP_ID

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


# ==========================================
# COMMAND LISTENERS
# ==========================================
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
    bot.remove_webhook()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)


def start_listener():
    """Starts the command listener when explicitly enabled by the API process."""
    listener_thread = threading.Thread(target=run_bot_listener)
    listener_thread.daemon = True
    listener_thread.start()