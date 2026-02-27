import requests
import re
import json
import time
import logging
from datetime import datetime
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

# Admin IDs - Updated as requested
ADMIN_IDS = [5326153007]  # Your admin ID
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

# Updated keyboard with your channels
def get_keyboard():
    keyboard = [
        [InlineKeyboardButton(" Channel", url="https://t.me/pyxuss_sms")],
        [InlineKeyboardButton(" Group", url="https://t.me/+sT7TU1EAX_w3ZjFl")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_powered_by():
    return f"©  xs {datetime.now().year}"

class IVASMSMonitor:
    def __init__(self):
        self.email = os.getenv("IVASMS_EMAIL")
        self.password = os.getenv("IVASMS_PASSWORD")
        self.session = requests.Session()
        self.last_sms = {}  # Store last 100 SMS to avoid duplicates
        self.logged_in = False
        self.login_attempts = 0
        self.max_sms_store = 100
        
        # Headers to mimic browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
    def login(self):
        """Login to IVASMS using requests"""
        try:
            logger.info(f"[LOGIN] Attempting login for {self.email}")
            
            # Get login page for token
            response = self.session.get("https://www.ivasms.com/login", headers=self.headers, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"[LOGIN] Failed to get login page: {response.status_code}")
                self.login_attempts += 1
                return False
            
            # Extract CSRF token
            token_match = re.search(r'<input type="hidden" name="_token" value="([^"]+)"', response.text)
            if not token_match:
                logger.error("[LOGIN] Could not find CSRF token")
                self.login_attempts += 1
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
            
            login_headers = self.headers.copy()
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
                self.login_attempts = 0
                logger.info("[LOGIN]  Successfully logged in")
                return True
            else:
                logger.error("[LOGIN] Login failed - check credentials")
                self.login_attempts += 1
                return False
                
        except Exception as e:
            logger.error(f"[LOGIN] Error: {e}")
            self.login_attempts += 1
            return False
    
    def check_sms(self):
        """Check for new SMS messages"""
        if not self.logged_in:
            if not self.login():
                return []
        
        try:
            # Go to SMS received page
            response = self.session.get(
                "https://www.ivasms.com/portal/sms/received", 
                headers=self.headers, 
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"[SMS] Failed to get SMS page: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            new_sms = []
            
            # Method 1: Look for table rows (most common)
            rows = soup.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Create unique ID for this SMS
                    sms_content = ' '.join([c.get_text(strip=True) for c in cells])
                    sms_id = str(hash(sms_content))
                    
                    if sms_id not in self.last_sms:
                        self.last_sms[sms_id] = datetime.now().isoformat()
                        
                        # Clean up old SMS
                        if len(self.last_sms) > self.max_sms_store:
                            oldest = min(self.last_sms.keys(), key=lambda k: self.last_sms[k])
                            del self.last_sms[oldest]
                        
                        sms_data = {
                            'from': cells[0].get_text(strip=True) if len(cells) > 0 else 'Unknown',
                            'message': cells[1].get_text(strip=True) if len(cells) > 1 else 'No message',
                            'time': cells[2].get_text(strip=True) if len(cells) > 2 else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id': sms_id
                        }
                        new_sms.append(sms_data)
            
            # Method 2: Look for div cards if no table rows found
            if not new_sms:
                cards = soup.find_all('div', class_=re.compile(r'card|sms-item|message-item'))
                for card in cards:
                    card_text = card.get_text(strip=True)
                    if card_text and len(card_text) > 10:
                        sms_id = str(hash(card_text[:200]))
                        
                        if sms_id not in self.last_sms:
                            self.last_sms[sms_id] = datetime.now().isoformat()
                            
                            if len(self.last_sms) > self.max_sms_store:
                                oldest = min(self.last_sms.keys(), key=lambda k: self.last_sms[k])
                                del self.last_sms[oldest]
                            
                            # Try to extract sender
                            sender = 'Unknown'
                            sender_match = re.search(r'(?:From|Sender)[:\s]+([^\n]+)', card_text)
                            if sender_match:
                                sender = sender_match.group(1).strip()
                            
                            sms_data = {
                                'from': sender,
                                'message': card_text[:300] + '...' if len(card_text) > 300 else card_text,
                                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'id': sms_id
                            }
                            new_sms.append(sms_data)
            
            if new_sms:
                logger.info(f"[SMS] Found {len(new_sms)} new message(s)")
            
            return new_sms
            
        except Exception as e:
            logger.error(f"[SMS] Error: {e}")
            return []
    
    def get_stats(self):
        """Get account statistics"""
        if not self.logged_in and not self.login():
            return " Not logged in"
        
        try:
            response = self.session.get("https://www.ivasms.com/portal", headers=self.headers, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find balance
            balance = "N/A"
            balance_selectors = ['.balance', '.user-balance', '.account-balance', 'span[class*="balance"]']
            for selector in balance_selectors:
                elem = soup.select_one(selector)
                if elem:
                    balance = elem.text.strip()
                    break
            
            return f""" **Email:** {self.email}
 **Balance:** {balance}
 **SMS Tracked:** {len(self.last_sms)}
 **Status:** Logged In
 **Last Check:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
        except Exception as e:
            logger.error(f"[STATS] Error: {e}")
            return f" **Email:** {self.email}\n Could not fetch stats\n SMS Tracked: {len(self.last_sms)}"

# Initialize monitor
monitor = IVASMSMonitor()

# Initial login attempt
monitor.login()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_users.add(user_id)
    
    welcome_text = f"""
 **Welcome to IVASMS Monitor Bot!**

This bot monitors your IVASMS account and forwards SMS to this chat.

** Commands:**
/status - Check bot status
/stats - View account statistics
/check - Manually check for SMS
/help - Show this help

** Join our channel:** @pyxuss_sms

{get_powered_by()}
"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_keyboard()
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_text = f"""
** Bot Status:**

 **Running:** Yes
 **Logged in:** {' Yes' if monitor.logged_in else ' No'}
 **SMS Tracked:** {len(monitor.last_sms)}
 **Users:** {len(bot_users)}
 **Login Attempts:** {monitor.login_attempts}

{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{get_powered_by()}
"""
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(" Fetching stats...")
    stats_text = monitor.get_stats()
    await msg.edit_text(f"** Account Statistics:**\n\n{stats_text}", parse_mode='Markdown')

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(" Checking for new SMS...")
    
    sms_list = monitor.check_sms()
    
    if sms_list:
        for sms in sms_list:
            sms_text = f"""
 **New SMS**

 **From:** `{sms['from']}`
 **Message:** 
`{sms['message']}`
 **Time:** {sms['time']}

{get_powered_by()}
"""
            await update.message.reply_text(sms_text, parse_mode='Markdown')
        await msg.delete()
    else:
        await msg.edit_text(" No new SMS messages found.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = f"""
** Available Commands:**

/start - Welcome message
/status - Check bot status
/stats - View account stats
/check - Manually check SMS
/help - Show this help

** Tips:**
• Bot automatically checks for SMS every 45-90 seconds
• New SMS are forwarded to this chat
• Contact admin for support

{get_powered_by()}
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(" This command is for admins only.")
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
                text=f" **Broadcast Message:**\n\n{message}\n\n{get_powered_by()}",
                parse_mode='Markdown'
            )
            success += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except Exception as e:
            logger.error(f"Failed to send to {uid}: {e}")
            failed += 1
    
    await update.message.reply_text(f" Sent to {success} users\n Failed: {failed}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

async def monitor_loop(app):
    """Background task to monitor SMS"""
    await asyncio.sleep(10)  # Wait for bot to start
    logger.info("[MONITOR] Starting monitoring loop")
    
    while True:
        try:
            # Ensure we're logged in
            if not monitor.logged_in:
                if monitor.login_attempts < 5:
                    monitor.login()
                else:
                    logger.warning("[MONITOR] Too many failed login attempts, waiting 5 minutes...")
                    await asyncio.sleep(300)
                    monitor.login_attempts = 0
                    continue
            
            # Check for new SMS
            sms_list = monitor.check_sms()
            
            if sms_list:
                logger.info(f"[MONITOR] Found {len(sms_list)} new SMS")
                for sms in sms_list:
                    sms_text = f"""
 **New SMS Received**

 **From:** `{sms['from']}`
 **Message:** 
`{sms['message']}`
 **Time:** {sms['time']}

{get_powered_by()}
"""
                    # Send to all users
                    for user_id in bot_users:
                        try:
                            await app.bot.send_message(
                                chat_id=user_id,
                                text=sms_text,
                                parse_mode='Markdown'
                            )
                            await asyncio.sleep(0.5)  # Rate limiting
                        except Exception as e:
                            logger.error(f"Failed to send to {user_id}: {e}")
                    
                    # Also send to main chat if set
                    chat_id = os.getenv("CHAT_ID")
                    if chat_id:
                        try:
                            await app.bot.send_message(
                                chat_id=chat_id,
                                text=sms_text,
                                parse_mode='Markdown'
                            )
                        except:
                            pass
            
            # Random wait between checks (45-90 seconds)
            wait_time = random.randint(45, 90)
            logger.info(f"[MONITOR] Next check in {wait_time}s")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"[MONITOR] Error: {e}")
            await asyncio.sleep(60)

async def main():
    """Main function"""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)
    
    logger.info("[BOT] Starting...")
    
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