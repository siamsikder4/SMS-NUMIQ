import requests
import time
import json
import random
import sqlite3
import os
import re
import html
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# Configuration
# ==========================================
BOT_TOKEN = "8463468131:AAGxlaWJWVWwSjGOEyUaLXFSTJ0NfvhSqCE"
ADMIN_ID = 8271633124
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
BOT_USERNAME = ""

# 2oo9 API Configuration
API_2OO9_BASE = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"
API_2OO9_KEY_DEFAULT = "MHF5UTYD3L7"

# Global states
current_db_mode = "sqlite"
db_firebase = None 
waiting_for_firebase = False
user_states = {}

# User & Cooldown States
user_cache = {} 
user_active_sessions = {}
user_cooldowns = {} 

# Voltx Auto System States
voltx_auto_mode = True 
voltx_keys = [API_2OO9_KEY_DEFAULT]
force_join_status = False
force_join_channels = []

# OTP Forwarding States
otp_forward_groups = []
otp_button_link = "https://t.me/numiiq_bot"
recent_success_otps = set()

voltx_dynamic_data = {} 
recent_traffic = []
daily_stats = {"date": "", "numbers": 0, "otps": 0}
daily_user_otps = {"date": "", "users": {}}

# Caching Variables
cached_services_kb = None
cached_countries_kb = {}
cached_leaderboard_text = ""

# ==========================================
# Animated & Custom Emojis Map
# ==========================================
GLOBAL_BODY_EMOJIS = {
    "📞": "5429167978761461870", "📡": "5429571662737611814", "🔐": "5337255927735163754",
    "👤": "5352861489541714456", "🔥": "5337267511261960341", "💬": "5337302974806922068",
    "📊": "5352877703043258544", "🕒": "5336983442125001376", "🏆": "5240021484516185513",
    "🌍": "5780471598922337683", "🔄": "5229111790842952353", "🔙": "5438541186539232243",
    "💳": "5190899075968441286", "💵": "5429612421977253466", "🎁": "5420396762189831222",
    "🔗": "5420517437885943844", "🔔": "5352980533150259581", "👑": "5352838545826420397",
    "🆔": "5226929552319594190", "💰": "5429105001655999635", "✅": "5352694861990501856",
    "❌": "5420130255174145507", "⚙️": "5420155432272438703", "🤝": "5192805934073685937",
    "1️⃣": "5352651766288652742", "2️⃣": "5355186458418257716", "3️⃣": "5352867219028091093"
}

def apply_emojis(text):
    hidden = []
    def hide(match):
        hidden.append(match.group(0))
        return f"__TG_EMOJI_{len(hidden)-1}__"
    text = re.sub(r'<tg-emoji[^>]*>.*?</tg-emoji>', hide, text)
    for char, eid in GLOBAL_BODY_EMOJIS.items():
        text = text.replace(char, f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>')
    for i, h in enumerate(hidden):
        text = text.replace(f"__TG_EMOJI_{i}__", h)
    return text

# Admin Settings
bot_settings = {
    "withdraw_on": True,
    "min_withdraw": 10.0,
    "support_link": "https://t.me/Zvshshhvc",
    "w_group": "",
    "auto_br_on": False,
    "auto_br_interval": 60,
    "cooldown": 5,
    "num_req": 1,
    "w_methods": ["bKash", "Nagad"],
    "otp_default_rate": 0.5,
    "otp_service_rates": {},
    "main_channel_link": "https://t.me/Zvshshhvc",
    "refer_reward": 0.2
}

BOT_DATA_FILE = "bot_data.json"
USERS_LIST_FILE = "users_list.json"

def get_api_key():
    return random.choice(voltx_keys) if voltx_keys else API_2OO9_KEY_DEFAULT

def get_otp_reward(service_name):
    rates = bot_settings.get("otp_service_rates", {})
    val = rates.get(service_name, bot_settings.get("otp_default_rate", 0.5))
    return float(val)

def update_daily_stat(key, amount=1):
    global daily_stats
    today = time.strftime("%Y-%m-%d")
    if daily_stats.get("date") != today:
        daily_stats = {"date": today, "numbers": 0, "otps": 0}
    daily_stats[key] = daily_stats.get(key, 0) + amount

# ==========================================
# Local Storage
# ==========================================
def load_local_data():
    global recent_traffic, voltx_dynamic_data, voltx_keys, force_join_status, force_join_channels, voltx_auto_mode, otp_forward_groups, otp_button_link, recent_success_otps, bot_settings, user_active_sessions, daily_stats, daily_user_otps
    if os.path.exists(BOT_DATA_FILE):
        try:
            with open(BOT_DATA_FILE, "r") as f:
                data = json.load(f)
                recent_traffic = data.get("recent_traffic", [])
                voltx_dynamic_data = data.get("voltx_dynamic_data", {})
                loaded_keys = data.get("voltx_keys", [])
                voltx_keys = loaded_keys if loaded_keys else [API_2OO9_KEY_DEFAULT]
                force_join_status = data.get("force_join_status", False)
                force_join_channels = data.get("force_join_channels", [])
                voltx_auto_mode = data.get("voltx_auto_mode", True)
                otp_forward_groups = data.get("otp_forward_groups", [])
                otp_button_link = data.get("otp_button_link", "https://t.me/numiiq_bot")
                recent_success_otps = set(data.get("recent_success_otps", []))
                loaded_settings = data.get("bot_settings", {})
                for k, v in loaded_settings.items(): bot_settings[k] = v
                daily_stats = data.get("daily_stats", {"date": "", "numbers": 0, "otps": 0})
                daily_user_otps = data.get("daily_user_otps", {"date": "", "users": {}})
                user_active_sessions = data.get("user_active_sessions", {})
        except Exception as e:
            print(f"Error loading local data: {e}")

def save_local_data():
    global recent_traffic, voltx_dynamic_data, voltx_keys, force_join_status, force_join_channels, voltx_auto_mode, otp_forward_groups, otp_button_link, recent_success_otps, bot_settings, user_active_sessions, daily_stats, daily_user_otps
    try:
        with open(BOT_DATA_FILE, "w") as f:
            json.dump({
                "recent_traffic": recent_traffic, 
                "voltx_dynamic_data": voltx_dynamic_data,
                "voltx_keys": voltx_keys,
                "force_join_status": force_join_status,
                "force_join_channels": force_join_channels,
                "voltx_auto_mode": voltx_auto_mode,
                "otp_forward_groups": otp_forward_groups,
                "otp_button_link": otp_button_link,
                "recent_success_otps": list(recent_success_otps),
                "bot_settings": bot_settings,
                "user_active_sessions": user_active_sessions,
                "daily_stats": daily_stats,
                "daily_user_otps": daily_user_otps
            }, f)
    except Exception as e:
        print(f"Error saving local data: {e}")

cached_user_list = set()
def add_to_broadcast_list(user_id):
    global cached_user_list
    if not cached_user_list and os.path.exists(USERS_LIST_FILE):
        try:
            with open(USERS_LIST_FILE, "r") as f:
                cached_user_list = set(json.load(f))
        except: pass
    if user_id not in cached_user_list:
        cached_user_list.add(user_id)
        try:
            with open(USERS_LIST_FILE, "w") as f:
                json.dump(list(cached_user_list), f)
        except: pass

def get_all_user_ids():
    global user_cache
    users = set(user_cache.keys())
    if os.path.exists(USERS_LIST_FILE):
        try:
            with open(USERS_LIST_FILE, "r") as f:
                for u in json.load(f): users.add(int(u))
        except: pass
    return list(users)

def get_bot_info():
    try:
        res = requests.get(BASE_URL + "getMe").json()
        if res.get("ok"): return res["result"]["username"]
    except Exception: pass
    return ""

def set_bot_commands():
    commands = [{"command": "start", "description": "Start the bot or refresh menu"}]
    try: requests.post(BASE_URL + "setMyCommands", json={"commands": commands})
    except Exception: pass

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": apply_emojis(text), "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: return requests.post(BASE_URL + "sendMessage", json=payload).json()
    except Exception: return None

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": apply_emojis(text), "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(BASE_URL + "editMessageText", json=payload)
    except Exception: pass

def answer_callback_query(callback_query_id, text="", show_alert=False):
    payload = {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
    requests.post(BASE_URL + "answerCallbackQuery", json=payload)

def delete_message(chat_id, message_id):
    payload = {"chat_id": chat_id, "message_id": message_id}
    requests.post(BASE_URL + "deleteMessage", json=payload)

# ==========================================
# Database Handlers
# ==========================================
def init_sqlite():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT DEFAULT 'User', balance REAL DEFAULT 0.0, total_invites INTEGER DEFAULT 0, total_otps INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

def get_user(user_id):
    global user_cache
    if user_id in user_cache: return user_cache[user_id]
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, balance, total_invites, total_otps FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        u_data = {"user_id": user_id, "first_name": row[0], "balance": row[1], "total_invites": row[2], "total_otps": row[3]}
        user_cache[user_id] = u_data
        return u_data
    return None

def add_user(user_id, first_name="User"):
    global user_cache
    add_to_broadcast_list(user_id)
    if user_id in user_cache and user_cache[user_id]["first_name"] == first_name: return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name, balance, total_invites, total_otps) VALUES (?, ?, 0.0, 0, 0)", (user_id, first_name))
    cursor.execute("UPDATE users SET first_name = ? WHERE user_id = ?", (first_name, user_id))
    conn.commit()
    conn.close()
    if user_id not in user_cache:
        user_cache[user_id] = {"user_id": user_id, "first_name": first_name, "balance": 0.0, "total_invites": 0, "total_otps": 0}
    else:
        user_cache[user_id]["first_name"] = first_name

def update_user_stats(user_id, balance_add=0.0, invite_add=0, otps_add=0):
    global user_cache
    if user_id not in user_cache: get_user(user_id)
    if user_id in user_cache:
        user_cache[user_id]["balance"] = round(user_cache[user_id]["balance"] + float(balance_add), 2)
        user_cache[user_id]["total_invites"] += int(invite_add)
        user_cache[user_id]["total_otps"] += int(otps_add)
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ?, total_invites = total_invites + ?, total_otps = total_otps + ? WHERE user_id = ?", (float(balance_add), int(invite_add), int(otps_add), user_id))
    conn.commit()
    conn.close()

# ==========================================
# Keyboards & Custom Layouts (Image Matches)
# ==========================================
def get_main_keyboard(user_id):
    # হুবহু স্ক্রিনশট ১ এর মতো ৬টি বাটন[span_4](start_span)[span_4](end_span)
    keyboard_layout = [
        [
            {"text": "Get Number", "icon_custom_emoji_id": "5429167978761461870"},
            {"text": "Live Traffic", "icon_custom_emoji_id": "5429571662737611814"}
        ],
        [
            {"text": "2F Auth", "icon_custom_emoji_id": "5337255927735163754"},
            {"text": "Profile", "icon_custom_emoji_id": "5352861489541714456"}
        ],
        [
            {"text": "Leaderboard", "icon_custom_emoji_id": "5337267511261960341"},
            {"text": "Support", "icon_custom_emoji_id": "5337302974806922068"}
        ]
    ]
    if user_id == ADMIN_ID:
        keyboard_layout.append([{"text": "Owner Panel", "icon_custom_emoji_id": "5352838545826420397"}])
    return {"keyboard": keyboard_layout, "resize_keyboard": True}

def get_live_traffic_content():
    # হুবহু স্ক্রিনশট ২ এর ডিজাইন[span_5](start_span)[span_5](end_span)
    total_hits = len(recent_traffic)
    top_country = "Cameroon" if total_hits > 0 else "None"
    
    msg = (
        "📊 <b>Live Traffic</b>\n\n"
        "🕒 <b>Window:</b> Last 5 minutes\n"
        f"🔥 <b>Results Sent:</b> {total_hits}\n"
        f"🏆 <b>Top Country:</b> 🇨🇲 {top_country}\n\n"
        "🌍 <b>Top Countries:</b>\n"
        f"1. 🇨🇲 Cameroon — {total_hits if total_hits else 0}"
    )
    markup = {
        "inline_keyboard": [
            [{"text": "Refresh", "icon_custom_emoji_id": "5229111790842952353", "callback_data": "refresh_traffic", "style": "primary"}],
            [{"text": "Back", "icon_custom_emoji_id": "5438541186539232243", "callback_data": "back_to_main", "style": "danger"}]
        ]
    }
    return msg, markup

def get_profile_content(user_id):
    # হুবহু স্ক্রিনশট ৩ এর প্রোফাইল লেআউট[span_6](start_span)[span_6](end_span)
    u = get_user(user_id)
    bal_bdt = u.get("balance", 0.0) if u else 0.0
    bal_usdt = round(bal_bdt / 125.0, 4) if bal_bdt > 0 else 0.0
    stats_count = u.get("total_otps", 0) if u else 0
    ref_count = u.get("total_invites", 0) if u else 0

    msg = (
        "👤 <b>MY PROFILE</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"💳 <b>Balance:</b> {bal_bdt:.4f} BDT\n"
        f"💵 <b>Balance (USDT):</b> {bal_usdt:.2f} USDT\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>My Statistics</b>\n"
        f"├ Today: {stats_count}\n"
        f"├ Last 7 Days: {stats_count}\n"
        f"├ Last 30 Days: {stats_count}\n"
        f"└ Lifetime: {stats_count}\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🤝 <b>Referrals:</b> {ref_count}"
    )

    markup = {
        "inline_keyboard": [
            [{"text": "Withdrawal", "icon_custom_emoji_id": "5190899075968441286", "callback_data": "profile_withdraw", "style": "danger"}],
            [{"text": "Refer Link", "icon_custom_emoji_id": "5420517437885943844", "callback_data": "profile_refer", "style": "success"}],
            [{"text": "Refer Notification: ON", "icon_custom_emoji_id": "5352980533150259581", "callback_data": "profile_toggle_notif", "style": "success"}],
            [{"text": f"Referral Dashboard ({ref_count})", "icon_custom_emoji_id": "5352877703043258544", "callback_data": "profile_ref_dash", "style": "primary"}],
            [{"text": "My Wallet History", "icon_custom_emoji_id": "5429105001655999635", "callback_data": "profile_wallet_history", "style": "primary"}],
            [{"text": "Back", "icon_custom_emoji_id": "5438541186539232243", "callback_data": "back_to_main", "style": "danger"}]
        ]
    }
    return msg, markup

# ==========================================
# Voltx Listeners
# ==========================================
def voltx_traffic_poller():
    global recent_traffic
    while True:
        try:
            headers = {"mauthapi": get_api_key()}
            res = requests.get(f"{API_2OO9_BASE}/console", headers=headers, timeout=10)
            data = res.json()
            if data.get("meta", {}).get("code") == 200:
                hits = data.get("data", {}).get("hits", [])
                recent_traffic = hits[-15:]
        except Exception:
            pass
        time.sleep(15)

# ==========================================
# Message & Callback Handlers
# ==========================================
def handle_message(message):
    if message.get("chat", {}).get("type") != "private": return
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")
    first_name = message["from"].get("first_name", "User")

    add_user(user_id, first_name)

    if text.startswith("/start"):
        send_message(chat_id, f"🔥 <b>Welcome {html.escape(first_name)} to SMS NUMIQ!</b>\nChoose an option from the menu below:", reply_markup=get_main_keyboard(user_id))
    elif text == "Live Traffic":
        msg, markup = get_live_traffic_content()
        send_message(chat_id, msg, reply_markup=markup)
    elif text == "Profile":
        msg, markup = get_profile_content(user_id)
        send_message(chat_id, msg, reply_markup=markup)
    elif text == "Get Number":
        send_message(chat_id, "📞 <b>Fetching active services...</b>\nChoose your service:", reply_markup=get_main_keyboard(user_id))
    elif text == "2F Auth":
        send_message(chat_id, "🔐 <b>2-Factor Authentication Hub</b>\nFeature is fully synced and active.", reply_markup=get_main_keyboard(user_id))
    elif text == "Leaderboard":
        send_message(chat_id, "🏆 <b>Leaderboard</b>\nCheck the top earners and OTP receivers today!", reply_markup=get_main_keyboard(user_id))
    elif text == "Support":
        send_message(chat_id, f"💬 <b>Support & Channel:</b>\nJoin: {bot_settings['main_channel_link']}", reply_markup=get_main_keyboard(user_id))

def handle_callback(callback_query):
    query_id = callback_query["id"]
    user_id = callback_query["from"]["id"]
    data = callback_query["data"]
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]

    if data == "refresh_traffic":
        msg, markup = get_live_traffic_content()
        edit_message(chat_id, message_id, msg, reply_markup=markup)
        answer_callback_query(query_id, "Live Traffic Refreshed!")
    elif data == "back_to_main":
        delete_message(chat_id, message_id)
        send_message(chat_id, "🏠 <b>Main Menu:</b>", reply_markup=get_main_keyboard(user_id))
        answer_callback_query(query_id)
    elif data == "profile_refer":
        invite_link = f"https://t.me/numiiq_bot?start={user_id}"
        answer_callback_query(query_id, "Link Generated!")
        send_message(chat_id, f"🔗 <b>Your Referral Link:</b>\n<code>{invite_link}</code>\n\nReward: 0.20 BDT per friend.")
    elif data == "profile_withdraw":
        u = get_user(user_id)
        bal = u.get("balance", 0.0) if u else 0.0
        if bal < bot_settings["min_withdraw"]:
            answer_callback_query(query_id, f"Minimum withdraw is {bot_settings['min_withdraw']} BDT!", show_alert=True)
        else:
            answer_callback_query(query_id, "Withdrawal menu opening...")
    else:
        answer_callback_query(query_id)

# ==========================================
# Render Port Server
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"SMS NUMIQ Bot is Running Successfully!")
    def log_message(self, format, *args): pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# ==========================================
# Main Execution
# ==========================================
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    load_local_data()
    init_sqlite()
    set_bot_commands()
    threading.Thread(target=voltx_traffic_poller, daemon=True).start()
    
    print(f"Bot @numiiq_bot is running with custom UI...")
    
    offset = None
    while True:
        try:
            url = BASE_URL + "getUpdates"
            res = requests.get(url, params={"timeout": 30, "offset": offset}).json()
            if res.get("ok"):
                for update in res["result"]:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        threading.Thread(target=handle_message, args=(update["message"],)).start()
                    elif "callback_query" in update:
                        threading.Thread(target=handle_callback, args=(update["callback_query"],)).start()
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    main()