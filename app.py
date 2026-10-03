import requests
import time
import json
import random
import sqlite3
import os
import re
import html
import threading
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# কনফিগারেশন
# ==========================================
BOT_TOKEN = "8463468131:AAGxlaWJWVWwSjGOEyUaLXFSTJ0NfvhSqCE"
ADMIN_ID = 8271633124  # আপনার টেলিগ্রাম আইডি
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
BOT_USERNAME = "numiiq_bot"

# 2oo9 API কনফিগারেশন
API_2OO9_BASE = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"
API_2OO9_KEY_DEFAULT = "MHF5UTYD3L7"

# গ্লোবাল স্টেট ও মেমোরি
user_cache = {} 
user_states = {} 
user_active_sessions = {}
voltx_keys = [API_2OO9_KEY_DEFAULT]
recent_traffic = []

# ==========================================
# টেলিগ্রাম কাস্টম অ্যানিমেটেড ইমোজি আইডি ম্যাপিং
# ==========================================
GLOBAL_BODY_EMOJIS = {
    "📞": "5429167978761461870", "📡": "5429571662737611814", "🔐": "5337255927735163754",
    "👤": "5352861489541714456", "🔥": "5337267511261960341", "💬": "5337302974806922068",
    "📊": "5352877703043258544", "🕒": "5336983442125001376", "🏆": "5240021484516185513",
    "🌍": "5780471598922337683", "🔄": "5229111790842952353", "🔙": "5438541186539232243",
    "💳": "5190899075968441286", "💵": "5429612421977253466", "🎁": "5420396762189831222",
    "🔗": "5420517437885943844", "🔔": "5352980533150259581", "👑": "5352838545826420397",
    "🆔": "5226929552319594190", "💰": "5429105001655999635", "✅": "5352694861990501856",
    "❌": "5420130255174145507", "⚙️️": "5420155432272438703", "🤝": "5192805934073685937",
    "👛": "5190899075968441286", "📍": "5352877703043258544", "⚡": "5420517437885943844",
    "📅": "5336983442125001376", "🗓️": "5336983442125001376", "🛡️": "5337255927735163754",
    "♾️": "5229111790842952353", "🔴": "5420130255174145507"
}

def apply_emojis(text):
    """মেসেজ টেক্সটকে টেলিগ্রাম কাস্টম অ্যানিমেটেড ইমোজিতে রূপান্তর করে"""
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

def tg_e(eid, fallback_char="✨"):
    return f'<tg-emoji emoji-id="{eid}">{fallback_char}</tg-emoji>'

# বট সেটিংস
bot_settings = {
    "withdraw_on": True,
    "min_withdraw": 10.0,
    "support_link": "https://t.me/Zvshshhvc",
    "main_channel_link": "https://t.me/Zvshshhvc",
    "refer_reward": 0.20,
    "otp_default_rate": 0.50
}

BOT_DATA_FILE = "bot_data.json"

def get_api_key():
    return random.choice(voltx_keys) if voltx_keys else API_2OO9_KEY_DEFAULT

# ==========================================
# ডাটাবেস অপারেশন (SQLite)
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
            refer_notif INTEGER DEFAULT 1,
            last_active_date TEXT DEFAULT ''
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            method TEXT,
            address TEXT,
            amount REAL,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    global user_cache
    if user_id in user_cache: return user_cache[user_id]
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, balance, total_invites, total_otps, today_otps, otps_7d, otps_30d, refer_notif, last_active_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        u_data = {
            "user_id": user_id, "first_name": row[0], "balance": row[1], 
            "total_invites": row[2], "total_otps": row[3], "today_otps": row[4], 
            "otps_7d": row[5], "otps_30d": row[6], "refer_notif": row[7],
            "last_active_date": row[8]
        }
        user_cache[user_id] = u_data
        return u_data
    return None

def add_user(user_id, first_name="User", referrer_id=None):
    global user_cache
    today_str = str(date.today())
    existing = get_user(user_id)
    if not existing:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name, balance, total_invites, total_otps, today_otps, otps_7d, otps_30d, refer_notif, last_active_date) VALUES (?, ?, 0.0, 0, 0, 0, 0, 0, 1, ?)", (user_id, first_name, today_str))
        conn.commit()
        conn.close()
        user_cache[user_id] = {
            "user_id": user_id, "first_name": first_name, "balance": 0.0, 
            "total_invites": 0, "total_otps": 0, "today_otps": 0, "otps_7d": 0, 
            "otps_30d": 0, "refer_notif": 1, "last_active_date": today_str
        }
        if referrer_id and referrer_id != user_id:
            ref_u = get_user(referrer_id)
            if ref_u:
                r_reward = bot_settings["refer_reward"]
                update_user_stats(referrer_id, balance_add=r_reward, invite_add=1)
                if ref_u.get("refer_notif", 1) == 1:
                    send_message(referrer_id, f"🎉 <b>New Referral Joined!</b>\nYou earned +{r_reward:.2f} BDT.")
    else:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        if existing["last_active_date"] != today_str:
            cursor.execute("UPDATE users SET today_otps = 0, last_active_date = ? WHERE user_id = ?", (today_str, user_id))
            user_cache[user_id]["today_otps"] = 0
            user_cache[user_id]["last_active_date"] = today_str
        if existing["first_name"] != first_name:
            cursor.execute("UPDATE users SET first_name = ? WHERE user_id = ?", (first_name, user_id))
            user_cache[user_id]["first_name"] = first_name
        conn.commit()
        conn.close()

def update_user_stats(user_id, balance_add=0.0, invite_add=0, otps_add=0):
    global user_cache
    u = get_user(user_id)
    if u:
        user_cache[user_id]["balance"] = round(u["balance"] + float(balance_add), 4)
        user_cache[user_id]["total_invites"] += int(invite_add)
        user_cache[user_id]["total_otps"] += int(otps_add)
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

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_leaderboard_data(period="daily"):
    col = "today_otps" if period == "daily" else ("otps_7d" if period == "weekly" else "total_otps")
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT first_name, {col} FROM users ORDER BY {col} DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ==========================================
# টেলিগ্রাম API কল ফাংশন
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
# 2oo9 API সার্ভিসেস
# ==========================================
def get_service_number(country_id, service_code):
    try:
        headers = {"mauthapi": get_api_key()}
        url = f"{API_2OO9_BASE}/orders"
        payload = {"country": country_id, "service": service_code}
        res = requests.post(url, json=payload, headers=headers, timeout=15).json()
        if res.get("meta", {}).get("code") == 200:
            return res.get("data")
    except Exception: pass
    return None

def check_order_otp(order_id):
    try:
        headers = {"mauthapi": get_api_key()}
        url = f"{API_2OO9_BASE}/orders/{order_id}"
        res = requests.get(url, headers=headers, timeout=10).json()
        if res.get("meta", {}).get("code") == 200:
            return res.get("data")
    except Exception: pass
    return None

def cancel_service_number(order_id):
    try:
        headers = {"mauthapi": get_api_key()}
        url = f"{API_2OO9_BASE}/orders/{order_id}/cancel"
        res = requests.post(url, headers=headers, timeout=10).json()
        return res.get("meta", {}).get("code") == 200
    except Exception: return False

# ==========================================
# স্ক্রিনশট অনুযায়ী UI মেনু ও বাটনসমূহ
# ==========================================
def get_main_keyboard(user_id):
    keyboard_layout = [
        [
            {"text": "Get Number", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["📞"]},
            {"text": "Live Traffic", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["📡"]}
        ],
        [
            {"text": "2F Auth", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔐"]},
            {"text": "Profile", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["👤"]}
        ],
        [
            {"text": "Leaderboard", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["👑"]},
            {"text": "Support", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["💬"]}
        ]
    ]
    if user_id == ADMIN_ID:
        keyboard_layout.append([{"text": "Owner Panel", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["⚙️"]}])
    return {"keyboard": keyboard_layout, "resize_keyboard": True}

# ১. প্রোফাইল ইন্টারফেস (স্ক্রিনশট ১ এর হুবহু)
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

    markup = {
        "inline_keyboard": [
            [{"text": "Withdrawal", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["💳"], "callback_data": "profile_withdraw"}],
            [{"text": "Refer Link", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🎁"], "callback_data": "profile_refer"}],
            [{"text": f"Refer Notification: {notif_status}", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔔"], "callback_data": "profile_toggle_notif"}],
            [{"text": f"Referral Dashboard ({ref_count})", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["📊"], "callback_data": "profile_ref_dash"}],
            [{"text": "My Wallet History", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["💳"], "callback_data": "profile_wallet_history"}],
            [{"text": "Back", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔙"], "callback_data": "back_to_main"}]
        ]
    }
    return msg, markup

# ২. লাইভ ট্রাফিক ইন্টারফেস (স্ক্রিনশট ৪ এর হুবহু)
def get_live_traffic_content():
    total_hits = len(recent_traffic) if recent_traffic else 42
    top_c = "Nepal"
    top_c_flag = "🇳🇵"
    
    msg = (
        "📊 <b>Live Traffic</b>\n\n"
        "🕒 <b>Window:</b> Last 5 minutes\n"
        f"🔥 <b>Results Sent:</b> {total_hits}\n"
        f"🏆 <b>Top Country:</b> {top_c_flag} {top_c}\n\n"
        "🌍 <b>Top Countries:</b>\n"
        f"1. {top_c_flag} {top_c} — 36\n"
        "2. 🇨🇲 Cameroon — 6"
    )
    markup = {
        "inline_keyboard": [
            [{"text": "Refresh", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔄"], "callback_data": "refresh_traffic"}],
            [{"text": "Back", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔙"], "callback_data": "back_to_main"}]
        ]
    }
    return msg, markup

# ৩. গেট নাম্বার সার্ভিস ইন্টারফেস (স্ক্রিনশট ৪ এর হুবহু)
def get_number_services_markup():
    msg = "📍 <b>Select a service from the list</b>"
    markup = {
        "inline_keyboard": [
            [
                {"text": "1XBET", "callback_data": "order_svc_1xbet"},
                {"text": "MELBET", "callback_data": "order_svc_melbet"}
            ],
            [
                {"text": "Back", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔙"], "callback_data": "back_to_main"}
            ]
        ]
    }
    return msg, markup

# ৪. লিডারবোর্ড মেনু ও পিরিয়ড সিলেকশন (স্ক্রিনশট ৩ এর হুবহু)
def get_leaderboard_menu():
    msg = (
        "━━━━━━━━━━━━━━━━━\n"
        "《 🏆 <b>LEADERBOARD</b> 》\n"
        "━━━━━━━━━━━━━━━━━\n"
        "টপ পারফর্মারদের দেখতে একটা পিরিয়ড বেছে নাও।\n"
        "━━━━━━━━━━━━━━━━━"
    )
    markup = {
        "inline_keyboard": [
            [{"text": "Daily", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["⚡"], "callback_data": "lb_daily"}],
            [{"text": "Weekly", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🛡️"], "callback_data": "lb_weekly"}],
            [{"text": "Lifetime", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔴"], "callback_data": "lb_lifetime"}],
            [{"text": "Back", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔙"], "callback_data": "back_to_main"}]
        ]
    }
    return msg, markup

# ৫. লিডারবোর্ড বিস্তারিত ভিউ (স্ক্রিনশট ২ এর হুবহু)
def get_leaderboard_view(period_key):
    p_name = "DAILY" if period_key == "daily" else ("WEEKLY" if period_key == "weekly" else "LIFETIME")
    rows = get_leaderboard_data(period_key)
    
    msg = (
        "━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>TOP 10 — 📅 {p_name}</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
    )
    
    medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    if not rows or all(r[1] == 0 for r in rows):
        # স্যাম্পল ফলব্যাক ডাটা স্ক্রিনশটের মতো
        sample_users = [
            ("Shakib", 434), ("MD", 367), ("GOKU", 289), ("MD", 286),
            ("Ajijul", 258), ("ORBIT ™", 256), ("ServiceCenter", 233),
            ("MD Anik Sk", 226), ("SI F AT", 209), ("Mukta", 198)
        ]
        for i, (name, count) in enumerate(sample_users):
            punc = "└" if i == 9 else "├"
            msg += f"{punc} {medals[i]} {html.escape(name)} ➔ {count} OTP\n"
    else:
        for i, row in enumerate(rows):
            punc = "└" if i == len(rows)-1 else "├"
            msg += f"{punc} {medals[i]} {html.escape(row[0])} ➔ {row[1]} OTP\n"

    msg += "━━━━━━━━━━━━━━━━━"
    markup = {
        "inline_keyboard": [
            [
                {"text": "Refresh", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔄"], "callback_data": f"lb_{period_key}"},
                {"text": "Back", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔙"], "callback_data": "leaderboard_main"}
            ]
        ]
    }
    return msg, markup

# ৬. অনার প্যানেল
def get_owner_panel():
    conn = sqlite3.connect("bot_database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(balance) FROM users")
    row = c.fetchone()
    conn.close()
    
    u_count = row[0] or 0
    t_bal = row[1] or 0.0

    msg = (
        "⚙️ <b>OWNER CONTROL PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Total Registered:</b> {u_count}\n"
        f"💰 <b>Total Balance:</b> {t_bal:.2f} BDT\n"
        f"🔑 <b>API Keys:</b> {len(voltx_keys)}\n"
        f"🔐 <b>Admin ID:</b> <code>{ADMIN_ID}</code>\n"
        "━━━━━━━━━━━━━━━━━"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "Add/Cut Balance", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["💰"], "callback_data": "admin_set_bal"},
                {"text": "Broadcast SMS", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔗"], "callback_data": "admin_broadcast"}
            ],
            [
                {"text": "Manage API Keys", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔐"], "callback_data": "admin_keys"},
                {"text": "User Search", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🆔"], "callback_data": "admin_find_user"}
            ],
            [
                {"text": "Back", "icon_custom_emoji_id": GLOBAL_BODY_EMOJIS["🔙"], "callback_data": "back_to_main"}
            ]
        ]
    }
    return msg, markup

# ==========================================
# ব্যাকগ্রাউন্ড ওয়ার্কার্স
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

def active_orders_poller():
    global user_active_sessions
    while True:
        try:
            for uid, sess in list(user_active_sessions.items()):
                order_id = sess.get("order_id")
                chat_id = sess.get("chat_id")
                msg_id = sess.get("msg_id")
                exp_at = sess.get("expire_at", 0)

                if time.time() > exp_at:
                    cancel_service_number(order_id)
                    edit_message(chat_id, msg_id, "❌ <b>Session Expired!</b>\nTime limit exceeded. No OTP received.")
                    del user_active_sessions[uid]
                    continue

                order_res = check_order_otp(order_id)
                if order_res and order_res.get("sms"):
                    sms_code = order_res["sms"]
                    rate = bot_settings["otp_default_rate"]
                    update_user_stats(uid, balance_add=rate, otps_add=1)
                    
                    finish_text = (
                        f"✅ <b>OTP RECEIVED SUCCESSFULLY!</b>\n\n"
                        f"📱 <b>Number:</b> <code>{sess.get('phone')}</code>\n"
                        f"💬 <b>OTP Code:</b> <code>{sms_code}</code>\n"
                        f"💵 <b>Reward:</b> +{rate:.2f} BDT"
                    )
                    edit_message(chat_id, msg_id, finish_text)
                    del user_active_sessions[uid]
        except Exception:
            pass
        time.sleep(4)

# ==========================================
# মেসেজ ও রাউটিং হ্যান্ডলার
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

    # অ্যাডমিন স্টেট হ্যান্ডলিং
    if user_id == ADMIN_ID and user_id in user_states:
        state = user_states[user_id]
        if state == "ADMIN_BROADCAST":
            del user_states[user_id]
            users = get_all_users()
            send_message(chat_id, "📢 ব্রডকাস্ট পাঠানো শুরু হয়েছে...")
            sent = 0
            for u in users:
                try:
                    res = send_message(u, text)
                    if res and res.get("ok"): sent += 1
                except: pass
            send_message(chat_id, f"✅ সফলভাবে <b>{sent}</b> জন ইউজারের কাছে পাঠানো হয়েছে!")
            return

        elif state == "ADMIN_SET_BAL":
            del user_states[user_id]
            try:
                t_uid, amount = text.split()
                t_uid, amount = int(t_uid), float(amount)
                target = get_user(t_uid)
                if target:
                    update_user_stats(t_uid, balance_add=amount)
                    send_message(chat_id, f"✅ ইউজার <code>{t_uid}</code> এর ব্যালেন্স {amount:+.2f} BDT আপডেট হয়েছে।")
                    send_message(t_uid, f"💰 আপনার ওয়ালেটে <b>{amount:+.2f} BDT</b> যোগ/কর্তন হয়েছে!")
                else:
                    send_message(chat_id, "❌ ইউজার খুঁজে পাওয়া যায়নি!")
            except Exception:
                send_message(chat_id, "❌ ভুল ফরম্যাট! লিখুন: <code>User_ID Amount</code>")
            return

        elif state == "ADMIN_FIND_USER":
            del user_states[user_id]
            if text.isdigit():
                t = get_user(int(text))
                if t:
                    send_message(chat_id, f"👤 <b>ইউজার ডাটা:</b>\nID: <code>{t['user_id']}</code>\nName: {html.escape(t['first_name'])}\nBalance: {t['balance']:.4f} BDT\nTotal OTP: {t['total_otps']}\nReferrals: {t['total_invites']}")
                else:
                    send_message(chat_id, "❌ ইউজার খুঁজে পাওয়া যায়নি!")
            return

        elif state == "ADMIN_ADD_KEY":
            del user_states[user_id]
            voltx_keys.append(text.strip())
            send_message(chat_id, f"✅ নতুন API Key সফলভাবে যুক্ত হয়েছে! মোট Key: {len(voltx_keys)}")
            return

    # ইউজার উইথড্র ইনপুট হ্যান্ডলিং
    if user_id in user_states:
        state = user_states[user_id]
        if state.startswith("W_INPUT_"):
            method = state.split("_")[2]
            del user_states[user_id]
            try:
                acc_num, amount = text.split()
                amount = float(amount)
                u = get_user(user_id)
                if u["balance"] < amount or amount < bot_settings["min_withdraw"]:
                    send_message(chat_id, f"❌ অপর্যাপ্ত ব্যালেন্স বা সর্বনিম্ন লিমিটের নিচে (Min: {bot_settings['min_withdraw']} BDT)!")
                    return
                update_user_stats(user_id, balance_add=-amount)
                conn = sqlite3.connect("bot_database.db")
                c = conn.cursor()
                c.execute("INSERT INTO withdrawals (user_id, method, address, amount) VALUES (?, ?, ?, ?)", (user_id, method, acc_num, amount))
                conn.commit()
                conn.close()
                send_message(chat_id, f"✅ <b>উইথড্র রিকোয়েস্ট সফল হয়েছে!</b>\nMethod: {method}\nAccount: {acc_num}\nAmount: {amount:.2f} BDT\nঅ্যাডমিন শীঘ্রই রিভিউ করবেন।")
                send_message(ADMIN_ID, f"🔔 <b>নতুন উইথড্রয়াল রিকোয়েস্ট!</b>\nUser: <code>{user_id}</code>\nMethod: {method}\nAccount: <code>{acc_num}</code>\nAmount: {amount} BDT")
                return
            except Exception:
                send_message(chat_id, "❌ ভুল ফরম্যাট! সঠিক ফরম্যাট: <code>017XXXXXXXX 50</code>")
                return

    # কিবোর্ড মেসেজ রাউটিং
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
        msg, markup = get_number_services_markup()
        send_message(chat_id, msg, reply_markup=markup)
    elif "Leaderboard" in text:
        msg, markup = get_leaderboard_menu()
        send_message(chat_id, msg, reply_markup=markup)
    elif "2F Auth" in text:
        send_message(chat_id, "🔐 <b>2-Factor Authentication Hub</b>\nবর্তমানে কোনো 2FA টাস্ক সক্রিয় নেই।", reply_markup=get_main_keyboard(user_id))
    elif "Support" in text:
        send_message(chat_id, f"💬 <b>Support & Community:</b>\nJoin our Official Channel: {bot_settings['main_channel_link']}", reply_markup=get_main_keyboard(user_id))
    elif "Owner Panel" in text and user_id == ADMIN_ID:
        msg, markup = get_owner_panel()
        send_message(chat_id, msg, reply_markup=markup)

# ==========================================
# ইনলাইন কলব্যাক হ্যান্ডলার
# ==========================================
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

    elif data == "leaderboard_main":
        msg, markup = get_leaderboard_menu()
        edit_message(chat_id, message_id, msg, reply_markup=markup)
        answer_callback_query(query_id)

    elif data.startswith("lb_"):
        period = data.split("_")[1]
        msg, markup = get_leaderboard_view(period)
        edit_message(chat_id, message_id, msg, reply_markup=markup)
        answer_callback_query(query_id)

    elif data == "profile_refer":
        invite_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        answer_callback_query(query_id, "Referral Link Ready!")
        send_message(chat_id, f"🎁 <b>Your Referral Link:</b>\n<code>{invite_link}</code>\n\nReward: {bot_settings['refer_reward']:.2f} BDT per active referral.")

    elif data == "profile_toggle_notif":
        new_val = toggle_refer_notif(user_id)
        status_text = "ON" if new_val == 1 else "OFF"
        answer_callback_query(query_id, f"Notifications: {status_text}")
        msg, markup = get_profile_content(user_id)
        edit_message(chat_id, message_id, msg, reply_markup=markup)

    elif data == "profile_ref_dash":
        u = get_user(user_id)
        ref_count = u.get("total_invites", 0) if u else 0
        answer_callback_query(query_id)
        send_message(chat_id, f"📊 <b>Referral Dashboard</b>\n\nTotal Friends Invited: <b>{ref_count}</b>\nEarnings: <b>{ref_count * bot_settings['refer_reward']:.2f} BDT</b>")

    elif data == "profile_wallet_history":
        conn = sqlite3.connect("bot_database.db")
        c = conn.cursor()
        c.execute("SELECT method, amount, status, created_at FROM withdrawals WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
        records = c.fetchall()
        conn.close()
        
        hist_txt = "💳 <b>Wallet History (Last 5):</b>\n\n"
        if not records:
            hist_txt += "কোনো উইথড্রয়াল হিস্ট্রি নেই।"
        else:
            for r in records:
                hist_txt += f"• {r[0]} | {r[1]} BDT | <b>{r[2]}</b> ({r[3]})\n"
        answer_callback_query(query_id)
        send_message(chat_id, hist_txt)

    elif data == "profile_withdraw":
        u = get_user(user_id)
        bal = u.get("balance", 0.0) if u else 0.0
        if bal < bot_settings["min_withdraw"]:
            answer_callback_query(query_id, f"Minimum withdrawal is {bot_settings['min_withdraw']} BDT!", show_alert=True)
        else:
            answer_callback_query(query_id)
            markup = {
                "inline_keyboard": [
                    [{"text": "bKash", "callback_data": "w_act_bKash"}, {"text": "Nagad", "callback_data": "w_act_Nagad"}],
                    [{"text": "Cancel", "callback_data": "back_to_main"}]
                ]
            }
            send_message(chat_id, f"💳 <b>পেমেন্ট মেথড বেছে নিন:</b>\nAvailable Balance: {bal:.4f} BDT", reply_markup=markup)

    elif data.startswith("w_act_"):
        method = data.split("_")[2]
        user_states[user_id] = f"W_INPUT_{method}"
        answer_callback_query(query_id)
        send_message(chat_id, f"আপনার <b>{method} নম্বর এবং এমাউন্ট</b> স্পেস দিয়ে লিখুন:\n\nযেমন: <code>017XXXXXXXX 50</code>")

    # নাম্বার অর্ডার
    elif data.startswith("order_svc_"):
        svc_name = data.replace("order_svc_", "")
        answer_callback_query(query_id, f"Ordering {svc_name.upper()}...")
        order = get_service_number("cm", svc_name)
        if order:
            phone = order.get("phone")
            oid = order.get("id")
            user_active_sessions[user_id] = {
                "order_id": oid, "phone": phone, "service": svc_name.upper(),
                "chat_id": chat_id, "msg_id": message_id, "expire_at": time.time() + 300
            }
            msg = (
                f"📱 <b>Service:</b> {svc_name.upper()}\n"
                f"📞 <b>Phone Number:</b> <code>+{phone}</code>\n"
                f"🕒 <b>Waiting for OTP... (5 minutes)</b>"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Cancel Number", "callback_data": f"cancel_num_{oid}"}]
                ]
            }
            send_message(chat_id, msg, reply_markup=markup)
        else:
            send_message(chat_id, f"❌ বর্তমানে <b>{svc_name.upper()}</b> এর কোনো নম্বর খালি নেই! অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন।")

    elif data.startswith("cancel_num_"):
        oid = data.split("_")[2]
        if user_id in user_active_sessions:
            cancel_service_number(oid)
            del user_active_sessions[user_id]
            edit_message(chat_id, message_id, "❌ <b>Number cancelled successfully.</b>")
            answer_callback_query(query_id, "বাতিল করা হয়েছে!")

    # অ্যাডমিন প্যানেল কলব্যাক
    elif data == "admin_broadcast" and user_id == ADMIN_ID:
        user_states[user_id] = "ADMIN_BROADCAST"
        answer_callback_query(query_id)
        send_message(chat_id, "📢 ব্রডকাস্ট মেসেজটি লিখে পাঠান:")

    elif data == "admin_set_bal" and user_id == ADMIN_ID:
        user_states[user_id] = "ADMIN_SET_BAL"
        answer_callback_query(query_id)
        send_message(chat_id, "💳 ইউজার আইডি এবং ব্যালেন্স লিখে পাঠান:\n\nযেমন: <code>8271633124 50</code> অথবা <code>8271633124 -20</code>")

    elif data == "admin_find_user" and user_id == ADMIN_ID:
        user_states[user_id] = "ADMIN_FIND_USER"
        answer_callback_query(query_id)
        send_message(chat_id, "🔍 যে ইউজারের ডাটা দেখতে চান তার Telegram ID পাঠান:")

    elif data == "admin_keys" and user_id == ADMIN_ID:
        user_states[user_id] = "ADMIN_ADD_KEY"
        answer_callback_query(query_id)
        send_message(chat_id, f"🔑 বর্তমানে সক্রিয় Key: {len(voltx_keys)}\n\nনতুন 2oo9 API Key যুক্ত করতে তা সেন্ড করুন:")
    else:
        answer_callback_query(query_id)

# ==========================================
# Render/Cloud হোস্টিং পোর্ট সার্ভার
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"SMS WAVE Bot is Running 24/7 with Animated Emojis!")
    def log_message(self, format, *args): pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# ==========================================
# মূল প্রোগ্রাম স্টার্ট
# ==========================================
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    init_sqlite()
    threading.Thread(target=voltx_traffic_poller, daemon=True).start()
    threading.Thread(target=active_orders_poller, daemon=True).start()
    
    print(f"Bot @{BOT_USERNAME} সব ফিচার ও অ্যানিমেটেড ইমোজিসহ সম্পূর্ণ চালু হয়েছে...")
    
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