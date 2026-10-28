
"""
SMM (nakrutka) Telegram bot
Kutubxona: pip install "aiogram>=3.4"
Ishga tushirish: python bot.py
"""
import asyncio
import html
import logging
import os
import re
import sqlite3
 
from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
 
# ============ SOZLAMALAR ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "8935979814:AAEqjMI55Q_sJQaRGOSMeOsCC-AKmE1pUnw")
ADMIN_PASSWORD = "2012"   # botga shu yozilsa admin panel ochiladi
# ====================================
 
logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
 
# ---------- Platformalar va xizmatlar ----------
PLATFORMS = {
    "ig": ("📸 Instagram", {
        "views": "👁 Ko'rishlar", "likes": "❤️ Layklar",
        "followers": "👥 Obunachilar", "comments": "💬 Komentariyalar"}),
    "tg": ("✈️ Telegram", {
        "followers": "👥 Obunachilar", "reactions": "🔥 Reaksiyalar",
        "views": "👁 Ko'rishlar"}),
    "yt": ("▶️ YouTube", {
        "likes": "👍 Layklar", "followers": "👥 Obunachilar",
        "comments": "💬 Komentariyalar"}),
    "tt": ("🎵 TikTok", {
        "likes": "❤️ Layklar", "followers": "👥 Obunachilar",
        "comments": "💬 Komentariyalar"}),
}
 
# ---------- Klaviatura (pastdagi) tugmalar ----------
BTN_BAL = "💰 Hisobim"
BTN_TOPUP = "💳 Hisob to'ldirish"
BTN_EXIT = "🚪 Admin paneldan chiqish"
ADMIN_BTNS = ["🧾 Zakazlar", "💰 Narxlar", "💵 Balans to'ldirish", "🏦 Karta raqami",
              "👤 Admin nomi", "📢 Reklama berish", "📊 Statistika", "📌 Majburiy obuna"]
PLATFORM_BTNS = {v[0]: k for k, v in PLATFORMS.items()}
MENU_TEXTS = set(PLATFORM_BTNS) | {BTN_BAL, BTN_TOPUP, BTN_EXIT} | set(ADMIN_BTNS)
 
# ---------- Ma'lumotlar bazasi ----------
db = sqlite3.connect("bot.db", check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, name TEXT, username TEXT,
    balance INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tariffs(
    id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, service TEXT,
    qty INTEGER, price INTEGER);
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT,
    tariff TEXT, link TEXT, price INTEGER, status TEXT DEFAULT 'new',
    created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS channels(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, title TEXT, link TEXT);
""")
db.commit()
 
 
def run(sql, args=()):
    cur = db.execute(sql, args)
    db.commit()
    return cur
 
 
def one(sql, args=()):
    return db.execute(sql, args).fetchone()
 
 
def many(sql, args=()):
    return db.execute(sql, args).fetchall()
 
 
def get_setting(key, default=""):
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default
 
 
def set_setting(key, value):
    run("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
 
 
def money(n):
    return f"{int(n):,}".replace(",", " ") + " so'm"
 
 
def is_admin(uid):
    r = one("SELECT is_admin FROM users WHERE id=?", (uid,))
    return bool(r and r["is_admin"])
 
 
def tariff_title(t):
    p, s = t["platform"], t["service"]
    return f"{PLATFORMS[p][0]} {PLATFORMS[p][1][s]} — {t['qty']} ta"
 
 
def register(u):
    run("INSERT OR IGNORE INTO users(id,name,username) VALUES(?,?,?)",
        (u.id, u.full_name, u.username or ""))
    run("UPDATE users SET name=?, username=? WHERE id=?",
        (u.full_name, u.username or "", u.id))
 
 
async def show(target, text, kb=None):
    """Callback bo'lsa xabarni tahrirlaydi, aks holda yangi yuboradi."""
    markup = kb.as_markup() if kb else None
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=markup)
        except Exception:
            await target.message.answer(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)
 
 
# ---------- Holatlar ----------
class OrderS(StatesGroup):
    link = State()
    confirm = State()
 
 
class TopupS(StatesGroup):
    check = State()
 
 
class AdminS(StatesGroup):
    add_tariff = State()
    topup_manual = State()
    topup_amount = State()
    card = State()
    admin_name = State()
    ads = State()
    add_channel = State()
 
 
# ============ ADMIN PANELGA KIRISH (2012) ============
@dp.message(F.text == ADMIN_PASSWORD)
async def admin_login(m: Message, state: FSMContext):
    await state.clear()
    register(m.from_user)
    run("UPDATE users SET is_admin=1 WHERE id=?", (m.from_user.id,))
    await admin_menu(m)
 
 
@dp.message(F.text.in_(MENU_TEXTS))
async def reply_menu(m: Message, state: FSMContext):
    """Pastdagi klaviatura tugmalari (holatdan qat'i nazar ishlaydi)."""
    await state.clear()
    register(m.from_user)
    t = m.text
    if t in PLATFORM_BTNS:
        return await platform_menu(m, PLATFORM_BTNS[t])
    if t == BTN_BAL:
        return await balance(m)
    if t == BTN_TOPUP:
        return await topup(m, state)
    if not is_admin(m.from_user.id):
        return
    if t == BTN_EXIT:
        await m.answer("🚪 Admin paneldan chiqdingiz.")
        return await main_menu(m)
    if t == "🧾 Zakazlar":
        await a_orders(m)
    elif t == "💰 Narxlar":
        await a_prices(m)
    elif t == "💵 Balans to'ldirish":
        await a_topup(m, state)
    elif t == "🏦 Karta raqami":
        await a_card(m, state)
    elif t == "👤 Admin nomi":
        await a_name(m, state)
    elif t == "📢 Reklama berish":
        await a_ads(m, state)
    elif t == "📊 Statistika":
        await a_stats(m)
    elif t == "📌 Majburiy obuna":
        await a_subs(m)
 
 
async def admin_menu(target):
    kb = ReplyKeyboardBuilder()
    for t in ADMIN_BTNS:
        kb.button(text=t)
    kb.button(text=BTN_EXIT)
    kb.adjust(2, 2, 2, 2, 1)
    msg = target.message if isinstance(target, CallbackQuery) else target
    await msg.answer("👑 <b>ADMIN PANEL</b>\n\nKerakli bo'limni tanlang 👇",
                     reply_markup=kb.as_markup(resize_keyboard=True))
    if isinstance(target, CallbackQuery):
        await target.answer()
 
 
@dp.callback_query(F.data == "a:menu")
async def a_menu(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        return await c.answer("Ruxsat yo'q", show_alert=True)
    await state.clear()
    await admin_menu(c)
 
 
def back_admin():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Admin panel", callback_data="a:menu")
    return kb
 
 
# ---------- Admin: zakazlar ----------
@dp.callback_query(F.data == "a:orders")
async def a_orders(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer()
    rows = many("SELECT * FROM orders WHERE status='new' ORDER BY id DESC LIMIT 20")
    msg = c.message if isinstance(c, CallbackQuery) else c
    if isinstance(c, CallbackQuery):
        await c.answer()
    if not rows:
        return await show(c, "🧾 Yangi zakazlar yo'q.", back_admin())
    await msg.answer(f"🧾 <b>Yangi zakazlar:</b> {len(rows)} ta")
    for o in rows:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Bajarildi", callback_data=f"done:{o['id']}")
        await msg.answer(
            f"🆔 Zakaz #{o['id']}\n"
            f"👤 Foydalanuvchi: {o['name']}\n"
            f"🔢 Telegram ID: <code>{o['user_id']}</code>\n"
            f"📦 Tarif: {o['tariff']}\n"
            f"🔗 Link: {o['link']}\n"
            f"💵 Narx: {money(o['price'])}",
            reply_markup=kb.as_markup(), disable_web_page_preview=True)
    await msg.answer("⬆️ Zakazlar ro'yxati", reply_markup=back_admin().as_markup())
 
 
@dp.callback_query(F.data.startswith("done:"))
async def a_done(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer()
    oid = int(c.data.split(":")[1])
    o = one("SELECT * FROM orders WHERE id=?", (oid,))
    if not o:
        return await c.answer("Topilmadi", show_alert=True)
    run("UPDATE orders SET status='done' WHERE id=?", (oid,))
    await c.message.edit_text(c.message.text + "\n\n✅ BAJARILDI")
    try:
        await bot.send_message(o["user_id"], f"✅ Zakaz #{oid} bajarildi!\n📦 {o['tariff']}")
    except Exception:
        pass
    await c.answer("Bajarildi")
 
 
# ---------- Admin: narxlar ----------
@dp.callback_query(F.data == "a:prices")
async def a_prices(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer()
    kb = InlineKeyboardBuilder()
    for k, (title, _) in PLATFORMS.items():
        kb.button(text=title, callback_data=f"ap:{k}")
    kb.button(text="⬅️ Orqaga", callback_data="a:menu")
    kb.adjust(2, 2, 1)
    await show(c, "💰 <b>Narxlar</b>\nPlatformani tanlang:", kb)
 
 
@dp.callback_query(F.data.startswith("ap:"))
async def a_prices_platform(c: CallbackQuery):
    p = c.data.split(":")[1]
    kb = InlineKeyboardBuilder()
    for k, title in PLATFORMS[p][1].items():
        kb.button(text=title, callback_data=f"as:{p}:{k}")
    kb.button(text="⬅️ Orqaga", callback_data="a:prices")
    kb.adjust(2)
    await show(c, f"{PLATFORMS[p][0]}\nXizmat turini tanlang:", kb)
 
 
@dp.callback_query(F.data.startswith("as:"))
async def a_prices_service(c: CallbackQuery, state: FSMContext):
    await state.clear()
    _, p, s = c.data.split(":")
    rows = many("SELECT * FROM tariffs WHERE platform=? AND service=? ORDER BY qty", (p, s))
    text = f"{PLATFORMS[p][0]} {PLATFORMS[p][1][s]}\n\n"
    kb = InlineKeyboardBuilder()
    if rows:
        for i, t in enumerate(rows, 1):
            text += f"{i}. {t['qty']} ta — {money(t['price'])}\n"
            kb.button(text=f"🗑 {i}-ni o'chirish", callback_data=f"ad:{t['id']}:{p}:{s}")
    else:
        text += "Hozircha tarif yo'q."
    kb.button(text="➕ Tarif qo'shish", callback_data=f"aa:{p}:{s}")
    kb.button(text="⬅️ Orqaga", callback_data=f"ap:{p}")
    kb.adjust(2)
    await show(c, text, kb)
 
 
@dp.callback_query(F.data.startswith("ad:"))
async def a_delete(c: CallbackQuery, state: FSMContext):
    _, tid, p, s = c.data.split(":")
    run("DELETE FROM tariffs WHERE id=?", (tid,))
    c.data = f"as:{p}:{s}"
    await a_prices_service(c, state)
 
 
@dp.callback_query(F.data.startswith("aa:"))
async def a_add(c: CallbackQuery, state: FSMContext):
    _, p, s = c.data.split(":")
    await state.set_state(AdminS.add_tariff)
    await state.update_data(p=p, s=s)
    await show(c, "➕ Tarifni <b>miqdor narx</b> ko'rinishida yozing.\n\n"
                  "Masalan: <code>100 15000</code>\n"
                  "(100 ta — 15 000 so'm)\n\nBir nechta qatorda ham yuborsangiz bo'ladi.",
               back_admin())
 
 
@dp.message(AdminS.add_tariff)
async def a_add_done(m: Message, state: FSMContext):
    d = await state.get_data()
    added = 0
    for line in m.text.splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            run("INSERT INTO tariffs(platform,service,qty,price) VALUES(?,?,?,?)",
                (d["p"], d["s"], int(parts[0]), int(parts[1])))
            added += 1
    if not added:
        return await m.answer("❌ Format noto'g'ri. Masalan: <code>100 15000</code>")
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Narxlarni ko'rish", callback_data=f"as:{d['p']}:{d['s']}")
    kb.button(text="⬅️ Admin panel", callback_data="a:menu")
    kb.adjust(1)
    await m.answer(f"✅ {added} ta tarif qo'shildi.", reply_markup=kb.as_markup())
 
 
# ---------- Admin: hisob to'ldirish ----------
@dp.callback_query(F.data == "a:topup")
async def a_topup(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        return await c.answer()
    await state.set_state(AdminS.topup_manual)
    await show(c, "💳 <b>Hisob to'ldirish</b>\n\nFoydalanuvchi ID va summani yozing:\n"
                  "<code>123456789 50000</code>", back_admin())
 
 
@dp.message(AdminS.topup_manual)
async def a_topup_manual(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) != 2 or not all(x.isdigit() for x in parts):
        return await m.answer("❌ Format: <code>ID summa</code>")
    await state.clear()
    await add_balance(m, int(parts[0]), int(parts[1]))
 
 
@dp.callback_query(F.data.startswith("fill:"))
async def a_fill(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        return await c.answer()
    uid = int(c.data.split(":")[1])
    await state.set_state(AdminS.topup_amount)
    await state.update_data(uid=uid)
    await c.message.answer(f"💵 <code>{uid}</code> hisobiga qancha qo'shamiz? Summani yozing:")
    await c.answer()
 
 
@dp.message(AdminS.topup_amount)
async def a_topup_amount(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("❌ Faqat raqam yozing.")
    uid = (await state.get_data())["uid"]
    await state.clear()
    await add_balance(m, uid, int(m.text))
 
 
async def add_balance(m: Message, uid: int, amount: int):
    if not one("SELECT id FROM users WHERE id=?", (uid,)):
        return await m.answer("❌ Bunday foydalanuvchi topilmadi.", reply_markup=back_admin().as_markup())
    run("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))
    bal = one("SELECT balance FROM users WHERE id=?", (uid,))["balance"]
    await m.answer(f"✅ Hisob to'ldirildi: +{money(amount)}", reply_markup=back_admin().as_markup())
    try:
        await bot.send_message(uid, f"✅ Hisobingiz to'ldirildi: <b>+{money(amount)}</b>\n"
                                    f"💰 Balans: <b>{money(bal)}</b>")
    except Exception:
        pass
 
 
# ---------- Admin: karta / ism / reklama / statistika ----------
@dp.callback_query(F.data == "a:card")
async def a_card(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        return await c.answer()
    await state.set_state(AdminS.card)
    await show(c, f"🏦 Hozirgi karta: <code>{get_setting('card', 'kiritilmagan')}</code>\n\n"
                  "Yangi karta raqamini yozing:", back_admin())
 
 
@dp.message(AdminS.card)
async def a_card_save(m: Message, state: FSMContext):
    set_setting("card", m.text.strip())
    await state.clear()
    await m.answer("✅ Karta saqlandi.", reply_markup=back_admin().as_markup())
 
 
@dp.callback_query(F.data == "a:name")
async def a_name(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        return await c.answer()
    await state.set_state(AdminS.admin_name)
    await show(c, f"👤 Hozirgi admin: {get_setting('admin_name', 'kiritilmagan')}\n\n"
                  "Yangi admin username yozing (masalan: @shohk_94):", back_admin())
 
 
@dp.message(AdminS.admin_name)
async def a_name_save(m: Message, state: FSMContext):
    set_setting("admin_name", m.text.strip())
    await state.clear()
    await m.answer("✅ Admin nomi saqlandi.", reply_markup=back_admin().as_markup())
 
 
@dp.callback_query(F.data == "a:ads")
async def a_ads(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        return await c.answer()
    await state.set_state(AdminS.ads)
    await show(c, "📢 Reklama xabarini yuboring (matn, rasm yoki video).\n"
                  "U hamma foydalanuvchilarga yuboriladi.", back_admin())
 
 
@dp.message(AdminS.ads)
async def a_ads_send(m: Message, state: FSMContext):
    await state.clear()
    ok = fail = 0
    for u in many("SELECT id FROM users"):
        try:
            await m.copy_to(u["id"])
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await m.answer(f"📢 Reklama yuborildi.\n✅ {ok} ta\n❌ {fail} ta",
                   reply_markup=back_admin().as_markup())
 
 
@dp.callback_query(F.data == "a:stats")
async def a_stats(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer()
    users = one("SELECT COUNT(*) n FROM users")["n"]
    orders = one("SELECT COUNT(*) n FROM orders")["n"]
    new = one("SELECT COUNT(*) n FROM orders WHERE status='new'")["n"]
    income = one("SELECT COALESCE(SUM(price),0) s FROM orders")["s"]
    await show(c, f"📊 <b>Statistika</b>\n\n👥 Foydalanuvchilar: {users}\n"
                  f"🧾 Jami zakazlar: {orders}\n🆕 Yangi zakazlar: {new}\n"
                  f"💵 Jami tushum: {money(income)}", back_admin())
 
 
# ============ MAJBURIY OBUNA ============
def parse_channel(text):
    """@kanal, t.me/kanal yoki "-100123... https://t.me/+xxxx" ni tahlil qiladi."""
    chat = link = None
    for p in text.split():
        if re.fullmatch(r"-?\d{5,}", p):
            chat = int(p)
        elif p.startswith("@"):
            chat = chat or p
            link = link or f"https://t.me/{p[1:]}"
        elif "t.me/" in p:
            path = p.split("t.me/")[1].split("?")[0].strip("/")
            link = "https://t.me/" + path
            if not path.startswith(("+", "joinchat")) and chat is None:
                chat = "@" + path
    return chat, link
 
 
async def not_subscribed(uid):
    missing = []
    for ch in many("SELECT * FROM channels"):
        try:
            mem = await bot.get_chat_member(ch["chat_id"], uid)
            ok = mem.status in ("member", "administrator", "creator") or (
                mem.status == "restricted" and getattr(mem, "is_member", False))
        except Exception as e:  # bot kanalda admin emas va hokazo
            logging.warning("Obuna tekshirib bo'lmadi (%s): %s", ch["chat_id"], e)
            ok = True
        if not ok:
            missing.append(ch)
    return missing
 
 
async def send_sub_prompt(event, missing):
    kb = InlineKeyboardBuilder()
    for ch in missing:
        kb.button(text=f"📢 {ch['title']}", url=ch["link"])
    kb.button(text="✅ Obunani tekshirish", callback_data="chk_sub")
    kb.adjust(1)
    text = ("❗ Botdan foydalanish uchun avval quyidagi kanallarga obuna bo'ling, "
            "so'ng <b>Tekshirish</b> tugmasini bosing 👇")
    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb.as_markup())
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb.as_markup())
 
 
class SubMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = event.from_user
        if user and not user.is_bot:
            register(user)
            bypass = (isinstance(event, Message) and event.text == ADMIN_PASSWORD) or \
                     (isinstance(event, CallbackQuery) and event.data == "chk_sub")
            if not bypass and not is_admin(user.id):
                missing = await not_subscribed(user.id)
                if missing:
                    return await send_sub_prompt(event, missing)
        return await handler(event, data)
 
 
dp.message.outer_middleware(SubMiddleware())
dp.callback_query.outer_middleware(SubMiddleware())
 
 
@dp.callback_query(F.data == "chk_sub")
async def chk_sub(c: CallbackQuery):
    if await not_subscribed(c.from_user.id):
        return await c.answer("❌ Siz hali hamma kanalga obuna bo'lmadingiz!", show_alert=True)
    try:
        await c.message.delete()
    except Exception:
        pass
    await main_menu(c)
 
 
@dp.callback_query(F.data == "a:subs")
async def a_subs(c):
    if not is_admin(c.from_user.id):
        return
    rows = many("SELECT * FROM channels ORDER BY id")
    text = "📌 <b>Majburiy obuna kanallari</b>\n\n"
    kb = InlineKeyboardBuilder()
    if rows:
        for i, ch in enumerate(rows, 1):
            text += f'{i}. <a href="{ch["link"]}">{html.escape(ch["title"] or "Kanal")}</a>\n'
            kb.button(text=f"🗑 {i}-ni olib tashlash", callback_data=f"cd:{ch['id']}")
    else:
        text += "Hozircha kanal yo'q — obuna talab qilinmaydi."
    kb.button(text="➕ Kanal qo'shish", callback_data="ca")
    kb.button(text="⬅️ Admin panel", callback_data="a:menu")
    kb.adjust(2)
    await show(c, text, kb)
 
 
@dp.callback_query(F.data == "ca")
async def a_channel_add(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        return await c.answer()
    await state.set_state(AdminS.add_channel)
    await show(c,
               "➕ <b>Kanal qo'shish</b>\n\n"
               "Ochiq kanal: linkini yoki @username ni yuboring.\n"
               "<code>https://t.me/kanal_nomi</code>\n\n"
               "Yopiq kanal: ID va invite linkni birga yuboring.\n"
               "<code>-1001234567890 https://t.me/+AbCdEf</code>\n\n"
               "⚠️ Avval botni kanalga <b>admin</b> qilib qo'shing, aks holda obunani tekshira olmaydi.",
               back_admin())
 
 
@dp.message(AdminS.add_channel, F.text)
async def a_channel_save(m: Message, state: FSMContext):
    chat, link = parse_channel(m.text)
    if chat is None or link is None:
        return await m.answer("❌ Format noto'g'ri. Ochiq kanal uchun link/@username, "
                              "yopiq kanal uchun <code>ID link</code> yuboring.")
    try:
        info = await bot.get_chat(chat)
        me = await bot.get_chat_member(info.id, bot.id)
        if me.status not in ("administrator", "creator"):
            raise ValueError("bot admin emas")
    except Exception:
        return await m.answer("❌ Kanal topilmadi yoki bot kanalda admin emas.\n"
                              "Botni kanalga admin qilib, qaytadan yuboring.")
    if one("SELECT id FROM channels WHERE chat_id=?", (info.id,)):
        await state.clear()
        return await m.answer("ℹ️ Bu kanal allaqachon qo'shilgan.")
    run("INSERT INTO channels(chat_id,title,link) VALUES(?,?,?)",
        (info.id, info.title or "Kanal", link))
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="📌 Kanallar ro'yxati", callback_data="a:subs")
    kb.button(text="⬅️ Admin panel", callback_data="a:menu")
    kb.adjust(1)
    await m.answer(f"✅ Kanal qo'shildi: <b>{html.escape(info.title or 'Kanal')}</b>",
                   reply_markup=kb.as_markup())
 
 
@dp.callback_query(F.data.startswith("cd:"))
async def a_channel_del(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer()
    run("DELETE FROM channels WHERE id=?", (c.data.split(":")[1],))
    await c.answer("🗑 Olib tashlandi")
    await a_subs(c)
 
 
# ============ FOYDALANUVCHI QISMI ============
async def main_menu(target):
    kb = ReplyKeyboardBuilder()
    for title, _ in PLATFORMS.values():
        kb.button(text=title)
    kb.button(text=BTN_BAL)
    kb.button(text=BTN_TOPUP)
    kb.adjust(2, 2, 2)
    msg = target.message if isinstance(target, CallbackQuery) else target
    await msg.answer("🔥 <b>Xush kelibsiz!</b>\n\nKerakli ijtimoiy tarmoqni tanlang 👇",
                     reply_markup=kb.as_markup(resize_keyboard=True))
    if isinstance(target, CallbackQuery):
        await target.answer()
 
 
@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    register(m.from_user)
    await main_menu(m)
 
 
@dp.callback_query(F.data == "menu")
async def menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await main_menu(c)
 
 
@dp.callback_query(F.data == "balance")
async def balance(c: CallbackQuery):
    register(c.from_user)
    bal = one("SELECT balance FROM users WHERE id=?", (c.from_user.id,))["balance"]
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Hisob to'ldirish", callback_data="topup")
    kb.button(text="⬅️ Menyu", callback_data="menu")
    kb.adjust(1)
    await show(c, f"💰 Sizning balansingiz: <b>{money(bal)}</b>\n🆔 ID: <code>{c.from_user.id}</code>", kb)
 
 
@dp.callback_query(F.data.startswith("p:"))
async def platform(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await platform_menu(c, c.data.split(":")[1])
 
 
async def platform_menu(target, p):
    kb = InlineKeyboardBuilder()
    for k, title in PLATFORMS[p][1].items():
        kb.button(text=title, callback_data=f"s:{p}:{k}")
    kb.button(text="⬅️ Orqaga", callback_data="menu")
    kb.adjust(2)
    await show(target, f"{PLATFORMS[p][0]}\n\nXizmat turini tanlang:", kb)
 
 
@dp.callback_query(F.data.startswith("s:"))
async def service(c: CallbackQuery):
    _, p, s = c.data.split(":")
    rows = many("SELECT * FROM tariffs WHERE platform=? AND service=? ORDER BY qty", (p, s))
    kb = InlineKeyboardBuilder()
    text = f"{PLATFORMS[p][0]} {PLATFORMS[p][1][s]}\n\n"
    if not rows:
        text += "😔 Hozircha bu xizmat uchun narxlar kiritilmagan."
    else:
        text += "💰 <b>Narxlar:</b>\n\n"
        for i, t in enumerate(rows, 1):
            text += f"<b>{i}.</b> {t['qty']} ta — {money(t['price'])}\n"
            kb.button(text=str(i), callback_data=f"t:{t['id']}")
        text += "\n👇 Kerakli tarif raqamini bosing:"
    kb.adjust(5)
    kb.row(*InlineKeyboardBuilder().button(text="⬅️ Orqaga", callback_data=f"p:{p}").buttons)
    await show(c, text, kb)
 
 
@dp.callback_query(F.data.startswith("t:"))
async def tariff(c: CallbackQuery, state: FSMContext):
    t = one("SELECT * FROM tariffs WHERE id=?", (c.data.split(":")[1],))
    if not t:
        return await c.answer("Tarif topilmadi", show_alert=True)
    await state.set_state(OrderS.link)
    await state.update_data(tid=t["id"])
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Bekor qilish", callback_data="menu")
    await show(c, f"✅ Siz shu tarifni tanladingiz:\n\n📦 <b>{tariff_title(t)}</b>\n"
                  f"💵 Narxi: <b>{money(t['price'])}</b>\n\n"
                  "🔗 Endi nakrutka uriladigan <b>linkni</b> yuboring:", kb)
 
 
@dp.message(OrderS.link, F.text)
async def got_link(m: Message, state: FSMContext):
    link = m.text.strip()
    if len(link) < 4:
        return await m.answer("❌ Link noto'g'ri, qaytadan yuboring.")
    d = await state.get_data()
    t = one("SELECT * FROM tariffs WHERE id=?", (d["tid"],))
    await state.update_data(link=link)
    await state.set_state(OrderS.confirm)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ TASTIQLASH", callback_data="confirm")
    kb.button(text="❌ Bekor qilish", callback_data="menu")
    kb.adjust(1)
    await m.answer(
        f"📋 <b>Buyurtma ma'lumotlari</b>\n\n📦 {tariff_title(t)}\n🔗 {link}\n"
        f"💵 Narx: <b>{money(t['price'])}</b>\n\n"
        "⚠️ Agar <b>TASTIQLAS</b>ni bossangiz hisobdan pul yechiladi.",
        reply_markup=kb.as_markup(), disable_web_page_preview=True)
 
 
@dp.callback_query(OrderS.confirm, F.data == "confirm")
async def confirm(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    t = one("SELECT * FROM tariffs WHERE id=?", (d["tid"],))
    if not t:
        await state.clear()
        return await c.answer("Tarif o'chirilgan", show_alert=True)
    cur = run("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
              (t["price"], c.from_user.id, t["price"]))
    if cur.rowcount == 0:
        await state.clear()
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Hisob to'ldirish", callback_data="topup")
        kb.button(text="⬅️ Menyu", callback_data="menu")
        kb.adjust(1)
        return await show(c, "❌ Hisobingizda mablag' yetarli emas.\nAvval hisobni to'ldiring.", kb)
 
    title = tariff_title(t)
    oid = run("INSERT INTO orders(user_id,name,tariff,link,price) VALUES(?,?,?,?,?)",
              (c.from_user.id, c.from_user.full_name, title, d["link"], t["price"])).lastrowid
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Menyu", callback_data="menu")
    await show(c, f"✅ Buyurtma #{oid} qabul qilindi!\n📦 {title}\n💵 {money(t['price'])} yechildi.\n\n"
                  "Tez orada bajariladi ⏳", kb)
 
    uname = f"@{c.from_user.username}" if c.from_user.username else "—"
    akb = InlineKeyboardBuilder()
    akb.button(text="✅ Bajarildi", callback_data=f"done:{oid}")
    for a in many("SELECT id FROM users WHERE is_admin=1"):
        try:
            await bot.send_message(
                a["id"],
                f"🆕 <b>YANGI ZAKAZ #{oid}</b>\n\n👤 Foydalanuvchi: {c.from_user.full_name} ({uname})\n"
                f"🔢 Telegram ID: <code>{c.from_user.id}</code>\n📦 Tarif: {title}\n"
                f"🔗 Link: {d['link']}\n💵 Narx: {money(t['price'])}",
                reply_markup=akb.as_markup(), disable_web_page_preview=True)
        except Exception:
            pass
 
 
# ---------- Foydalanuvchi: hisob to'ldirish ----------
@dp.callback_query(F.data == "topup")
async def topup(c: CallbackQuery, state: FSMContext):
    await state.set_state(TopupS.check)
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Menyu", callback_data="menu")
    await show(c,
               "💳 <b>Hisob to'ldirish</b>\n\n"
               f"Karta raqami:\n<code>{get_setting('card', 'Hali kiritilmagan')}</code>\n\n"
               f"Karta egasi / admin: {get_setting('admin_name', '@admin')}\n\n"
               f"💸 Pulni o'tkazing va <b>chekni (screenshot) shu yerga yuboring</b> "
               f"yoki adminga tashlang: {get_setting('admin_name', '@admin')}\n\n"
               f"🆔 Sizning ID: <code>{c.from_user.id}</code>", kb)
 
 
@dp.message(TopupS.check, F.photo | F.document)
async def got_check(m: Message, state: FSMContext):
    await state.clear()
    uname = f"@{m.from_user.username}" if m.from_user.username else "—"
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 Hisobni to'ldirish", callback_data=f"fill:{m.from_user.id}")
    for a in many("SELECT id FROM users WHERE is_admin=1"):
        try:
            await m.copy_to(
                a["id"],
                caption=f"💳 <b>Yangi chek</b>\n👤 {m.from_user.full_name} ({uname})\n"
                        f"🆔 <code>{m.from_user.id}</code>",
                reply_markup=kb.as_markup())
        except Exception:
            pass
    await m.answer("✅ Chek adminga yuborildi. Tez orada hisobingiz to'ldiriladi.")
 
 
@dp.message(F.text)
async def fallback(m: Message):
    register(m.from_user)
    await main_menu(m)
 
 
# ---------- Ishga tushirish ----------
async def main():
    from aiogram.client.default import DefaultBotProperties
    global bot
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
 
 
if __name__ == "__main__":
    asyncio.run(main())