import asyncio
import io
import re
import json
import html
import os
import httpx
import random
import string
import time
import unicodedata
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from telegram.request import HTTPXRequest

# ==================== CONFIGURATION SECTION ====================

BOT_TOKEN = "8463468131:AAE7iTujWlYP8z61kOwZkZc-Cps4RjUYxxM"
ADMINS = [8271633124]

USD_TO_BDT = 122.50  # BDT কনভার্সন রেট

USER_DATA_FILE = "users.json"
PAID_SMS_FILE = "paid_sms.json"
STATS_FILE = "user_stats.json"
BANNED_USERS_FILE = "banned_users.json"
WITHDRAW_DATA_FILE = "withdraw_requests.json"
ACTIVITY_LOGS_FILE = "activity_logs.json"
SETTINGS_FILE = "settings.json"
ACTIVE_NUMBERS_FILE = "active_numbers.json"
MANUAL_RANGES_FILE = "manual_ranges.json"

DEFAULT_SETTINGS = {
    "api_key": "3e725522f5759b8212776aed6c615f1a6f1da525",
    "base_url": "https://axnumberserver.shop/number/api",
    "otp_group_id": "-1004372443286",
    "welcome_message": (
        "<blockquote>"
        "⚡ <b>WELCOME TO SMS WAVE</b> 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>স্ট্যান্ট ওটিপি রিসিভ করা শুরু করুন!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>নিচের মেনু থেকে আপনার কাঙ্ক্ষিত অপশন সিলেক্ট করুন।</i>"
        "</blockquote>"
    ),
    "otp_group_url": "https://t.me/myotpchanne",
    "channel_url": "https://t.me/myotpchanne",
    "support_username": "admin",
    "maintenance_mode": False,
    "min_withdraw": 0.5,
    "max_withdraw": 100.0,
    "cooldown_time": 1.0,
    "otp_reward": 0.0020,
    "refer_bonus": 0.050,
    "numbers_per_request": 1,
    "force_join_enabled": False,
    "force_join_channels": ["@your_chanel"],
    "join_alert_enabled": True,
    "auto_range": True
}

# ==================== DATA & SETTINGS ENGINE ====================

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)
        return DEFAULT_SETTINGS
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        updated = False
        for k, v in DEFAULT_SETTINGS.items():
            if k not in data:
                data[k] = v
                updated = True
        if updated:
            save_settings(data)
        return data
    except Exception:
        return DEFAULT_SETTINGS

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

def load_json(filepath, default_val):
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            json.dump(default_val, f)
        return default_val
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception:
        return default_val

def save_json(filepath, data):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

# ==================== USER & BALANCE MANAGEMENT ====================

def get_user(uid, username=None, full_name=None):
    uid_str = str(uid)
    data = load_json(USER_DATA_FILE, {})
    if uid_str not in data:
        data[uid_str] = {
            "user_id": uid_str,
            "balance": 0.0,
            "username": username,
            "full_name": full_name,
            "referrals": 0,
            "referral_earnings": 0.0,
            "referred_by": None,
            "withdrawal_method": None,
            "refer_notify": True
        }
        save_json(USER_DATA_FILE, data)
    else:
        updated = False
        if username and data[uid_str].get("username") != username:
            data[uid_str]["username"] = username
            updated = True
        if full_name and data[uid_str].get("full_name") != full_name:
            data[uid_str]["full_name"] = full_name
            updated = True
        if "refer_notify" not in data[uid_str]:
            data[uid_str]["refer_notify"] = True
            updated = True
        if updated:
            save_json(USER_DATA_FILE, data)
    return data[uid_str]

async def update_db_balance(uid, amount):
    uid_str = str(uid)
    data = load_json(USER_DATA_FILE, {})
    if uid_str in data:
        data[uid_str]["balance"] = round(data[uid_str].get("balance", 0.0) + amount, 4)
        save_json(USER_DATA_FILE, data)
        return data[uid_str]["balance"]
    return 0.0

def is_admin(user_id):
    return user_id in ADMINS

def is_user_banned(uid):
    banned_list = load_json(BANNED_USERS_FILE, [])
    return str(uid) in banned_list

def ban_user(uid):
    banned_list = load_json(BANNED_USERS_FILE, [])
    uid_str = str(uid)
    if uid_str not in banned_list:
        banned_list.append(uid_str)
        save_json(BANNED_USERS_FILE, banned_list)
        return True
    return False

def unban_user(uid):
    banned_list = load_json(BANNED_USERS_FILE, [])
    uid_str = str(uid)
    if uid_str in banned_list:
        banned_list.remove(uid_str)
        save_json(BANNED_USERS_FILE, banned_list)
        return True
    return False

# ==================== UTILITY FUNCTIONS ====================

def strip_html_tags(text: str) -> str:
    return re.sub(r'<[^>]*>', '', str(text))

def unstyle_text(text: str) -> str:
    if not text: return ""
    return unicodedata.normalize('NFKC', str(text))

def normalize_number(num):
    return re.sub(r'\D', '', str(num))

def mask_number(num):
    num_str = str(num).replace('+', '').replace(' ', '').strip()
    if len(num_str) >= 8:
        return f"{num_str[:4]}••••{num_str[-4:]}"
    return num_str

def generate_payment_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

def extract_otp(text):
    if not text or text == "No Content": return "N/A"
    text_clean = str(text).strip()
    label_match = re.search(r'(?:code|otp|verify|verification|pin|confirmation|kod|passcode)[\s:-]+([a-zA-Z0-9]{3,10})\b', text_clean, re.IGNORECASE)
    if label_match: return label_match.group(1).strip()
    spaced_otp = re.search(r'\b(\d{3}[\s-]\d{3})\b', text_clean)
    if spaced_otp: return spaced_otp.group(1)
    digit_match = re.search(r'\b(\d{4,8})\b', text_clean)
    if digit_match: return digit_match.group(1)
    return "N/A"

def load_country_map(filename="Country.txt"):
    country_map = {}
    if not os.path.exists(filename):
        return country_map
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("|")
                    if len(parts) >= 3:
                        prefix = parts[0].strip()
                        flag = parts[1].strip()
                        name = parts[2].strip()
                        country_map[prefix] = (flag, name)
    except Exception as e:
        print(f"Error loading Country.txt: {e}")
    return country_map

def get_country_info(number):
    clean_num = normalize_number(number)
    country_map = load_country_map()
    sorted_prefixes = sorted(country_map.keys(), key=len, reverse=True)
    for prefix in sorted_prefixes:
        if clean_num.startswith(prefix):
            return country_map[prefix]
    return "🌐", "Global"

def detect_service(full_sms):
    if not full_sms: return "SMS SERVICE"
    sms_lower = full_sms.lower()
    if "uber" in sms_lower: return "UBER"
    if "whatsapp" in sms_lower: return "WHATSAPP"
    if "1xbet" in sms_lower: return "1XBET"
    if "melbet" in sms_lower: return "MELBET"
    if "apple" in sms_lower: return "APPLE"
    if "telegram" in sms_lower or "tg" in sms_lower: return "TELEGRAM"
    if "facebook" in sms_lower or "fb" in sms_lower: return "FACEBOOK"
    return "SMS SERVICE"

def clean_range_id(range_str: str) -> str:
    if not range_str: return ""
    number_str = str(range_str).split('|')[-1].strip()
    return re.sub(r'[^\w]', '', number_str)

def get_service_icon(app_name):
    name = str(app_name).lower().strip()
    icons = {
        "uber": "🚗", "whatsapp": "🟢", "apple": "🍏", "1xbet": "🎰",
        "melbet": "🟡", "switch": "🟢", "facebook": "📘", "telegram": "✈️"
    }
    for key, icon in icons.items():
        if key in name: return icon
    return "📱"

# ==================== STATS ENGINE ====================

def add_number_taken(uid, count=1):
    uid = str(uid)
    stats = load_json(STATS_FILE, {})
    if uid not in stats: stats[uid] = {"numbers_taken": [], "otps_received": []}
    now = datetime.now().isoformat()
    for _ in range(count): stats[uid]["numbers_taken"].append(now)
    save_json(STATS_FILE, stats)

def add_otp_received(uid):
    uid = str(uid)
    stats = load_json(STATS_FILE, {})
    if uid not in stats: stats[uid] = {"numbers_taken": [], "otps_received": []}
    stats[uid]["otps_received"].append(datetime.now().isoformat())
    save_json(STATS_FILE, stats)

def get_user_otp_stats(uid):
    uid = str(uid)
    stats = load_json(STATS_FILE, {})
    user_stats = stats.get(uid, {}).get("otps_received", [])
    
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    
    today_cnt = 0
    seven_cnt = 0
    thirty_cnt = 0
    lifetime_cnt = len(user_stats)
    
    for t_str in user_stats:
        try:
            dt = datetime.fromisoformat(t_str)
            if dt >= today_start:
                today_cnt += 1
            if dt >= seven_days_ago:
                seven_cnt += 1
            if dt >= thirty_days_ago:
                thirty_cnt += 1
        except Exception:
            pass
            
    return today_cnt, seven_cnt, thirty_cnt, lifetime_cnt

def log_global_activity(uid, action, details):
    logs = load_json(ACTIVITY_LOGS_FILE, [])
    log_entry = {
        "uid": str(uid),
        "action": action,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    logs.append(log_entry)
    save_json(ACTIVITY_LOGS_FILE, logs)

# ==================== KEYBOARDS ====================

def rkbtn(text: str, style: str = None):
    return KeyboardButton(text=text, api_kwargs={"style": style}) if style else KeyboardButton(text=text)

def rbtn(text: str, style: str = None, callback_data: str = None, url: str = None):
    return InlineKeyboardButton(**{k: v for k, v in [("text", text), ("callback_data", callback_data), ("url", url), ("api_kwargs", {"style": style} if style else None)] if v is not None})

def main_keyboard(user_id):
    keyboard = [
        [rkbtn("📞 Get Number", style="primary"), rkbtn("(•) Live Traffic", style="primary")],
        [rkbtn("🔒 2F Auth", style="primary"), rkbtn("👤 Profile", style="primary")],
        [rkbtn("🔥 Leaderboard", style="primary"), rkbtn("💬 Support", style="primary")]
    ]
    if is_admin(user_id):
        keyboard.append([rkbtn("⚙️ ADMIN PANEL", style="primary")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_main_keyboard():
    keyboard = [
        [KeyboardButton("⚙️ SYSTEM CONFIG"), KeyboardButton("💵 USER & BALANCE")],
        [KeyboardButton("🔒 SECURITY & JOIN"), KeyboardButton("📢 NOTICE & B-CAST")],
        [KeyboardButton("🔙 BACK TO MAIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_system_config_keyboard():
    keyboard = [
        [KeyboardButton("🔑 SET API KEY"), KeyboardButton("🌐 SET API BASE URL")],
        [KeyboardButton("📢 SET OTP CHANNEL ID"), KeyboardButton("💰 SET WITHDRAW LIMITS")],
        [KeyboardButton("🎁 SET REFER BONUS"), KeyboardButton("⏱ SET COOLDOWN")],
        [KeyboardButton("🚫 TOGGLE MAINTENANCE"), KeyboardButton("🔙 BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_user_balance_keyboard():
    keyboard = [
        [KeyboardButton("➕ ADD BALANCE"), KeyboardButton("➖ REMOVE BALANCE")],
        [KeyboardButton("💬 DIRECT MSG USER"), KeyboardButton("📜 ALL USER BALANCE")],
        [KeyboardButton("🔙 BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_security_join_keyboard():
    keyboard = [
        [KeyboardButton("🚫 BAN USER"), KeyboardButton("✅ UNBAN USER")],
        [KeyboardButton("📢 FORCE CHANNELS"), KeyboardButton("📜 BAN USER LIST")],
        [KeyboardButton("🔙 BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_force_channel_keyboard():
    keyboard = [
        [KeyboardButton("➕ ADD CHANNEL"), KeyboardButton("➖ DELETE CHANNEL")],
        [KeyboardButton("🔙 BACK TO SECURITY")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_notice_bcast_keyboard():
    keyboard = [
        [KeyboardButton("📢 TEXT BROADCAST"), KeyboardButton("🎙 VOICE BROADCAST")],
        [KeyboardButton("📝 SET WELCOME MSG"), KeyboardButton("💬 SET SUPPORT USERNAME")],
        [KeyboardButton("🔗 SET CHANNEL LINK"), KeyboardButton("🔙 BACK TO ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ CANCEL")]], resize_keyboard=True)

# ==================== ASYNC CLIENT & QUEUE ====================

client_async = httpx.AsyncClient(timeout=10.0, verify=False, headers={"User-Agent": "Mozilla/5.0"})
request_queue = asyncio.Queue()
active_numbers = load_json(ACTIVE_NUMBERS_FILE, {})
last_range = {}

# ==================== API FUNCTIONS ====================

async def fetch_top_ranges():
    settings = load_settings()
    api_key = settings.get("api_key")
    base_url = settings.get("base_url").rstrip('/')
    
    try:
        url = f"{base_url}/liveaccess?api_key={api_key}"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        r = await client_async.get(url, headers=headers, timeout=10.0)
        
        if r.status_code != 200:
            return None, f"HTTP Status {r.status_code}"
            
        data = r.json()
        top_ranges = {}
        services_list = []

        if isinstance(data, dict):
            inner_data = data.get("data")
            if isinstance(inner_data, dict):
                services_list = inner_data.get("services") or inner_data.get("ranges") or []
            elif isinstance(inner_data, list):
                services_list = inner_data
            else:
                services_list = data.get("services") or data.get("ranges") or []

        if isinstance(services_list, list):
            for s_item in services_list:
                if isinstance(s_item, dict):
                    app_raw = s_item.get("sid") or s_item.get("service") or s_item.get("app") or "Unknown"
                    rng_list = s_item.get("ranges", [])
                    app_name = app_raw.strip().upper()
                    if app_name not in top_ranges:
                        top_ranges[app_name] = []
                    for rng in rng_list:
                        if rng and rng not in top_ranges[app_name]:
                            top_ranges[app_name].append(rng)

        return top_ranges, None
    except Exception as e:
        return None, str(e)

async def fetch_number_async(range_str):
    try:
        settings = load_settings()
        api_key = settings.get("api_key")
        base_url = settings.get("base_url").rstrip('/')
        url = f"{base_url}/getnumber"
        clean_rid = clean_range_id(range_str)
        
        params = {"api_key": api_key, "rid": clean_rid, "national": 1, "remove_plus": 1}
        headers = {"User-Agent": "Mozilla/5.0"}
        r = await client_async.get(url, params=params, headers=headers, timeout=10.0)
        data = r.json()
        
        if isinstance(data, dict) and data.get("status") == "success":
            return data.get("number") or data.get("phone")
    except Exception as e:
        print(f"[DEBUG] Fetch error: {e}")
    return None

# ==================== WORKER TASK ====================

async def worker():
    while True:
        task = await request_queue.get()
        try:
            uid = task['uid']
            chat_id = task['chat_id']
            context = task['context']
            range_text = task['range_text']
            
            status_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="<blockquote>⏳ <b>Searching number...</b>\n<i>Please wait a few seconds...</i></blockquote>",
                parse_mode="HTML"
            )
            result = await fetch_number_async(range_text)
            
            if not result:
                await status_msg.edit_text(
                    "<blockquote>❌ <b>NO NUMBER FOUND</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n<i>No stock available right now. Please try again!</i></blockquote>",
                    parse_mode="HTML"
                )
            else:
                clean_num = normalize_number(result)
                active_numbers[clean_num] = {"uid": uid, "range": range_text, "timestamp": datetime.now().isoformat()}
                save_json(ACTIVE_NUMBERS_FILE, active_numbers)
                add_number_taken(uid, 1)
                
                flag, c_name = get_country_info(clean_num)
                settings = load_settings()
                otp_target = settings.get("otp_group_id", "")
                otp_link = settings.get("channel_url")
                if str(otp_target).startswith("https://t.me/"):
                    otp_link = otp_target
                elif str(otp_target).startswith("@"):
                    otp_link = f"https://t.me/{str(otp_target)[1:]}"
    
                txt = (
                    f"<blockquote>"
                    f"📱 <b>NUMBER DETAILS</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🌐 <b>Country:</b> {flag} {c_name}\n"
                    f"📞 <b>Number:</b> <code>+{clean_num}</code>\n"
                    f"⚡ <b>Success Rate:</b> <code>95%</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏳ <b>SMS STATUS:</b> Waiting for message..."
                    f"</blockquote>"
                )
                kb = InlineKeyboardMarkup([
                    [rbtn("🔄 Change Number", style="primary", callback_data="same_range")],
                    [rbtn("📢 OTP Channel", style="success", url=otp_link)]
                ])
                await status_msg.edit_text(txt, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print(f"Worker Error: {e}")
        finally:
            request_queue.task_done()

# ==================== AUTO MONITOR LOOP ====================

async def monitor_loop(app):
    while True:
        try:
            settings = load_settings()
            api_key = settings.get("api_key")
            base_url = settings.get("base_url").rstrip('/')
            otp_target = settings.get("otp_group_id")
            otp_reward = settings.get("otp_reward", 0.0020)
            
            if api_key:
                r = await client_async.get(f"{base_url}/success_otp?api_key={api_key}")
                res = r.json()
                otps = res.get("data") or res.get("otps") or [] if isinstance(res, dict) else res if isinstance(res, list) else []

                if otps:
                    paid_data = load_json(PAID_SMS_FILE, {})
                    for otp in otps:
                        if not isinstance(otp, dict): continue
                        num = normalize_number(otp.get("number") or otp.get("phone") or "")
                        full_sms = otp.get("message") or otp.get("sms") or "No SMS Content"
                        otp_code = otp.get("otp_code") or extract_otp(full_sms)
                        otp_id = str(otp.get("otp_id", f"{num}_{otp_code}"))

                        if num in active_numbers and otp_id not in paid_data:
                            details = active_numbers[num]
                            user_id = details["uid"]
                            paid_data[otp_id] = True
                            save_json(PAID_SMS_FILE, paid_data)
                            
                            await update_db_balance(user_id, otp_reward)
                            add_otp_received(user_id)
                            log_global_activity(user_id, "OTP_RECEIVED", {"number": num, "otp": otp_code, "sms": full_sms})
                            
                            flag, c_name = get_country_info(num)
                            service = detect_service(full_sms)
                            masked_num = mask_number(num)
                            
                            user_msg = (
                                f"<blockquote>"
                                f"✅ <b>OTP RECEIVED SUCCESSFULLY!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"📞 <b>Number:</b> <code>+{num}</code>\n"
                                f"🔑 <b>OTP:</b> <code>{otp_code}</code>\n"
                                f"💰 <b>Bonus:</b> <code>+{otp_reward:.4f}$ Credited</code>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"💬 <b>Full SMS:</b>\n"
                                f"<code>{html.escape(full_sms)}</code>"
                                f"</blockquote>"
                            )
                            try:
                                await app.bot.send_message(user_id, user_msg, parse_mode="HTML")
                            except Exception: pass

                            group_msg = (
                                f"<blockquote>"
                                f"🚀 <b>LIVE OTP RECEIVED</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"⚙️ <b>Service:</b> <code>{service}</code>\n"
                                f"📞 <b>Mobile:</b> <code>{masked_num}</code>\n"
                                f"🌐 <b>Country:</b> {flag} {c_name}\n"
                                f"🔑 <b>OTP Code:</b> <code>{otp_code}</code>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"💬 <b>SMS:</b>\n"
                                f"<code>{html.escape(full_sms)}</code>"
                                f"</blockquote>"
                            )
                            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 JOIN PANEL", url=settings.get("channel_url"))]])
                            try:
                                await app.bot.send_message(otp_target, group_msg, parse_mode="HTML", reply_markup=kb)
                            except Exception as e:
                                print(f"Channel Post Error: {e}")
        except Exception:
            pass
        await asyncio.sleep(1.0)

# ==================== SUB & CORE HANDLERS ====================

async def is_user_member(bot, user_id, channel):
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception:
        return False

async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    if is_admin(uid):
        return True

    settings = load_settings()
    if not settings.get("force_join_enabled", False):
        return True

    channels = settings.get("force_join_channels", [])
    if not channels:
        return True

    not_joined = []
    for ch in channels:
        if not await is_user_member(context.bot, uid, ch):
            not_joined.append(ch)

    if not_joined:
        buttons = []
        for ch in not_joined:
            clean_ch = ch.replace("@", "")
            buttons.append([rbtn(f"📢 Join {ch}", style="primary", url=f"https://t.me/{clean_ch}")])
        buttons.append([rbtn("🔄 Verify / Check", style="success", callback_data="check_join")])

        msg = (
            "<blockquote>"
            "⚠️ <b>বটটি ব্যবহার করতে আমাদের চ্যানেলে জয়েন করুন!</b>\n\n"
            "দয়া করে নিচের চ্যানেলে জয়েন হয়ে <b>Verify / Check</b> বাটনে ক্লিক করুন:"
            "</blockquote>"
        )
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return False

    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return
    uid = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name
    
    users_db = load_json(USER_DATA_FILE, {})
    is_new = str(uid) not in users_db
    user_data = get_user(uid, username, full_name)
    
    if context.args and is_new:
        referrer_id = str(context.args[0])
        if referrer_id != str(uid) and referrer_id in users_db:
            settings = load_settings()
            bonus = settings.get("refer_bonus", 0.05)
            
            user_data["referred_by"] = referrer_id
            save_json(USER_DATA_FILE, users_db)
            
            await update_db_balance(referrer_id, bonus)
            ref_user = users_db[referrer_id]
            ref_user["referrals"] = ref_user.get("referrals", 0) + 1
            ref_user["referral_earnings"] = round(ref_user.get("referral_earnings", 0.0) + bonus, 4)
            save_json(USER_DATA_FILE, users_db)
            
            if ref_user.get("refer_notify", True):
                try:
                    ref_msg = (
                        f"<blockquote>"
                        f"🎁 <b>New Referral Joined!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"User: <b>{html.escape(full_name or 'N/A')}</b>\n"
                        f"Earned: <code>+{bonus}$</code>"
                        f"</blockquote>"
                    )
                    await context.bot.send_message(int(referrer_id), ref_msg, parse_mode="HTML")
                except Exception: pass

    settings = load_settings()
    await update.message.reply_text(settings.get("welcome_message"), parse_mode="HTML", reply_markup=main_keyboard(uid))

# ==================== PROFILE UI BUILDER ====================

def get_profile_view(uid):
    user_info = get_user(uid)
    today_cnt, seven_cnt, thirty_cnt, lifetime_cnt = get_user_otp_stats(uid)
    
    balance_usd = user_info.get("balance", 0.0)
    balance_bdt = balance_usd * USD_TO_BDT
    referrals_count = user_info.get("referrals", 0)
    refer_notify_status = "ON" if user_info.get("refer_notify", True) else "OFF"
    
    text = (
        f"<blockquote>"
        f"👤 <b>MY PROFILE</b>\n"
        f"────────────────────────\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"👛 <b>Balance:</b> <code>{balance_bdt:.4f} BDT</code>\n"
        f"💵 <b>Balance (USDT):</b> <code>{balance_usd:.4f} USDT</code>\n"
        f"────────────────────────\n"
        f"👑 <b>My Statistics</b>\n"
        f"├ Today: <b>{today_cnt}</b>\n"
        f"├ Last 7 Days: <b>{seven_cnt}</b>\n"
        f"├ Last 30 Days: <b>{thirty_cnt}</b>\n"
        f"└ Lifetime: <b>{lifetime_cnt}</b>\n"
        f"────────────────────────\n"
        f"🤝 <b>Referrals:</b> <code>{referrals_count}</code>"
        f"</blockquote>"
    )
    
    keyboard = [
        [rbtn("🗓 Withdrawal", style="danger", callback_data="init_withdraw")],
        [rbtn("🎁 ❐ Refer Link", style="success", callback_data="get_refer_link")],
        [rbtn(f"🔔 Refer Notification: {refer_notify_status}", style="success", callback_data="toggle_refer_notify")],
        [rbtn(f"📊 Referral Dashboard ({referrals_count})", style="primary", callback_data="refer_dashboard")],
        [rbtn("💳 My Wallet History", style="primary", callback_data="wallet_history")],
        [rbtn("↩ Back", style="secondary", callback_data="close_profile")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ==================== BROADCAST HELPER ====================

async def broadcast_media(bot, media_type, file_id, caption=""):
    users = load_json(USER_DATA_FILE, {})
    succ, fail = 0, 0
    for u_id in users.keys():
        try:
            if media_type == "voice":
                await bot.send_voice(int(u_id), voice=file_id, caption=caption, parse_mode="HTML")
            elif media_type == "audio":
                await bot.send_audio(int(u_id), audio=file_id, caption=caption, parse_mode="HTML")
            elif media_type == "text":
                await bot.send_message(int(u_id), text=caption, parse_mode="HTML")
            succ += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.04)
    return succ, fail

# ==================== VOICE & MEDIA HANDLER ====================

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    edit_mode = context.user_data.get("admin_edit_mode")
    if edit_mode == "voice_broadcast":
        context.user_data["admin_edit_mode"] = None
        media_type = "voice" if update.message.voice else "audio"
        file_id = update.message.voice.file_id if update.message.voice else update.message.audio.file_id
        caption = update.message.caption_html if update.message.caption else ""
        
        status = await update.message.reply_text("<blockquote>🎙 <b>Broadcasting audio to all users...</b></blockquote>", parse_mode="HTML")
        succ, fail = await broadcast_media(context.bot, media_type, file_id, caption)
        await status.edit_text(
            f"<blockquote>"
            f"✅ <b>VOICE BROADCAST FINISHED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Delivered: <code>{succ}</code> | Failed: <code>{fail}</code>"
            f"</blockquote>",
            parse_mode="HTML",
            reply_markup=admin_notice_bcast_keyboard()
        )

# ==================== TEXT MESSAGE HANDLER ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    uid = update.effective_user.id
    raw_text = update.message.text.strip()
    text = unstyle_text(raw_text)

    if is_user_banned(uid):
        await update.message.reply_text("<blockquote>🚫 <b>YOU ARE BANNED FROM USING THIS BOT!</b></blockquote>", parse_mode="HTML")
        return
    if not await check_force_sub(update, context):
        return

    if text == "❌ CANCEL":
        context.user_data.clear()
        await update.message.reply_text("<blockquote>❌ <b>Action cancelled.</b></blockquote>", parse_mode="HTML", reply_markup=main_keyboard(uid))
        return

    # --- WITHDRAW INPUT MODE ---
    w_mode = context.user_data.get("withdraw_mode")
    if w_mode == "amount":
        try:
            amount = float(text)
            settings = load_settings()
            min_w, max_w = settings.get("min_withdraw", 0.5), settings.get("max_withdraw", 100.0)
            u_bal = get_user(uid)["balance"]
            
            if amount < min_w or amount > max_w:
                await update.message.reply_text(f"<blockquote>❌ Invalid amount! Limit: <b>{min_w}$ - {max_w}$</b></blockquote>", parse_mode="HTML", reply_markup=cancel_keyboard())
                return
            if amount > u_bal:
                await update.message.reply_text("<blockquote>❌ <b>Insufficient balance!</b></blockquote>", parse_mode="HTML", reply_markup=cancel_keyboard())
                return
                
            context.user_data["withdraw_amount"] = amount
            context.user_data["withdraw_mode"] = "number"
            await update.message.reply_text("<blockquote>📱 <b>Enter your Account / Wallet Number:</b></blockquote>", parse_mode="HTML", reply_markup=cancel_keyboard())
            return
        except ValueError:
            await update.message.reply_text("<blockquote>❌ Send a valid numeric amount!</blockquote>", parse_mode="HTML", reply_markup=cancel_keyboard())
            return

    if w_mode == "number":
        method = context.user_data.get("withdraw_method")
        amount = context.user_data.get("withdraw_amount")
        payment_num = text
        pid = generate_payment_id()
        
        await update_db_balance(uid, -amount)
        w_requests = load_json(WITHDRAW_DATA_FILE, {})
        w_requests[pid] = {
            "user_id": uid, "method": method, "amount": amount,
            "number": payment_num, "payment_id": pid, "status": "pending",
            "timestamp": datetime.now().isoformat()
        }
        save_json(WITHDRAW_DATA_FILE, w_requests)
        
        context.user_data.clear()
        await update.message.reply_text(
            f"<blockquote>"
            f"✅ <b>WITHDRAWAL REQUEST SUBMITTED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>PID:</b> <code>{pid}</code>\n"
            f"💵 <b>Amount:</b> <code>{amount}$</code>\n"
            f"💳 <b>Method:</b> {method}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Request has been sent to admin for approval.</i>"
            f"</blockquote>",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
        
        admin_msg = (
            f"<blockquote>"
            f"💰 <b>NEW WITHDRAWAL REQUEST</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
            f"⚙️ <b>Method:</b> {method}\n"
            f"📞 <b>Number:</b> <code>{payment_num}</code>\n"
            f"💵 <b>Amount:</b> <code>{amount}$</code>\n"
            f"🆔 <b>PID:</b> <code>{pid}</code>"
            f"</blockquote>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"adm_app_{pid}"), InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{pid}")]
        ])
        for a_id in ADMINS:
            try: await context.bot.send_message(a_id, admin_msg, parse_mode="HTML", reply_markup=kb)
            except Exception: pass
        return

    # --- ADMIN INPUT ENGINE ---
    edit_mode = context.user_data.get("admin_edit_mode")
    if edit_mode and is_admin(uid):
        settings = load_settings()
        context.user_data["admin_edit_mode"] = None
        
        if edit_mode == "api_key":
            settings["api_key"] = raw_text
            save_settings(settings)
            await update.message.reply_text("✅ API Key updated!", reply_markup=admin_system_config_keyboard())
        elif edit_mode == "base_url":
            settings["base_url"] = raw_text
            save_settings(settings)
            await update.message.reply_text("✅ API Base URL updated!", reply_markup=admin_system_config_keyboard())
        elif edit_mode == "otp_channel":
            settings["otp_group_id"] = raw_text
            save_settings(settings)
            await update.message.reply_text(f"✅ OTP Channel ID set to: <code>{raw_text}</code>", parse_mode="HTML", reply_markup=admin_system_config_keyboard())
        elif edit_mode == "withdraw_limits":
            parts = raw_text.split()
            if len(parts) == 2:
                settings["min_withdraw"] = float(parts[0])
                settings["max_withdraw"] = float(parts[1])
                save_settings(settings)
                await update.message.reply_text(f"✅ Limits set: Min {parts[0]}$ | Max {parts[1]}$", reply_markup=admin_system_config_keyboard())
            else:
                await update.message.reply_text("❌ Format: 0.5 100")
        elif edit_mode == "refer_bonus":
            settings["refer_bonus"] = float(raw_text)
            save_settings(settings)
            await update.message.reply_text("✅ Referral bonus updated!", reply_markup=admin_system_config_keyboard())
        elif edit_mode == "cooldown":
            settings["cooldown_time"] = float(raw_text)
            save_settings(settings)
            await update.message.reply_text("✅ Cooldown updated!", reply_markup=admin_system_config_keyboard())
        elif edit_mode == "welcome":
            settings["welcome_message"] = raw_text
            save_settings(settings)
            await update.message.reply_text("✅ Welcome Message updated!", reply_markup=admin_notice_bcast_keyboard())
        elif edit_mode == "support":
            settings["support_username"] = raw_text.replace("@", "")
            save_settings(settings)
            await update.message.reply_text("✅ Support username updated!", reply_markup=admin_notice_bcast_keyboard())
        elif edit_mode == "channel_link":
            settings["channel_url"] = raw_text
            save_settings(settings)
            await update.message.reply_text("✅ Channel link updated!", reply_markup=admin_notice_bcast_keyboard())
        elif edit_mode == "add_balance":
            parts = raw_text.split()
            if len(parts) == 2 and parts[0].isdigit():
                t_uid, amt = parts[0], float(parts[1])
                new_b = await update_db_balance(t_uid, amt)
                await update.message.reply_text(f"✅ Added {amt}$ to User {t_uid}. New Balance: {new_b}$", reply_markup=admin_user_balance_keyboard())
            else:
                await update.message.reply_text("❌ Format: USER_ID AMOUNT", reply_markup=admin_user_balance_keyboard())
        elif edit_mode == "remove_balance":
            parts = raw_text.split()
            if len(parts) == 2 and parts[0].isdigit():
                t_uid, amt = parts[0], float(parts[1])
                new_b = await update_db_balance(t_uid, -amt)
                await update.message.reply_text(f"✅ Removed {amt}$ from User {t_uid}. New Balance: {new_b}$", reply_markup=admin_user_balance_keyboard())
            else:
                await update.message.reply_text("❌ Format: USER_ID AMOUNT", reply_markup=admin_user_balance_keyboard())
        elif edit_mode == "ban_user":
            if ban_user(raw_text):
                await update.message.reply_text(f"✅ User {raw_text} banned!", reply_markup=admin_security_join_keyboard())
            else:
                await update.message.reply_text("❌ User already banned!")
        elif edit_mode == "broadcast_text":
            succ, fail = await broadcast_media(context.bot, "text", None, f"<blockquote>📢 <b>ANNOUNCEMENT:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n{raw_text}</blockquote>")
            await update.message.reply_text(f"✅ Broadcast complete!\nSuccess: {succ} | Failed: {fail}", parse_mode="HTML", reply_markup=admin_notice_bcast_keyboard())
        return

    # --- USER ACTIONS ---
    if "Profile" in text or "PROFILE" in text:
        caption_text, reply_markup = get_profile_view(uid)
        await update.message.reply_text(caption_text, parse_mode="HTML", reply_markup=reply_markup)
        return

    if "Get Number" in text or "GET NUMBER" in text:
        status = await update.message.reply_text("<blockquote>⏳ <b>Loading Services...</b></blockquote>", parse_mode="HTML")
        top_ranges, err = await fetch_top_ranges()
        if err or not top_ranges:
            err_msg = err if err else "No active services returned from API"
            await status.edit_text(f"<blockquote>❌ Could not fetch services.\nReason: <code>{err_msg}</code></blockquote>", parse_mode="HTML")
            return
        
        context.user_data["top_ranges"] = top_ranges
        buttons, row = [], []
        for app_name in top_ranges.keys():
            icon = get_service_icon(app_name)
            btn_title = f"{icon} {app_name}"
            row.append(rbtn(btn_title, style="primary", callback_data=f"sel_app_{app_name}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
        buttons.append([rbtn("↩ Back", style="secondary", callback_data="close_services")])
        await status.edit_text("<blockquote>🔘 <b>Select a service from the list:</b></blockquote>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if "Live Traffic" in text:
        logs = load_json(ACTIVITY_LOGS_FILE, [])
        one_h_ago = datetime.now() - timedelta(hours=1)
        counts, total = {}, 0
        
        for log in logs:
            if log.get("action") == "OTP_RECEIVED":
                try:
                    ts = datetime.fromisoformat(log.get("timestamp"))
                    if ts >= one_h_ago:
                        dtls = log.get("details", {})
                        num, sms = dtls.get("number"), dtls.get("sms")
                        srv = detect_service(sms)
                        flag, cname = get_country_info(num)
                        key = (srv, flag, cname)
                        counts[key] = counts.get(key, 0) + 1
                        total += 1
                except Exception: pass
                
        if total == 0:
            await update.message.reply_text("<blockquote>📊 <b>Live Traffic (Last 1 Hour)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n<i>No OTP transactions in the last hour.</i></blockquote>", parse_mode="HTML")
            return
            
        lines = ["<blockquote>📊 <b>Live Traffic (Last 1 Hour)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━"]
        for (srv, flag, cname), count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total) * 100
            lines.append(f"📱 <b>{srv}</b> | {flag} {cname} | <code>{pct:.1f}% ({count})</code>")
        lines.append("</blockquote>")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if "Leaderboard" in text:
        stats = load_json(STATS_FILE, {})
        users = load_json(USER_DATA_FILE, {})
        ranked = [(u_id, len(s.get("otps_received", []))) for u_id, s in stats.items() if len(s.get("otps_received", [])) > 0]
        ranked = sorted(ranked, key=lambda x: x[1], reverse=True)[:10]
        
        lines = ["<blockquote>🏆 <b>OTP LEADERBOARD TOP 10</b>\n━━━━━━━━━━━━━━━━━━━━━━━━"]
        if ranked:
            for idx, (r_uid, count) in enumerate(ranked, 1):
                u_name = users.get(str(r_uid), {}).get("full_name") or f"User ({r_uid[-4:]})"
                lines.append(f"<b>#{idx}</b> {html.escape(u_name)} - <code>{count} OTPs</code>")
        else:
            lines.append("<i>No OTP records available yet.</i>")
        lines.append("</blockquote>")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if "Support" in text:
        settings = load_settings()
        sup = settings.get("support_username")
        kb = InlineKeyboardMarkup([[rbtn("💬 Contact Support", style="primary", url=f"https://t.me/{sup}")]])
        await update.message.reply_text("<blockquote>💬 <b>Need help? Click below to contact our support team:</b></blockquote>", parse_mode="HTML", reply_markup=kb)
        return

    if "2F Auth" in text:
        await update.message.reply_text(
            "<blockquote>"
            "🔒 <b>TWO-FACTOR AUTHENTICATION</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "2FA authentication feature is active and secured."
            "</blockquote>",
            parse_mode="HTML"
        )
        return

    # --- ADMIN ROUTING ---
    if "ADMIN PANEL" in text and is_admin(uid):
        await update.message.reply_text("⚙️ <b>ADMIN CONTROL PANEL</b>", parse_mode="HTML", reply_markup=admin_main_keyboard())
        return

    if text == "⚙️ SYSTEM CONFIG" and is_admin(uid):
        await update.message.reply_text("⚙️ <b>SYSTEM CONFIGURATION</b>", parse_mode="HTML", reply_markup=admin_system_config_keyboard())
        return

    if text == "💵 USER & BALANCE" and is_admin(uid):
        await update.message.reply_text("💵 <b>USER & BALANCE MANAGEMENT</b>", parse_mode="HTML", reply_markup=admin_user_balance_keyboard())
        return

    if "SECURITY & JOIN" in text and is_admin(uid):
        await update.message.reply_text("🔒 <b>SECURITY & JOIN CONTROLS</b>", parse_mode="HTML", reply_markup=admin_security_join_keyboard())
        return

    if "FORCE CHANNELS" in text and is_admin(uid):
        settings = load_settings()
        ch_list = settings.get("force_join_channels", [])
        channels_text = "\n".join([f"• <code>{c}</code>" for c in ch_list]) if ch_list else "<i>কোনো চ্যানেল সেট করা নেই</i>"
        msg = f"📢 <b>FORCE JOIN CHANNELS:</b>\n\n<b>বর্তমান চ্যানেলসমূহ:</b>\n{channels_text}"
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=admin_force_channel_keyboard())
        return

    if "ADD CHANNEL" in text and is_admin(uid):
        context.user_data["admin_edit_mode"] = "add_force_channel"
        await update.message.reply_text("চ্যানেলের ইউজারনেম দিন (যেমন: <code>@yourchannel</code>):", parse_mode="HTML", reply_markup=cancel_keyboard())
        return

    if "DELETE CHANNEL" in text and is_admin(uid):
        context.user_data["admin_edit_mode"] = "del_force_channel"
        settings = load_settings()
        ch_list = settings.get("force_join_channels", [])
        channels_text = "\n".join([f"• <code>{c}</code>" for c in ch_list]) if ch_list else "<i>কোনো চ্যানেল নেই</i>"
        await update.message.reply_text(f"যে চ্যানেলটি বাদ দিতে চান লিখুন:\n\n{channels_text}", parse_mode="HTML", reply_markup=cancel_keyboard())
        return

    if "BACK TO SECURITY" in text and is_admin(uid):
        await update.message.reply_text("🔒 <b>SECURITY & JOIN CONTROLS</b>", parse_mode="HTML", reply_markup=admin_security_join_keyboard())
        return

    if "NOTICE & B-CAST" in text and is_admin(uid):
        await update.message.reply_text("📢 <b>NOTICE & BROADCASTING</b>", parse_mode="HTML", reply_markup=admin_notice_bcast_keyboard())
        return

    if text == "📢 TEXT BROADCAST" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "broadcast_text"
        await update.message.reply_text("Enter message to broadcast:", reply_markup=cancel_keyboard())
        return

    if text == "🎙 VOICE BROADCAST" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "voice_broadcast"
        await update.message.reply_text("<blockquote>🎙 Send a voice note or audio file to broadcast:</blockquote>", parse_mode="HTML", reply_markup=cancel_keyboard())
        return

    if text == "🔑 SET API KEY" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "api_key"
        await update.message.reply_text("Enter new API Key:", reply_markup=cancel_keyboard())
        return

    if text == "🌐 SET API BASE URL" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "base_url"
        await update.message.reply_text("Enter new API Base URL:", reply_markup=cancel_keyboard())
        return

    if text == "📢 SET OTP CHANNEL ID" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "otp_channel"
        await update.message.reply_text("Enter OTP Channel ID:", reply_markup=cancel_keyboard())
        return

    if text == "💰 SET WITHDRAW LIMITS" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "withdraw_limits"
        await update.message.reply_text("Enter MIN and MAX limit (e.g. 0.5 100):", reply_markup=cancel_keyboard())
        return

    if text == "🎁 SET REFER BONUS" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "refer_bonus"
        await update.message.reply_text("Enter Referral Bonus Amount:", reply_markup=cancel_keyboard())
        return

    if text == "⏱ SET COOLDOWN" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "cooldown"
        await update.message.reply_text("Enter Cooldown (seconds):", reply_markup=cancel_keyboard())
        return

    if text == "🚫 TOGGLE MAINTENANCE" and is_admin(uid):
        settings = load_settings()
        settings["maintenance_mode"] = not settings.get("maintenance_mode", False)
        save_settings(settings)
        await update.message.reply_text(f"🛠 Maintenance Mode: <b>{'ENABLED' if settings['maintenance_mode'] else 'DISABLED'}</b>", parse_mode="HTML")
        return

    if text == "➕ ADD BALANCE" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "add_balance"
        await update.message.reply_text("Enter USER_ID and AMOUNT:", reply_markup=cancel_keyboard())
        return

    if text == "➖ REMOVE BALANCE" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "remove_balance"
        await update.message.reply_text("Enter USER_ID and AMOUNT:", reply_markup=cancel_keyboard())
        return

    if text == "📜 ALL USER BALANCE" and is_admin(uid):
        users = load_json(USER_DATA_FILE, {})
        tot_bal = sum(u.get("balance", 0.0) for u in users.values())
        lines = [f"Total Users: {len(users)} | Total Balance: {tot_bal:.4f}$\n"]
        for idx, (u_id, u_data) in enumerate(users.items(), 1):
            lines.append(f"{idx}. ID: {u_id} | Bal: {u_data.get('balance', 0.0):.4f}$")
        file_io = io.BytesIO("\n".join(lines).encode('utf-8'))
        file_io.name = "All_Users_Balance.txt"
        await update.message.reply_document(file_io, caption=f"📊 Total System Balance: {tot_bal:.4f}$")
        return

    if text == "🚫 BAN USER" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "ban_user"
        await update.message.reply_text("Enter USER_ID to ban:", reply_markup=cancel_keyboard())
        return

    if text == "✅ UNBAN USER" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "unban_user"
        await update.message.reply_text("Enter USER_ID to unban:", reply_markup=cancel_keyboard())
        return

    if text == "📜 BAN USER LIST" and is_admin(uid):
        banned = load_json(BANNED_USERS_FILE, [])
        await update.message.reply_text(f"🚫 <b>Banned Users ({len(banned)}):</b>\n\n" + "\n".join(banned), parse_mode="HTML")
        return

    if text == "📝 SET WELCOME MSG" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "welcome"
        await update.message.reply_text("Enter Welcome Text (HTML Supported):", reply_markup=cancel_keyboard())
        return

    if text == "💬 SET SUPPORT USERNAME" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "support"
        await update.message.reply_text("Enter Support Username:", reply_markup=cancel_keyboard())
        return

    if text == "🔗 SET CHANNEL LINK" and is_admin(uid):
        context.user_data["admin_edit_mode"] = "channel_link"
        await update.message.reply_text("Enter Channel Link:", reply_markup=cancel_keyboard())
        return

    if text in ["🔙 BACK TO ADMIN", "BACK TO ADMIN"]:
        await update.message.reply_text("⚙️ <b>ADMIN MANAGEMENT PANEL</b>", parse_mode="HTML", reply_markup=admin_main_keyboard())
        return

    if text in ["🔙 BACK TO MAIN", "BACK TO MAIN"]:
        await update.message.reply_text("Main Menu.", reply_markup=main_keyboard(uid))
        return

# ==================== CALLBACK QUERY ROUTER ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()

    if data == "check_join":
        if await check_force_sub(update, context):
            try: await query.message.delete()
            except Exception: pass
            await query.message.reply_text("<blockquote>✅ ধন্যবাদ! সফলভাবে যাচাই করা হয়েছে।</blockquote>", parse_mode="HTML", reply_markup=main_keyboard(uid))
        else:
            await query.answer("❌ আপনি এখনো সব চ্যানেলে জয়েন করেননি!", show_alert=True)
        return

    # --- PROFILE CALLBACKS ---
    if data == "get_refer_link":
        b_info = await context.bot.get_me()
        ref_link = f"https://t.me/{b_info.username}?start={uid}"
        await query.message.reply_text(
            f"<blockquote>"
            f"🎁 <b>YOUR REFERRAL LINK</b>\n"
            f"────────────────────────\n"
            f"<code>{ref_link}</code>\n\n"
            f"<i>শেয়ার করে প্রতি জয়েনে রেফার বোনাস পান!</i>"
            f"</blockquote>",
            parse_mode="HTML"
        )
        return

    if data == "toggle_refer_notify":
        users = load_json(USER_DATA_FILE, {})
        u_str = str(uid)
        if u_str in users:
            curr = users[u_str].get("refer_notify", True)
            users[u_str]["refer_notify"] = not curr
            save_json(USER_DATA_FILE, users)
        caption_text, reply_markup = get_profile_view(uid)
        await query.edit_message_text(caption_text, parse_mode="HTML", reply_markup=reply_markup)
        return

    if data == "refer_dashboard":
        u_info = get_user(uid)
        settings = load_settings()
        dashboard_msg = (
            f"<blockquote>"
            f"📊 <b>REFERRAL DASHBOARD</b>\n"
            f"────────────────────────\n"
            f"👥 <b>Total Invited:</b> <code>{u_info.get('referrals', 0)}</code>\n"
            f"💰 <b>Total Earnings:</b> <code>{u_info.get('referral_earnings', 0.0):.4f}$</code>\n"
            f"🎁 <b>Per Refer Reward:</b> <code>{settings.get('refer_bonus', 0.05)}$</code>\n"
            f"────────────────────────\n"
            f"<i>আপনার লিংক থেকে নতুন ইউজার যুক্ত হলে সাথে সাথেই ব্যালেন্সে জমা হবে।</i>"
            f"</blockquote>"
        )
        await query.message.reply_text(dashboard_msg, parse_mode="HTML")
        return

    if data == "wallet_history":
        w_reqs = load_json(WITHDRAW_DATA_FILE, {})
        user_reqs = [r for r in w_reqs.values() if str(r.get("user_id")) == str(uid)]
        
        if not user_reqs:
            await query.message.reply_text("<blockquote>💳 <b>Wallet History</b>\n────────────────────────\n<i>কোনো ট্রানজ্যাকশন হিস্টোরি পাওয়া যায়নি।</i></blockquote>", parse_mode="HTML")
            return
            
        lines = ["<blockquote>💳 <b>RECENT WALLET HISTORY</b>\n────────────────────────"]
        for r in user_reqs[-5:]:
            status_emoji = "✅" if r.get("status") == "approved" else "❌" if r.get("status") == "rejected" else "⏳"
            lines.append(f"{status_emoji} <b>{r.get('amount')}$</b> | {r.get('method')} | <code>{r.get('status').upper()}</code>")
        lines.append("</blockquote>")
        await query.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if data == "close_profile":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if data == "close_services":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # --- GET NUMBER PIPELINE ---
    if data.startswith("sel_app_"):
        app_name = data.replace("sel_app_", "")
        top_ranges = context.user_data.get("top_ranges", {})
        ranges = top_ranges.get(app_name, [])
        if not ranges:
            await query.edit_message_text("<blockquote>❌ No ranges available for this service.</blockquote>", parse_mode="HTML")
            return

        country_map = {}
        for rng in ranges:
            flag, cname = get_country_info(rng)
            c_key = f"{flag} {cname}"
            if c_key not in country_map:
                country_map[c_key] = []
            country_map[c_key].append(rng)

        if "country_ranges" not in context.user_data:
            context.user_data["country_ranges"] = {}

        buttons, row = [], []
        for c_label, rng_list in country_map.items():
            c_idx = str(len(context.user_data["country_ranges"]) + 1)
            context.user_data["country_ranges"][c_idx] = {
                "app": app_name,
                "label": c_label,
                "ranges": rng_list
            }
            row.append(rbtn(c_label, style="primary", callback_data=f"sel_cty_{c_idx}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row: buttons.append(row)

        buttons.append([rbtn("↩ Back to Services", style="secondary", callback_data="back_to_services")])
        await query.edit_message_text(f"<blockquote>🌐 <b>SELECT REGION FOR {app_name}:</b></blockquote>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("sel_cty_"):
        c_idx = data.replace("sel_cty_", "")
        c_info = context.user_data.get("country_ranges", {}).get(c_idx)
        if not c_info:
            await query.edit_message_text("<blockquote>❌ Session expired. Please click Get Number again.</blockquote>", parse_mode="HTML")
            return

        app_name = c_info["app"]
        country_label = c_info["label"]
        ranges = c_info["ranges"]

        selected_range = random.choice(ranges)
        last_range[uid] = selected_range

        await query.edit_message_text(f"<blockquote>⏳ <b>Searching active line for {app_name} ({country_label})...</b></blockquote>", parse_mode="HTML")
        await request_queue.put({
            'uid': uid,
            'chat_id': query.message.chat_id,
            'context': context,
            'range_text': selected_range
        })
        return

    if data == "back_to_services":
        top_ranges = context.user_data.get("top_ranges", {})
        if not top_ranges:
            await query.edit_message_text("<blockquote>❌ Session expired. Please click Get Number again.</blockquote>", parse_mode="HTML")
            return
        buttons, row = [], []
        for app_name in top_ranges.keys():
            icon = get_service_icon(app_name)
            btn_title = f"{icon} {app_name}"
            row.append(rbtn(btn_title, style="primary", callback_data=f"sel_app_{app_name}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
        buttons.append([rbtn("↩ Back", style="secondary", callback_data="close_services")])
        await query.edit_message_text("<blockquote>🔘 <b>Select a service from the list:</b></blockquote>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data == "same_range":
        r_text = last_range.get(uid)
        if r_text:
            await query.edit_message_text("<blockquote>🔄 Requesting new number...</blockquote>", parse_mode="HTML")
            await request_queue.put({
                'uid': uid,
                'chat_id': query.message.chat_id,
                'context': context,
                'range_text': r_text
            })
        else:
            await query.answer("No previous range recorded.", show_alert=True)
        return

    # --- WITHDRAW METHODS ---
    if data == "init_withdraw":
        kb = InlineKeyboardMarkup([
            [rbtn("bKash", style="primary", callback_data="m_bKash"), rbtn("Nagad", style="primary", callback_data="m_Nagad")],
            [rbtn("Rocket", style="primary", callback_data="m_Rocket"), rbtn("Binance (USDT)", style="primary", callback_data="m_Binance")]
        ])
        await query.message.reply_text("<blockquote>💳 <b>Select Withdrawal Gateway:</b></blockquote>", parse_mode="HTML", reply_markup=kb)
        return

    if data.startswith("m_"):
        method_name = data.replace("m_", "")
        users = load_json(USER_DATA_FILE, {})
        if str(uid) in users:
            users[str(uid)]["withdrawal_method"] = method_name
            save_json(USER_DATA_FILE, users)
        
        u_info = get_user(uid)
        settings = load_settings()
        if u_info["balance"] < settings["min_withdraw"]:
            await query.message.reply_text(f"<blockquote>❌ <b>Minimum withdrawal limit is {settings['min_withdraw']}$</b>\nYour Balance: <code>{u_info['balance']:.4f}$</code></blockquote>", parse_mode="HTML")
            return
            
        context.user_data["withdraw_method"] = method_name
        context.user_data["withdraw_mode"] = "amount"
        await query.message.reply_text(
            f"<blockquote>"
            f"💵 <b>Selected Gateway: {method_name}</b>\n"
            f"────────────────────────\n"
            f"Balance: <code>{u_info['balance']:.4f}$</code>\n"
            f"Min Limit: <code>{settings['min_withdraw']}$</code>\n\n"
            f"উত্তোলন করার পরিমাণ (USD) লিখুন:"
            f"</blockquote>",
            parse_mode="HTML",
            reply_markup=cancel_keyboard()
        )
        return

    # --- ADMIN ACTIONS ---
    if data.startswith("adm_app_"):
        pid = data.replace("adm_app_", "")
        w_reqs = load_json(WITHDRAW_DATA_FILE, {})
        if pid in w_reqs and w_reqs[pid]["status"] == "pending":
            w_reqs[pid]["status"] = "approved"
            save_json(WITHDRAW_DATA_FILE, w_reqs)
            
            u_id = w_reqs[pid]["user_id"]
            amt = w_reqs[pid]["amount"]
            try:
                await context.bot.send_message(u_id, f"<blockquote>✅ <b>WITHDRAWAL APPROVED!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nAmount: <code>{amt}$</code>\nPID: <code>{pid}</code></blockquote>", parse_mode="HTML")
            except Exception: pass
            
            await query.edit_message_text(f"✅ Approved Request {pid}")
        return

    if data.startswith("adm_rej_"):
        pid = data.replace("adm_rej_", "")
        w_reqs = load_json(WITHDRAW_DATA_FILE, {})
        if pid in w_reqs and w_reqs[pid]["status"] == "pending":
            w_reqs[pid]["status"] = "rejected"
            save_json(WITHDRAW_DATA_FILE, w_reqs)
            
            u_id = w_reqs[pid]["user_id"]
            amt = w_reqs[pid]["amount"]
            await update_db_balance(u_id, amt)
            
            try:
                await context.bot.send_message(u_id, f"<blockquote>❌ <b>WITHDRAWAL REJECTED & REFUNDED!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\nAmount: <code>{amt}$</code>\nPID: <code>{pid}</code></blockquote>", parse_mode="HTML")
            except Exception: pass
            
            await query.edit_message_text(f"❌ Rejected Request {pid}")
        return

# ==================== APPLICATION RUNNER ====================

async def post_init(application):
    asyncio.create_task(worker())
    asyncio.create_task(monitor_loop(application))

def main():
    request_config = HTTPXRequest(connect_timeout=15.0, read_timeout=15.0)
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request_config)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_media))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🚀 BOT RUNNING WITH PROFILE DASHBOARD UI...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass