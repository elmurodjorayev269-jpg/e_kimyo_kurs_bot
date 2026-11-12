import asyncio
import csv
import os
import sqlite3
from datetime import datetime, timedelta
import pytz

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= SOZLAMALAR =================
BOT_TOKEN = "8636730483:AAFPSG094HwEzScSHZ170hRD1_xNC6Au0tg"
ADMIN_ID = 6734050237
TIMEZONE = pytz.timezone("Asia/Tashkent")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= BAZA BILAN ISHLASH (SQLite) =================
def init_db():
    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    phone TEXT,
                    paid_date TEXT,
                    expiry_date TEXT,
                    hw_today INTEGER DEFAULT 0,
                    missed_days INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 0
                )''')
    conn.commit()
    conn.close()

# ================= HOLATLAR (FSM) =================
class RegState(StatesGroup):
    full_name = State()
    phone = State()
    receipt = State()

# ================= TUGMALAR =================
def student_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Vazifa topshirish"), KeyboardButton(text="💳 To'lov qilish / Uzaytirish")],
            [KeyboardButton(text="👤 Mening holatim")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 O'quvchilar jadvali (Excel)"), KeyboardButton(text="🚨 Bugun vazifa qilmaganlar")],
            [KeyboardButton(text="🔄 Kunlik vazifani nolga tushirish")]
        ],
        resize_keyboard=True
    )

# ================= START VA RO'YXATDAN O'TISH =================
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "Assalomu alaykum, Azizbek ustoz! Admin panelga xush kelibsiz:",
            reply_markup=admin_menu()
        )
        return

    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("SELECT is_active FROM students WHERE user_id = ?", (message.from_user.id,))
    row = c.fetchone()
    conn.close()

    if row and row[0] == 1:
        await message.answer("«A+ Kimyo» platformasidasiz! Kerakli bo'limni tanlang:", reply_markup=student_menu())
    else:
        await message.answer(
            "Assalomu alaykum! **«A+ Kimyo | Online Maktabi»** rasmiy botiga xush kelibsiz!\n\n"
            "Kursga qo'shilish uchun **Ism va Familiyangizni** to'liq yozib yuboring:",
            parse_mode="Markdown"
        )
        await state.set_state(RegState.full_name)

@dp.message(RegState.full_name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Endi pastdagi tugmani bosib telefon raqamingizni yuboring (yoki yozing):", reply_markup=kb)
    await state.set_state(RegState.phone)

@dp.message(RegState.phone)
async def get_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)
    await message.answer(
        "💳 Kurs uchun to'lovni amalga oshiring va **to'lov cheki (skrinshot)**ni shu yerga rasm qilib yuboring:",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(RegState.receipt)

@dp.message(RegState.receipt, F.photo)
async def get_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "Yo'q"
    full_name = data['full_name']
    phone = data['phone']

    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO students (user_id, full_name, username, phone, is_active)
                 VALUES (?, ?, ?, ?, 0)''', (user_id, full_name, username, phone))
    conn.commit()
    conn.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash (+30 kun)", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{user_id}")
        ]
    ])

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=(
            f"💰 **Yangi to'lov cheki!**\n\n"
            f"👤 **O'quvchi:** {full_name}\n"
            f"📞 **Tel:** {phone}\n"
            f"🔗 **Username:** {username}\n"
            f"🆔 **ID:** `{user_id}`"
        ),
        reply_markup=kb,
        parse_mode="Markdown"
    )

    await message.answer("✅ Chekingiz ustozga yuborildi! Tasdiqlangach sizga xabar keladi.")
    await state.clear()

# ================= TO'LOVNI TASDIQLASH (ADMIN) =================
@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    user_id = int(call.data.split("_")[1])
    now = datetime.now(TIMEZONE)
    paid_date = now.strftime("%Y-%m-%d")
    expiry_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute('''UPDATE students 
                 SET paid_date = ?, expiry_date = ?, is_active = 1, hw_today = 0 
                 WHERE user_id = ?''', (paid_date, expiry_date, user_id))
    conn.commit()
    conn.close()

    await call.message.edit_caption(
        caption=call.message.caption + f"\n\n✅ **TASDIQLANDI** (Muddati: {expiry_date} gacha)",
        parse_mode="Markdown"
    )
    await bot.send_message(
        user_id,
        f"🎉 **Tabriklaymiz! To'lovingiz tasdiqlandi.**\n"
        f"📅 Obuna muddati: **{expiry_date}** gacha.\n\n"
        f"Har kuni soat **22:00 gacha** vazifalarni «📚 Vazifa topshirish» tugmasi orqali yuborishni unutmang!",
        reply_markup=student_menu(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(call: types.CallbackQuery):
    user_id = int(call.data.split("_")[1])
    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ **RAD ETILDI**")
    await bot.send_message(user_id, "❌ To'lov chekingiz tasdiqlanmadi. Iltimos, qayta tekshirib yuboring.")

# ================= VAZIFA QABUL QILISH =================
@dp.message(F.text == "📚 Vazifa topshirish")
async def ask_hw(message: types.Message):
    await message.answer("📸 Bugungi yozma ish yoki organika vazifangizni **rasm (yoki fayl)** ko'rinishida yuboring:")

@dp.message(F.photo | F.document)
async def receive_hw(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        return

    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("SELECT full_name, is_active FROM students WHERE user_id = ?", (message.from_user.id,))
    row = c.fetchone()

    if not row or row[1] == 0:
        await message.answer("⚠️ Sizning obunangiz faol emas. Avval to'lovni amalga oshiring.")
        conn.close()
        return

    c.execute("UPDATE students SET hw_today = 1, missed_days = 0 WHERE user_id = ?", (message.from_user.id,))
    conn.commit()
    conn.close()

    await message.answer("✅ **Barakalla! Bugungi vazifangiz qabul qilindi va jadvalga (+) belgilandi.**", parse_mode="Markdown")

@dp.message(F.text == "👤 Mening holatim")
async def my_status(message: types.Message):
    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("SELECT full_name, paid_date, expiry_date, hw_today FROM students WHERE user_id = ?", (message.from_user.id,))
    row = c.fetchone()
    conn.close()

    if row:
        hw_status = "✅ Topshirilgan" if row[3] == 1 else "❌ Hali topshirilmadi"
        await message.answer(
            f"👤 **O'quvchi:** {row[0]}\n"
            f"📅 **To'langan sana:** {row[1]}\n"
            f"⏳ **Tugash sanasi:** {row[2]}\n"
            f"📝 **Bugungi vazifa:** {hw_status}",
            parse_mode="Markdown"
        )

@dp.message(F.text == "💳 To'lov qilish / Uzaytirish")
async def renew_sub(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("SELECT full_name, phone FROM students WHERE user_id = ?", (message.from_user.id,))
    row = c.fetchone()
    conn.close()
    if row:
        await state.update_data(full_name=row[0], phone=row[1])
        await message.answer("💳 Yangi oy uchun to'lov cheki (skrinshot)ni rasm qilib yuboring:")
        await state.set_state(RegState.receipt)

# ================= ADMIN PANEL FUNKSIYALARI =================
@dp.message(F.text == "📊 O'quvchilar jadvali (Excel)")
async def export_excel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, username, phone, paid_date, expiry_date, hw_today, missed_days FROM students WHERE is_active = 1")
    rows = c.fetchall()
    conn.close()

    filename = "oquvchilar_jadvali.csv"
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ID", "Ism-Familiya", "Username", "Telefon", "To'lagan sana", "Tugash sanasi", "Bugungi vazifa", "Qoldirgan kunlar"])
        for r in rows:
            hw_str = "Topshirdi (+)" if r[6] == 1 else "Topshirmadi (-)"
            writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], hw_str, r[7]])

    await message.answer_document(
        FSInputFile(filename),
        caption=f"📊 **Faol o'quvchilar jadvali**\nJami faol o'quvchilar: **{len(rows)} ta**",
        parse_mode="Markdown"
    )
    os.remove(filename)

async def send_daily_report():
    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, username, phone, missed_days FROM students WHERE is_active = 1 AND hw_today = 0")
    lazy_students = c.fetchall()

    c.execute("SELECT COUNT(*) FROM students WHERE is_active = 1")
    total_active = c.fetchone()[0]

    if not lazy_students:
        await bot.send_message(ADMIN_ID, f"🎉 **Ajoyib natija!** Bugun barcha {total_active} ta o'quvchi vazifani to'liq topshirdi!", parse_mode="Markdown")
    else:
        text = f"🚨 **USTOZ, BUGUN VAZIFA TOPSHIRMAGANLAR ({datetime.now(TIMEZONE).strftime('%d.%m.%Y')}):**\n\n"
        for idx, st in enumerate(lazy_students, 1):
            uid, name, uname, phone, missed = st
            new_missed = missed + 1
            c.execute("UPDATE students SET missed_days = ? WHERE user_id = ?", (new_missed, uid))
            text += f"{idx}. **{name}** ({uname}) — `{phone}` *(Ketma-ket {new_missed} kun)*\n"
            
            # O'quvchining o'ziga ham ogohlantirish yuborish
            try:
                await bot.send_message(
                    uid,
                    "⚠️ **DIQQAT!** Siz bugun soat 22:00 gacha vazifa topshirmadingiz!\n"
                    "Ma'lumotingiz **Azizbek ustozga** yuborildi. Intizomni buzmasdan vazifani tezda yuklang!",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        done_count = total_active - len(lazy_students)
        text += f"\n📊 **Jami:** {total_active} tadan {done_count} tasi topshirdi, **{len(lazy_students)} tasi qoldirdi.**"
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")

    # Yangi kun uchun hw_today ni 0 qilish va muddati tugaganlarni tekshirish
    today_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    c.execute("UPDATE students SET hw_today = 0")
    c.execute("UPDATE students SET is_active = 0 WHERE expiry_date < ?", (today_str,))
    conn.commit()
    conn.close()

@dp.message(F.text == "🚨 Bugun vazifa qilmaganlar")
async def manual_check_lazy(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("SELECT full_name, username, phone FROM students WHERE is_active = 1 AND hw_today = 0")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.answer("✅ Hozircha hamma vazifani topshirgan!")
        return

    text = "⏳ **Hozirgi vaqtgacha vazifa topshirmaganlar:**\n\n"
    for idx, r in enumerate(rows, 1):
        text += f"{idx}. {r[0]} ({r[1]}) — `{r[2]}`\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔄 Kunlik vazifani nolga tushirish")
async def reset_hw_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("akimyo_baza.db")
    c = conn.cursor()
    c.execute("UPDATE students SET hw_today = 0")
    conn.commit()
    conn.close()
    await message.answer("🔄 Barcha o'quvchilarning bugungi vazifa statusi yangi kun uchun `0` qilindi!")

# ================= ISHGA TUSHIRISH =================
async def main():
    init_db()
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    # Har kuni soat 22:00 da avtomatik hisobot chiqaradi
    scheduler.add_job(send_daily_report, trigger="cron", hour=22, minute=0)
    scheduler.start()
    
    print("A+ Kimyo Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
