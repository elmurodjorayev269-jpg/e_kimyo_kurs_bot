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

YOPIQ_GURUH_ID = int(os.environ.get("YOPIQ_GURUH_ID", "-1001234567890"))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://e-kimyo-kurs-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_data = {}
attendance_sessions = {}

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
                is_active INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
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
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                score INTEGER,
                tested_at TEXT
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
        KeyboardButton("📝 Test ishlash (Avto-tekshirish)"),
        KeyboardButton("🎖 Sertifikat olish"),
        KeyboardButton("👤 Shaxsiy kabinet"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📊 Dars davomatini boshlash"),
        KeyboardButton("👥 O'quvchilarni boshqarish"),
        KeyboardButton("📢 Xabar yuborish"),
        KeyboardButton("🔙 Bosh menyu")
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
        return bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
    elif is_active:
        bot.send_message(uid, "Xush kelibsiz!", reply_markup=student_menu())
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
            conn.cursor().execute("INSERT OR REPLACE INTO users (user_id, full_name, is_admin) VALUES (?, ?, 1)", 
                                  (uid, message.from_user.full_name))
            conn.commit()
        bot.send_message(uid, "✅ Siz adminga aylandingiz!", reply_markup=admin_menu())
    elif is_admin:
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "🚫 Ruxsat yo‘q.")

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🔙 Bosh menyu")
def main_menu_route(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    is_active, is_admin = db_check_user(uid)
    if is_admin:
        bot.send_message(message.chat.id, "⚙️ Admin Panel:", reply_markup=admin_menu())
    elif is_active:
        bot.send_message(message.chat.id, "🏠 Asosiy menyu:", reply_markup=student_menu())
    else:
        bot.send_message(message.chat.id, "🏠 Asosiy menyu:", reply_markup=guest_menu())

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "❌ Bekor qilish")
def cancel_action(message):
    main_menu_route(message)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    bot.send_message(message.chat.id, f"👨‍🏫 Murojaat uchun: {ADMIN_LICHKA}")

# ================= TO'LOV JARAYONI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    user_states[message.from_user.id] = "reg_name"
    bot.send_message(message.chat.id, "📝 Iltimos, Ism va Familiyangizni yozing:\n<i>(Masalan: Azizbek Ibrohimov)</i>", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text'], func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_2(message):
    uid = message.from_user.id
    user_data[uid] = {"full_name": message.text}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("📱 Raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

@bot.message_handler(chat_types=["private"], content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_3(message):
    uid = message.from_user.id
    if not message.contact and message.text == "❌ Bekor qilish":
        return cancel_action(message)
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users (user_id, full_name, phone) VALUES (?, ?, ?)",
                  (uid, user_data[uid]["full_name"], phone))
        conn.commit()
        
    bot.send_message(uid, f"💳 Karta: <code>{KARTA_RAQAM}</code> ({KARTA_EGASI})\n📸 To'lov chekini rasm ko'rinishida yuboring:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_done(message):
    uid = message.from_user.id
    photo_id = message.photo[-1].file_id
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}")
    )
    caption = f"🆕 <b>YANGI TO'LOV CHEKI</b>\nFoydalanuvchi: {user_data.get(uid, {}).get('full_name', 'Noma’lum')}\nTelefon: {user_data.get(uid, {}).get('phone', 'Aniqlanmagan')}\nID: <code>{uid}</code>"
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek qabul qilindi. Tez orada admin tasdiqlaydi!", reply_markup=guest_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_decision(call):
    action, target_id = call.data.split("_")[1], int(call.data.split("_")[2])
    if action == "ok":
        user_states[call.from_user.id] = f"choose_group_{target_id}"
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("4️⃣ 4-Guruh: Milliy Sertifikat", callback_data=f"setgrp_{target_id}_4-Guruh"),
            InlineKeyboardButton("5️⃣ 5-Guruh: Milliy Sertifikat", callback_data=f"setgrp_{target_id}_5-Guruh"),
            InlineKeyboardButton("6️⃣ 6-Guruh: Milliy Sertifikat", callback_data=f"setgrp_{target_id}_6-Guruh"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"pay_no_{target_id}")
        )
        bot.send_message(call.message.chat.id, f"O'quvchi (ID: <code>{target_id}</code>) qaysi guruhga qo'shilishi kerak?", reply_markup=kb)
    else:
        bot.send_message(target_id, "To'lov tasdiqlanmadi.</b>")
        bot.edit_message_caption("❌ <b>RAD ETILDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("setgrp_"))
def finalize_payment(call):
    target_id = int(call.data.split("_")[1])
    group_name = call.data.split("_")[2]
    expiry_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    try:
        bot.unban_chat_member(YOPIQ_GURUH_ID, target_id, only_if_banned=True)
        invite = bot.create_chat_invite_link(chat_id=YOPIQ_GURUH_ID, name=group_name, member_limit=1)
        invite_link = invite.invite_link
    except Exception as e:
        invite_link = f"Havola yaratishda xato: {e}"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 1, group_name = ?, paid_until = ? WHERE user_id = ?", 
                  (group_name, expiry_date, target_id))
        conn.commit()

    bot.send_message(target_id, f"🎉 <b>To'lovingiz tasdiqlandi!</b>\n\nGuruh: {group_name}\nTo'lov muddati: {expiry_date} gacha\nSiz uchun maxsus havola: {invite_link}", reply_markup=student_menu())
    bot.edit_message_caption(f"✅ <b>TASDIQLANDI</b>\nGuruh: {group_name}", chat_id=call.message.chat.id, message_id=call.message.message_id)
    user_states.pop(call.from_user.id, None)
    bot.answer_callback_query(call.id)

# ================= DARS DAVOMATI (KUNLIK CHEKLANGAN) =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📊 Dars davomatini boshlash")
def start_attendance(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    user_states[message.from_user.id] = "att_group"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("4️⃣ 4-Guruh", callback_data="att_grp_4-Guruh"),
        InlineKeyboardButton("5️⃣ 5-Guruh", callback_data="att_grp_5-Guruh"),
        InlineKeyboardButton("6️⃣ 6-Guruh", callback_data="att_grp_6-Guruh")
    )
    bot.send_message(message.chat.id, "Qaysi guruh uchun davomat o'tkazmoqchisiz?", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("att_grp_"))
def trigger_attendance(call):
    group_name = call.data.split("_")[2]
    today_str = datetime.now().strftime("%Y-%m-%d")
    session_id = datetime.now().strftime("%H%M%S")
    session_key = f"{group_name}_{today_str}"
    
    attendance_sessions[session_key] = True
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE group_name = ? AND is_active = 1", (group_name,))
        students = c.fetchall()

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ DARSDA VAQTIDAMAN", callback_data=f"here_{session_key}_{session_id}"))

    count = 0
    for s in students:
        try:
            bot.send_message(s[0], f"⏰ <b>Diqqat, davomat ({today_str})!</b>\n\n<b>{group_name}</b> darsi boshlandi. Ishtirokingizni tasdiqlang:", reply_markup=kb)
            count += 1
        except Exception:
            pass

    bot.edit_message_caption(f"<b>{group_name}</b> uchun bugungi davomat boshlandi ({count} o'quvchiga yuborildi).", chat_id=call.message.chat.id, message_id=call.message.message_id)
    bot.answer_callback_query(call.id)

    threading.Thread(target=close_attendance, args=(session_key, group_name), daemon=True).start()

def close_attendance(session_key, group_name):
    time.sleep(600)
    attendance_sessions[session_key] = False
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM attendance WHERE session_date = ? AND group_name = ?", (datetime.now().strftime("%Y-%m-%d"), group_name))
        present_count = c.fetchone()[0]
    for adm in db_get_admins():
        try:
            bot.send_message(adm, f"🛑 <b>Davomat sessiyasi yakunlandi ({group_name}).</b>\nBugun qatnashganlar: <b>{present_count} ta</b> o'quvchi.")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("here_"))
def mark_attendance(call):
    parts = call.data.split("_")
    session_key = f"{parts[1]}_{parts[2]}"
    uid = call.from_user.id
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if not attendance_sessions.get(session_key, False):
        return bot.answer_callback_query(call.id, "❌ Davomat vaqti tugadi yoki faol emas!", show_alert=True)
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, group_name FROM users WHERE user_id = ?", (uid,))
        user = c.fetchone()
        if not user:
            return bot.answer_callback_query(call.id, "🚫 Ro'yxatdan o'tmagansiz.")
        
        c.execute("SELECT id FROM attendance WHERE user_id = ? AND session_date = ?", (uid, today_str))
        if c.fetchone():
            return bot.answer_callback_query(call.id, "⚠️ Siz bugun ushbu guruh davomatida allaqachon qatnashgansiz!", show_alert=True)
            
        c.execute("INSERT INTO attendance (user_id, full_name, group_name, session_date, session_id, checked_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (uid, user[0], user[1], today_str, parts[3], datetime.now().strftime("%H:%M")))
        conn.commit()
        
    bot.answer_callback_query(call.id, "✅ Davomatingiz qabul qilindi!", show_alert=True)
    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)

# ================= KENGAYTIRILGAN FUNKSIYALI TEST VA SERTIFIKAT =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📝 Test ishlash (Avto-tekshirish)")
def start_test_process(message):
    uid = message.from_user.id
    is_active, _ = db_check_user(uid)
    if not is_active:
        return bot.send_message(uid, "🚫 Ruxsat yo'q. Kursga yoziling.")
    user_states[uid] = "test_q1"
    bot.send_message(uid, "🧪 <b>1-savol:</b> H2O molekulyar massasi qanday?\n\nA) 16\nB) 18\nC) 20", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text'], func=lambda m: user_states.get(m.from_user.id) in ["test_q1", "test_q2"])
def handle_test_answers(message):
    uid = message.from_user.id
    state = user_states[uid]
    text = message.text.upper()
    
    if state == "test_q1":
        user_data[uid] = {"q1_score": 1 if text == "B" else 0}
        user_states[uid] = "test_q2"
        bot.send_message(uid, "🧪 <b>2-savol:</b> Eng kuchli kislitani ko'rsating:\n\nA) HCl\nB) H2SO4\nC) HF")
    elif state == "test_q2":
        q2_score = 1 if text == "A" else 0
        total_score = (user_data[uid]["q1_score"] + q2_score) * 50
        
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT full_name FROM users WHERE user_id = ?", (uid,))
            name = c.fetchone()[0]
            c.execute("INSERT INTO test_results (user_id, full_name, score, tested_at) VALUES (?, ?, ?, ?)",
                      (uid, name, total_score, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
            
        user_states.pop(uid, None)
        bot.send_message(uid, f"🎉 <b>Test yakunlandi!</b>\nTo'plagan ballingiz: <b>{total_score} ball</b>", reply_markup=student_menu())

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🎖 Sertifikat olish")
def generate_certificate(message):
    uid = message.from_user.id
    is_active, _ = db_check_user(uid)
    if not is_active:
        return bot.send_message(uid, "🚫 Sertifikat olish uchun avval kursni tugatishingiz kerak.")
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name FROM users WHERE user_id = ?", (uid,))
        name = c.fetchone()[0]
        
    cert_text = (f"📜 <b>A+ KIMYO TA'LIM PLATFORMASI</b>\n\n"
                 f"Ushbu sertifikat <b>{name}</b> ga\n"
                 f"Kimyo fanidan o'quv kursini muvaffaqiyatli tamomlagani uchun beriladi.\n\n"
                 f"Sana: {datetime.now().strftime('%d.%m.%Y')}\n"
                 f"Tasdiqladi: {KARTA_EGASI}")
    bot.send_message(uid, cert_text)

# ================= VAZIFA TOPSHIRISH =================
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
        c.execute("SELECT full_name FROM users WHERE user_id = ?", (uid,))
        name = c.fetchone()[0]
        c.execute("INSERT INTO written_works (user_id, full_name, photo_id, checked_at) VALUES (?, ?, ?, ?)",
                  (uid, name, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
        work_id = c.lastrowid
        conn.commit()

    kb = InlineKeyboardMarkup(row_width=5)
    buttons = [InlineKeyboardButton(str(i), callback_data=f"rate_{work_id}_{i}") for i in range(1, 11)]
    kb.add(*buttons)

    caption = f"📝 <b>YANGI VAZIFA KELDI!</b>\nO'quvchi: {name}\nID: <code>{uid}</code>\nBaho qo'ying (1-10):"
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Vazifa ustozga yuborildi!", reply_markup=student_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("rate_"))
def rate_work(call):
    _, work_id, score = call.data.split("_")
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE written_works SET score = ? WHERE id = ?", (score, work_id))
        c.execute("SELECT user_id FROM written_works WHERE id = ?", (work_id,))
        student_id = c.fetchone()[0]
        conn.commit()
    bot.edit_message_caption(f"✅ Baholandi: <b>{score} ball</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
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
        c.execute("SELECT full_name, phone, group_name, paid_until FROM users WHERE user_id = ?", (uid,))
        user_info = c.fetchone()
        c.execute("SELECT COUNT(*), AVG(score) FROM written_works WHERE user_id = ? AND score >= 0", (uid,))
        stats = c.fetchone()
    avg_score = round(stats[1], 1) if stats[1] and stats[1] >= 0 else "Baholanmagan"
    text = (f"👤 <b>SHAXSIY KABINET</b>\n\n"
            f"👤 F.I.Sh: {user_info[0]}\n"
            f"📞 Tel: {user_info[1]}\n"
            f"👥 Guruh: {user_info[2]}\n"
            f"⏳ To'lov muddati: {user_info[3] or 'Muddatsiz'}\n\n"
            f"📊 Topshirilgan vazifalar: {stats[0]} ta\n"
            f"📈 O'rtacha ball: {avg_score}")
    bot.send_message(uid, text)

# ================= ADMIN FUNKSIYALARI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "👥 O'quvchilarni boshqarish")
def admin_users(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, group_name, paid_until, is_active FROM users WHERE is_admin = 0")
        users = c.fetchall()
    text = "👥 <b>O'quvchilar ro'yxati:</b>\n" + "\n".join([f"• {u[0]} | {u[1]} | {u[2]} ({'Aktiv' if u[3] else 'Kutilmoqda'})" for u in users])
    bot.send_message(message.chat.id, text)

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📢 Xabar yuborish")
def broadcast_ask(message):
    user_states[message.from_user.id] = "broad_text"
    bot.send_message(message.chat.id, "📢 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text', 'photo'], func=lambda m: user_states.get(m.from_user.id) == "broad_text")
def broadcast_send(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [r[0] for r in c.fetchall()]
    user_states.pop(message.from_user.id, None)
    for u in users:
        try:
            bot.copy_message(u, message.chat.id, message.message_id)
        except Exception:
            pass
    bot.send_message(message.chat.id, "✅ Xabar barchaga muvaffaqiyatli yuborildi!", reply_markup=admin_menu())

# ================= CRM & MUDDAT NAZORATI =================
def check_subscriptions():
    while True:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            with sqlite3.connect("database.db") as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, paid_until, full_name FROM users WHERE is_active = 1 AND paid_until IS NOT NULL")
                users = c.fetchall()
                
                for uid, paid_until, name in users:
                    exp_date = datetime.strptime(paid_until, "%Y-%m-%d")
                    curr_date = datetime.strptime(today, "%Y-%m-%d")
                    days_left = (exp_date - curr_date).days
                    
                    if 0 < days_left <= 3:
                        try:
                            bot.send_message(uid, f"⚠️ <b>Diqqat, {name}!</b>\n\nObuna muddatingiz tugashiga <b>{days_left} kun</b> qoldi. Bloklanmaslik uchun to'lovni amalga oshiring.")
                        except Exception:
                            pass
                    elif days_left <= 0:
                        try:
                            bot.unban_chat_member(YOPIQ_GURUH_ID, uid)
                            c.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (uid,))
                            conn.commit()
                            bot.send_message(uid, "🚫 <b>Obuna muddatingiz yakunlandi.</b>\n\nSiz guruhdan chetlatildingiz. Qayta kirish uchun kursga ro'yxatdan o'ting.")
                        except Exception as e:
                            print(f"Foydalanuvchini chiqarish xatosi: {e}")
        except Exception as e:
            print(f"CRM tekshirish xatosi: {e}")
        time.sleep(86400) # Kuniga bir marta tekshiradi

# ================= SERVER VA POLLING =================
@app.route("/")
def index():
    return "Bot platformasi ishlamoqda!"

def bot_polling():
    while True:
        try:
            bot.infinity_polling(none_stop=True, timeout=30)
        except Exception as e:
            time.sleep(5)

def keep_alive():
    while True:
        try:
            requests.get(RENDER_URL, timeout=10)
        except Exception as e:
            pass
        time.sleep(300)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=app.run, args=("0.0.0.0", int(os.environ.get("PORT", 8080))), daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=check_subscriptions, daemon=True).start()
    bot_polling()
