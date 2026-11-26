import os
import time
import sqlite3
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================= SOZLAMALAR =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SIZNING_BOT_TOKENINGIZ")
ADMIN_PAROL = os.environ.get("ADMIN_PAROL", "kimyo2026")
ADMIN_LICHKA = "@onlyibrohimov"
KARTA_RAQAM = "9860 3501 4209 7954"
KARTA_EGASI = "Azizbek Ibrohimov"

RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://e-kimyo-kurs-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_data = {}
active_attendance_sessions = {}

# ================= BAZA VA XAVFSIZLIK =================
def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT DEFAULT '',
                group_name TEXT DEFAULT 'Guruh tanlanmagan',
                paid_until TEXT,
                missed_hw INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS group_settings (
                group_name TEXT PRIMARY KEY,
                chat_id INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS written_works (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                photo_id TEXT,
                score REAL DEFAULT -1,
                checked_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                group_name TEXT,
                session_date TEXT,
                session_id TEXT,
                checked_at TEXT
            )
        """)
        # Boshlang'ich guruhlar uchun bo'sh joy yaratib qo'yamiz (agar env'da bo'lsa oladi)
        default_groups = {
            "4-Guruh": os.environ.get("GURUH_4_ID"),
            "5-Guruh": os.environ.get("GURUH_5_ID"),
            "6-Guruh": os.environ.get("GURUH_6_ID")
        }
        for g_name, g_id in default_groups.items():
            if g_id:
                c.execute("INSERT OR IGNORE INTO group_settings (group_name, chat_id) VALUES (?, ?)", (g_name, int(g_id)))
        conn.commit()

def get_group_chat_id(group_name):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT chat_id FROM group_settings WHERE group_name = ?", (group_name,))
        row = c.fetchone()
        return row[0] if row else None

def set_group_chat_id(group_name, chat_id):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO group_settings (group_name, chat_id) VALUES (?, ?)", (group_name, chat_id))
        conn.commit()

def db_check_user(user_id):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT is_active, is_admin FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return (bool(row[0] == 1), bool(row[1] == 1)) if row else (False, False)

def db_get_admins():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE is_admin = 1")
        return [r[0] for r in c.fetchall()]

# ================= MENYULAR =================
def guest_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(
        KeyboardButton("✍️ Kursga yozilish"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    return kb

def student_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📸 Vazifa yuborish"),
        KeyboardButton("👤 Shaxsiy kabinet"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📊 Dars davomatini boshlash"),
        KeyboardButton("📝 Yangi vazifa e'lon qilish"),
        KeyboardButton("⚙️ Guruh ID larini sozlash"),
        KeyboardButton("👥 O'quvchilar ro'yxati"),
        KeyboardButton("📢 Xabar yuborish")
    )
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Bekor qilish"))
    return kb

# ================= ASOSIY BUYRUQLAR =================
@bot.message_handler(chat_types=["private"], commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    is_active, is_admin = db_check_user(uid)
    
    if is_admin:
        return bot.send_message(uid, "⚙️ <b>Admin Panelga xush kelibsiz!</b>", reply_markup=admin_menu())
    elif is_active:
        bot.send_message(uid, "🧪 <b>A+ Kimyo</b> platformasiga xush kelibsiz!", reply_markup=student_menu())
    else:
        text = (f"Assalomu alaykum!\n"
                f"🧪 <b>A+ Kimyo</b> platformasiga xush kelibsiz.\n"
                f"Kursga yozilish uchun davom eting:")
        bot.send_message(uid, text, reply_markup=guest_menu())

@bot.message_handler(chat_types=["private"], commands=['admin'])
def admin_cmd(message):
    uid = message.from_user.id
    is_active, is_admin = db_check_user(uid)
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PAROL:
        with sqlite3.connect("database.db") as conn:
            conn.cursor().execute(
                "INSERT OR REPLACE INTO users (user_id, full_name, is_admin, is_active) VALUES (?, ?, 1, 1)", 
                (uid, message.from_user.full_name)
            )
            conn.commit()
        bot.send_message(uid, "✅ Siz adminga aylandingiz!", reply_markup=admin_menu())
    elif is_admin:
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "🚫 Ruxsat yo‘q.")

# Guruh ichida /id yozilsa ID ni ko'rsatadi
@bot.message_handler(commands=['id'])
def get_chat_id(message):
    bot.reply_to(message, f"🆔 Ushbu guruh ID si:\n<code>{message.chat.id}</code>")

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "❌ Bekor qilish")
def cancel_action(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    is_active, is_admin = db_check_user(uid)
    if is_admin:
        bot.send_message(uid, "🏠 Bekor qilindi. Admin Panel:", reply_markup=admin_menu())
    elif is_active:
        bot.send_message(uid, "🏠 Bekor qilindi. Asosiy menyu:", reply_markup=student_menu())
    else:
        bot.send_message(uid, "🏠 Bekor qilindi. Asosiy menyu:", reply_markup=guest_menu())

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    bot.send_message(message.chat.id, f"👨‍🏫 Savollar va murojaat uchun: {ADMIN_LICHKA}")

# ================= ADMIN: GURUH ID LARINI SOZLASH VA HAVOLA TEKSHIRISH =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "⚙️ Guruh ID larini sozlash")
def setup_groups_menu(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    
    g4 = get_group_chat_id("4-Guruh") or "Kiritilmagan"
    g5 = get_group_chat_id("5-Guruh") or "Kiritilmagan"
    g6 = get_group_chat_id("6-Guruh") or "Kiritilmagan"

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"4️⃣ 4-Guruh ({g4})", callback_data="cfggrp_4-Guruh"),
        InlineKeyboardButton(f"5️⃣ 5-Guruh ({g5})", callback_data="cfggrp_5-Guruh"),
        InlineKeyboardButton(f"6️⃣ 6-Guruh ({g6})", callback_data="cfggrp_6-Guruh")
    )
    bot.send_message(
        message.chat.id, 
        "⚙️ <b>Guruh ID larini bog'lash</b>\n\n"
        "Qaysi guruhning ID raqamini kiritmoqchisiz?\n"
        "<i>(Guruh ID sini bilish uchun botni o'sha guruhga Admin qiling va guruh ichida /id deb yozing)</i>", 
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("cfggrp_"))
def ask_group_id_input(call):
    group_name = call.data.split("_")[1]
    user_states[call.from_user.id] = f"wait_gid_{group_name}"
    bot.send_message(
        call.message.chat.id, 
        f"🆔 <b>{group_name}</b> uchun Telegram guruh ID sini yuboring:\n<i>(Masalan: -1001234567890)</i>", 
        reply_markup=cancel_kb()
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(chat_types=["private"], content_types=['text'], func=lambda m: str(user_states.get(m.from_user.id, "")).startswith("wait_gid_"))
def save_group_id_and_test_link(message):
    uid = message.from_user.id
    group_name = user_states[uid].replace("wait_gid_", "")
    raw_text = message.text.strip()
    
    try:
        chat_id = int(raw_text)
    except ValueError:
        return bot.send_message(uid, "❌ Noto'g'ri format! Guruh ID si faqat raqamlardan iborat bo'lishi kerak (masalan: <code>-1001234567890</code>). Qaytadan yuboring:")

    set_group_chat_id(group_name, chat_id)
    user_states.pop(uid, None)

    # Darhol havola yaratib tekshirib ko'ramiz
    try:
        expire_unix = int(time.time()) + 3600 # 1 soatlik sinov havolasi
        invite = bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"Test_{group_name}",
            expire_date=expire_unix,
            member_limit=1
        )
        bot.send_message(
            uid, 
            f"✅ <b>{group_name}</b> muvaffaqiyatli bog'landi!\n"
            f"🆔 Saqlangan ID: <code>{chat_id}</code>\n\n"
            f"🔗 <b>Tekshiruv uchun 1 martalik havola yaratildi:</b>\n{invite.invite_link}\n\n"
            f"<i>Endi to'lov tasdiqlanganda o'quvchilarga xuddi shunday avtomatik havola yuboriladi!</i>",
            reply_markup=admin_menu()
        )
    except Exception as e:
        bot.send_message(
            uid,
            f"⚠️ <b>ID saqlandi (<code>{chat_id}</code>), lekin havola yaratishda xatolik chiqdi:</b>\n<code>{e}</code>\n\n"
            f"<b>Tekshiring:</b>\n"
            f"1. Bot ushbu guruhga qo'shilganmi?\n"
            f"2. Botga <b>Admin</b> huquqi va <i>\"Foydalanuvchilarni havola orqali taklif qilish\"</i> ruxsati berilganmi?",
            reply_markup=admin_menu()
        )

# ================= TO'LOV VA GURUHGA QO'SHISH JARAYONI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    user_states[message.from_user.id] = "reg_name"
    bot.send_message(message.chat.id, "📝 Iltimos, Ism va Familiyangizni yozing:\n<i>(Masalan: Azizbek Ibrohimov)</i>", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text'], func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_2(message):
    uid = message.from_user.id
    user_data[uid] = {"full_name": message.text.strip()}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("📱 Raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni pastdagi tugma orqali yuboring:", reply_markup=kb)

@bot.message_handler(chat_types=["private"], content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_3(message):
    uid = message.from_user.id
    if not message.contact and message.text == "❌ Bekor qilish":
        return cancel_action(message)
    phone = message.contact.phone_number if message.contact else message.text.strip()
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users (user_id, full_name, phone, is_active, is_admin) VALUES (?, ?, ?, 0, 0)",
                  (uid, user_data[uid]["full_name"], phone))
        conn.commit()
        
    bot.send_message(uid, f"💳 To'lov uchun karta: <code>{KARTA_RAQAM}</code>\n👤 Karta egasi: <b>{KARTA_EGASI}</b>\n\n📸 To'lov chekini rasm (skrinshot) ko'rinishida yuboring:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_done(message):
    uid = message.from_user.id
    photo_id = message.photo[-1].file_id
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}")
    )
    name = user_data.get(uid, {}).get('full_name', 'Noma’lum')
    phone = user_data.get(uid, {}).get('phone', 'Aniqlanmagan')
    caption = f"🆕 <b>YANGI TO'LOV CHEKI</b>\n\n👤 O'quvchi: {name}\n📞 Telefon: {phone}\n🆔 ID: <code>{uid}</code>"
    
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
            
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek adminga yuborildi. Tasdiqlanishini kuting!", reply_markup=guest_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_decision(call):
    parts = call.data.split("_")
    action = parts[1]
    target_id = int(parts[2])
    
    if action == "ok":
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("4️⃣ 4-Guruh: Milliy Sertifikat", callback_data=f"setgrp_{target_id}_4-Guruh"),
            InlineKeyboardButton("5️⃣ 5-Guruh: Milliy Sertifikat", callback_data=f"setgrp_{target_id}_5-Guruh"),
            InlineKeyboardButton("6️⃣ 6-Guruh: Milliy Sertifikat", callback_data=f"setgrp_{target_id}_6-Guruh"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"pay_no_{target_id}")
        )
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, f"O'quvchini (ID: <code>{target_id}</code>) qaysi guruhga qo'shamiz?", reply_markup=kb)
    else:
        try:
            bot.send_message(target_id, "❌ <b>To'lov chekingiz rad etildi.</b> Ma'lumotlarni tekshirib qaytadan urinib ko'ring yoki admin bilan bog'laning.")
        except Exception:
            pass
        try:
            bot.edit_message_caption("❌ <b>TO'LOV RAD ETILDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("setgrp_"))
def finalize_payment(call):
    parts = call.data.split("_")
    target_id = int(parts[1])
    group_name = parts[2]
    expiry_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    target_chat_id = get_group_chat_id(group_name)

    invite_link = ""
    admin_status_note = ""
    
    if not target_chat_id:
        invite_link = f"\n⚠️ <i>Guruh havolasini olish uchun admin bilan bog'laning: {ADMIN_LICHKA}</i>"
        admin_status_note = f"⚠️ <b>Diqqat:</b> <code>{group_name}</code> uchun guruh ID kiritilmagan! Admin paneldan <b>⚙️ Guruh ID larini sozlash</b> bo'limiga kirib ID ni kiriting."
    else:
        try:
            bot.unban_chat_member(target_chat_id, target_id, only_if_banned=True)
            expire_unix = int(time.time()) + 86400 # 24 soat amal qiladi
            invite = bot.create_chat_invite_link(
                chat_id=target_chat_id, 
                name=f"{group_name}_{target_id}", 
                expire_date=expire_unix,
                member_limit=1
            )
            invite_link = f"\n🔗 <b>Yopiq guruhga kirish havolasi (1 martalik):</b>\n{invite.invite_link}"
            admin_status_note = "✅ 1 martalik guruh havolasi yaratildi va o'quvchiga yuborildi."
        except Exception as e:
            invite_link = f"\n⚠️ <i>Guruh havolasini olish uchun admin bilan bog'laning: {ADMIN_LICHKA}</i>"
            admin_status_note = f"⚠️ <b>Havola yaratishda xato:</b> {e}"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 1, group_name = ?, paid_until = ?, missed_hw = 0 WHERE user_id = ?", 
                  (group_name, expiry_date, target_id))
        conn.commit()

    try:
        bot.send_message(
            target_id, 
            f"🎉 <b>Tabriklaymiz, to'lovingiz tasdiqlandi!</b>\n\n"
            f"👥 Guruhingiz: <b>{group_name}</b>\n"
            f"⏳ Obuna muddati: <b>{expiry_date}</b> gacha (30 kun)\n"
            f"{invite_link}", 
            reply_markup=student_menu()
        )
    except Exception:
        pass

    try:
        bot.edit_message_caption(
            f"✅ <b>TASDIQLANDI!</b>\n👤 O'quvchi ID: <code>{target_id}</code>\n👥 Guruh: <b>{group_name}</b>\n⏳ Muddat: {expiry_date}\n\n{admin_status_note}", 
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id
        )
    except Exception:
        pass
    bot.answer_callback_query(call.id, "Tasdiqlandi!")

# ================= DARS DAVOMATI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📊 Dars davomatini boshlash")
def start_attendance(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("4️⃣ 4-Guruh uchun davomat", callback_data="attgrp_4-Guruh"),
        InlineKeyboardButton("5️⃣ 5-Guruh uchun davomat", callback_data="attgrp_5-Guruh"),
        InlineKeyboardButton("6️⃣ 6-Guruh uchun davomat", callback_data="attgrp_6-Guruh")
    )
    bot.send_message(message.chat.id, "📊 Qaysi guruh uchun hozir davomat ochmoqchisiz?\n<i>(Dars davomida bir necha marta ochishingiz mumkin, barchasi bugungi sana bilan yoziladi)</i>", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("attgrp_"))
def trigger_attendance(call):
    group_name = call.data.split("_")[1]
    today_str = datetime.now().strftime("%Y-%m-%d")
    session_id = datetime.now().strftime("%H%M%S")
    session_key = f"{group_name}_{today_str}_{session_id}"
    
    active_attendance_sessions[session_key] = True
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE group_name = ? AND is_active = 1 AND is_admin = 0", (group_name,))
        students = c.fetchall()

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ DARSDA QATNASHYAPMAN", callback_data=f"here_{session_key}"))

    count = 0
    for s in students:
        try:
            bot.send_message(
                s[0], 
                f"⏰ <b>DIQQAT, DAVOMAT TEKSHIRUVI!</b>\n\n"
                f"📅 Sana: <b>{today_str}</b>\n"
                f"👥 Guruh: <b>{group_name}</b>\n\n"
                f"Darsda ekanligingizni tasdiqlash uchun 10 daqiqa ichida pastdagi tugmani bosing:", 
                reply_markup=kb
            )
            count += 1
        except Exception:
            pass

    try:
        bot.edit_message_text(
            f"✅ <b>{group_name}</b> uchun davomat ochildi!\n📨 Xabar yuborildi: <b>{count} ta</b> o'quvchiga.\n⏳ Vaqt: 10 daqiqa (yakunlangach kelgan va kelmaganlar ro'yxati yuboriladi).", 
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id
        )
    except Exception:
        pass
    bot.answer_callback_query(call.id)

    threading.Thread(target=close_attendance, args=(session_key, group_name, today_str, session_id), daemon=True).start()

def close_attendance(session_key, group_name, today_str, session_id):
    time.sleep(600)
    active_attendance_sessions[session_key] = False
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, full_name FROM users WHERE group_name = ? AND is_active = 1 AND is_admin = 0", (group_name,))
        all_students = dict(c.fetchall())
        
        c.execute("SELECT user_id, full_name, checked_at FROM attendance WHERE session_date = ? AND session_id = ? AND group_name = ?", (today_str, session_id, group_name))
        present_rows = c.fetchall()
        
    present_ids = {r[0] for r in present_rows}
    present_list = "\n".join([f"✅ {r[1]} ({r[2]})" for r in present_rows]) if present_rows else "Hech kim tasdiqlamadi"
    
    absent_names = [name for uid, name in all_students.items() if uid not in present_ids]
    absent_list = "\n".join([f"❌ {name}" for name in absent_names]) if absent_names else "Barcha o'quvchilar qatnashdi!"

    report = (
        f"🛑 <b>DAVOMAT YAKUNLANDI ({group_name} | {today_str})</b>\n\n"
        f"<b>Qatnashganlar ({len(present_rows)} ta):</b>\n{present_list}\n\n"
        f"<b>Qatnashmaganlar ({len(absent_names)} ta):</b>\n{absent_list}"
    )

    for adm in db_get_admins():
        try:
            bot.send_message(adm, report)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("here_"))
def mark_attendance(call):
    session_key = call.data.replace("here_", "")
    parts = session_key.split("_")
    group_name = parts[0]
    session_date = parts[1]
    session_id = parts[2]
    uid = call.from_user.id
    current_today = datetime.now().strftime("%Y-%m-%d")
    
    if not active_attendance_sessions.get(session_key, False) or session_date != current_today:
        return bot.answer_callback_query(call.id, "❌ Bu davomat vaqti tugagan!", show_alert=True)
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name FROM users WHERE user_id = ? AND is_active = 1", (uid,))
        user = c.fetchone()
        if not user:
            return bot.answer_callback_query(call.id, "🚫 Siz faol o'quvchilar ro'yxatida emassiz.", show_alert=True)
        
        c.execute("SELECT id FROM attendance WHERE user_id = ? AND session_id = ?", (uid, session_id))
        if c.fetchone():
            return bot.answer_callback_query(call.id, "⚠️ Siz bu tekshiruvdan o'tib bo'lgansiz!", show_alert=True)
            
        c.execute(
            "INSERT INTO attendance (user_id, full_name, group_name, session_date, session_id, checked_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, user[0], group_name, current_today, session_id, datetime.now().strftime("%H:%M"))
        )
        conn.commit()
        
    bot.answer_callback_query(call.id, "✅ Davomatingiz qabul qilindi!", show_alert=True)
    try:
        bot.edit_message_text(f"✅ <b>Davomatingiz tasdiqlandi!</b> ({current_today} | {datetime.now().strftime('%H:%M')})", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass

# ================= YANGI VAZIFA E'LON QILISH =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📝 Yangi vazifa e'lon qilish")
def announce_new_hw(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("4️⃣ 4-Guruhga vazifa belgilash", callback_data="newhw_4-Guruh"),
        InlineKeyboardButton("5️⃣ 5-Guruhga vazifa belgilash", callback_data="newhw_5-Guruh"),
        InlineKeyboardButton("6️⃣ 6-Guruhga vazifa belgilash", callback_data="newhw_6-Guruh")
    )
    bot.send_message(
        message.chat.id, 
        "📝 Qaysi guruhga yangi vazifa berildi?\n<i>(Tugma bosilganda, o'quvchilarning topshirilmagan vazifalar soni +1 ga oshadi. Vazifa yuborganida esa 0 ga tushadi. 5 taga yetsa avtomat guruhdan chiqariladi)</i>", 
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("newhw_"))
def process_new_hw(call):
    group_name = call.data.split("_")[1]
    target_chat_id = get_group_chat_id(group_name)
    kicked_users = []
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET missed_hw = missed_hw + 1 WHERE group_name = ? AND is_active = 1 AND is_admin = 0", (group_name,))
        conn.commit()
        
        c.execute("SELECT user_id, full_name FROM users WHERE group_name = ? AND is_active = 1 AND is_admin = 0 AND missed_hw >= 5", (group_name,))
        violators = c.fetchall()
        
        for uid, name in violators:
            if target_chat_id:
                try:
                    bot.unban_chat_member(target_chat_id, uid)
                except Exception:
                    pass
            c.execute("UPDATE users SET is_active = 0, missed_hw = 0 WHERE user_id = ?", (uid,))
            kicked_users.append(name)
            try:
                bot.send_message(uid, "🚫 <b>Siz yopiq guruhdan chetlatildingiz!</b>\n\nSabab: Ketma-ket 5 ta uy vazifasini topshirmadingiz.")
            except Exception:
                pass
        conn.commit()

    kicked_text = f"\n\n🚫 5 ta vazifa qoldirgani uchun guruhdan chiqarildi:\n" + "\n".join([f"• {n}" for n in kicked_users]) if kicked_users else ""
    try:
        bot.edit_message_text(
            f"✅ <b>{group_name}</b> uchun yangi vazifa nazorati yoqildi!{kicked_text}", 
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id
        )
    except Exception:
        pass
    bot.answer_callback_query(call.id)

# ================= VAZIFA TOPSHIRISH VA TEKSHIRISH =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📸 Vazifa yuborish")
def ask_written_photo(message):
    uid = message.from_user.id
    is_active, _ = db_check_user(uid)
    if not is_active:
        return bot.send_message(uid, "🚫 Ruxsat yo'q. Kursga yoziling.")
    user_states[uid] = "wait_hw_photo"
    bot.send_message(uid, "📸 Yechimlar tushirilgan rasmni ustoz tekshiruvi uchun yuboring:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "wait_hw_photo")
def receive_written_photo(message):
    uid = message.from_user.id
    photo_id = message.photo[-1].file_id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, group_name FROM users WHERE user_id = ?", (uid,))
        row = c.fetchone()
        name, grp = row[0], row[1]
        c.execute("INSERT INTO written_works (user_id, full_name, photo_id, checked_at) VALUES (?, ?, ?, ?)",
                  (uid, name, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
        c.execute("UPDATE users SET missed_hw = 0 WHERE user_id = ?", (uid,))
        work_id = c.lastrowid
        conn.commit()

    kb = InlineKeyboardMarkup(row_width=5)
    buttons = [InlineKeyboardButton(str(i), callback_data=f"rate_{work_id}_{i}") for i in range(1, 11)]
    kb.add(*buttons)

    caption = f"📝 <b>YANGI VAZIFA KELDI!</b>\n👤 O'quvchi: {name} ({grp})\n🆔 ID: <code>{uid}</code>\nBaho qo'ying (1-10):"
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Vazifa ustozga yuborildi va qarz hisoblagichi nollandi!", reply_markup=student_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("rate_"))
def rate_work(call):
    _, work_id, score = call.data.split("_")
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE written_works SET score = ? WHERE id = ?", (score, work_id))
        c.execute("SELECT user_id FROM written_works WHERE id = ?", (work_id,))
        student_id = c.fetchone()[0]
        conn.commit()
    try:
        bot.edit_message_caption(f"✅ Baholandi: <b>{score} ball</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass
    try:
        bot.send_message(student_id, f"🎉 <b>Ustoz vazifangizni tekshirdi!</b>\nBahoyingiz: <b>{score} ball</b>")
    except Exception:
        pass
    bot.answer_callback_query(call.id)

# ================= SHAXSIY KABINET =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "👤 Shaxsiy kabinet")
def profile(message):
    uid = message.from_user.id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, phone, group_name, paid_until, missed_hw FROM users WHERE user_id = ?", (uid,))
        user_info = c.fetchone()
        c.execute("SELECT COUNT(*), AVG(score) FROM written_works WHERE user_id = ? AND score >= 0", (uid,))
        stats = c.fetchone()
    if not user_info:
        return
    avg_score = round(stats[1], 1) if stats[1] and stats[1] >= 0 else "Baholanmagan"
    text = (f"👤 <b>SHAXSIY KABINET</b>\n\n"
            f"👤 F.I.Sh: {user_info[0]}\n"
            f"📞 Tel: {user_info[1]}\n"
            f"👥 Guruh: {user_info[2]}\n"
            f"⏳ To'lov muddati: <b>{user_info[3] or 'Muddatsiz'}</b>\n"
            f"⚠️ Topshirilmagan vazifalar: <b>{user_info[4]} / 5 ta</b>\n\n"
            f"📊 Tekshirilgan vazifalar: {stats[0]} ta\n"
            f"📈 O'rtacha ball: {avg_score}")
    bot.send_message(uid, text)

# ================= ADMIN FUNKSIYALARI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "👥 O'quvchilar ro'yxati")
def admin_users(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, group_name, paid_until, missed_hw, is_active FROM users WHERE is_admin = 0")
        users = c.fetchall()
    if not users:
        return bot.send_message(message.chat.id, "Hozircha o'quvchilar yo'q.")
    lines = [f"• <b>{u[0]}</b> | {u[1]} | Muddat: {u[2]} | Qarz vazifa: {u[3]} | {'✅ Aktiv' if u[4] else '❌ Blok'}" for u in users]
    bot.send_message(message.chat.id, "👥 <b>O'quvchilar ro'yxati:</b>\n\n" + "\n".join(lines))

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📢 Xabar yuborish")
def broadcast_ask(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    user_states[message.from_user.id] = "broad_text"
    bot.send_message(message.chat.id, "📢 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text', 'photo'], func=lambda m: user_states.get(m.from_user.id) == "broad_text")
def broadcast_send(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [r[0] for r in c.fetchall()]
    user_states.pop(message.from_user.id, None)
    sent = 0
    for u in users:
        try:
            bot.copy_message(u, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"✅ Xabar {sent} ta foydalanuvchiga muvaffaqiyatli yuborildi!", reply_markup=admin_menu())

# ================= CRM & MUDDAT NAZORATI =================
def check_subscriptions():
    while True:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            with sqlite3.connect("database.db") as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, paid_until, full_name, group_name FROM users WHERE is_active = 1 AND is_admin = 0 AND paid_until IS NOT NULL")
                users = c.fetchall()
                
                for uid, paid_until, name, grp in users:
                    exp_date = datetime.strptime(paid_until, "%Y-%m-%d")
                    curr_date = datetime.strptime(today, "%Y-%m-%d")
                    days_left = (exp_date - curr_date).days
                    target_chat_id = get_group_chat_id(grp)
                    
                    if 0 < days_left <= 3:
                        try:
                            bot.send_message(uid, f"⚠️ <b>Diqqat, {name}!</b>\n\nOylik obuna muddatingiz tugashiga <b>{days_left} kun</b> qoldi. Guruhdan chiqarilmaslik uchun to'lovni amalga oshiring.")
                        except Exception:
                            pass
                    elif days_left <= 0:
                        if target_chat_id:
                            try:
                                bot.unban_chat_member(target_chat_id, uid)
                            except Exception as e:
                                print(f"Foydalanuvchini chiqarish xatosi: {e}")
                        c.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (uid,))
                        conn.commit()
                        try:
                            bot.send_message(uid, "🚫 <b>Oylik obuna muddatingiz yakunlandi.</b>\n\nTo'lov qilinmagani sababli yopiq guruhdan chetlatildingiz. Qayta qo'shilish uchun kursga yoziling.", reply_markup=guest_menu())
                        except Exception:
                            pass
        except Exception as e:
            print(f"CRM tekshirish xatosi: {e}")
        time.sleep(86400)

# ================= SERVER VA POLLING =================
@app.route("/")
def index():
    return "A+ Kimyo Bot platformasi uzluksiz ishlamoqda!"

def bot_polling():
    while True:
        try:
            bot.infinity_polling(none_stop=True, timeout=30)
        except Exception:
            time.sleep(5)

def keep_alive():
    while True:
        try:
            requests.get(RENDER_URL, timeout=10)
        except Exception:
            pass
        time.sleep(300)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=app.run, args=("0.0.0.0", int(os.environ.get("PORT", 8080))), daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=check_subscriptions, daemon=True).start()
    bot_polling()
