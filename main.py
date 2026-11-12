import sqlite3
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ================= SOZLAMALAR =================
BOT_TOKEN = "8636730483:AAGl0wHYP-ZBqaEA64EKUkzSlo1G3DDmkcI"
ADMIN_PAROL = "kimyo2026"
KANAL_USER = "@kimyo_sertifkat_uchun"
KARTA_RAQAM = "9860350142097954"
KARTA_EGASI = "Azizbek Ibrohimov"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

user_states = {}
user_data = {}

# ================= BAZA =================
def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                is_admin INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                test_code INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                answers TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                test_code INTEGER,
                score INTEGER,
                total INTEGER,
                percent REAL
            )
        """)
        conn.commit()

def db_add_user(user_id, full_name, username):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, full_name, username) VALUES (?, ?, ?)", (user_id, full_name, username or ""))
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
    kb.add(
        KeyboardButton("📝 Test tekshirish"),
        KeyboardButton("🏆 Test reytingi"),
        KeyboardButton("✍️ Kursga yozilish"),
        KeyboardButton("ℹ️ Kurslar haqida"),
        KeyboardButton("📞 Admin bilan aloqa")
    )
    if db_is_admin(user_id):
        kb.add(KeyboardButton("⚙️ Admin Panel"))
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("➕ Yangi test yaratish"),
        KeyboardButton("📋 Testlar roʻyxati"),
        KeyboardButton("🗑 Testni oʻchirish"),
        KeyboardButton("📊 Statistika"),
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
    bot.send_message(uid, f"Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n🧪 A+ Kimyo botiga xush kelibsiz.", reply_markup=main_menu(uid))

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    uid = message.from_user.id
    db_add_user(uid, message.from_user.full_name, message.from_user.username)
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PAROL:
        db_set_admin(uid)
        bot.send_message(uid, "✅ Sizga Admin huquqi berildi!", reply_markup=admin_menu())
    elif db_is_admin(uid):
        bot.send_message(uid, "⚙️ Admin Panel:", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "🔒 Parolni kiriting:\n<code>/admin kimyo2026</code>")

@bot.message_handler(func=lambda m: m.text in ["❌ Bekor qilish", "🔙 Asosiy menyu"])
def cancel_action(message):
    uid = message.from_user.id
    user_states.pop(uid, None)
    bot.send_message(uid, "🏠 Asosiy menyu:", reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def open_admin(message):
    uid = message.from_user.id
    if db_is_admin(uid):
        user_states.pop(uid, None)
        bot.send_message(uid, "⚙️ Admin Panel:", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "ℹ️ Kurslar haqida")
def about_courses(message):
    bot.send_message(message.chat.id, f"🧪 <b>A+ Kimyo kurslari</b>\n- Noldan boshlovchilar uchun\n- Milliy sertifikat va attestatsiya\n\n📢 Kanal: {KANAL_USER}")

@bot.message_handler(func=lambda m: m.text == "📞 Admin bilan aloqa")
def contact_admin(message):
    bot.send_message(message.chat.id, f"👨‍🏫 Muallif: Azizbek Ibrohimov\n📢 Kanal: {KANAL_USER}")

# ================= TEST TEKSHIRISH =================
@bot.message_handler(func=lambda m: m.text == "📝 Test tekshirish")
def ask_test_code(message):
    uid = message.from_user.id
    user_states[uid] = "wait_test_input"
    bot.send_message(uid, "📝 Test kodini yuboring (masalan: <code>1</code> yoki <code>1*abcd</code>):", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_test_input")
def process_test_input(message):
    uid = message.from_user.id
    txt = message.text.strip()
    if "*" in txt:
        parts = txt.split("*", 1)
        if not parts[0].isdigit():
            return bot.send_message(uid, "⚠️ Test kodi raqam boʻlishi kerak!")
        evaluate_test(message, int(parts[0]), parts[1].strip().lower())
    else:
        if not txt.isdigit():
            return bot.send_message(uid, "⚠️ Test kodini raqamda kiriting!")
        test_code = int(txt)
        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (test_code,))
            row = c.fetchone()
        if not row:
            return bot.send_message(uid, "❌ Test topilmadi!")
        user_data[uid] = {"test_code": test_code}
        user_states[uid] = "wait_test_answers"
        bot.send_message(uid, f"📘 Test: <b>{row[0]}</b>\nJavoblarni yuboring (masalan: <code>abcd...</code>):")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_test_answers")
def process_test_answers(message):
    uid = message.from_user.id
    test_code = user_data[uid]["test_code"]
    evaluate_test(message, test_code, message.text.strip().lower())

def evaluate_test(message, test_code, user_ans):
    uid = message.from_user.id
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title, answers FROM tests WHERE test_code = ?", (test_code,))
        row = c.fetchone()
    if not row:
        return bot.send_message(uid, "❌ Test topilmadi!")
    title, correct_ans = row[0], row[1].lower()
    if len(user_ans) != len(correct_ans):
        return bot.send_message(uid, f"⚠️ Savollar soni toʻgʻri kelmadi! Testda {len(correct_ans)} ta savol bor.")
    score = sum(1 for u, k in zip(user_ans, correct_ans) if u == k)
    total = len(correct_ans)
    percent = round((score / total) * 100, 1)

    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM results WHERE user_id = ? AND test_code = ?", (uid, test_code))
        if not c.fetchone():
            c.execute("INSERT INTO results (user_id, full_name, test_code, score, total, percent) VALUES (?, ?, ?, ?, ?, ?)", (uid, message.from_user.full_name, test_code, score, total, percent))
            conn.commit()

    user_states.pop(uid, None)
    bot.send_message(uid, f"📊 <b>Natija:</b> {score}/{total} ({percent}%)\n📘 {title}", reply_markup=main_menu(uid))

# ================= REYTING =================
@bot.message_handler(func=lambda m: m.text == "🏆 Test reytingi")
def ask_rating_code(message):
    uid = message.from_user.id
    user_states[uid] = "wait_rating_code"
    bot.send_message(uid, "🏆 Reyting uchun test kodini kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "wait_rating_code")
def show_test_rating(message):
    uid = message.from_user.id
    if not message.text.isdigit():
        return bot.send_message(uid, "⚠️ Raqam kiriting!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT title FROM tests WHERE test_code = ?", (code,))
        t_row = c.fetchone()
        if not t_row:
            return bot.send_message(uid, "❌ Test topilmadi!")
        c.execute("SELECT full_name, score, total, percent FROM results WHERE test_code = ? ORDER BY score DESC LIMIT 20", (code,))
        rows = c.fetchall()
    user_states.pop(uid, None)
    if not rows:
        return bot.send_message(uid, "📭 Hali hech kim ishlamagan.", reply_markup=main_menu(uid))
    text = f"🏆 <b>TEST #{code} REYTINGI</b>\n📘 <b>{t_row[0]}</b>\n\n"
    for idx, r in enumerate(rows, start=1):
        text += f"{idx}. {r[0]} — <b>{r[1]}/{r[2]}</b> ({r[3]}%)\n"
    bot.send_message(uid, text, reply_markup=main_menu(uid))

# ================= KURSGA YOZILISH =================
@bot.message_handler(func=lambda m: m.text == "✍️ Kursga yozilish")
def reg_step1(message):
    uid = message.from_user.id
    user_states[uid] = "reg_name"
    bot.send_message(uid, "✍️ Ism va familiyangizni kiriting:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "reg_name")
def reg_step2(message):
    uid = message.from_user.id
    user_data[uid] = {"ism": message.text}
    user_states[uid] = "reg_phone"
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True), KeyboardButton("❌ Bekor qilish"))
    bot.send_message(uid, "📱 Telefon raqamingizni yuboring:", reply_markup=kb)

@bot.message_handler(content_types=['contact', 'text'], func=lambda m: user_states.get(m.from_user.id) == "reg_phone")
def reg_step3(message):
    uid = message.from_user.id
    if message.text == "❌ Bekor qilish":
        return cancel_action(message)
    phone = message.contact.phone_number if message.contact else message.text
    user_data[uid]["phone"] = phone
    user_states[uid] = "reg_receipt"
    bot.send_message(uid, f"💳 Karta: <code>{KARTA_RAQAM}</code> ({KARTA_EGASI})\n📸 Toʻlov chekini yuboring:", reply_markup=cancel_kb())

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.from_user.id) == "reg_receipt")
def reg_finish(message):
    uid = message.from_user.id
    info = user_data.get(uid, {})
    photo_id = message.photo[-1].file_id
    admins = db_get_admins()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{uid}"), InlineKeyboardButton("❌ Rad etish", callback_data=f"pay_no_{uid}"))
    caption = f"🆕 <b>YANGI ARIZA</b>\nIsm: {info.get('ism')}\nTel: {info.get('phone')}\nID: <code>{uid}</code>"
    for adm in admins:
        try:
            bot.send_photo(adm, photo_id, caption=caption, reply_markup=kb)
        except Exception:
            pass
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Chek adminga yuborildi!", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def handle_payment_decision(call):
    parts = call.data.split("_")
    action, target_uid = parts[1], int(parts[2])
    if action == "ok":
        bot.send_message(target_uid, "🎉 Toʻlovingiz tasdiqlandi!")
        bot.edit_message_caption(caption=call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    else:
        bot.send_message(target_uid, "❌ Toʻlov tasdiqlanmadi.")
        bot.edit_message_caption(caption=call.message.caption + "\n\n❌ <b>RAD ETILDI</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
    bot.answer_callback_query(call.id)

# ================= ADMIN PANEL =================
@bot.message_handler(func=lambda m: m.text == "➕ Yangi test yaratish")
def adm_new_test(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "adm_test_title"
    bot.send_message(uid, "📘 Test nomini yozing:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_test_title")
def adm_new_test_keys(message):
    uid = message.from_user.id
    user_data[uid] = {"title": message.text}
    user_states[uid] = "adm_test_keys"
    bot.send_message(uid, "🔑 Javoblar kalitini yozing (masalan: <code>abcd...</code>):")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_test_keys")
def adm_save_test(message):
    uid = message.from_user.id
    keys = message.text.strip().lower().replace(" ", "")
    title = user_data[uid]["title"]
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tests (title, answers) VALUES (?, ?)", (title, keys))
        code = c.lastrowid
        conn.commit()
    user_states.pop(uid, None)
    bot.send_message(uid, f"✅ Test qoʻshildi!\n🔢 Kod: <code>{code}</code>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Testlar roʻyxati")
def adm_list_tests(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT test_code, title, length(answers) FROM tests ORDER BY test_code DESC LIMIT 15")
        rows = c.fetchall()
    if not rows: return bot.send_message(uid, "Testlar yoʻq.")
    text = "📋 <b>Testlar:</b>\n" + "\n".join([f"🔹 Kod: <code>{r[0]}</code> | {r[1]} ({r[2]} ta)" for r in rows])
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🗑 Testni oʻchirish")
def adm_del_test_ask(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    user_states[uid] = "adm_del_test"
    bot.send_message(uid, "🗑 Test kodini yozing:", reply_markup=cancel_kb())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "adm_del_test")
def adm_del_test_confirm(message):
    uid = message.from_user.id
    if not message.text.isdigit(): return bot.send_message(uid, "⚠️ Faqat raqam!")
    code = int(message.text)
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tests WHERE test_code = ?", (code,))
        conn.commit()
        deleted = c.rowcount
    user_states.pop(uid, None)
    bot.send_message(uid, "✅ Oʻchirildi!" if deleted else "❌ Topilmadi.", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def adm_stats(message):
    uid = message.from_user.id
    if not db_is_admin(uid): return
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        u = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM tests")
        t = c.fetchone()[0]
    bot.send_message(uid, f"📊 Oʻquvchilar: {u}\nTestlar: {t}")

if __name__ == "__main__":
    init_db()
    print("Bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
