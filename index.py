import requests
import re
import json
import time
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import os
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys
import threading

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Admin IDs
ADMIN_IDS = [5326153007]
bot_users = set()

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'''<!DOCTYPE html>
<html><head><title>IVASMS Bot</title></head>
<body><h1>IVASMS Bot is running!</h1><p>Status: OK</p></body></html>''')
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"[HEALTH] Server listening on port {port}")
    server.serve_forever()

# Start health server in background
health_thread = threading.Thread(target=run_health_server, daemon=True)
health_thread.start()

BANNER_URL = "https://files.catbox.moe/koc535.jpg"

def get_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Channel", url="https://t.me/pyxuss_sms")],
        [InlineKeyboardButton("👥 Group", url="https://t.me/+sT7TU1EAX_w3ZjFl")],
    ]
    return InlineKeyboardMarkup(keyboard)

class IVASMSMonitor:
    def __init__(self):
        self.email = os.getenv("IVASMS_EMAIL")
        self.password = os.getenv("IVASMS_PASSWORD")
        self.session = requests.Session()
        self.last_sms = set()
        self.logged_in = False
        
    def login(self):
        """Login to IVASMS using requests (no Selenium)"""
        try:
            logger.info("[LOGIN] Attempting login...")
            
            # Get login page for token
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            response = self.session.get("https://www.ivasms.com/login", headers=headers, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"[LOGIN] Failed to get login page: {response.status_code}")
                return False
            
            # Extract CSRF token
            token_match = re.search(r'<input type="hidden" name="_token" value="([^"]+)"', response.text)
            if not token_match:
                logger.error("[LOGIN] No CSRF token found")
                return False
            
            _token = token_match.group(1)
            
            # Perform login
            login_data = {
                "_token": _token,
                "email": self.email,
                "password": self.password,
                "remember": "on",
                "submit": "register"
            }
            
            login_headers = headers.copy()
            login_headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www.ivasms.com",
                "Referer": "https://www.ivasms.com/login"
            })
            
            login_response = self.session.post(
                "https://www.ivasms.com/login",
                data=login_data,
                headers=login_headers,
                allow_redirects=True,
                timeout=30
            )
            
            # Check if login successful
            if "dashboard" in login_response.url or "portal" in login_response.url:
                self.logged_in = True
                logger.info("[LOGIN] ✓ Successfully logged in")
                return True
            else:
                logger.error("[LOGIN] Login failed - check credentials")
                return False
                
        except Exception as e:
            logger.error(f"[LOGIN] Error: {e}")
            return False
    
    def check_sms(self):
        """Check for new SMS messages"""
        if not self.logged_in:
            if not self.login():
                return []
        
        try:
            # Go to SMS received page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.ivasms.com/portal',
            }
            
            response = self.session.get(
                "https://www.ivasms.com/portal/sms/received", 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"[SMS] Failed to get SMS page: {response.status_code}")
                return []
            
            # Parse SMS
            soup = BeautifulSoup(response.text, 'html.parser')
            new_sms = []
            
            # Look for SMS entries - adjust selectors based on actual HTML
            sms_elements = soup.find_all('tr', class_='sms-row')
            if not sms_elements:
                # Try alternative selectors
                sms_elements = soup.find_all('div', class_='sms-item')
            
            for element in sms_elements:
                element_text = element.get_text()
                # Create a simple hash of the SMS to avoid duplicates
                sms_hash = hash(element_text[:200])
                
                if sms_hash not in self.last_sms:
                    self.last_sms.add(sms_hash)
                    
                    # Extract basic info
                    sms_data = {
                        'from': 'Unknown',
                        'message': element_text[:200] + '...' if len(element_text) > 200 else element_text,
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Try to extract sender and message
                    sender_match = re.search(r'(?:From|Sender)[:\s]+([^\n]+)', element_text)
                    if sender_match:
                        sms_data['from'] = sender_match.group(1).strip()
                    
                    new_sms.append(sms_data)
            
            if new_sms:
                logger.info(f"[SMS] Found {len(new_sms)} new messages")
            
            return new_sms
            
        except Exception as e:
            logger.error(f"[SMS] Error: {e}")
            return []
    
    def get_stats(self):
        """Get account statistics"""
        if not self.logged_in:
            if not self.login():
                return "Not logged in"
        
        try:
            response = self.session.get("https://www.ivasms.com/portal", timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find balance
            balance_elem = soup.find('span', class_='balance')
            balance = balance_elem.text.strip() if balance_elem else "N/A"
            
            return f"Email: {self.email}\nBalance: {balance}"
        except:
            return "Could not fetch stats"

# Initialize monitor
monitor = IVASMSMonitor()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_users.add(user_id)
    
    await update.message.reply_text(
        "👋 **Welcome to IVASMS Monitor Bot!**\n\n"
        "This bot monitors your IVASMS account and forwards SMS to this chat.\n\n"
        "**Commands:**\n"
        "/status - Check bot status\n"
        "/stats - View account statistics\n"
        "/check - Manually check for SMS\n"
        "/help - Show this help",
        parse_mode='Markdown',
        reply_markup=get_keyboard()
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = f"🟢 Bot is running\n"
    status_text += f"📱 Logged in: {'Yes' if monitor.logged_in else 'No'}\n"
    status_text += f"📊 SMS tracked: {len(monitor.last_sms)}\n"
    status_text += f"👥 Users: {len(bot_users)}"
    
    await update.message.reply_text(status_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats_text = monitor.get_stats()
    await update.message.reply_text(f"**Account Stats:**\n{stats_text}", parse_mode='Markdown')

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Checking for new SMS...")
    
    sms_list = monitor.check_sms()
    
    if sms_list:
        for sms in sms_list:
            sms_text = f"""
📱 **New SMS**

📞 **From:** {sms['from']}
💬 **Message:** `{sms['message']}`
🕐 **Time:** {sms['time']}
"""
            await update.message.reply_text(sms_text, parse_mode='Markdown')
        await msg.delete()
    else:
        await msg.edit_text("📭 No new SMS messages found.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "**Available Commands:**\n\n"
        "/start - Welcome message\n"
        "/status - Bot status\n"
        "/stats - Account stats\n"
        "/check - Check SMS now\n"
        "/help - This message",
        parse_mode='Markdown'
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only command")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    
    message = " ".join(context.args)
    success = 0
    failed = 0
    
    for uid in bot_users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 **Broadcast:**\n\n{message}",
                parse_mode='Markdown'
            )
            success += 1
        except:
            failed += 1
    
    await update.message.reply_text(f"✅ Sent to {success} users\n❌ Failed: {failed}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

async def monitor_loop(app):
    """Background task to monitor SMS"""
    while True:
        try:
            if monitor.logged_in or monitor.login():
                sms_list = monitor.check_sms()
                
                if sms_list:
                    for sms in sms_list:
                        sms_text = f"""
📱 **New SMS Received**

📞 **From:** {sms['from']}
💬 **Message:** `{sms['message']}`
🕐 **Time:** {sms['time']}
"""
                        # Send to all users
                        for user_id in bot_users:
                            try:
                                await app.bot.send_message(
                                    chat_id=user_id,
                                    text=sms_text,
                                    parse_mode='Markdown'
                                )
                            except:
                                pass
                        
                        # Also send to main chat
                        if os.getenv("CHAT_ID"):
                            try:
                                await app.bot.send_message(
                                    chat_id=os.getenv("CHAT_ID"),
                                    text=sms_text,
                                    parse_mode='Markdown'
                                )
                            except:
                                pass
                
                # Wait 30-60 seconds between checks
                await asyncio.sleep(random.randint(30, 60))
            else:
                logger.warning("[MONITOR] Not logged in, waiting 60s...")
                await asyncio.sleep(60)
                
        except Exception as e:
            logger.error(f"[MONITOR] Error: {e}")
            await asyncio.sleep(60)

async def main():
    """Main function"""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)
    
    # Login initially
    monitor.login()
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("broadcast", broadcast))
    
    application.add_error_handler(error_handler)
    
    logger.info("[BOT] Starting...")
    
    # Start bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Start monitoring loop
    asyncio.create_task(monitor_loop(application))
    
    logger.info("[BOT] Running!")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("[BOT] Shutting down...")
        await application.stop()

if __name__ == "__main__":
    asyncio.run(main())