import asyncio
import html
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import aiosqlite

# ================= SOZLAMALAR =================
BOT_TOKEN = "8636730483:AAFPSG094HwEzScSHZ170hRD1_xNC6Au0tg"
CARD_NUMBER = "9860350142097954"
CARD_OWNER = "Azizbek Ibrohimov"
TEST_QUESTIONS = 43
ADMIN_IDS = set()  # birinchi /admin yozgan odam admin bo'ladi
# ==============================================

DB_PATH = "kurs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, full_name TEXT, username TEXT,
    joined TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS courses(
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, price INTEGER, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS enrollments(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, course_id INTEGER,
    status TEXT DEFAULT 'pending', receipt TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS lessons(
    id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER, title TEXT,
    content_chat INTEGER, content_msg INTEGER);
CREATE TABLE IF NOT EXISTS homeworks(
    id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER, title TEXT,
    description TEXT, deadline TEXT, reported INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS submissions(
    id INTEGER PRIMARY KEY AUTOINCREMENT, hw_id INTEGER, user_id INTEGER,
    created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tests(
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, answer_key TEXT, active INTEGER DEFAULT 1,
    created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS test_results(
    id INTEGER PRIMARY KEY AUTOINCREMENT, test_id INTEGER, user_id INTEGER,
    score INTEGER, total INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_id, user_id));
"""


async def init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    for r in await q("SELECT value FROM settings WHERE key='admin'"):
        ADMIN_IDS.add(int(r["value"]))


async def q(sql, args=(), one=False, commit=False):
    """commit=True -> lastrowid; one=True -> bitta qator yoki None; aks holda ro'yxat."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, args)
        if commit:
            await db.commit()
            return cur.lastrowid
        rows = await cur.fetchall()
        if one:
            return rows[0] if rows else None
        return rows


TZ = ZoneInfo("Asia/Tashkent")
esc = html.escape

admin = Router()
admin.message.filter(lambda m: m.from_user.id in ADMIN_IDS)
admin.callback_query.filter(lambda c: c.from_user.id in ADMIN_IDS)
student = Router()


# ───────────────────────── Holatlar ─────────────────────────
class Pay(StatesGroup):
    receipt = State()


class Sub(StatesGroup):
    work = State()


class TestS(StatesGroup):
    answers = State()


class AddCourse(StatesGroup):
    title = State()
    price = State()


class AddLesson(StatesGroup):
    title = State()
    content = State()


class AddHw(StatesGroup):
    title = State()
    desc = State()
    deadline = State()


class AddTest(StatesGroup):
    title = State()
    key = State()


class Broadcast(StatesGroup):
    text = State()


# ───────────────────────── Yordamchilar ─────────────────────────
MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📚 Kurslar"), KeyboardButton(text="📖 Mening kurslarim")],
        [KeyboardButton(text="📝 Vazifa topshirish"),
         KeyboardButton(text=f"🧪 Test tekshirish ({TEST_QUESTIONS} talik)")],
        [KeyboardButton(text="🏆 Reyting")],
    ],
    resize_keyboard=True,
)


def parse_answers(text: str) -> dict:
    """'1a2b3c' yoki '1-a 2-b' yoki 'abcd...' formatlarini {raqam: harf} ga aylantiradi."""
    t = text.lower()
    pairs = re.findall(r"(\d+)\s*[-.):]?\s*([a-d])", t)
    if pairs:
        return {int(n): l for n, l in pairs}
    return {i + 1: l for i, l in enumerate(re.findall(r"[a-d]", t))}


def name_of(u) -> str:
    return esc(u.full_name or "Noma'lum")


async def has_access(user_id: int, course_id: int) -> bool:
    r = await q("SELECT 1 FROM enrollments WHERE user_id=? AND course_id=? AND status='approved'",
                (user_id, course_id), one=True)
    return r is not None


async def notify_admins(bot: Bot, text: str, **kw):
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, text, **kw)
        except Exception as e:
            logging.warning("Adminga yuborilmadi %s: %s", a, e)


async def missing_students(hw):
    return await q(
        """SELECT u.id, u.full_name, u.username FROM enrollments e
           JOIN users u ON u.id = e.user_id
           WHERE e.course_id=? AND e.status='approved'
             AND u.id NOT IN (SELECT user_id FROM submissions WHERE hw_id=?)""",
        (hw["course_id"], hw["id"]))


async def send_missing_report(bot: Bot, hw):
    rows = await missing_students(hw)
    if not rows:
        await notify_admins(bot, f"✅ «{esc(hw['title'])}» vazifasini hamma topshirgan.")
        return
    lines = [f"❗ <b>{esc(hw['title'])}</b> — topshirmaganlar ({len(rows)} ta):"]
    for r in rows:
        un = f" @{r['username']}" if r["username"] else ""
        lines.append(f"• {esc(r['full_name'] or '—')}{un}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📩 Ularga eslatma yuborish", callback_data=f"remind:{hw['id']}")]])
    await notify_admins(bot, "\n".join(lines[:60]), reply_markup=kb)


async def deadline_job(bot: Bot):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    for hw in await q("SELECT * FROM homeworks WHERE reported=0 AND deadline<=?", (now,)):
        await send_missing_report(bot, hw)
        await q("UPDATE homeworks SET reported=1 WHERE id=?", (hw["id"],), commit=True)


# ───────────────────────── TALABA ─────────────────────────
@student.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    u = m.from_user
    await q("INSERT OR IGNORE INTO users(id) VALUES(?)", (u.id,), commit=True)
    await q("UPDATE users SET full_name=?, username=? WHERE id=?",
            (u.full_name, u.username, u.id), commit=True)
    await m.answer(f"Assalomu alaykum, <b>{esc(u.full_name)}</b>! 👋\nOnlayn kurs botiga xush kelibsiz.",
                   reply_markup=MENU)


@student.message(Command("admin"))
async def claim_admin(m: Message):
    if ADMIN_IDS:
        return await m.answer("Bu buyruq faqat admin uchun.")
    ADMIN_IDS.add(m.from_user.id)
    await q("INSERT OR REPLACE INTO settings(key, value) VALUES('admin', ?)", (str(m.from_user.id),), commit=True)
    await m.answer("✅ Siz admin bo'ldingiz! Panel:", reply_markup=admin_kb())


@student.message(F.text == "📚 Kurslar")
async def courses(m: Message, state: FSMContext):
    await state.clear()
    rows = await q("SELECT * FROM courses WHERE active=1")
    if not rows:
        return await m.answer("Hozircha kurslar yo'q.")
    kb = InlineKeyboardBuilder()
    for c in rows:
        kb.button(text=f"{c['title']} — {c['price']:,} so'm".replace(",", " "), callback_data=f"course:{c['id']}")
    kb.adjust(1)
    await m.answer("Kursni tanlang:", reply_markup=kb.as_markup())


@student.callback_query(F.data.startswith("course:"))
async def course_info(c: CallbackQuery):
    cid = int(c.data.split(":")[1])
    course = await q("SELECT * FROM courses WHERE id=?", (cid,), one=True)
    if not course:
        return await c.answer("Kurs topilmadi", show_alert=True)
    if await has_access(c.from_user.id, cid):
        return await c.message.answer("✅ Bu kursga kirish ochiq. «📖 Mening kurslarim» bo'limiga o'ting.")
    pend = await q("SELECT 1 FROM enrollments WHERE user_id=? AND course_id=? AND status='pending'",
                   (c.from_user.id, cid), one=True)
    if pend:
        return await c.message.answer("⏳ Chekingiz tekshirilmoqda, biroz kuting.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💳 To'lov qildim", callback_data=f"pay:{cid}")]])
    await c.message.answer(
        f"<b>{esc(course['title'])}</b>\nNarxi: <b>{course['price']:,}</b> so'm\n\n"
        f"Quyidagi kartaga to'lang:\n💳 <code>{CARD_NUMBER}</code>\n👤 {esc(CARD_OWNER)}\n\n"
        "To'lagach «To'lov qildim» tugmasini bosib, chek rasmini yuboring.".replace(",", " "),
        reply_markup=kb)
    await c.answer()


@student.callback_query(F.data.startswith("pay:"))
async def pay_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(Pay.receipt)
    await state.update_data(course_id=int(c.data.split(":")[1]))
    await c.message.answer("📸 To'lov chekining rasmini yuboring.")
    await c.answer()


@student.message(Pay.receipt, F.photo)
async def pay_receipt(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    course = await q("SELECT * FROM courses WHERE id=?", (data["course_id"],), one=True)
    fid = m.photo[-1].file_id
    eid = await q("INSERT INTO enrollments(user_id, course_id, receipt) VALUES(?,?,?)",
                  (m.from_user.id, course["id"], fid), commit=True)
    await state.clear()
    await m.answer("✅ Chek qabul qilindi. Admin tasdiqlagach sizga xabar keladi.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"payok:{eid}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"payno:{eid}")]])
    un = f" @{m.from_user.username}" if m.from_user.username else ""
    for a in ADMIN_IDS:
        try:
            await bot.send_photo(
                a, fid, reply_markup=kb,
                caption=f"💰 Yangi to'lov\n👤 {name_of(m.from_user)}{un}\n📚 {esc(course['title'])}\n"
                        f"💵 {course['price']:,} so'm".replace(",", " "))
        except Exception as e:
            logging.warning("Chek adminga yuborilmadi: %s", e)


@student.message(Pay.receipt)
async def pay_not_photo(m: Message):
    await m.answer("Iltimos, chek <b>rasmini</b> yuboring.")


@student.message(F.text == "📖 Mening kurslarim")
async def my_courses(m: Message, state: FSMContext):
    await state.clear()
    rows = await q("""SELECT c.id, c.title FROM enrollments e JOIN courses c ON c.id=e.course_id
                      WHERE e.user_id=? AND e.status='approved'""", (m.from_user.id,))
    if not rows:
        return await m.answer("Sizda hali faol kurs yo'q. «📚 Kurslar» orqali sotib oling.")
    kb = InlineKeyboardBuilder()
    for c in rows:
        kb.button(text=c["title"], callback_data=f"lessons:{c['id']}")
    kb.adjust(1)
    await m.answer("Kurslaringiz:", reply_markup=kb.as_markup())


@student.callback_query(F.data.startswith("lessons:"))
async def lessons_list(c: CallbackQuery):
    cid = int(c.data.split(":")[1])
    if not await has_access(c.from_user.id, cid):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    rows = await q("SELECT * FROM lessons WHERE course_id=? ORDER BY id", (cid,))
    if not rows:
        await c.message.answer("Darslar hali qo'shilmagan.")
    else:
        kb = InlineKeyboardBuilder()
        for i, l in enumerate(rows, 1):
            kb.button(text=f"{i}. {l['title']}", callback_data=f"lesson:{l['id']}")
        kb.adjust(1)
        await c.message.answer("Darslar:", reply_markup=kb.as_markup())
    await c.answer()


@student.callback_query(F.data.startswith("lesson:"))
async def lesson_send(c: CallbackQuery, bot: Bot):
    l = await q("SELECT * FROM lessons WHERE id=?", (int(c.data.split(":")[1]),), one=True)
    if not l or not await has_access(c.from_user.id, l["course_id"]):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    await bot.copy_message(c.from_user.id, l["content_chat"], l["content_msg"])
    await c.answer()


# ── Vazifa topshirish ──
@student.message(F.text == "📝 Vazifa topshirish")
async def hw_list(m: Message, state: FSMContext):
    await state.clear()
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    rows = await q(
        """SELECT h.* FROM homeworks h JOIN enrollments e ON e.course_id=h.course_id
           WHERE e.user_id=? AND e.status='approved' AND h.deadline>?
             AND h.id NOT IN (SELECT hw_id FROM submissions WHERE user_id=?)
           ORDER BY h.deadline""", (m.from_user.id, now, m.from_user.id))
    if not rows:
        return await m.answer("Topshirilishi kerak bo'lgan vazifa yo'q 🎉")
    kb = InlineKeyboardBuilder()
    for h in rows:
        kb.button(text=f"{h['title']} (⏰ {h['deadline']})", callback_data=f"hw:{h['id']}")
    kb.adjust(1)
    await m.answer("Vazifani tanlang:", reply_markup=kb.as_markup())


@student.callback_query(F.data.startswith("hw:"))
async def hw_pick(c: CallbackQuery, state: FSMContext):
    h = await q("SELECT * FROM homeworks WHERE id=?", (int(c.data.split(":")[1]),), one=True)
    if not h or not await has_access(c.from_user.id, h["course_id"]):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    await state.set_state(Sub.work)
    await state.update_data(hw_id=h["id"])
    await c.message.answer(f"<b>{esc(h['title'])}</b>\n{esc(h['description'] or '')}\n\n"
                           "Ishingizni yuboring (matn, rasm yoki fayl):")
    await c.answer()


@student.message(Sub.work)
async def hw_submit(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    h = await q("SELECT * FROM homeworks WHERE id=?", (data["hw_id"],), one=True)
    await q("INSERT INTO submissions(hw_id, user_id) VALUES(?,?)", (h["id"], m.from_user.id), commit=True)
    await state.clear()
    await m.answer("✅ Vazifa qabul qilindi. Rahmat!")
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, f"📥 {name_of(m.from_user)} «{esc(h['title'])}» vazifasini topshirdi:")
            await m.copy_to(a)
        except Exception as e:
            logging.warning("Vazifa adminga yuborilmadi: %s", e)


# ── 43 talik test (alohida bo'lim) ──
@student.message(F.text.startswith("🧪 Test tekshirish"))
async def test_list(m: Message, state: FSMContext):
    await state.clear()
    rows = await q("SELECT * FROM tests WHERE active=1 ORDER BY id DESC")
    if not rows:
        return await m.answer("Hozircha faol test yo'q.")
    kb = InlineKeyboardBuilder()
    for t in rows:
        kb.button(text=t["title"], callback_data=f"test:{t['id']}")
    kb.adjust(1)
    await m.answer(f"🧪 <b>Test tekshirish ({TEST_QUESTIONS} talik)</b>\nTestni tanlang:",
                   reply_markup=kb.as_markup())


@student.callback_query(F.data.startswith("test:"))
async def test_pick(c: CallbackQuery, state: FSMContext):
    tid = int(c.data.split(":")[1])
    done = await q("SELECT * FROM test_results WHERE test_id=? AND user_id=?", (tid, c.from_user.id), one=True)
    if done:
        await c.message.answer(f"Siz bu testni topshirgansiz: <b>{done['score']}/{done['total']}</b>")
        return await c.answer()
    await state.set_state(TestS.answers)
    await state.update_data(test_id=tid)
    await c.message.answer(
        f"{TEST_QUESTIONS} ta javobingizni yuboring (A, B, C, D).\n"
        "Format: <code>1a2b3c4d...</code> yoki <code>abcd...</code>\n"
        "Rasm yuborsangiz, admin qo'lda tekshiradi.")
    await c.answer()


@student.message(TestS.answers, F.photo)
async def test_photo(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    t = await q("SELECT * FROM tests WHERE id=?", (data["test_id"],), one=True)
    await state.clear()
    await m.answer("📸 Rasm adminga yuborildi, natija keyin aytiladi.")
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, f"🧪 {name_of(m.from_user)} «{esc(t['title'])}» testi javob varaqasini yubordi:")
            await m.copy_to(a)
        except Exception as e:
            logging.warning("Test rasmi adminga yuborilmadi: %s", e)


@student.message(TestS.answers, F.text)
async def test_check(m: Message, state: FSMContext):
    data = await state.get_data()
    t = await q("SELECT * FROM tests WHERE id=?", (data["test_id"],), one=True)
    ans = parse_answers(m.text)
    if len(ans) < TEST_QUESTIONS or any(i not in ans for i in range(1, TEST_QUESTIONS + 1)):
        return await m.answer(f"❗ {TEST_QUESTIONS} ta javob kerak, siz {len(ans)} ta yubordingiz. Qayta yuboring.")
    key = t["answer_key"]
    wrong = [i for i in range(1, TEST_QUESTIONS + 1) if ans[i] != key[i - 1]]
    score = TEST_QUESTIONS - len(wrong)
    await q("INSERT OR IGNORE INTO test_results(test_id, user_id, score, total) VALUES(?,?,?,?)",
            (t["id"], m.from_user.id, score, TEST_QUESTIONS), commit=True)
    await state.clear()
    text = f"✅ To'g'ri javoblar: <b>{score}/{TEST_QUESTIONS}</b>"
    if wrong:
        text += "\n❌ Xato savollar: " + ", ".join(map(str, wrong))
    await m.answer(text)


@student.message(F.text == "🏆 Reyting")
async def rating(m: Message, state: FSMContext):
    await state.clear()
    t = await q("SELECT * FROM tests WHERE active=1 ORDER BY id DESC LIMIT 1", one=True)
    if not t:
        return await m.answer("Hozircha reyting yo'q.")
    rows = await q("""SELECT u.full_name, r.score, r.total FROM test_results r JOIN users u ON u.id=r.user_id
                      WHERE r.test_id=? ORDER BY r.score DESC, r.created LIMIT 15""", (t["id"],))
    if not rows:
        return await m.answer("Bu testni hali hech kim topshirmagan.")
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 <b>{esc(t['title'])}</b> reytingi:"]
    for i, r in enumerate(rows):
        lines.append(f"{medals[i] if i < 3 else str(i + 1) + '.'} {esc(r['full_name'] or '—')} — {r['score']}/{r['total']}")
    await m.answer("\n".join(lines))


# ───────────────────────── ADMIN ─────────────────────────
def admin_kb():
    kb = InlineKeyboardBuilder()
    for text, cb in [("➕ Kurs", "adm:course"), ("➕ Dars", "adm:lesson"), ("➕ Vazifa", "adm:hw"),
                     (f"➕ Test ({TEST_QUESTIONS} talik)", "adm:test"), ("👥 Talabalar", "adm:students"),
                     ("📊 Statistika", "adm:stats"), ("❗ Topshirmaganlar", "adm:missing"),
                     ("📢 Xabar yuborish", "adm:bc")]:
        kb.button(text=text, callback_data=cb)
    kb.adjust(2)
    return kb.as_markup()


@admin.message(Command("admin"))
async def admin_panel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🛠 <b>Admin panel</b>", reply_markup=admin_kb())


@admin.callback_query(F.data.startswith("payok:"))
async def pay_ok(c: CallbackQuery, bot: Bot):
    e = await q("SELECT * FROM enrollments WHERE id=?", (int(c.data.split(":")[1]),), one=True)
    if not e or e["status"] != "pending":
        return await c.answer("Allaqachon ko'rib chiqilgan", show_alert=True)
    await q("UPDATE enrollments SET status='approved' WHERE id=?", (e["id"],), commit=True)
    course = await q("SELECT * FROM courses WHERE id=?", (e["course_id"],), one=True)
    await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n✅ Tasdiqlandi", reply_markup=None)
    try:
        await bot.send_message(e["user_id"], f"✅ To'lovingiz tasdiqlandi! «{esc(course['title'])}» kursi ochildi.\n"
                                             "«📖 Mening kurslarim» bo'limiga o'ting.")
    except Exception:
        pass
    await c.answer("Tasdiqlandi")


@admin.callback_query(F.data.startswith("payno:"))
async def pay_no(c: CallbackQuery, bot: Bot):
    e = await q("SELECT * FROM enrollments WHERE id=?", (int(c.data.split(":")[1]),), one=True)
    if not e or e["status"] != "pending":
        return await c.answer("Allaqachon ko'rib chiqilgan", show_alert=True)
    await q("UPDATE enrollments SET status='rejected' WHERE id=?", (e["id"],), commit=True)
    await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n❌ Rad etildi", reply_markup=None)
    try:
        await bot.send_message(e["user_id"], "❌ To'lovingiz tasdiqlanmadi. Chekni tekshirib, qaytadan yuboring.")
    except Exception:
        pass
    await c.answer("Rad etildi")


async def courses_kb(prefix: str):
    kb = InlineKeyboardBuilder()
    for c in await q("SELECT * FROM courses WHERE active=1"):
        kb.button(text=c["title"], callback_data=f"{prefix}:{c['id']}")
    kb.adjust(1)
    return kb.as_markup()


# ── Kurs qo'shish ──
@admin.callback_query(F.data == "adm:course")
async def a_course(c: CallbackQuery, state: FSMContext):
    await state.set_state(AddCourse.title)
    await c.message.answer("Kurs nomini yozing:")
    await c.answer()


@admin.message(AddCourse.title, F.text)
async def a_course_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AddCourse.price)
    await m.answer("Narxini yozing (so'mda, faqat raqam):")


@admin.message(AddCourse.price, F.text)
async def a_course_price(m: Message, state: FSMContext):
    digits = re.sub(r"\D", "", m.text)
    if not digits:
        return await m.answer("Faqat raqam yozing.")
    d = await state.get_data()
    await q("INSERT INTO courses(title, price) VALUES(?,?)", (d["title"], int(digits)), commit=True)
    await state.clear()
    await m.answer("✅ Kurs qo'shildi.", reply_markup=admin_kb())


# ── Dars qo'shish ──
@admin.callback_query(F.data == "adm:lesson")
async def a_lesson(c: CallbackQuery):
    await c.message.answer("Qaysi kursga dars qo'shamiz?", reply_markup=await courses_kb("lc"))
    await c.answer()


@admin.callback_query(F.data.startswith("lc:"))
async def a_lesson_course(c: CallbackQuery, state: FSMContext):
    await state.update_data(course_id=int(c.data.split(":")[1]))
    await state.set_state(AddLesson.title)
    await c.message.answer("Dars nomini yozing:")
    await c.answer()


@admin.message(AddLesson.title, F.text)
async def a_lesson_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AddLesson.content)
    await m.answer("Dars materialini yuboring (matn, video, fayl, rasm — hammasi mumkin):")


@admin.message(AddLesson.content)
async def a_lesson_content(m: Message, state: FSMContext):
    d = await state.get_data()
    await q("INSERT INTO lessons(course_id, title, content_chat, content_msg) VALUES(?,?,?,?)",
            (d["course_id"], d["title"], m.chat.id, m.message_id), commit=True)
    await state.clear()
    await m.answer("✅ Dars qo'shildi. (Shu xabarni chatdan o'chirmang.)", reply_markup=admin_kb())


# ── Vazifa qo'shish ──
@admin.callback_query(F.data == "adm:hw")
async def a_hw(c: CallbackQuery):
    await c.message.answer("Qaysi kurs uchun vazifa?", reply_markup=await courses_kb("hc"))
    await c.answer()


@admin.callback_query(F.data.startswith("hc:"))
async def a_hw_course(c: CallbackQuery, state: FSMContext):
    await state.update_data(course_id=int(c.data.split(":")[1]))
    await state.set_state(AddHw.title)
    await c.message.answer("Vazifa nomini yozing:")
    await c.answer()


@admin.message(AddHw.title, F.text)
async def a_hw_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AddHw.desc)
    await m.answer("Vazifa tavsifini yozing:")


@admin.message(AddHw.desc, F.text)
async def a_hw_desc(m: Message, state: FSMContext):
    await state.update_data(desc=m.text)
    await state.set_state(AddHw.deadline)
    await m.answer("Topshirish muddati (Toshkent vaqti): <code>2026-11-20 23:59</code>")


@admin.message(AddHw.deadline, F.text)
async def a_hw_deadline(m: Message, state: FSMContext, bot: Bot):
    try:
        dl = datetime.strptime(m.text.strip(), "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return await m.answer("Format noto'g'ri. Misol: <code>2026-11-20 23:59</code>")
    d = await state.get_data()
    await q("INSERT INTO homeworks(course_id, title, description, deadline) VALUES(?,?,?,?)",
            (d["course_id"], d["title"], d["desc"], dl), commit=True)
    await state.clear()
    await m.answer("✅ Vazifa qo'shildi. Talabalarga xabar yuborildi.", reply_markup=admin_kb())
    for s in await q("SELECT user_id FROM enrollments WHERE course_id=? AND status='approved'", (d["course_id"],)):
        try:
            await bot.send_message(s["user_id"], f"📝 Yangi vazifa: <b>{esc(d['title'])}</b>\n⏰ Muddat: {dl}\n"
                                                 "«📝 Vazifa topshirish» bo'limidan yuboring.")
        except Exception:
            pass


# ── Test qo'shish (43 talik) ──
@admin.callback_query(F.data == "adm:test")
async def a_test(c: CallbackQuery, state: FSMContext):
    await state.set_state(AddTest.title)
    await c.message.answer("Test nomini yozing:")
    await c.answer()


@admin.message(AddTest.title, F.text)
async def a_test_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AddTest.key)
    await m.answer(f"{TEST_QUESTIONS} ta to'g'ri javob kalitini yuboring.\n"
                   "Misol: <code>1a2b3c4d...</code> yoki <code>abcd...</code>")


@admin.message(AddTest.key, F.text)
async def a_test_key(m: Message, state: FSMContext):
    ans = parse_answers(m.text)
    if any(i not in ans for i in range(1, TEST_QUESTIONS + 1)):
        return await m.answer(f"❗ {TEST_QUESTIONS} ta javob kerak, siz {len(ans)} ta yubordingiz.")
    key = "".join(ans[i] for i in range(1, TEST_QUESTIONS + 1))
    d = await state.get_data()
    await q("INSERT INTO tests(title, answer_key) VALUES(?,?)", (d["title"], key), commit=True)
    await state.clear()
    await m.answer("✅ Test qo'shildi va faollashtirildi.", reply_markup=admin_kb())


# ── Talabalar / statistika / topshirmaganlar / xabar ──
@admin.callback_query(F.data == "adm:students")
async def a_students(c: CallbackQuery):
    rows = await q("""SELECT u.full_name, u.username, co.title FROM enrollments e
                      JOIN users u ON u.id=e.user_id JOIN courses co ON co.id=e.course_id
                      WHERE e.status='approved' ORDER BY e.id DESC LIMIT 50""")
    if not rows:
        await c.message.answer("Hali tasdiqlangan talaba yo'q.")
    else:
        lines = ["👥 <b>Oxirgi talabalar:</b>"]
        for r in rows:
            un = f" @{r['username']}" if r["username"] else ""
            lines.append(f"• {esc(r['full_name'] or '—')}{un} — {esc(r['title'])}")
        await c.message.answer("\n".join(lines))
    await c.answer()


@admin.callback_query(F.data == "adm:stats")
async def a_stats(c: CallbackQuery):
    async def n(sql):
        return (await q(sql, one=True))[0]
    users = await n("SELECT COUNT(*) FROM users")
    active = await n("SELECT COUNT(*) FROM enrollments WHERE status='approved'")
    pending = await n("SELECT COUNT(*) FROM enrollments WHERE status='pending'")
    subs = await n("SELECT COUNT(*) FROM submissions")
    results = await n("SELECT COUNT(*) FROM test_results")
    await c.message.answer(
        "📊 <b>Statistika</b>\n"
        f"Foydalanuvchilar: {users}\n"
        f"Faol talabalar: {active}\n"
        f"Kutilayotgan to'lovlar: {pending}\n"
        f"Topshirilgan vazifalar: {subs}\n"
        f"Test natijalari: {results}")
    await c.answer()


@admin.callback_query(F.data == "adm:missing")
async def a_missing(c: CallbackQuery, bot: Bot):
    hws = await q("SELECT * FROM homeworks ORDER BY id DESC LIMIT 5")
    if not hws:
        await c.message.answer("Vazifalar yo'q.")
    for hw in hws:
        await send_missing_report(bot, hw)
    await c.answer()


@admin.callback_query(F.data.startswith("remind:"))
async def a_remind(c: CallbackQuery, bot: Bot):
    hw = await q("SELECT * FROM homeworks WHERE id=?", (int(c.data.split(":")[1]),), one=True)
    sent = 0
    for s in await missing_students(hw):
        try:
            await bot.send_message(s["id"], f"⏰ Eslatma: «{esc(hw['title'])}» vazifasi hali topshirilmagan!")
            sent += 1
        except Exception:
            pass
    await c.answer(f"{sent} ta talabaga yuborildi", show_alert=True)


@admin.callback_query(F.data == "adm:bc")
async def a_bc(c: CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.text)
    await c.message.answer("Hammaga yuboriladigan xabarni yozing:")
    await c.answer()


@admin.message(Broadcast.text)
async def a_bc_send(m: Message, state: FSMContext, bot: Bot):
    await state.clear()
    ok = 0
    for u in await q("SELECT id FROM users"):
        try:
            await m.copy_to(u["id"])
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await m.answer(f"📢 {ok} ta foydalanuvchiga yuborildi.")


# ───────────────────────── Ishga tushirish ─────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO)
    await init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin)
    dp.include_router(student)
    sched = AsyncIOScheduler(timezone=TZ)
    sched.add_job(deadline_job, "interval", minutes=30, args=[bot])
    sched.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
