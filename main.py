import asyncio
import io
import logging
import os
import sqlite3
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile
)

# PDF hisobot yaratish
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

BOT_TOKEN = os.getenv("BOT_TOKEN", "8636730483:AAFU8mRl0pH5AjmCASWETCNLy35q4lMpB-s")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6734050237"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@onlyibrohimov")

CARD_NUMBER = "9860 3501 4209 7954"
CARD_OWNER = "Azizbek Ibrohimov"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Barcha darslar bazasi (Siz bergan aniq ro'yxat)
DEFAULT_LESSONS = [
    # 1-BLOK: Dastlabki kimyo va atom
    ("dastlabki_5", "cat_1", "🧪 Dastlabki tushunchalar (5 ta mavzu)", 15000),
    ("mol", "cat_1", "⚖️ Modda miqdori mol", 15000),
    ("ekvivalent", "cat_1", "📐 Ekvivalent", 15000),
    ("kimyoviy_bog", "cat_1", "🔗 Kimyoviy bog'lanish", 15000),
    ("kimyoviy_reaksiya", "cat_1", "💥 Kimyoviy reaksiya", 15000),
    ("atom_tuzilishi", "cat_1", "⚛️ Atom tuzilishi", 15000),
    ("kvant_sonlar", "cat_1", "🔢 Kvant sonlar", 15000),
    ("yadro_reaksiya", "cat_1", "☢️ Yadro reaksiyalari", 15000),

    # 2-BLOK: Gazlar, eritmalar va muvozanat
    ("gazlar_aralashmasi", "cat_2", "💨 Gazlar aralashmasi", 15000),
    ("aralashmalar", "cat_2", "🥣 Aralashmalar", 15000),
    ("klapeyron", "cat_2", "🌡 Mendeleyev-Klapeyron tenglamasi", 15000),
    ("gibridlanish", "cat_2", "🔄 Gibridlanish", 15000),
    ("eritmalar_to'liq", "cat_2", "💧 Eritmalar (Foiz, molyar, molyal, normal, titr)", 15000),
    ("eruvchanlik", "cat_2", "🧊 Eruvchanlik", 15000),
    ("elektroliz", "cat_2", "⚡️ Elektroliz", 15000),
    ("dissotsiyalanish", "cat_2", "⚡️ Dissotsiyalanish", 15000),
    ("suv_ioni", "cat_2", "💧 Suvning ion ko'paytmasi va pH", 15000),
    ("oleum", "cat_2", "🧪 Oleum masalalari", 15000),
    ("plastinka", "cat_2", "🔩 Plastinka masalalari", 15000),

    # 3-BLOK: Organik kimyo
    ("alkanlar", "cat_3", "🛢 Alkanlar", 15000),
    ("alkenlar", "cat_3", "🌿 Alkenlar", 15000),
    ("alkinlar", "cat_3", "🔥 Alkinlar", 15000),
    ("alkadiyenlar", "cat_3", "⛓ Alkadiyenlar", 15000),
    ("aromatik", "cat_3", "💠 Aromatik uglevodorodlar (Arenlar)", 15000),
    ("spirtlar", "cat_3", "🍷 Spirtlar", 15000),
    ("aminokislotalar", "cat_3", "🧬 Aminokislotalar", 15000),

    # 4-BLOK: Milliy Sertifikat Maxsus Qism
    ("masala_41", "cat_4", "🎯 41-masala ishlash usuli & namuna tahlili", 30000),
    ("band_42", "cat_4", "🔥 42-band murakkab masalalar tahlili", 50000),
    ("analitik_43", "cat_4", "🔬 43 - Analitik kimyo masalalari", 30000),
]

CATEGORIES = {
    "cat_1": "🧪 Dastlabki kimyo & Atom",
    "cat_2": "⚗️ Gazlar, Eritmalar & Reaksiyalar",
    "cat_3": "🧬 Organik kimyo",
    "cat_4": "🎯 Milliy Sertifikat Maxsus (41, 42, 43)"
}

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            joined_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_id TEXT,
            item_name TEXT,
            price INTEGER,
            status TEXT,
            created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id TEXT PRIMARY KEY,
            category TEXT,
            title TEXT,
            price INTEGER,
            theory_file_id TEXT,
            problem_file_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_purchases (
            user_id INTEGER,
            lesson_id TEXT,
            purchased_at TEXT,
            PRIMARY KEY (user_id, lesson_id)
        )
    """)

    # Darslarni bazaga kiritish (agar bo'sh bo'lsa)
    for lid, cat, title, price in DEFAULT_LESSONS:
        cursor.execute("""
            INSERT OR IGNORE INTO lessons (id, category, title, price, theory_file_id, problem_file_id)
            VALUES (?, ?, ?, ?, NULL, NULL)
        """, (lid, cat, title, price))

    # Birlamchi test kalitlari
    cursor.execute("SELECT value FROM settings WHERE key = 'test_keys_30'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES ('test_keys_30', ?)",
            ("abcdabcdabcdabcdabcdabcdabcdab",)
        )

    conn.commit()
    conn.close()

def add_user(user_id: int, full_name: str, username: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, full_name, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_lessons_by_category(category_key: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, price, theory_file_id, problem_file_id FROM lessons WHERE category = ?", (category_key,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_lesson_by_id(lesson_id: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, price, theory_file_id, problem_file_id FROM lessons WHERE id = ?", (lesson_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_lesson_video(lesson_id: str, video_type: str, file_id: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    field = "theory_file_id" if video_type == "theory" else "problem_file_id"
    cursor.execute(f"UPDATE lessons SET {field} = ? WHERE id = ?", (file_id, lesson_id))
    conn.commit()
    conn.close()

def record_purchase(user_id: int, lesson_id: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_purchases (user_id, lesson_id, purchased_at)
        VALUES (?, ?, ?)
    """, (user_id, lesson_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def user_has_lesson(user_id: int, lesson_id: str) -> bool:
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_purchases WHERE user_id = ? AND lesson_id = ?", (user_id, lesson_id))
    row = cursor.fetchone()
    conn.close()
    return bool(row)

def get_user_purchases(user_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.id, l.title, l.theory_file_id, l.problem_file_id 
        FROM user_purchases up
        JOIN lessons l ON up.lesson_id = l.id
        WHERE up.user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def record_payment(user_id: int, item_id: str, item_name: str, price: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments (user_id, item_id, item_name, price, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (user_id, item_id, item_name, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    p_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return p_id

def get_payment(payment_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, item_id, item_name, price, status FROM payments WHERE id = ?", (payment_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_payment_status(payment_id: int, status: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment_id))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'approved'")
    approved = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
    pending = cursor.fetchone()[0]
    conn.close()
    return {"users": total_users, "approved": approved, "pending": pending}

def get_setting(key: str, default: str = ""):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, val: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# Holatlar (States)
class PaymentState(StatesGroup):
    waiting_for_receipt = State()

class Test30State(StatesGroup):
    waiting_for_answers = State()

class AdminVideoUploadState(StatesGroup):
    choosing_type = State()
    waiting_for_video = State()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_new_keys = State()

# 30 talik test PDF hisoboti
def generate_test_pdf(full_name: str, user_id: int, user_answers: str, correct_keys: str):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=colors.HexColor("#0f172a"), alignment=1
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=11, leading=14, textColor=colors.HexColor("#2563eb"), alignment=1
    )
    info_style = ParagraphStyle(
        'InfoText', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=15, textColor=colors.HexColor("#1e293b")
    )

    story.append(Paragraph("A+ KIMYO TA'LIM PLATFORMASI", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("30 TALIK TEST TAHLILI VA SERTIFIKATI", subtitle_style))
    story.append(Spacer(1, 15))

    correct_count = 0
    results_detail = []
    for idx, (u, c) in enumerate(zip(user_answers.upper(), correct_keys.upper()), start=1):
        is_correct = (u == c)
        if is_correct:
            correct_count += 1
        results_detail.append((idx, u, c, "+" if is_correct else "-"))

    percentage = round((correct_count / 30) * 100, 1)
    total_ball = round(correct_count * 3.1, 1)

    info_data = [
        [Paragraph(f"<b>O'quvchi:</b> {full_name}", info_style), Paragraph(f"<b>Sana:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", info_style)],
        [Paragraph(f"<b>Telegram ID:</b> {user_id}", info_style), Paragraph(f"<b>To'g'ri javoblar:</b> {correct_count} / 30 ta ({percentage}%)", info_style)],
        [Paragraph("<b>Fan:</b> Kimyo", info_style), Paragraph(f"<b>To'plangan ball:</b> <b>{total_ball}</b> / 93.0 ball", info_style)]
    ]
    info_table = Table(info_data, colWidths=[260, 260])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 16))

    table_header = ["№", "Siz", "Kalit", "Holat", "№", "Siz", "Kalit", "Holat"]
    table_rows = [table_header]
    for i in range(15):
        left = results_detail[i]
        right = results_detail[i + 15]
        table_rows.append([str(left[0]), left[1], left[2], left[3], str(right[0]), right[1], right[2], right[3]])

    detail_table = Table(table_rows, colWidths=[35, 45, 45, 45, 35, 45, 45, 45])
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ]
    for r_idx in range(1, 16):
        for col_flag, col_idx in [(results_detail[r_idx - 1][3], 3), (results_detail[r_idx + 14][3], 7)]:
            if col_flag == "+":
                t_style.append(('BACKGROUND', (col_idx, r_idx), (col_idx, r_idx), colors.HexColor("#dcfce7")))
                t_style.append(('TEXTCOLOR', (col_idx, r_idx), (col_idx, r_idx), colors.HexColor("#166534")))
            else:
                t_style.append(('BACKGROUND', (col_idx, r_idx), (col_idx, r_idx), colors.HexColor("#fee2e2")))
                t_style.append(('TEXTCOLOR', (col_idx, r_idx), (col_idx, r_idx), colors.HexColor("#991b1b")))

    detail_table.setStyle(TableStyle(t_style))
    story.append(detail_table)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue(), correct_count, percentage, total_ball

# Asosiy tugmalar menyusi
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Video Darslar Katalogi")],
            [KeyboardButton(text="🎯 Maxsus Masalalar (41, 42, 43)")],
            [KeyboardButton(text="📝 30 talik test tekshirish (PDF)")],
            [KeyboardButton(text="📁 Xarid qilingan darslarim"), KeyboardButton(text="🔴 Jonli dars (30 000)")],
            [KeyboardButton(text="👨‍🏫 Ustoz haqida"), KeyboardButton(text="📞 Bog'lanish")]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    full_name = message.from_user.full_name or "O'quvchi"
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    add_user(user_id, full_name, username)

    welcome = (
        f"Assalomu alaykum, <b>{full_name}</b>! 👋\n\n"
        f"🧪 <b>A+ Kimyo</b> rasmiy ta'lim va imtihon botiga xush kelibsiz!\n\n"
        f"Bu yerda siz:\n"
        f"• <b>Nazariya va masala</b> video darslarini to'g'ridan-to'g'ri xarid qilib ko'rishingiz;\n"
        f"• <b>41, 42, 43-maxsus masalalar</b> tahlilini o'rganishingiz;\n"
        f"• <b>30 talik test</b> topshirib, rasmiy PDF hisobot olishingiz mumkin.\n\n"
        f"Kerakli bo'limni tanlang 👇"
    )
    await message.answer(welcome, parse_mode="HTML", reply_markup=get_main_keyboard())

# 1. Darslar katalogi toifalari
@dp.message(F.text == "📚 Video Darslar Katalogi")
async def catalog_categories_handler(message: types.Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 1. Dastlabki kimyo & Atom (15 000)", callback_data="show_cat:cat_1")],
            [InlineKeyboardButton(text="⚗️ 2. Gazlar, Eritmalar & Reaksiyalar (15 000)", callback_data="show_cat:cat_2")],
            [InlineKeyboardButton(text="🧬 3. Organik kimyo (15 000)", callback_data="show_cat:cat_3")],
            [InlineKeyboardButton(text="🎯 4. Milliy Sertifikat Maxsus Masalalar", callback_data="show_cat:cat_4")]
        ]
    )
    await message.answer(
        "📚 <b>Kimyo video darslari (Nazariya + Masala darsi):</b>\n\n"
        "O'zingizga kerakli bo'limni tanlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.message(F.text == "🎯 Maxsus Masalalar (41, 42, 43)")
async def special_tasks_handler(message: types.Message):
    await show_category_lessons(message, "cat_4")

@dp.callback_query(F.data.startswith("show_cat:"))
async def category_callback_handler(callback: types.CallbackQuery):
    cat_key = callback.data.split(":")[1]
    await show_category_lessons(callback.message, cat_key, edit=True)
    await callback.answer()

async def show_category_lessons(message: types.Message, cat_key: str, edit: bool = False):
    lessons = get_lessons_by_category(cat_key)
    cat_title = CATEGORIES.get(cat_key, "Mavzular")

    kb_buttons = []
    for lid, title, price, th, pr in lessons:
        status_icon = "🎬" if (th or pr) else "⏳"
        btn_text = f"{status_icon} {title} — {price:,} so'm"
        kb_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_lesson:{lid}")])

    kb_buttons.append([InlineKeyboardButton(text="🔙 Boshqa bo'limlar", callback_data="back_to_cats")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    text = (
        f"📂 <b>{cat_title}</b>\n\n"
        f"Har bir mavzu <b>Nazariya va Masala</b> darslarini o'z ichiga oladi.\n"
        f"Mavzuni tanlang va xarid qiling 👇"
    )
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats_handler(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 1. Dastlabki kimyo & Atom (15 000)", callback_data="show_cat:cat_1")],
            [InlineKeyboardButton(text="⚗️ 2. Gazlar, Eritmalar & Reaksiyalar (15 000)", callback_data="show_cat:cat_2")],
            [InlineKeyboardButton(text="🧬 3. Organik kimyo (15 000)", callback_data="show_cat:cat_3")],
            [InlineKeyboardButton(text="🎯 4. Milliy Sertifikat Maxsus Masalalar", callback_data="show_cat:cat_4")]
        ]
    )
    await callback.message.edit_text(
        "📚 <b>Kimyo video darslari (Nazariya + Masala darsi):</b>\n\nBo'limni tanlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

# Dars ma'lumotlari va xarid oynasi
@dp.callback_query(F.data.startswith("view_lesson:"))
async def view_lesson_handler(callback: types.CallbackQuery):
    lid = callback.data.split(":")[1]
    lesson = get_lesson_by_id(lid)
    if not lesson:
        await callback.answer("Dars topilmadi!", show_alert=True)
        return

    _, title, price, theory_id, problem_id = lesson
    user_id = callback.from_user.id
    is_purchased = user_has_lesson(user_id, lid)

    text = (
        f"📖 <b>Mavzu:</b> {title}\n"
        f"💰 <b>Narxi:</b> {price:,} so'm\n"
        f"📦 <b>Tarkibi:</b> To'liq Nazariya darsi + Masala yechish darsi\n\n"
    )

    btns = []
    if is_purchased:
        text += "✅ <i>Siz ushbu darsni xarid qilgansiz! Quyidagi tugma orqali videolarni ko'rishingiz mumkin:</i>"
        btns.append([InlineKeyboardButton(text="▶️ Videolarni ko'rish", callback_data=f"play_lesson:{lid}")])
    else:
        text += "Videolarni bot ichida ko'rish uchun to'lov qiling 👇"
        btns.append([InlineKeyboardButton(text=f"💳 Xarid qilish ({price:,} so'm)", callback_data=f"buy_lesson:{lid}")])

    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_cats")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await callback.answer()

# Darsni sotib olish jarayoni
@dp.callback_query(F.data.startswith("buy_lesson:"))
async def buy_lesson_callback(callback: types.CallbackQuery, state: FSMContext):
    lid = callback.data.split(":")[1]
    lesson = get_lesson_by_id(lid)
    if not lesson:
        return

    _, title, price, _, _ = lesson
    await state.update_data(item_id=lid, item_name=title, item_price=price)
    await state.set_state(PaymentState.waiting_for_receipt)

    text = (
        f"💳 <b>To'lov ma'lumotlari:</b>\n"
        f"📚 <b>Mavzu:</b> {title}\n"
        f"💰 <b>Summa:</b> {price:,} so'm\n\n"
        f"💳 <b>Karta raqam:</b> <code>{CARD_NUMBER}</code> (ustiga bosib nusxalang)\n"
        f"👤 <b>Karta egasi:</b> {CARD_OWNER}\n\n"
        f"❗️ <b>To'lovni amalga oshirib, chek rasmini (skrinshot) shu yerga yuboring:</b>"
    )
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb)
    await callback.answer()

# Jonli dars (30 000)
@dp.message(F.text == "🔴 Jonli dars (30 000)")
async def live_lesson_handler(message: types.Message, state: FSMContext):
    await state.update_data(item_id="live_lesson", item_name="🔴 Jonli Dars & Savol-Javob", item_price=30000)
    await state.set_state(PaymentState.waiting_for_receipt)

    text = (
        f"🔴 <b>Jonli Darsga yozilish (Zoom / Telegram):</b>\n\n"
        f"Ustoz bilan jonli savol-javob, murakkab masalalar tahlili.\n"
        f"💰 <b>Narxi:</b> 30 000 so'm\n\n"
        f"💳 <b>Karta:</b> <code>{CARD_NUMBER}</code>\n"
        f"👤 <b>Egasi:</b> {CARD_OWNER}\n\n"
        f"To'lov qilib, chekni yuboring 👇"
    )
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await message.answer(text, parse_mode="HTML", reply_markup=cancel_kb)

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Jarayon bekor qilindi.", reply_markup=get_main_keyboard())

# Chekni qabul qilish va adminga yuborish
@dp.message(PaymentState.waiting_for_receipt, F.photo)
async def receive_receipt_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("item_id", "lesson")
    item_name = data.get("item_name", "Dars")
    price = data.get("item_price", 15000)

    user_id = message.from_user.id
    user_name = message.from_user.full_name or "O'quvchi"
    username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    photo_id = message.photo[-1].file_id

    pay_id = record_payment(user_id, item_id, item_name, price)
    await state.clear()

    await message.answer(
        "✅ <b>To'lov chekingiz qabul qilindi!</b>\n\n"
        "Administrator tekshirishi bilan video darslar botingizga avtomatik yuboriladi. ⏳",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_ok:{pay_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_no:{pay_id}")
            ]
        ]
    )

    admin_caption = (
        f"🧾 <b>YANGI TO'LOV CHEKI #{pay_id}</b>\n"
        f"────────────────────────\n"
        f"📚 <b>Mavzu:</b> {item_name}\n"
        f"💰 <b>Summa:</b> {price:,} so'm\n"
        f"👤 <b>O'quvchi:</b> {user_name}\n"
        f"💬 <b>Telegram:</b> {username}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"────────────────────────\n"
        f"Tasdiqlaysizmi?"
    )

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=admin_caption,
        parse_mode="HTML",
        reply_markup=admin_kb
    )

# Admin to'lovni tasdiqlaganda
@dp.callback_query(F.data.startswith("pay_ok:"))
async def approve_payment_handler(callback: types.CallbackQuery):
    pay_id = int(callback.data.split(":")[1])
    pay = get_payment(pay_id)
    if not pay:
        await callback.answer("To'lov topilmadi!")
        return

    _, user_id, item_id, item_name, price, status = pay
    if status == "approved":
        await callback.answer("Allaqachon tasdiqlangan!")
        return

    update_payment_status(pay_id, "approved")

    # Agar maxsus dars bo'lsa
    if item_id != "live_lesson":
        record_purchase(user_id, item_id)
        lesson = get_lesson_by_id(item_id)
        theory_id = lesson[3] if lesson else None
        problem_id = lesson[4] if lesson else None

        student_text = (
            f"🎉 <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"📚 <b>Mavzu:</b> {item_name}\n\n"
            f"Videolar quyida shaxsiy xabar tarzida taqdim etilmoqda 👇"
        )
        await bot.send_message(chat_id=user_id, text=student_text, parse_mode="HTML")

        # Nazariya videosi bormi?
        if theory_id:
            await bot.send_video(
                chat_id=user_id,
                video=theory_id,
                caption=f"📘 <b>Nazariya darsi:</b> {item_name}\n<i>Faqat siz uchun! O'g'irlash va uzatishdan himoyalangan.</i>",
                parse_mode="HTML",
                protect_content=True
            )
        # Masala videosi bormi?
        if problem_id:
            await bot.send_video(
                chat_id=user_id,
                video=problem_id,
                caption=f"📝 <b>Masala yechish darsi:</b> {item_name}\n<i>Faqat siz uchun! O'g'irlash va uzatishdan himoyalangan.</i>",
                parse_mode="HTML",
                protect_content=True
            )

        if not theory_id and not problem_id:
            await bot.send_message(
                chat_id=user_id,
                text="⏳ <i>Dars videosi ustoz tomonidan suratga olinmoqda va tez orada botga yuklanishi bilan sizga to'g'ridan-to'g'ri tashlab beriladi!</i>",
                parse_mode="HTML"
            )
    else:
        # Jonli dars havolasi
        channel_link = get_setting("channel_link", "https://t.me/onlyibrohimov")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Jonli Dars Guruhiga Kirish", url=channel_link)]])
        await bot.send_message(
            chat_id=user_id,
            text="🎉 <b>Jonli dars to'lovi tasdiqlandi!</b>\n\nQuyidagi havola orqali efir guruhiga kiring 👇",
            parse_mode="HTML",
            reply_markup=kb
        )

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n🟢 <b>TASDIQLANDI VA YUBORILDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("Tasdiqlandi!")

@dp.callback_query(F.data.startswith("pay_no:"))
async def reject_payment_handler(callback: types.CallbackQuery):
    pay_id = int(callback.data.split(":")[1])
    pay = get_payment(pay_id)
    if pay:
        update_payment_status(pay_id, "rejected")
        try:
            await bot.send_message(
                chat_id=pay[1],
                text=f"❌ To'lovingiz tasdiqlanmadi. Iltimos, administrator bilan bog'laning: {ADMIN_USERNAME}"
            )
        except Exception:
            pass

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n🔴 <b>RAD ETILDI</b>",
        parse_mode="HTML"
    )
    await callback.answer("Rad etildi!")

# O'quvchi xarid qilgan darslarini qayta ko'rishi
@dp.message(F.text == "📁 Xarid qilingan darslarim")
async def my_purchased_lessons_handler(message: types.Message):
    purchases = get_user_purchases(message.from_user.id)
    if not purchases:
        await message.answer("Sizda hali xarid qilingan darslar mavjud emas. Katalogdan dars tanlashingiz mumkin!")
        return

    text = "📁 <b>Siz xarid qilgan darslar:</b>\n\nQayta ko'rmoqchi bo'lgan mavzuni tanlang 👇"
    btns = []
    for lid, title, th, pr in purchases:
        btns.append([InlineKeyboardButton(text=f"▶️ {title}", callback_data=f"play_lesson:{lid}")])

    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("play_lesson:"))
async def play_lesson_handler(callback: types.CallbackQuery):
    lid = callback.data.split(":")[1]
    lesson = get_lesson_by_id(lid)
    if not lesson:
        return

    _, title, _, th_id, pr_id = lesson
    user_id = callback.from_user.id

    if not th_id and not pr_id:
        await callback.answer("Ushbu dars videosi tez orada yuklanadi!", show_alert=True)
        return

    await callback.message.answer(f"🎬 <b>{title}</b> darsi videolari yuborilmoqda...")

    if th_id:
        await bot.send_video(
            chat_id=user_id,
            video=th_id,
            caption=f"📘 <b>Nazariya darsi:</b> {title}",
            parse_mode="HTML",
            protect_content=True
        )
    if pr_id:
        await bot.send_video(
            chat_id=user_id,
            video=pr_id,
            caption=f"📝 <b>Masala yechish darsi:</b> {title}",
            parse_mode="HTML",
            protect_content=True
        )
    await callback.answer()

# ==================== ADMIN: VIDEOLARNI BOTGA YUKLASH TIZIMI ====================
@dp.message(Command("admin"))
async def admin_main_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📹 Dars videosini yuklash (Nazariya/Masala)", callback_data="admin_upload_video")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🔑 30 talik kalitni o'zgartirish", callback_data="admin_change_keys")],
            [InlineKeyboardButton(text="🔗 Jonli dars havolasini yangilash", callback_data="admin_change_link")],
            [InlineKeyboardButton(text="📢 Barchaga xabar yuborish", callback_data="admin_broadcast")]
        ]
    )
    await message.answer("👑 <b>Ustoz & Admin Boshqaruv Paneli:</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "admin_upload_video")
async def admin_start_upload(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. Dastlabki kimyo & Atom", callback_data="adm_cat:cat_1")],
            [InlineKeyboardButton(text="2. Gazlar & Eritmalar", callback_data="adm_cat:cat_2")],
            [InlineKeyboardButton(text="3. Organik kimyo", callback_data="adm_cat:cat_3")],
            [InlineKeyboardButton(text="4. Maxsus masalalar (41, 42, 43)", callback_data="adm_cat:cat_4")]
        ]
    )
    await callback.message.edit_text("Qaysi bo'limdagi darsga video yuklamoqchisiz?", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_cat:"))
async def admin_select_cat(callback: types.CallbackQuery):
    cat_key = callback.data.split(":")[1]
    lessons = get_lessons_by_category(cat_key)

    btns = []
    for lid, title, price, th, pr in lessons:
        th_icon = "✅" if th else "❌"
        pr_icon = "✅" if pr else "❌"
        btns.append([InlineKeyboardButton(text=f"{title} (N:{th_icon} M:{pr_icon})", callback_data=f"adm_les:{lid}")])

    btns.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_upload_video")])
    await callback.message.edit_text("Videoni biriktirmoqchi bo'lgan mavzuni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_les:"))
async def admin_select_lesson_type(callback: types.CallbackQuery, state: FSMContext):
    lid = callback.data.split(":")[1]
    lesson = get_lesson_by_id(lid)
    if not lesson:
        return

    await state.update_data(target_lesson_id=lid, target_title=lesson[1])
    await state.set_state(AdminVideoUploadState.choosing_type)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📘 1. Nazariya videosi", callback_data="vid_type:theory")],
            [InlineKeyboardButton(text="📝 2. Masala yechish videosi", callback_data="vid_type:problem")]
        ]
    )
    await callback.message.edit_text(f"<b>{lesson[1]}</b>\n\nQaysi dars videosini yuklamoqchisiz?", parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@dp.callback_query(AdminVideoUploadState.choosing_type, F.data.startswith("vid_type:"))
async def admin_wait_video(callback: types.CallbackQuery, state: FSMContext):
    v_type = callback.data.split(":")[1]
    await state.update_data(video_type=v_type)
    await state.set_state(AdminVideoUploadState.waiting_for_video)

    type_name = "Nazariya" if v_type == "theory" else "Masala yechish"
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

    await callback.message.answer(
        f"📹 <b>{type_name} darsi videosini shu yerga yuboring:</b>\n\n"
        f"Telegramda videoni oddiygina yuborsangiz, bot uni avtomat saqlab oladi.",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(AdminVideoUploadState.waiting_for_video, F.video)
async def admin_save_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lid = data.get("target_lesson_id")
    v_type = data.get("video_type")
    title = data.get("target_title")
    file_id = message.video.file_id

    update_lesson_video(lid, v_type, file_id)
    await state.clear()

    type_str = "Nazariya videosi" if v_type == "theory" else "Masala yechish videosi"
    await message.answer(
        f"✅ <b>Muvaffaqiyatli saqlandi!</b>\n\n"
        f"Mavzu: <b>{title}</b>\n"
        f"Turi: <b>{type_str}</b>\n\n"
        f"Endi ushbu mavzuni xarid qilgan o'quvchilarga video avtomatik yetkazib beriladi!",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

# 30 talik test topshirish
@dp.message(F.text == "📝 30 talik test tekshirish (PDF)")
async def test_30_start(message: types.Message, state: FSMContext):
    await state.set_state(Test30State.waiting_for_answers)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await message.answer(
        "📝 <b>30 talik test javoblaringizni yuboring!</b>\n\n"
        "Javoblarni ketma-ket 30 ta harf ko'rinishida yozing (A, B, C, D):\n"
        "Masalan: <code>abcdabcdabcdabcdabcdabcdabcdab</code>\n\n"
        "Bot sizga darhol PDF hisobot tayyorlab beradi! 📄",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

@dp.message(Test30State.waiting_for_answers)
async def test_30_process(message: types.Message, state: FSMContext):
    user_keys = message.text.strip().lower().replace(" ", "").replace("\n", "")
    if len(user_keys) != 30:
        await message.answer(f"❗️ Siz kiritgan javoblar soni: <b>{len(user_keys)} ta</b>. Testda qat'iy 30 ta bo'lishi kerak:")
        return

    official_keys = get_setting("test_keys_30", "abcdabcdabcdabcdabcdabcdabcdab")
    await message.answer("⏳ PDF hisobot tayyorlanmoqda...")

    pdf_bytes, correct, percentage, total_ball = generate_test_pdf(
        full_name=message.from_user.full_name or "O'quvchi",
        user_id=message.from_user.id,
        user_answers=user_keys,
        correct_keys=official_keys
    )
    await state.clear()

    caption = (
        f"🎉 <b>TEST NATIJANGIZ TAYYOR!</b>\n"
        f"────────────────────────\n"
        f"👤 O'quvchi: <b>{message.from_user.full_name}</b>\n"
        f"✅ To'g'ri: <b>{correct} / 30 ta</b> ({percentage}%)\n"
        f"🎯 Ball: <b>{total_ball} ball</b>\n"
        f"────────────────────────"
    )
    pdf_file = BufferedInputFile(pdf_bytes, filename=f"Natija_{message.from_user.id}.pdf")
    await message.answer_document(document=pdf_file, caption=caption, parse_mode="HTML", reply_markup=get_main_keyboard())

# Statistika va boshqa admin funksiyalar
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    s = get_stats()
    text = (
        "📊 <b>BOT STATISTIKASI:</b>\n"
        "────────────────────────\n"
        f"👥 O'quvchilar: <b>{s['users']} ta</b>\n"
        f"✅ Tasdiqlangan to'lovlar: <b>{s['approved']} ta</b>\n"
        f"⏳ Kutilayotgan cheklar: <b>{s['pending']} ta</b>\n"
        "────────────────────────"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_change_keys")
async def admin_change_keys(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.waiting_for_new_keys)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer("Yangi 30 talik test kalitini yozing (30 ta harf):", reply_markup=cancel_kb)
    await callback.answer()

@dp.message(AdminState.waiting_for_new_keys)
async def process_new_keys(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    k = message.text.strip().lower().replace(" ", "")
    if len(k) != 30:
        await message.answer("Kalit 30 ta bo'lishi shart!")
        return
    set_setting("test_keys_30", k)
    await state.clear()
    await message.answer("✅ Yangi kalit saqlandi!", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "admin_change_link")
async def admin_change_link(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    cur = get_setting("channel_link", "https://t.me/onlyibrohimov")
    await callback.message.answer(f"Hozirgi havola: {cur}\n\nYangi havola yuboring:")
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.waiting_for_broadcast)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer("Barchaga yuboriladigan xabarni yozing:", reply_markup=cancel_kb)
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_all_users()
    count = 0
    await message.answer(f"⏳ {len(users)} ta o'quvchiga yuborilmoqda...")
    for uid in users:
        try:
            await message.send_copy(chat_id=uid)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await state.clear()
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yetkazildi!", reply_markup=get_main_keyboard())

@dp.message(F.text == "👨‍🏫 Ustoz haqida")
async def teacher_info(message: types.Message):
    await message.answer(
        "👨‍🏫 <b>Ustoz haqida:</b>\n\n"
        "• Azizbek Ibrohimov — Kimyo fani bo'yicha maxsus uslubiyot muallifi;\n"
        "• DTM va Milliy Sertifikat imtihonlariga tayyorlovchi murabbiy;\n"
        "• Masalalarni formulalarsiz va mantiqiy usullarda oson yechish tizimi.",
        parse_mode="HTML"
    )

@dp.message(F.text == "📞 Bog'lanish")
async def contact_info(message: types.Message):
    await message.answer(f"📞 Savollar bo'yicha admin: {ADMIN_USERNAME}", parse_mode="HTML")

async def main():
    init_db()
    print("=" * 60)
    print(">>> A+ Kimyo Boti (Yangi Darslar Katalogi & Video Baza) ishga tushdi!")
    print(f">>> Admin ID: {ADMIN_ID} | Admin: {ADMIN_USERNAME}")
    print("=" * 60)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())