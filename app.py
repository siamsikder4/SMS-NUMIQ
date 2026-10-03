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

# ==========================================
# Configuration
# ==========================================
BOT_TOKEN = "8463468131:AAGxlaWJWVWwSjGOEyUaLXFSTJ0NfvhSqCE"
ADMIN_ID = 8271633124
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
BOT_USERNAME = "numiiq_bot"

# 2oo9 API Configuration
API_2OO9_BASE = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"
API_2OO9_KEY_DEFAULT = "MHF5UTYD3L7"

# Global states
user_cache = {} 
user_states = {}
voltx_keys = [API_2OO9_KEY_DEFAULT]
recent_traffic = []

# ==========================================
# Custom Animated Emojis Mapping
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
    "👛": "5190899075968441286"
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

# Bot Settings
bot_settings = {
    "withdraw_on": True,
    "min_withdraw": 10.0,
    "support_link": "https://t.me/Zvshshhvc",
    "main_channel_link": "https://t.me/Zvshshhvc",
    "refer_reward": 0.20
}

BOT_DATA_FILE = "bot_data.json"
USERS_LIST_FILE = "users_list.json"

def get_api_key():
    return random.choice(voltx_keys) if voltx_keys else API_2OO9_KEY_DEFAULT

# ==========================================
# Local Storage & Database (SQLite)
# ==========================================
def init_sqlite():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            first_name TEXT DEFAULT 'User', 
            balance REAL DEFAULT 0.0, 
            total_invites INTEGER DEFAULT 0, 
            total_otps INTEGER DEFAULT 0,
            today_otps INTEGER DEFAULT 0,
            otps_7d INTEGER DEFAULT 0,
            otps_30d INTEGER DEFAULT 0,
            refer_notif INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    global user_cache
    if user_id in user_cache:
        return user_cache[user_id]
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, balance, total_invites, total_otps, today_otps, otps_7d, otps_30d, refer_notif FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        u_data = {
            "user_id": user_id, 
            "first_name": row[0], 
            "balance": row[1], 
            "total_invites": row[2], 
            "total_otps": row[3],
            "today_otps": row[4],
            "otps_7d": row[5],
            "otps_30d": row[6],
            "refer_notif": row[7]
        }
        user_cache[user_id] = u_data
        return u_data
    return None

def add_user(user_id, first_name="User", referrer_id=None):
    global user_cache
    existing = get_user(user_id)
    if not existing:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name, balance, total_invites, total_otps, today_otps, otps_7d, otps_30d, refer_notif) VALUES (?, ?, 0.0, 0, 0, 0, 0, 0, 1)", (user_id, first_name))
        conn.commit()
        conn.close()
        user_cache[user_id] = {
            "user_id": user_id, "first_name": first_name, "balance": 0.0, 
            "total_invites": 0, "total_otps": 0, "today_otps": 0, "otps_7d": 0, 
            "otps_30d": 0, "refer_notif": 1
        }
        
        # Handle Referral Award
        if referrer_id and referrer_id != user_id:
            ref_user = get_user(referrer_id)
            if ref_user:
                reward = bot_settings["refer_reward"]
                update_user_stats(referrer_id, balance_add=reward, invite_add=1)
                if ref_user.get("refer_notif", 1) == 1:
                    send_message(referrer_id, f"🎉 <b>New Referral Joined!</b>\nYou earned +{reward:.2f} BDT from {html.escape(first_name)}.")
    else:
        if existing["first_name"] != first_name:
            conn = sqlite3.connect("bot_database.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET first_name = ? WHERE user_id = ?", (first_name, user_id))
            conn.commit()
            conn.close()
            user_cache[user_id]["first_name"] = first_name

def update_user_stats(user_id, balance_add=0.0, invite_add=0, otps_add=0):
    global user_cache
    u = get_user(user_id)
    if u:
        new_bal = round(u["balance"] + float(balance_add), 4)
        new_inv = u["total_invites"] + int(invite_add)
        new_otps = u["total_otps"] + int(otps_add)
        user_cache[user_id]["balance"] = new_bal
        user_cache[user_id]["total_invites"] = new_inv
        user_cache[user_id]["total_otps"] = new_otps
        user_cache[user_id]["today_otps"] += int(otps_add)
        user_cache[user_id]["otps_7d"] += int(otps_add)
        user_cache[user_id]["otps_30d"] += int(otps_add)
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET 
                balance = balance + ?, 
                total_invites = total_invites + ?, 
                total_otps = total_otps + ?,
                today_otps = today_otps + ?,
                otps_7d = otps_7d + ?,
                otps_30d = otps_30d + ?
            WHERE user_id = ?
        """, (float(balance_add), int(invite_add), int(otps_add), int(otps_add), int(otps_add), int(otps_add), user_id))
        conn.commit()
        conn.close()

def toggle_refer_notif(user_id):
    global user_cache
    u = get_user(user_id)
    current = u.get("refer_notif", 1) if u else 1
    new_val = 0 if current == 1 else 1
    if u: user_cache[user_id]["refer_notif"] = new_val
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET refer_notif = ? WHERE user_id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    return new_val

# ==========================================
# Telegram API Call Helpers
# ==========================================
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
# UI Layouts
# ==========================================
def get_main_keyboard(user_id):
    keyboard_layout = [
        [
            {"text": "📞 Get Number"},
            {"text": "📡 Live Traffic"}
        ],
        [
            {"text": "🔐 2F Auth"},
            {"text": "👤 Profile"}
        ],
        [
            {"text": "👑 Leaderboard"},
            {"text": "💬 Support"}
        ]
    ]
    if user_id == ADMIN_ID:
        keyboard_layout.append([{"text": "⚙️ Owner Panel"}])
    return {"keyboard": keyboard_layout, "resize_keyboard": True}

def get_profile_content(user_id):
    u = get_user(user_id)
    bal_bdt = u.get("balance", 0.0) if u else 0.0
    bal_usdt = round(bal_bdt / 125.0, 2) if bal_bdt > 0 else 0.0
    today_otps = u.get("today_otps", 0) if u else 0
    otps_7d = u.get("otps_7d", 0) if u else 0
    otps_30d = u.get("otps_30d", 0) if u else 0
    total_otps = u.get("total_otps", 0) if u else 0
    ref_count = u.get("total_invites", 0) if u else 0
    notif_status = "ON" if (u and u.get("refer_notif", 1) == 1) else "OFF"

    # হুবহু স্ক্রিনশট ৩ এর মেসেজ টেক্সট ফরম্যাট[span_2](start_span)[span_2](end_span)
    msg = (
        "👤 <b>MY PROFILE</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"👛 <b>Balance:</b> {bal_bdt:.4f} BDT\n"
        f"💵 <b>Balance (USDT):</b> {bal_usdt:.2f} USDT\n"
        "━━━━━━━━━━━━━━━━━\n"
        "👑 <b>My Statistics</b>\n"
        f"├ Today: {today_otps}\n"
        f"├ Last 7 Days: {otps_7d}\n"
        f"├ Last 30 Days: {otps_30d}\n"
        f"└ Lifetime: {total_otps}\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🤝 <b>Referrals:</b> {ref_count}"
    )

    # হুবহু স্ক্রিনশটের বাটন লেআউট ও কালার স্কিম[span_3](start_span)[span_3](end_span)
    markup = {
        "inline_keyboard": [
            [{"text": "💳 Withdrawal", "callback_data": "profile_withdraw"}],
            [{"text": "🎁 Refer Link", "callback_data": "profile_refer"}],
            [{"text": f"🔔 Refer Notification: {notif_status}", "callback_data": "profile_toggle_notif"}],
            [{"text": f"📊 Referral Dashboard ({ref_count})", "callback_data": "profile_ref_dash"}],
            [{"text": "💳 My Wallet History", "callback_data": "profile_wallet_history"}],
            [{"text": "🔙 Back", "callback_data": "back_to_main"}]
        ]
    }
    return msg, markup

def get_live_traffic_content():
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
            [{"text": "🔄 Refresh", "callback_data": "refresh_traffic"}],
            [{"text": "🔙 Back", "callback_data": "back_to_main"}]
        ]
    }
    return msg, markup

# ==========================================
# Background Tasks
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
# Bot Message & Event Routing
# ==========================================
def handle_message(message):
    if message.get("chat", {}).get("type") != "private": return
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")
    first_name = message["from"].get("first_name", "User")

    referrer_id = None
    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1 and parts[1].isdigit():
            referrer_id = int(parts[1])

    add_user(user_id, first_name, referrer_id)

    if text.startswith("/start"):
        send_message(
            chat_id, 
            f"🔥 <b>Welcome {html.escape(first_name)} to SMS WAVE!</b>\nChoose an option from the menu below:", 
            reply_markup=get_main_keyboard(user_id)
        )
    elif "Live Traffic" in text:
        msg, markup = get_live_traffic_content()
        send_message(chat_id, msg, reply_markup=markup)
    elif "Profile" in text:
        msg, markup = get_profile_content(user_id)
        send_message(chat_id, msg, reply_markup=markup)
    elif "Get Number" in text:
        send_message(chat_id, "📞 <b>Service Selection:</b>\nActive numbers ready to receive SMS.", reply_markup=get_main_keyboard(user_id))
    elif "2F Auth" in text:
        send_message(chat_id, "🔐 <b>2-Factor Authentication Hub</b>\nNo 2FA tasks pending.", reply_markup=get_main_keyboard(user_id))
    elif "Leaderboard" in text:
        send_message(chat_id, "👑 <b>Top Earners & Receivers Today:</b>\n1. User 827163... (158 OTPs)\n2. User 592817... (112 OTPs)", reply_markup=get_main_keyboard(user_id))
    elif "Support" in text:
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
        answer_callback_query(query_id, "Traffic Refreshed!")
        
    elif data == "back_to_main":
        delete_message(chat_id, message_id)
        send_message(chat_id, "🏠 <b>Main Menu:</b>", reply_markup=get_main_keyboard(user_id))
        answer_callback_query(query_id)
        
    elif data == "profile_refer":
        invite_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        answer_callback_query(query_id, "Referral Link Generated!")
        send_message(chat_id, f"🔗 <b>Your Referral Link:</b>\n<code>{invite_link}</code>\n\n🎁 <b>Reward:</b> {bot_settings['refer_reward']:.2f} BDT per active referral.")
        
    elif data == "profile_toggle_notif":
        new_val = toggle_refer_notif(user_id)
        status_text = "ON" if new_val == 1 else "OFF"
        answer_callback_query(query_id, f"Notifications turned {status_text}!")
        msg, markup = get_profile_content(user_id)
        edit_message(chat_id, message_id, msg, reply_markup=markup)
        
    elif data == "profile_ref_dash":
        u = get_user(user_id)
        ref_count = u.get("total_invites", 0) if u else 0
        answer_callback_query(query_id)
        send_message(chat_id, f"📊 <b>Referral Dashboard</b>\n\nTotal Friends Invited: <b>{ref_count}</b>\nEarnings from Referrals: <b>{ref_count * bot_settings['refer_reward']:.2f} BDT</b>")
        
    elif data == "profile_wallet_history":
        answer_callback_query(query_id)
        send_message(chat_id, "💳 <b>Wallet History</b>\n\nNo recent withdrawal transactions found.")
        
    elif data == "profile_withdraw":
        u = get_user(user_id)
        bal = u.get("balance", 0.0) if u else 0.0
        if bal < bot_settings["min_withdraw"]:
            answer_callback_query(query_id, f"Minimum withdrawal is {bot_settings['min_withdraw']} BDT!", show_alert=True)
        else:
            answer_callback_query(query_id)
            send_message(chat_id, f"💳 <b>Withdrawal Request</b>\n\nAvailable Balance: {bal:.4f} BDT\nPlease select a payment method: bKash / Nagad")
            
    else:
        answer_callback_query(query_id)

# ==========================================
# Webhook/Port Server for Hosting
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is Running Successfully!")
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
    init_sqlite()
    threading.Thread(target=voltx_traffic_poller, daemon=True).start()
    
    print(f"Bot @{BOT_USERNAME} running perfectly...")
    
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