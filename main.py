import os
import time
import sqlite3
import threading
import requests
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from fpdf import FPDF
from docx import Document

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
        KeyboardButton("🏆 Reyting natija"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📊 Dars davomatini boshlash"),
        KeyboardButton("📝 Yangi vazifa e'lon qilish"),
        KeyboardButton("🏆 Reyting va Hisobotlar"),
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

# ================= REYTING NATIJA (O'QUVCHILAR UCHUN) =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🏆 Reyting natija")
def student_rating(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.full_name, u.group_name, COUNT(w.id) as hw_cnt, COALESCE(ROUND(AVG(w.score), 1), 0) as avg_sc, COALESCE(SUM(w.score), 0) as total_sc
            FROM users u
            LEFT JOIN written_works w ON u.user_id = w.user_id AND w.score >= 0
            WHERE u.is_admin = 0 AND u.is_active = 1
            GROUP BY u.user_id
            ORDER BY total_sc DESC, avg_sc DESC
            LIMIT 20
        """)
        rows = c.fetchall()

    if not rows:
        return bot.send_message(message.chat.id, "📊 Hozircha reyting ma'lumotlari mavjud emas.")

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>A+ KIMYO — UMUMIY REYTING NATIJALARI</b>\n"]
    for idx, r in enumerate(rows):
        prefix = medals[idx] if idx < 3 else f"<b>{idx+1}.</b>"
        lines.append(f"{prefix} <b>{r[0]}</b> ({r[1]})\n   └ Vazifalar: {r[2]} ta | O'rtacha: {r[3]} | Jami ball: <b>{int(r[4])}</b>")

    bot.send_message(message.chat.id, "\n".join(lines))

# ================= REYTING VA HISOBOTLAR (EXCEL, PDF, WORD) =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "🏆 Reyting va Hisobotlar")
def admin_reports_menu(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("🏆 Reytingni xabar ko'rinishida ko'rish", callback_data="rep_view_rating"))
    kb.row(
        InlineKeyboardButton("📊 Reyting (Excel)", callback_data="exp_rating_xlsx"),
        InlineKeyboardButton("📕 Reyting (PDF)", callback_data="exp_rating_pdf"),
        InlineKeyboardButton("📘 Reyting (Word)", callback_data="exp_rating_docx")
    )
    kb.row(
        InlineKeyboardButton("📊 Davomat (Excel)", callback_data="exp_att_xlsx"),
        InlineKeyboardButton("📕 Davomat (PDF)", callback_data="exp_att_pdf"),
        InlineKeyboardButton("📘 Davomat (Word)", callback_data="exp_att_docx")
    )
    bot.send_message(message.chat.id, "📈 <b>Reyting natijalari va Davomat hisobotlari</b>\nKerakli bo'lim va fayl formatini tanlang:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "rep_view_rating")
def admin_view_rating_msg(call):
    bot.answer_callback_query(call.id)
    student_rating(call.message)

def clean_latin(text):
    replacements = {
        "‘": "'", "’": "'", "“": '"', "”": '"', "—": "-", "–": "-",
        "№": "No", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h"
    }
    res = str(text)
    for k, v in replacements.items():
        res = res.replace(k, v)
    return res.encode('latin-1', 'ignore').decode('latin-1')

@bot.callback_query_handler(func=lambda call: call.data.startswith("exp_"))
def export_report_handler(call):
    _, category, fmt = call.data.split("_")
    bot.answer_callback_query(call.id, "⏳ Fayl tayyorlanmoqda...")
    date_tag = datetime.now().strftime("%Y-%m-%d")

    try:
        with sqlite3.connect("database.db") as conn:
            if category == "rating":
                query = """
                SELECT 
                    u.full_name AS 'Ism Familiya',
                    u.group_name AS 'Guruh',
                    COUNT(w.id) AS 'Vazifalar',
                    COALESCE(ROUND(AVG(w.score), 1), 0) AS 'Ortacha ball',
                    COALESCE(CAST(SUM(w.score) AS INTEGER), 0) AS 'Jami ball',
                    u.missed_hw AS 'Qarz',
                    CASE WHEN u.is_active = 1 THEN 'Aktiv' ELSE 'Nofaol' END AS 'Holat'
                FROM users u
                LEFT JOIN written_works w ON u.user_id = w.user_id AND w.score >= 0
                WHERE u.is_admin = 0
                GROUP BY u.user_id
                ORDER BY SUM(w.score) DESC, AVG(w.score) DESC
                """
                title = f"A+ Kimyo - Reyting Natijalari ({date_tag})"
                base_name = f"Reyting_Natija_{date_tag}"
            else:
                query = """
                SELECT 
                    full_name AS 'Ism Familiya',
                    group_name AS 'Guruh',
                    session_date AS 'Sana',
                    checked_at AS 'Kelgan vaqti'
                FROM attendance
                ORDER BY session_date DESC, checked_at DESC
                """
                title = f"A+ Kimyo - Dars Davomati ({date_tag})"
                base_name = f"Davomat_Hisoboti_{date_tag}"

            df = pd.read_sql_query(query, conn)

        if df.empty:
            return bot.send_message(call.message.chat.id, "⚠️ Hozircha bazada ma'lumot mavjud emas.")

        file_path = f"/tmp/{base_name}.{fmt}"

        # 1. EXCEL FORMAT
        if fmt == "xlsx":
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Hisobot', index=False)

        # 2. WORD FORMAT (.docx)
        elif fmt == "docx":
            doc = Document()
            doc.add_heading(title, level=1)
            table = doc.add_table(rows=1, cols=len(df.columns))
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            for i, col_name in enumerate(df.columns):
                hdr_cells[i].text = str(col_name)
            for _, row in df.iterrows():
                row_cells = table.add_row().cells
                for i, val in enumerate(row):
                    row_cells[i].text = str(val)
            doc.save(file_path)

        # 3. PDF FORMAT (.pdf)
        elif fmt == "pdf":
            pdf = FPDF(orientation="L", unit="mm", format="A4")
            pdf.add_page()
            pdf.set_font("Arial", "B", 14)
            pdf.cell(0, 10, clean_latin(title), ln=True, align="C")
            pdf.ln(4)

            col_width = 275 / len(df.columns)
            pdf.set_font("Arial", "B", 9)
            for col in df.columns:
                pdf.cell(col_width, 8, clean_latin(col), border=1, align="C")
            pdf.ln()

            pdf.set_font("Arial", "", 9)
            for _, row in df.iterrows():
                for val in row:
                    pdf.cell(col_width, 8, clean_latin(val), border=1, align="C")
                pdf.ln()
            pdf.output(file_path)

        with open(file_path, "rb") as f:
            bot.send_document(call.message.chat.id, f, caption=f"✅ <b>{title}</b>")
        os.remove(file_path)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Fayl yaratishda xatolik: <code>{e}</code>")

# ================= ADMIN: GURUH ID LARINI SOZLASH =================
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
        "⚙️ <b>Guruh ID larini bog'lash</b>\n\nQaysi guruhning ID raqamini kiritmoqchisiz?", 
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
        return bot.send_message(uid, "❌ Noto'g'ri format! Guruh ID si faqat raqamlardan iborat bo'lishi kerak.")

    set_group_chat_id(group_name, chat_id)
    user_states.pop(uid, None)

    try:
        expire_unix = int(time.time()) + 3600
        invite = bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"Test_{group_name}",
            expire_date=expire_unix,
            member_limit=1
        )
        bot.send_message(
            uid, 
            f"✅ <b>{group_name}</b> muvaffaqiyatli bog'landi!\n🆔 Saqlangan ID: <code>{chat_id}</code>\n\n🔗 <b>Havola yaratildi:</b>\n{invite.invite_link}",
            reply_markup=admin_menu()
        )
    except Exception as e:
        bot.send_message(
            uid,
            f"⚠️ <b>ID saqlandi (<code>{chat_id}</code>), lekin havola yaratishda xatolik:</b>\n<code>{e}</code>",
            reply_markup=admin_menu()
        )

# ================= TO'LOV VA GURUHGA QO'SHISH =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    user_states[message.from_user.id] = "reg_name"
    bot.send_message(message.chat.id, "📝 Iltimos, Ism va Familiyangizni yozing:", reply_markup=cancel_kb())

@bot.message_handler(chat_types=["private"], content_types=['text'], func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_2(message):
    uid = message.from_user.id
    user_data[uid] = {"full_name": message.text.strip()}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("📱 Raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

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
        
    bot.send_message(uid, f"💳 To'lov uchun karta: <code>{KARTA_RAQAM}</code>\n👤 Karta egasi: <b>{KARTA_EGASI}</b>\n\n📸 To'lov chekini yuboring:", reply_markup=cancel_kb())

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
    bot.send_message(uid, "✅ Chek adminga yuborildi.", reply_markup=guest_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_decision(call):
    parts = call.data.split("_")
    action = parts[1]
    target_id = int(parts[2])
    
    if action == "ok":
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("4️⃣ 4-Guruh", callback_data=f"setgrp_{target_id}_4-Guruh"),
            InlineKeyboardButton("5️⃣ 5-Guruh", callback_data=f"setgrp_{target_id}_5-Guruh"),
            InlineKeyboardButton("6️⃣ 6-Guruh", callback_data=f"setgrp_{target_id}_6-Guruh"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"pay_no_{target_id}")
        )
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "O'quvchini qaysi guruhga qo'shamiz?", reply_markup=kb)
    else:
        try:
            bot.send_message(target_id, "❌ To'lov chekingiz rad etildi.")
        except Exception:
            pass
        try:
            bot.edit_message_caption("❌ TO'LOV RAD ETILDI", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
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
        invite_link = f"\n⚠️ Admin bilan bog'laning: {ADMIN_LICHKA}"
        admin_status_note = f"⚠️ <b>Diqqat:</b> <code>{group_name}</code> ID kiritilmagan!"
    else:
        try:
            bot.unban_chat_member(target_chat_id, target_id, only_if_banned=True)
            expire_unix = int(time.time()) + 86400
            invite = bot.create_chat_invite_link(
                chat_id=target_chat_id, 
                name=f"{group_name}_{target_id}", 
                expire_date=expire_unix,
                member_limit=1
            )
            invite_link = f"\n🔗 <b>Kirish havolasi:</b>\n{invite.invite_link}"
            admin_status_note = "✅ Havola yaratildi va yuborildi."
        except Exception as e:
            invite_link = f"\n⚠️ Admin bilan bog'laning: {ADMIN_LICHKA}"
            admin_status_note = f"⚠️ <b>Xato:</b> {e}"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_active = 1, group_name = ?, paid_until = ?, missed_hw = 0 WHERE user_id = ?", 
                  (group_name, expiry_date, target_id))
        conn.commit()

    try:
        bot.send_message(
            target_id, 
            f"🎉 <b>To'lovingiz tasdiqlandi!</b>\n\n👥 Guruhingiz: <b>{group_name}</b>\n⏳ Muddat: <b>{expiry_date}</b>\n{invite_link}", 
            reply_markup=student_menu()
        )
    except Exception:
        pass

    try:
        bot.edit_message_caption(
            f"✅ <b>TASDIQLANDI!</b>\n👤 ID: <code>{target_id}</code>\n👥 Guruh: <b>{group_name}</b>\n\n{admin_status_note}", 
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
        InlineKeyboardButton("4️⃣ 4-Guruh davomati", callback_data="attgrp_4-Guruh"),
        InlineKeyboardButton("5️⃣ 5-Guruh davomati", callback_data="attgrp_5-Guruh"),
        InlineKeyboardButton("6️⃣ 6-Guruh davomati", callback_data="attgrp_6-Guruh")
    )
    bot.send_message(message.chat.id, "📊 Qaysi guruh uchun davomat ochmoqchisiz?", reply_markup=kb)

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
            bot.send_message(s[0], f"⏰ <b>DAVOMAT TEKSHIRUVI!</b>\n👥 Guruh: <b>{group_name}</b>\n\n10 daqiqa ichida tasdiqlang:", reply_markup=kb)
            count += 1
        except Exception:
            pass

    try:
        bot.edit_message_text(f"✅ <b>{group_name}</b> uchun davomat ochildi! ({count} ta o'quvchi).", chat_id=call.message.chat.id, message_id=call.message.message_id)
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

    report = f"🛑 <b>DAVOMAT YAKUNLANDI ({group_name})</b>\n\n<b>Qatnashganlar ({len(present_rows)} ta):</b>\n{present_list}\n\n<b>Qatnashmaganlar ({len(absent_names)} ta):</b>\n{absent_list}"
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
        return bot.answer_callback_query(call.id, "❌ Vaqt tugagan!", show_alert=True)
    
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name FROM users WHERE user_id = ? AND is_active = 1", (uid,))
        user = c.fetchone()
        if not user:
            return bot.answer_callback_query(call.id, "🚫 Faol emassiz.", show_alert=True)
        
        c.execute("SELECT id FROM attendance WHERE user_id = ? AND session_id = ?", (uid, session_id))
        if c.fetchone():
            return bot.answer_callback_query(call.id, "⚠️ O'tib bo'lgansiz!", show_alert=True)
            
        c.execute("INSERT INTO attendance (user_id, full_name, group_name, session_date, session_id, checked_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, user[0], group_name, current_today, session_id, datetime.now().strftime("%H:%M")))
        conn.commit()
        
    bot.answer_callback_query(call.id, "✅ Davomat qabul qilindi!", show_alert=True)
    try:
        bot.edit_message_text("✅ <b>Davomatingiz tasdiqlandi!</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass

# ================= VAZIFA NAZORATI =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📝 Yangi vazifa e'lon qilish")
def announce_new_hw(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("4️⃣ 4-Guruhga vazifa", callback_data="newhw_4-Guruh"),
        InlineKeyboardButton("5️⃣ 5-Guruhga vazifa", callback_data="newhw_5-Guruh"),
        InlineKeyboardButton("6️⃣ 6-Guruhga vazifa", callback_data="newhw_6-Guruh")
    )
    bot.send_message(message.chat.id, "📝 Qaysi guruhga yangi vazifa berildi?", reply_markup=kb)

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
                bot.send_message(uid, "🚫 <b>Siz guruhdan chetlatildingiz!</b> (5 ta vazifa qoldirildi).")
            except Exception:
                pass
        conn.commit()

    kicked_text = "\n\n🚫 5 ta vazifa uchun chiqarildi:\n" + "\n".join([f"• {n}" for n in kicked_users]) if kicked_users else ""
    try:
        bot.edit_message_text(f"✅ <b>{group_name}</b> vazifa nazorati yoqildi!{kicked_text}", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass
    bot.answer_callback_query(call.id)

# ================= VAZIFA TOPSHIRISH =================
@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📸 Vazifa yuborish")
def ask_written_photo(message):
    uid = message.from_user.id
    is_active, _ = db_check_user(uid)
    if not is_active:
        return bot.send_message(uid, "🚫 Ruxsat yo'q.")
    user_states[uid] = "wait_hw_photo"
    bot.send_message(uid, "📸 Yechimlar tushirilgan rasmni yuboring:", reply_markup=cancel_kb())

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

    caption = f"📝 <b>YANGI VAZIFA!</b>\n👤 O'quvchi: {name} ({grp})\nBaho qo'ying (1-10):"
    for adm in db_get_admins():
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Vazifa yuborildi!", reply_markup=student_menu())

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
        bot.send_message(student_id, f"🎉 <b>Bahoyingiz:</b> <b>{score} ball</b>")
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
    text = (f"👤 <b>SHAXSIY KABINET</b>\n\n👤 F.I.Sh: {user_info[0]}\n📞 Tel: {user_info[1]}\n👥 Guruh: {user_info[2]}\n⏳ To'lov muddati: <b>{user_info[3] or 'Muddatsiz'}</b>\n⚠️ Qarz vazifalar: <b>{user_info[4]} / 5 ta</b>\n\n📊 Tekshirilgan: {stats[0]} ta\n📈 O'rtacha ball: {avg_score}")
    bot.send_message(uid, text)

# ================= ADMINLAR RO'YXATI =================
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
        return bot.send_message(message.chat.id, "O'quvchilar yo'q.")
    lines = [f"• <b>{u[0]}</b> | {u[1]} | Muddat: {u[2]} | Qarz: {u[3]} | {'✅ Aktiv' if u[4] else '❌ Nofaol'}" for u in users]
    bot.send_message(message.chat.id, "👥 <b>O'quvchilar:</b>\n\n" + "\n".join(lines))

@bot.message_handler(chat_types=["private"], func=lambda m: m.text == "📢 Xabar yuborish")
def broadcast_ask(message):
    _, is_admin = db_check_user(message.from_user.id)
    if not is_admin:
        return
    user_states[message.from_user.id] = "broad_text"
    bot.send_message(message.chat.id, "📢 Xabarni kiriting:", reply_markup=cancel_kb())

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
    bot.send_message(message.chat.id, f"✅ Yuborildi: {sent} ta.", reply_markup=admin_menu())

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
                            bot.send_message(uid, f"⚠️ <b>Diqqat, {name}!</b> Obuna tugashiga <b>{days_left} kun</b> qoldi.")
                        except Exception:
                            pass
                    elif days_left <= 0:
                        if target_chat_id:
                            try:
                                bot.unban_chat_member(target_chat_id, uid)
                            except Exception:
                                pass
                        c.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (uid,))
                        conn.commit()
                        try:
                            bot.send_message(uid, "🚫 <b>Obuna muddati tugadi.</b>", reply_markup=guest_menu())
                        except Exception:
                            pass
        except Exception as e:
            print(f"CRM xatosi: {e}")
        time.sleep(86400)

@app.route("/")
def index():
    return "A+ Kimyo Bot platformasi ishlamoqda!"

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
