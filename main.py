import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- SOZLAMALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8636730483:AAFU8mRl0pH5AjmCASWETCNLy35q4lMpB-s")
ADMIN_PAROL = "kimyo2026"  # Bot ichida /admin kimyo2026 deb yozsangiz admin bo'lasiz

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- MA'LUMOTLAR BAZASI (SQLite) ---
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
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
            test_code INTEGER,
            score INTEGER,
            total INTEGER,
            checked_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id: int, full_name: str, username: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
        (user_id, full_name, username, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

def set_admin(user_id: int):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_user_admin(user_id: int) -> bool:
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def get_all_admins():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_admin = 1")
    admins = [r[0] for r in c.fetchall()]
    conn.close()
    return admins

# --- HOLATLAR (FSM) ---
class KursgaYozilish(StatesGroup):
    ism = State()
    telefon = State()
    chek = State()

class TestIshlash(StatesGroup):
    kod = State()
    javoblar = State()

class YangiTest(StatesGroup):
    nomi = State()
    kalitlar = State()

class Rassilka(StatesGroup):
    xabar = State()

# --- TUGMALAR ---
def get_main_menu(user_id: int):
    kb = [
        [KeyboardButton(text="📝 Test tekshirish"), KeyboardButton(text="✍️ Kursga yozilish")],
        [KeyboardButton(text="📚 Kurslar haqida"), KeyboardButton(text="📞 Bogʻlanish")]
    ]
    if is_user_admin(user_id):
        kb.append([KeyboardButton(text="⚙️ Admin panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Yangi test qoʻshish"), KeyboardButton(text="📋 Oxirgi testlar")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="🔙 Asosiy menyu")]
    ],
    resize_keyboard=True
)

# --- /START VA /ADMIN BUYRUQLARI ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    add_user(message.from_user.id, message.from_user.full_name, message.from_user.username or "")
    await message.answer(
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n"
        "🧪 <b>A+ Kimyo | Online Maktabi</b> rasmiy botiga xush kelibsiz.\n\n"
        "Quyidagi boʻlimlardan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_menu(message.from_user.id)
    )

@dp.message(Command("admin"))
async def cmd_make_admin(message: types.Message):
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PAROL:
        add_user(message.from_user.id, message.from_user.full_name, message.from_user.username or "")
        set_admin(message.from_user.id)
        await message.answer("✅ Sizga Admin huquqi berildi!", reply_markup=admin_menu)
    elif is_user_admin(message.from_user.id):
        await message.answer("⚙️ Admin panelga xush kelibsiz:", reply_markup=admin_menu)
    else:
        await message.answer("⚠️ Admin boʻlish uchun parolni kiriting.\nMasalan: <code>/admin kimyo2026</code>", parse_mode="HTML")

@dp.message(F.text == "⚙️ Admin panel")
async def open_admin_panel(message: types.Message):
    if is_user_admin(message.from_user.id):
        await message.answer("⚙️ Admin panel:", reply_markup=admin_menu)

@dp.message(F.text == "🔙 Asosiy menyu")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=get_main_menu(message.from_user.id))

# --- KURSLAR VA ALOQA ---
@dp.message(F.text == "📚 Kurslar haqida")
async def info_courses(message: types.Message):
    await message.answer(
        "🧪 <b>A+ Kimyo | Online Maktabi kurslari:</b>\n\n"
        "✅ Noldan boshlovchilar uchun fundamental kimyo\n"
        "✅ Milliy sertifikat va Attestatsiyaga maxsus tayyorlov\n"
        "✅ Video-darslar, PDF qoʻllanmalar va har haftalik diagnostik testlar\n\n"
        "📢 Kanalimiz: @kimyo_sertifkat_uchun\n"
        "Kursga qoʻshilish uchun <b>«✍️ Kursga yozilish»</b> tugmasini bosing.",
        parse_mode="HTML"
    )

@dp.message(F.text == "📞 Bogʻlanish")
async def contact_info(message: types.Message):
    await message.answer(
        "👨‍🏫 <b>Murojaat va savollar uchun:</b>\n"
        "📢 Rasmiy kanal: @kimyo_sertifkat_uchun",
        parse_mode="HTML"
    )

# --- TEST TEKSHIRISH TIZIMI ---
@dp.message(F.text == "📝 Test tekshirish")
async def start_test_check(message: types.Message, state: FSMContext):
    await state.set_state(TestIshlash.kod)
    await message.answer("🔢 Test kodini kiriting (masalan: <code>1</code>):", parse_mode="HTML")

@dp.message(TestIshlash.kod)
async def get_test_code(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("⚠️ Test kodi faqat raqamdan iborat boʻlishi kerak!")
    
    test_code = int(message.text)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (test_code,))
    row = c.fetchone()
    conn.close()

    if not row:
        return await message.answer("❌ Bunday kodli test topilmadi. Kodni tekshirib qayta kiriting:")

    await state.update_data(test_code=test_code, title=row[0], correct_answers=row[1])
    await state.set_state(TestIshlash.javoblar)
    await message.answer(
        f"📘 Test: <b>{row[0]}</b>\n"
        f"Savollar soni: <b>{len(row[1])} ta</b>\n\n"
        f"✍️ Javoblaringizni ketma-ket harflar bilan yuboring (masalan: <code>abcdabcd...</code>):",
        parse_mode="HTML"
    )

@dp.message(TestIshlash.javoblar)
async def check_user_answers(message: types.Message, state: FSMContext):
    user_ans = message.text.strip().lower()
    data = await state.get_data()
    correct_ans = data["correct_answers"].lower()

    if len(user_ans) != len(correct_ans):
        return await message.answer(
            f"⚠️ Javoblar soni mos kelmadi!\n"
            f"Testda <b>{len(correct_ans)} ta</b> savol bor, siz esa <b>{len(user_ans)} ta</b> harf yubordingiz.",
            parse_mode="HTML"
        )

    score = 0
    detail = []
    for i, (u, k) in enumerate(zip(user_ans, correct_ans), start=1):
        if u == k:
            score += 1
            detail.append(f"{i}. ✅")
        else:
            detail.append(f"{i}. ❌ ({u.upper()})")

    percent = round((score / len(correct_ans)) * 100, 1)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO results (user_id, test_code, score, total, checked_at) VALUES (?, ?, ?, ?, ?)",
        (message.from_user.id, data["test_code"], score, len(correct_ans), datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

    await message.answer(
        f"📊 <b>Test natijangiz:</b>\n\n"
        f"📘 Mavzu: <b>{data['title']}</b>\n"
        f"✅ Toʻgʻri javoblar: <b>{score} / {len(correct_ans)}</b> ({percent}%)\n\n"
        + "\n".join(detail[:35]),
        parse_mode="HTML",
        reply_markup=get_main_menu(message.from_user.id)
    )
    await state.clear()

# --- ADMIN: YANGI TEST QO'SHISH ---
@dp.message(F.text == "➕ Yangi test qoʻshish")
async def admin_add_test(message: types.Message, state: FSMContext):
    if not is_user_admin(message.from_user.id):
        return
    await state.set_state(YangiTest.nomi)
    await message.answer("📘 Yangi test nomini (mavzusini) kiriting:")

@dp.message(YangiTest.nomi)
async def admin_test_title(message: types.Message, state: FSMContext):
    await state.update_data(nomi=message.text)
    await state.set_state(YangiTest.kalitlar)
    await message.answer("🔑 Toʻgʻri javoblar kalitini ketma-ket yozing (masalan: <code>abcdabcd...</code>):", parse_mode="HTML")

@dp.message(YangiTest.kalitlar)
async def admin_test_keys(message: types.Message, state: FSMContext):
    kalitlar = message.text.strip().lower()
    data = await state.get_data()
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO tests (title, answers, created_at) VALUES (?, ?, ?)",
        (data["nomi"], kalitlar, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    test_code = c.lastrowid
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ <b>Yangi test bazaga qoʻshildi!</b>\n\n"
        f"🔢 Test kodi: <code>{test_code}</code>\n"
        f"📘 Nomi: {data['nomi']}\n"
        f"❓ Savollar soni: {len(kalitlar)} ta",
        parse_mode="HTML",
        reply_markup=admin_menu
    )
    await state.clear()

@dp.message(F.text == "📋 Oxirgi testlar")
async def admin_recent_tests(message: types.Message):
    if not is_user_admin(message.from_user.id):
        return
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT test_code, title, length(answers), created_at FROM tests ORDER BY test_code DESC LIMIT 12")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return await message.answer("Hozircha testlar yoʻq.")
    
    text = "📋 <b>Oxirgi 12 ta test:</b>\n\n"
    for r in rows:
        text += f"🔹 Kod: <code>{r[0]}</code> | {r[1]} ({r[2]} ta) — <i>{r[3]}</i>\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    if not is_user_admin(message.from_user.id):
        return
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    u_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tests")
    t_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM results")
    r_count = c.fetchone()[0]
    conn.close()
    await message.answer(
        f"📊 <b>Bot statistikasi:</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{u_count} ta</b>\n"
        f"📘 Jami testlar: <b>{t_count} ta</b>\n"
        f"✅ Ishlangan testlar: <b>{r_count} marta</b>",
        parse_mode="HTML"
    )

# --- ADMIN: XABAR YUBORISH (RASSILKA) ---
@dp.message(F.text == "📢 Xabar yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if not is_user_admin(message.from_user.id):
        return
    await state.set_state(Rassilka.xabar)
    await message.answer("📢 Barcha foydalanuvchilarga yuboriladigan xabarni (matn, rasm yoki video) joʻnating:")

@dp.message(Rassilka.xabar)
async def send_broadcast(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [r[0] for r in c.fetchall()]
    conn.close()

    sent = 0
    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Xabar {sent} ta foydalanuvchiga yetkazildi!", reply_markup=admin_menu)
    await state.clear()

# --- KURSGA YOZILISH VA CHEK YUBORISH ---
@dp.message(F.text == "✍️ Kursga yozilish")
async def reg_course_start(message: types.Message, state: FSMContext):
    await state.set_state(KursgaYozilish.ism)
    await message.answer("✍️ Ism va familiyangizni kiriting:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(KursgaYozilish.ism)
async def reg_course_name(message: types.Message, state: FSMContext):
    await state.update_data(ism=message.text)
    await state.set_state(KursgaYozilish.telefon)
    tel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True
    )
    await message.answer("📱 Telefon raqamingizni yuboring:", reply_markup=tel_kb)

@dp.message(KursgaYozilish.telefon)
async def reg_course_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(telefon=phone)
    await state.set_state(KursgaYozilish.chek)
    await message.answer(
        "💳 Kurs uchun toʻlov cheki rasmini (skrinshotini) shu yerga yuboring:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(KursgaYozilish.chek, F.photo)
async def reg_course_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id
    photo_id = message.photo[-1].file_id
    admins = get_all_admins()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ok_{uid}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"no_{uid}")
    ]])
    caption = (
        f"🆕 <b>Yangi oʻquvchi arizasi!</b>\n"
        f"👤 Ism: {data['ism']}\n"
        f"📞 Tel: {data['telefon']}\n"
        f"🆔 @{message.from_user.username or 'yoq'} (<code>{uid}</code>)"
    )

    for admin_id in admins:
        try:
            await bot.send_photo(chat_id=admin_id, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    await message.answer(
        "✅ Arizangiz va toʻlov cheki adminga yuborildi! Tez orada tasdiqlanadi.",
        reply_markup=get_main_menu(uid)
    )
    await state.clear()

@dp.callback_query(F.data.startswith("ok_"))
async def approve_payment(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    await bot.send_message(uid, "🎉 <b>Toʻlovingiz tasdiqlandi!</b> Admin tez orada sizni yopiq guruhga qoʻshadi.", parse_mode="HTML")
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode="HTML")
    await callback.answer("Tasdiqlandi!")

@dp.callback_query(F.data.startswith("no_"))
async def reject_payment(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    await bot.send_message(uid, "❌ <b>Toʻlov cheki tasdiqlanmadi.</b> Qaytadan urinib koʻring yoki adminga murojaat qiling.", parse_mode="HTML")
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML")
    await callback.answer("Rad etildi!")

# --- RENDER UCHUN WEB-SERVER ---
async def health_check(request):
    return web.Response(text="A+ Kimyo Bot 24/7 ishlayapti!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    init_db()
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
