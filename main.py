import os
import json
import sqlite3
import threading
from datetime import datetime
from flask import Flask, send_file
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo
)

# Hisobot kutubxonalari
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ================= SOZLAMALAR =================
BOT_TOKEN = "8636730483:AAFCHNjwvmaLZuRk3fd3sOIbN2QMYd-h_4g"
ADMIN_PAROL = "kimyo2026"
KANAL_USER = "@kimyo_sertifkat_uchun"
KARTA_RAQAM = "9860 3501 4209 7954"
KARTA_EGASI = "Azizbek Ibrohimov"

# Render avtomatik beradigan tashqi URL manzil
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://e-kimyo-kurs-bot.onrender.com")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_data = {}

# ================= MA'LUMOTLAR BAZASI =================
def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                phone TEXT DEFAULT '',
                group_name TEXT DEFAULT 'Umumiy guruh',
                is_admin INTEGER DEFAULT 0,
                joined_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                test_code INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                answers TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                test_code INTEGER,
                raw_correct INTEGER,
                rash_score REAL,
                percent REAL,
                daraja TEXT,
                checked_at TEXT
            )
        """)
        conn.commit()

def db_add_user(user_id, full_name, username):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, full_name, username or "", datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()

def db_is_admin(user_id):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row[0] == 1)

def db_set_admin(user_id):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

def db_get_admins():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE is_admin = 1")
        return [r[0] for r in c.fetchall()]

# ================= MENYULAR =================
def main_menu(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Elektron Titr Web App tugmasi
    titr_solve_btn = KeyboardButton(
        text="📊 Elektron Titr (43 talik MS)",
        web_app=WebAppInfo(url=f"{RENDER_URL}/titr?mode=solve")
    )
    kb.add(titr_solve_btn)
    kb.add(
        KeyboardButton("🏆 Umumiy Reyting"),
        KeyboardButton("📋 Mening natijalarim"),
        KeyboardButton("✍️ Kursga yozilish"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    if db_is_admin(user_id):
        kb.add(KeyboardButton("⚙️ Admin Panel"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    titr_create_btn = KeyboardButton(
        text="➕ Titr orqali Test Yaratish (43 ta)",
        web_app=WebAppInfo(url=f"{RENDER_URL}/titr?mode=create")
    )
    kb.add(titr_create_btn)
    kb.add(
        KeyboardButton("📑 Vazifa nazorati (Qilgan/Qilmagan)"),
        KeyboardButton("📊 Elektron Jadval (Excel/Word/PDF)"),
        KeyboardButton("📋 Testlar roʻyxati"),
        KeyboardButton("🗑 Testni oʻchirish"),
        KeyboardButton("📢 Hammaga xabar"),
        KeyboardButton("🔙 Asosiy menyu")
    )
    return kb

def cancel_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("❌ Bekor qilish"))
    return kb

# ================= BUYRUQLAR =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    db_add_user(uid, message.from_user.full_name, message.from_user.username)
    
    text = (
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>! 👋\n\n"
        f"🧪 <b>A+ Kimyo | Online Maktabi</b> platformasiga xush kelibsiz!\n\n"
        f"👇 Milliy Sertifikat (43 talik) testini topshirish uchun <b>«📊 Elektron Titr»</b> tugmasini bosing:"
    )
    bot.send_message(uid, text, reply_markup=main_menu(uid))

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    uid = message.from_user.id
    db_add_user(uid, message.from_user.full_name, message.from_user.username)
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PAROL:
        db_set_admin(uid)
        bot.send_message(uid, "✅ <b>Admin huquqi faollashtirildi!</b>", reply_markup=admin_menu())
    elif db_is_admin(uid):
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "🔒 Parolni kiriting: <code>/admin kimyo2026</code>")

@bot.message_handler(func=lambda m: m.text in ["❌ Bekor qilish", "🔙 Asosiy menyu"])
def cancel_action(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    bot.send_message(uid, "🏠 Asosiy menyu:", reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def open_admin(message):
    uid = message.from_user.id
    if db_is_admin(uid):
        bot.send_message(uid, "⚙️ <b>Admin Panel:</b>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    bot.send_message(message.chat.id, f"👨‍🏫 <b>Muallif:</b> Azizbek Ibrohimov\n📢 <b>Kanal:</b> {KANAL_USER}")

# ================= WEB APP (ELEKTRON TITR) MA'LUMOTLARINI QABUL QILISH =================
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    uid = message.from_user.id
    raw_json = message.web_app_data.data
    payload = json.loads(raw_json)
    
    mode = payload.get("mode")
    meta = payload.get("meta")
    answers = payload.get("answers")  # 43 talik massiv

    # 1. ADMIN YANGI TEST YARATGANDA
    if mode == "create":
        if not db_is_admin(uid):
            return bot.send_message(uid, "⚠️ Siz admin emassiz!")
        
        stored_keys = json.dumps(answers)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO tests (title, answers, created_at) VALUES (?, ?, ?)",
                (meta, stored_keys, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            code = c.lastrowid
            conn.commit()

        bot.send_message(
            uid,
            f"✅ <b>Yangi 43 talik MS Testi Titr orqali yaratildi!</b>\n\n"
            f"🔢 <b>Test kodi:</b> <code>{code}</code>\n"
            f"📘 <b>Mavzu:</b> {meta}\n\n"
            f"Oʻquvchilar endi <b>«📊 Elektron Titr»</b> tugmasini bosib, <code>{code}</code> kodi orqali javob yuborishlari mumkin!",
            reply_markup=admin_menu()
        )

    # 2. O'QUVCHI TEST TOPSHIRGANDA
    elif mode == "solve":
        if not meta.isdigit():
            return bot.send_message(uid, "⚠️ Test kodi faqat raqam boʻlishi kerak!", reply_markup=main_menu(uid))
        
        code = int(meta)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (code,))
            row = c.fetchone()

        if not row:
            return bot.send_message(uid, f"❌ <code>{code}</code>-kodli test topilmadi!", reply_markup=main_menu(uid))

        title = row[0]
        correct_keys = json.loads(row[1])

        raw_correct = 0
        rash_score = 0.0
        details = []

        for i in range(43):
            u = str(answers[i]).strip().lower()
            k = str(correct_keys[i]).strip().lower()
            q_num = i + 1

            # Rash ball taqsimoti
            if q_num <= 32:
                weight = 1.5
            elif q_num <= 35:
                weight = 2.2
            else:
                weight = 2.55

            if u != "" and u == k:
                raw_correct += 1
                rash_score += weight
                details.append(f"{q_num}.✅")
            else:
                details.append(f"{q_num}.❌")

        rash_score = round(rash_score, 2)
        percent = round((rash_score / 75.0) * 100, 1)

        if rash_score >= 70: daraja = "🏆 A+ daraja"
        elif rash_score >= 65: daraja = "🥇 A daraja"
        elif rash_score >= 60: daraja = "🥈 B+ daraja"
        elif rash_score >= 55: daraja = "🥈 B daraja"
        elif rash_score >= 50: daraja = "🥉 C+ daraja"
        elif rash_score >= 46: daraja = "🥉 C daraja"
        else: daraja = "📚 Sertifikat baliga yetmadi"

        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM results WHERE user_id = ? AND test_code = ?", (uid, code))
            if not c.fetchone():
                c.execute(
                    "INSERT INTO results (user_id, full_name, test_code, raw_correct, rash_score, percent, daraja, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (uid, message.from_user.full_name, code, raw_correct, rash_score, percent, daraja, datetime.now().strftime("%Y-%m-%d %H:%M"))
                )
                conn.commit()

        res_text = (
            f"📊 <b>MILLIY SERTIFIKAT NATIJASI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Oʻquvchi:</b> {message.from_user.full_name}\n"
            f"🔢 <b>Test kodi:</b> <code>{code}</code> ({title})\n"
            f"✅ <b>Toʻgʻri javoblar:</b> {raw_correct} / 43 ta\n"
            f"📈 <b>Rash bali:</b> <b>{rash_score} ball</b> ({percent}%)\n"
            f"🎖 <b>Daraja:</b> <b>{daraja}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n" + " | ".join(details) + f"\n\n📢 {KANAL_USER}"
        )
        bot.send_message(uid, res_text, reply_markup=main_menu(uid))

# ================= REYTING VA SHAXSIY NATIJALAR =================
@bot.message_handler(func=lambda m: m.text == "🏆 Umumiy Reyting")
def show_global_rating(message):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT full_name, rash_score, raw_correct, daraja FROM results ORDER BY rash_score DESC LIMIT 20")
        rows = c.fetchall()

    if not rows:
        return bot.send_message(message.chat.id, "📭 Hali hech kim test topshirmagan.")

    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 <b>A+ KIMYO | TOP-20 REYTING</b>\n━━━━━━━━━━━━━━━━━━\n"
    for idx, r in enumerate(rows, 1):
        m = medals[idx - 1] if idx <= 3 else f"<b>{idx}.</b>"
        text += f"{m} {r[0]} — <b>{r[1]} ball</b> ({r[2]}/43) | {r[3]}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📋 Mening natijalarim")
def my_results(message):
    uid = message.from_user.id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT test_code, raw_correct, rash_score, daraja, checked_at FROM results WHERE user_id = ? ORDER BY id DESC LIMIT 10", (uid,))
        rows = c.fetchall()

    if not rows:
        return bot.send_message(uid, "📭 Siz hali birorta ham test ishlamagansiz.")

    text = "📋 <b>SIZNING NATIJALARINGIZ:</b>\n━━━━━━━━━━━━━━━━━━\n"
    for r in rows:
        text += f"🔹 Test #{r[0]}: <b>{r[2]} ball</b> ({r[1]}/43) — {r[3]} <i>({r[4]})</i>\n"
    bot.send_message(uid, text)

# ================= ADMIN: VAZIFA NAZORATI (QILGAN / QILMAGAN) =================
@bot.message_handler(func=lambda m: m.text == "📑 Vazifa nazorati (Qilgan/Qilmagan)")
def ask_check_test_code(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "check_hw_code"
    bot.send_message(uid, "🔢 Qaysi test boʻyicha vazifa qilgan va qilmaganlarni koʻrmoqchisiz? <b>Test kodini</b> kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "check_hw_code")
def show_hw_status(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ Test kodini raqamda yozing!")
    code = int(message.text)

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title FROM tests WHERE test_code = ?", (code,))
        t = c.fetchone()
        if not t:
            return bot.send_message(uid, "❌ Bunday test topilmadi!")

        # Bajarilganlar
        c.execute("SELECT user_id, full_name, rash_score, raw_correct FROM results WHERE test_code = ? ORDER BY rash_score DESC", (code,))
        done_rows = c.fetchall()
        done_ids = {r[0] for r in done_rows}

        # Barcha o'quvchilar
        c.execute("SELECT user_id, full_name, phone FROM users WHERE is_admin = 0")
        all_users = c.fetchall()

    user_states.pop(uid, None)
    not_done = [u for u in all_users if u[0] not in done_ids]

    text = f"📑 <b>VAZIFA NAZORATI: Test #{code} ({t[0]})</b>\n━━━━━━━━━━━━━━━━━━\n"
    text += f"✅ <b>Vazifani bajarganlar ({len(done_rows)} ta):</b>\n"
    for r in done_rows:
        text += f"  • {r[1]} — <b>{r[2]} ball</b> ({r[3]}/43)\n"

    text += f"\n❌ <b>Vazifa qilmaganlar ({len(not_done)} ta):</b>\n"
    for u in not_done:
        text += f"  • {u[1]} (Tel: {u[2] or 'yoʻq'})\n"

    bot.send_message(uid, text, reply_markup=admin_menu())

# ================= ADMIN: ELEKTRON JADVAL (EXCEL, WORD, PDF) =================
@bot.message_handler(func=lambda m: m.text == "📊 Elektron Jadval (Excel/Word/PDF)")
def export_menu(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return

    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("📊 Excel (.xlsx)", callback_data="exp_excel"),
        InlineKeyboardButton("📄 Word (.docx)", callback_data="exp_word"),
        InlineKeyboardButton("📑 PDF (.pdf)", callback_data="exp_pdf")
    )
    bot.send_message(uid, "📥 <b>Oʻquvchilar reytingi va vazifa holatini qaysi formatda yuklab olasiz?</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("exp_"))
def handle_export(call):
    uid = call.from_user.id
    if not db_is_admin(uid): return
    fmt = call.data.split("_")[1]

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.full_name, u.phone, COALESCE(r.test_code, 0),
                   COALESCE(r.raw_correct, 0), COALESCE(r.rash_score, 0),
                   COALESCE(r.daraja, 'Vazifa qilinmagan'), COALESCE(r.checked_at, '-')
            FROM users u
            LEFT JOIN results r ON u.user_id = r.user_id
            WHERE u.is_admin = 0
            ORDER BY r.rash_score DESC
        """)
        rows = c.fetchall()

    if fmt == "excel":
        filename = "A_Plus_Kimyo_Hisobot.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Reyting va Vazifalar"

        headers = ["№", "O'quvchi F.I.Sh.", "Telefon", "Test Kodi", "To'g'ri Javob", "Rash Ball", "Holati / Daraja", "Topshirgan Vaqti"]
        ws.append(headers)

        # Sarlavha dizayni
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        for col in range(1, 9):
            cell = ws.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(horizontal="center")

        for idx, r in enumerate(rows, 1):
            holat = "Bajarilgan (" + r[5] + ")" if r[2] != 0 else "❌ Qilinmagan"
            ws.append([idx, r[0], r[1], r[2] or "-", f"{r[3]}/43" if r[2] else "-", r[4], holat, r[6]])

        wb.save(filename)
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📊 <b>Oʻquvchilar reytingi va vazifa holati (Excel jadval)</b>")

    elif fmt == "word":
        filename = "A_Plus_Kimyo_Hisobot.docx"
        doc = Document()
        doc.add_heading("A+ KIMYO | O'QUVCHILAR REYTINGI VA VAZIFA NAZORATI", 0)
        table = doc.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        hdr = table.rows[0].cells
        hdr[0].text = "№"
        hdr[1].text = "O'quvchi F.I.Sh."
        hdr[2].text = "Telefon"
        hdr[3].text = "To'g'ri"
        hdr[4].text = "Rash Ball"
        hdr[5].text = "Vazifa Holati"

        for idx, r in enumerate(rows, 1):
            row_cells = table.add_row().cells
            row_cells[0].text = str(idx)
            row_cells[1].text = str(r[0])
            row_cells[2].text = str(r[1] or "-")
            row_cells[3].text = f"{r[3]}/43" if r[2] else "-"
            row_cells[4].text = str(r[4])
            row_cells[5].text = "Bajarilgan" if r[2] != 0 else "Qilinmagan"

        doc.save(filename)
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📄 <b>Oʻquvchilar hisoboti (Word hujjat)</b>")

    elif fmt == "pdf":
        filename = "A_Plus_Kimyo_Hisobot.pdf"
        c_pdf = canvas.Canvas(filename, pagesize=letter)
        c_pdf.setFont("Helvetica-Bold", 14)
        c_pdf.drawString(50, 750, "A+ KIMYO | O'QUVCHILAR REYTINGI VA VAZIFA HOLATI")
        c_pdf.setFont("Helvetica", 10)
        y = 720
        for idx, r in enumerate(rows[:32], 1):
            status = "Bajarilgan" if r[2] != 0 else "Qilinmagan"
            line = f"{idx}. {r[0]} | Tel: {r[1] or '-'} | Ball: {r[4]} | Holati: {status}"
            c_pdf.drawString(50, y, line)
            y -= 20
        c_pdf.save()
        with open(filename, "rb") as f:
            bot.send_document(uid, f, caption="📑 <b>Oʻquvchilar hisoboti (PDF fayl)</b>")

    bot.answer_callback_query(call.id, "Tayyor!")

# ================= KURSGA YOZILISH VA TO'LOV CHEKI =================
@bot.message_handler(func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_1(message):
    uid = message.from_user.id
    user_states[uid] = "reg_name"
    bot.send_message(uid, "✍️ Ism va familiyangizni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_2(message):
    uid = message.from_user.id
    user_data[uid] = {"ism": message.text}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

@bot.message_handler(content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_3(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish": return cancel_action(message)
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET full_name = ?, phone = ? WHERE user_id = ?", (user_data[uid]["ism"], phone, uid))
        conn.commit()

    pay_text = (
        f"💳 <b>Toʻlov rekvizitlari:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔹 <b>Karta:</b> <code>9860350142097954</code>\n"
        f"🔹 <b>Egasi:</b> <b>{KARTA_EGASI}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📸 Toʻlovni qilib, <b>chek rasmini</b> shu yerga tashlang:"
    )
    bot.send_message(uid, pay_text, reply_markup=cancel_kb())

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_done(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    photo = message.photo[-1].file_id
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"), InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}"))
    caption = f"🆕 <b>YANGI TOʻLOV CHEKI</b>\n👤 Ism: {info.get('ism')}\n📞 Tel: {info.get('phone')}\n🆔 ID: <code>{uid}</code>"
    for adm in db_get_admins():
        try: bot.send_photo(adm, photo, caption=caption, reply_markup=kb)
        except Exception: pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek yuborildi! Tasdiqlangach xabar keladi.", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_decision(call):
    _, act, target = call.data.split("_")
    target = int(target)
    if act == "ok":
        bot.send_message(target, "🎉 <b>Tabriklaymiz! Toʻlovingiz tasdiqlandi!</b>")
        bot.edit_message_caption(caption=call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    else:
        bot.send_message(target, "❌ <b>Toʻlov cheki tasdiqlanmadi.</b>")
        bot.edit_message_caption(caption=call.message.caption + "\n\n❌ <b>RAD ETILDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    bot.answer_callback_query(call.id)

# Admin boshqa funksiyalari
@bot.message_handler(func=lambda m: m.text == "📋 Testlar roʻyxati")
def list_tests(message):
    if not db_is_admin(message.from_user.id): return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT test_code, title, created_at FROM tests ORDER BY test_code DESC LIMIT 15")
        rows = c.fetchall()
    if not rows: return bot.send_message(message.chat.id, "📭 Testlar yoʻq.")
    bot.send_message(message.chat.id, "📋 <b>Testlar:</b>\n" + "\n".join([f"🔹 Kod: <code>{r[0]}</code> — {r[1]} <i>({r[2]})</i>" for r in rows]))

@bot.message_handler(func=lambda m: m.text == "🗑 Testni oʻchirish")
def del_test(message):
    if not db_is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "del_t"
    bot.send_message(message.chat.id, "🗑 Oʻchiriladigan test kodini yuboring:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "del_t")
def del_test_do(message):
    uid = message.from_user.id
    if not message.text.isdigit(): return bot.send_message(uid, "Faqat raqam!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tests WHERE test_code = ?", (code,))
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Oʻchirildi!", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📢 Hammaga xabar")
def broadcast(message):
    if not db_is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "broad"
    bot.send_message(message.chat.id, "📢 Hammaga boradigan xabarni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(content_types=['text', 'photo', 'video', 'document'], func=lambda m: user_states.get(m.from_user.id) == "broad")
def broadcast_send(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish": return cancel_action(message)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [r[0] for r in c.fetchall()]
    user_states.pop(uid, None)
    sent = 0
    for u in users:
        try: bot.copy_message(u, message.chat.id, message.message_id); sent += 1
        except Exception: pass
    bot.send_message(uid, f"✅ {sent} ta oʻquvchiga yuborildi!", reply_markup=admin_menu())

# ================= FLASK WEB SERVER VA WEB APP =================
@app.route("/")
def index():
    return "A+ Kimyo Bot 24/7 ishlamoqda!"

@app.route("/titr")
def serve_titr():
    return send_file("titr.html")

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot.remove_webhook()
    print("Bot va Elektron Titr ishga tushdi...")
    bot.infinity_polling(none_stop=True, interval=0, timeout=20)
