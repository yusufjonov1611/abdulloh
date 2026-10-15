import os
import sys
import html
import asyncio
import logging
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from aiohttp import web
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from pdf_searcher import search_word_in_pdf, get_total_pages
from web_server import setup_web_app
from data_manager import (
    SUPER_ADMIN_ID, is_super_admin, is_admin,
    get_second_admin, set_second_admin, remove_second_admin,
    get_channels, add_channel, remove_channel,
    register_user, get_users_count, get_users_list,
    get_all_books, get_active_book, set_active_book,
    add_new_book, delete_book
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "8329325372:AAFo02n3AKlZntAD_JMvTcPrIgefwXvgQ-Y").strip()
APP_URL = os.getenv("APP_URL", "https://kitobbot-m6m8.onrender.com").rstrip("/")
PORT = int(os.getenv("PORT", 8080))
DEFAULT_BOOK_PATH = os.getenv("BOOK_PATH", "books/book.pdf")
ADMIN_PASSWORD = "12@$"
MAX_FILE_SIZE_MB = 60
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()

class AdminStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_channel = State()
    waiting_for_second_admin_id = State()
    waiting_for_book_file = State()
    waiting_for_book_name = State()

# --- Obunani tekshirish yordamchisi ---
async def check_user_subscriptions(bot: Bot, user_id: int):
    """Foydalanuvchi barcha majburiy kanallarga a'zo ekanligini tekshiradi."""
    if is_admin(user_id):
        return True, []

    channels = get_channels()
    if not channels:
        return True, []

    unsubscribed = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                unsubscribed.append(ch)
        except Exception as e:
            logger.warning(f"Kanal a'zoligini tekshirishda xatolik ({ch}): {e}")
    return len(unsubscribed) == 0, unsubscribed

def get_subscription_keyboard(unsubscribed_channels):
    buttons = []
    for idx, ch in enumerate(unsubscribed_channels, 1):
        clean_ch = ch.lstrip("@")
        url = ch if ch.startswith("http") else f"https://t.me/{clean_ch}"
        buttons.append([InlineKeyboardButton(text=f"📢 {idx}-kanalga a'zo bo'lish", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Start Handler ---
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user = message.from_user
    register_user(user.id, user.first_name, user.username)

    is_subbed, unsubbed = await check_user_subscriptions(message.bot, user.id)
    if not is_subbed:
        await message.answer(
            "⚠️ <b>Botdan foydalanish uchun quyidagi guruh/kanallarga a'zo bo'ling:</b>\n"
            "A'zo bo'lgach, '✅ Obunani tekshirish' tugmasini bosing.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(unsubbed)
        )
        return

    active_b = get_active_book()
    active_name = active_b['name'] if active_b else "Kitob yuklanmagan"
    active_pages = active_b['pages'] if active_b else 0

    text = (
        "👋 <b>Assalomu alaykum! Kitob qidiruv botiga xush kelibsiz.</b>\n\n"
        "🔍 Ushbu bot orqali kitob ichidan istalgan so'z yoki iborani qidirishingiz mumkin.\n"
        "Bot so'zning qomusiy ta'rifini va kitobdagi to'liq mazmunli izohini chiqarib beradi!\n\n"
        f"📚 <b>Hozirgi faol kitob:</b> {html.escape(active_name)} ({active_pages} sahifa)\n\n"
        "💡 <i>Qidirish uchun shunchaki biror so'z yozib yuboring yoki /kitoblar buyrug'ini bosing.</i>"
    )

    await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: types.CallbackQuery):
    is_subbed, unsubbed = await check_user_subscriptions(callback.bot, callback.from_user.id)
    if is_subbed:
        await callback.message.delete()
        await callback.message.answer(
            "✅ <b>Tabriklaymiz, barcha kanallarga a'zo bo'ldingiz!</b>\n\n"
            "Endi botdan to'liq foydalanishingiz mumkin. Qidirmoqchi bo'lgan so'zingizni yozing.",
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=get_subscription_keyboard(unsubbed))

# --- Kitoblar ro'yxati buyrug'i (/kitoblar) ---
@dp.message(Command("kitoblar"))
async def list_books_command(message: types.Message):
    books = get_all_books()
    if not books:
        await message.answer("⚠️ Hozircha botda kitoblar mavjud emas.")
        return

    text = "📚 <b>Botdagi kitoblar ro'yxati:</b>\n\n"
    for idx, b in enumerate(books, 1):
        status = "✅ <b>(Faol)</b>" if b.get("is_active") else "▫️"
        text += f"{status} {idx}. <b>{html.escape(b['name'])}</b> — {b['pages']} sahifa\n"

    text += "\n💡 <i>Qidiruvlar faol kitob ichidan amalga oshiriladi.</i>"

    keyboard = None
    if is_admin(message.from_user.id):
        buttons = [
            [InlineKeyboardButton(text="➕ Yangi kitob qo'shish", callback_data="admin_add_book_btn")],
            [InlineKeyboardButton(text="🔄 Faol kitobni almashtirish", callback_data="admin_switch_book_btn")]
        ]
        if len(books) > 1:
            buttons.append([InlineKeyboardButton(text="🗑 Kitobni o'chirish", callback_data="admin_delete_book_btn")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

# --- /admin buyrug'i va Parol tekshiruvi ---
@dp.message(Command("admin"))
async def admin_command_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("❌ Kechirasiz, sizda adminlik huquqi yo'q.")
        return

    await state.set_state(AdminStates.waiting_for_password)
    await message.answer(
        "🔐 <b>Admin Panelga kirish:</b>\n"
        "Iltimos, admin parolini kiriting:",
        parse_mode="HTML"
    )

@dp.message(AdminStates.waiting_for_password)
async def admin_password_check(message: types.Message, state: FSMContext):
    password_input = message.text.strip()
    user_id = message.from_user.id

    if password_input == ADMIN_PASSWORD and is_admin(user_id):
        await state.clear()
        await show_admin_panel(message, user_id)
    else:
        await message.answer("❌ Parol noto'g'ri yoki sizning ID raqamingiz adminlar ro'yxatida yo'q!")
        await state.clear()

async def show_admin_panel(message_or_call, user_id: int):
    """Asosiy admin panel menyusi."""
    is_super = is_super_admin(user_id)
    channels_count = len(get_channels())
    users_count = get_users_count()
    books = get_all_books()
    active_b = get_active_book()
    active_name = active_b['name'] if active_b else "Yo'q"

    text = (
        "⚙️ <b>ADMIN PANEL</b>\n\n"
        f"👤 <b>Darajangiz:</b> {'👑 Bosh Admin (Super)' if is_super else '👮‍♂️ Yordamchi Admin'}\n"
        f"📖 <b>Faol kitob:</b> {html.escape(active_name)}\n"
        f"📚 <b>Jami kitoblar:</b> {len(books)} ta\n"
        f"📢 <b>Majburiy kanallar:</b> {channels_count} ta\n"
        f"👥 <b>Foydalanuvchilar:</b> {users_count} nafar\n"
    )

    buttons = [
        [InlineKeyboardButton(text="📚 Kitoblar boshqaruvi", callback_data="admin_books")],
        [InlineKeyboardButton(text="📢 Majburiy obuna kanallari", callback_data="admin_channels")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar ro'yxati", callback_data="admin_users")]
    ]

    if is_super:
        buttons.append([InlineKeyboardButton(text="👑 2-Adminni boshqarish", callback_data="admin_manage_second")])

    buttons.append([InlineKeyboardButton(text="❌ Panelni yopish", callback_data="admin_close")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(message_or_call, types.Message):
        await message_or_call.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message_or_call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer("Panel yopildi.")

@dp.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_admin_panel(callback, callback.from_user.id)

# ==================== KITOBLAR BOSHQARUVI ====================
@dp.callback_query(F.data == "admin_books")
async def cb_admin_books(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    books = get_all_books()
    text = "📚 <b>Mavjud kitoblar ro'yxati:</b>\n\n"
    for idx, b in enumerate(books, 1):
        status = "✅ <b>(Faol)</b>" if b.get("is_active") else "▫️"
        text += f"{status} {idx}. <b>{html.escape(b['name'])}</b> ({b['pages']} sahifa)\n"

    buttons = [
        [InlineKeyboardButton(text="➕ Yangi kitob qo'shish", callback_data="admin_add_book_btn")],
        [InlineKeyboardButton(text="🔄 Faol kitobni almashtirish", callback_data="admin_switch_book_btn")]
    ]
    if len(books) > 1:
        buttons.append([InlineKeyboardButton(text="🗑 Kitobni o'chirish", callback_data="admin_delete_book_btn")])

    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_main")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_switch_book_btn")
async def cb_switch_book_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    books = get_all_books()
    buttons = []
    for b in books:
        mark = "✅ " if b.get("is_active") else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{b['name'][:35]}",
            callback_data=f"set_act_book:{b['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_books")])

    await callback.message.edit_text(
        "Qaysi kitobdan qidirilishi kerak? Tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(F.data.startswith("set_act_book:"))
async def cb_select_active_book(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    book_id = callback.data.split("set_act_book:", 1)[1]
    if set_active_book(book_id):
        await callback.answer("Faol kitob almashtirildi!")
    await cb_admin_books(callback)

@dp.callback_query(F.data == "admin_delete_book_btn")
async def cb_delete_book_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    books = get_all_books()
    buttons = []
    for b in books:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {b['name'][:35]}",
            callback_data=f"del_book:{b['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_books")])

    await callback.message.edit_text(
        "O'chirmoqchi bo'lgan kitob ustiga bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(F.data.startswith("del_book:"))
async def cb_delete_book_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    book_id = callback.data.split("del_book:", 1)[1]
    if delete_book(book_id):
        await callback.answer("Kitob o'chirildi!", show_alert=True)
    await cb_admin_books(callback)

@dp.callback_query(F.data == "admin_add_book_btn")
async def cb_add_book_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_book_file)
    await callback.message.edit_text(
        f"📥 <b>Yangi kitob qo'shish:</b>\n\n"
        f"1. Botga <b>PDF fayl</b> yuboring ({MAX_FILE_SIZE_MB} MB gacha);\n"
        f"2. Yoki kitobning <b>to'g'ridan-to'g'ri yuklab olish havolasini (linkini)</b> yuboring ({MAX_FILE_SIZE_MB} MB gacha).\n\n"
        f"Shuningdek, <code>/yukla https://link... Kitob nomi</code> ko'rinishida ham yozishingiz mumkin.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Bekor qilish", callback_data="admin_books")]])
    )

@dp.message(Command("yukla"))
async def cmd_load_book(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    args = message.text.split(maxsplit=2)
    if len(args) == 1:
        await state.set_state(AdminStates.waiting_for_book_file)
        await message.answer(
            f"📥 <b>Yangi kitob yuklash:</b>\n\n"
            f"1. Botga <b>PDF fayl</b> yuboring ({MAX_FILE_SIZE_MB} MB gacha);\n"
            f"2. Yoki kitobning <b>to'g'ridan-to'g'ri yuklab olish havolasini (linkini)</b> yuboring ({MAX_FILE_SIZE_MB} MB gacha).\n\n"
            f"💡 Fayl qabul qilingach, bot sizdan <b>kitobning to'liq nomini</b> so'raydi.",
            parse_mode="HTML"
        )
        return

    url = args[1].strip()
    book_name = args[2].strip() if len(args) > 2 else None

    wait_msg = await message.answer(f"⏳ Kitob serverga yuklab olinmoqda ({url})...")
    try:
        filename = f"books/book_{len(get_all_books()) + 1}.pdf"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_FILE_SIZE:
                await wait_msg.edit_text(f"⚠️ Kitob hajmi {MAX_FILE_SIZE_MB} MB dan oshmasligi kerak! ({round(int(content_length)/(1024*1024), 1)} MB)")
                return
            content = resp.read()
            if len(content) > MAX_FILE_SIZE:
                await wait_msg.edit_text(f"⚠️ Kitob hajmi {MAX_FILE_SIZE_MB} MB dan oshmasligi kerak! ({round(len(content)/(1024*1024), 1)} MB)")
                return
            with open(filename, "wb") as f:
                f.write(content)

        pages = get_total_pages(filename)

        if not book_name:
            await state.update_data(pending_book={"path": filename, "pages": pages, "url": url})
            await state.set_state(AdminStates.waiting_for_book_name)
            await wait_msg.edit_text(
                f"📖 <b>Kitob fayli muvaffaqiyatli yuklandi!</b> ({pages} sahifa)\n\n"
                f"✍️ <b>Iltimos, ushbu kitobning to'liq nomini yozing:</b>\n"
                f"<i>(Masalan: O'tkan kunlar, Jinoyat huquqi darsligi va h.k.)</i>",
                parse_mode="HTML"
            )
            return

        add_new_book(name=book_name, path=filename, pages=pages, url=url)
        await wait_msg.edit_text(
            f"✅ <b>Kitob muvaffaqiyatli yuklandi va faol qilindi!</b>\n"
            f"📖 Nomi: <b>{html.escape(book_name)}</b>\n"
            f"📄 Sahifalar soni: <b>{pages}</b> ta\n\n"
            f"Endi botdan ushbu yangi kitob bo'yicha qidirishingiz mumkin!",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception("Yuklab olishda xatolik:")
        await wait_msg.edit_text(f"❌ Yuklab olishda xatolik yuz berdi: {e}")

@dp.message(AdminStates.waiting_for_book_file)
async def process_book_input(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    # 1. Agar foydalanuvchi havola (link) yuborgan bo'lsa
    if message.text and message.text.startswith("http"):
        url = message.text.strip()
        wait_msg = await message.answer("⏳ Havola orqali kitob tekshirilmoqda...")
        try:
            filename = f"books/book_{len(get_all_books()) + 1}.pdf"
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_FILE_SIZE:
                    await wait_msg.edit_text(f"⚠️ Kitob hajmi {MAX_FILE_SIZE_MB} MB dan oshmasligi kerak! ({round(int(content_length)/(1024*1024), 1)} MB)")
                    await state.clear()
                    return
                content = resp.read()
                if len(content) > MAX_FILE_SIZE:
                    await wait_msg.edit_text(f"⚠️ Kitob hajmi {MAX_FILE_SIZE_MB} MB dan oshmasligi kerak! ({round(len(content)/(1024*1024), 1)} MB)")
                    await state.clear()
                    return
                with open(filename, "wb") as f:
                    f.write(content)
            pages = get_total_pages(filename)
            await state.update_data(pending_book={"path": filename, "pages": pages, "url": url})
            await state.set_state(AdminStates.waiting_for_book_name)
            await wait_msg.edit_text(
                f"📖 <b>Kitob fayli qabul qilindi!</b> ({pages} sahifa)\n\n"
                f"✍️ <b>Iltimos, ushbu kitobning to'liq nomini yozing:</b>\n"
                f"<i>(Masalan: O'tkan kunlar, Jinoyat huquqi darsligi va h.k.)</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            await wait_msg.edit_text(f"❌ Yuklab olishda xatolik: {e}")
            await state.clear()
        return

    # 2. Agar PDF hujjat yuborgan bo'lsa
    if message.document:
        doc = message.document
        if not doc.file_name.lower().endswith(".pdf"):
            await message.answer("Iltimos, faqat PDF fayl yuboring.")
            return

        if doc.file_size and doc.file_size > MAX_FILE_SIZE:
            await message.answer(
                f"⚠️ Kitob hajmi {MAX_FILE_SIZE_MB} MB dan oshmasligi kerak ({round(doc.file_size / (1024*1024), 1)} MB).\n"
                f"Iltimos, hajmi {MAX_FILE_SIZE_MB} MB gacha bo'lgan kitob yuboring."
            )
            return

        wait_msg = await message.answer("⏳ Kitob serverga saqlanmoqda...")
        try:
            filename = f"books/book_{len(get_all_books()) + 1}.pdf"
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            file = await message.bot.get_file(doc.file_id)
            await message.bot.download_file(file.file_path, filename)
            pages = get_total_pages(filename)
            await state.update_data(pending_book={"path": filename, "pages": pages, "url": None})
            await state.set_state(AdminStates.waiting_for_book_name)
            await wait_msg.edit_text(
                f"📖 <b>Kitob fayli qabul qilindi!</b> ({pages} sahifa)\n\n"
                f"✍️ <b>Iltimos, ushbu kitobning to'liq nomini yozing:</b>\n"
                f"<i>(Masalan: O'tkan kunlar, Ingliz tili grammatikasi va h.k.)</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            err_str = str(e).lower()
            if "too big" in err_str or (doc.file_size and doc.file_size > 20 * 1024 * 1024):
                await wait_msg.edit_text(
                    f"⚠️ <b>Telegram cheklovi:</b>\n"
                    f"Telegram serveri 20 MB dan oshiq fayllarni bot chatiga bevosita yuklashga ruxsat bermaydi "
                    f"({round(doc.file_size / (1024*1024), 1)} MB).\n\n"
                    f"💡 <b>Lekin ushbu kitobni ({MAX_FILE_SIZE_MB} MB gacha) yuklash juda oson:</b>\n"
                    f"Kitobning yuklab olish linkini yuboring yoki quyidagicha yozing:\n"
                    f"<code>/yukla https://havola.pdf Kitob nomi</code>\n\n"
                    f"<i>(Masalan: catbox.moe yoki istalgan fayl saqlash xizmati linki)</i>",
                    parse_mode="HTML"
                )
                await state.clear()
            else:
                await wait_msg.edit_text(f"❌ Saqlashda xatolik: {e}")
                await state.clear()
        return

    await message.answer("Iltimos, PDF fayl yoki havola yuboring.")

@dp.message(AdminStates.waiting_for_book_name)
async def process_book_name(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    book_name = message.text.strip()
    data = await state.get_data()
    pending = data.get("pending_book")
    if not pending:
        await message.answer("Kitob ma'lumotlari topilmadi, iltimos qaytadan urinib ko'ring.")
        await state.clear()
        return

    add_new_book(
        name=book_name,
        path=pending["path"],
        pages=pending["pages"],
        url=pending.get("url")
    )
    await state.clear()
    await message.answer(
        f"✅ <b>\"{html.escape(book_name)}\"</b> kitobi muvaffaqiyatli saqlandi va faol qilindi!\n"
        f"📄 Jami sahifalar soni: <b>{pending['pages']}</b> ta.\n\n"
        f"Endi botdagi barcha qidiruvlar aynan shu kitobdan amalga oshiriladi!",
        parse_mode="HTML"
    )
    await show_admin_panel(message, message.from_user.id)

@dp.message(F.document)
async def handle_document_direct(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    doc = message.document
    if not doc.file_name.lower().endswith(".pdf"):
        return

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer(
            f"⚠️ Kitob hajmi {MAX_FILE_SIZE_MB} MB dan oshmasligi kerak ({round(doc.file_size / (1024*1024), 1)} MB).\n"
            f"Iltimos, hajmi {MAX_FILE_SIZE_MB} MB gacha bo'lgan kitob yuboring."
        )
        return

    wait_msg = await message.answer("⏳ Kitob serverga saqlanmoqda...")
    try:
        filename = f"books/book_{len(get_all_books()) + 1}.pdf"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file.file_path, filename)
        pages = get_total_pages(filename)
        await state.update_data(pending_book={"path": filename, "pages": pages, "url": None})
        await state.set_state(AdminStates.waiting_for_book_name)
        await wait_msg.edit_text(
            f"📖 <b>Kitob fayli qabul qilindi!</b> ({pages} sahifa)\n\n"
            f"✍️ <b>Iltimos, ushbu kitobning to'liq nomini yozing:</b>\n"
            f"<i>(Masalan: O'tkan kunlar, Alisher Navoiy asarlari va h.k.)</i>",
            parse_mode="HTML"
        )
    except Exception as e:
        err_str = str(e).lower()
        if "too big" in err_str or (doc.file_size and doc.file_size > 20 * 1024 * 1024):
            await wait_msg.edit_text(
                f"⚠️ <b>Telegram cheklovi:</b>\n"
                f"Telegram serveri 20 MB dan oshiq fayllarni bot chatiga bevosita yuklashga ruxsat bermaydi "
                f"({round(doc.file_size / (1024*1024), 1)} MB).\n\n"
                f"💡 <b>Lekin ushbu kitobni ({MAX_FILE_SIZE_MB} MB gacha) yuklash juda oson:</b>\n"
                f"Kitobning yuklab olish linkini yuboring yoki quyidagicha yozing:\n"
                f"<code>/yukla https://havola.pdf Kitob nomi</code>\n\n"
                f"<i>(Masalan: catbox.moe yoki istalgan fayl saqlash xizmati linki)</i>",
                parse_mode="HTML"
            )
            await state.clear()
        else:
            await wait_msg.edit_text(f"❌ Kitobni saqlashda xatolik: {e}")
            await state.clear()

# ==================== MAJBURIY OBUNALAR ====================
@dp.callback_query(F.data == "admin_channels")
async def cb_admin_channels(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    channels = get_channels()
    text = "📢 <b>Majburiy obuna kanallari:</b>\n\n"
    if channels:
        for idx, ch in enumerate(channels, 1):
            text += f"{idx}. <b>{html.escape(ch)}</b>\n"
    else:
        text += "<i>Hozircha kanallar qo'shilmagan.</i>\n"

    buttons = [
        [InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="admin_add_channel")],
    ]
    if channels:
        buttons.append([InlineKeyboardButton(text="🗑 Kanalni o'chirish", callback_data="admin_remove_channel")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_main")])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_add_channel")
async def cb_add_channel_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_new_channel)
    await callback.message.edit_text(
        "📢 <b>Qo'shmoqchi bo'lgan kanal yoki guruhingizni yuboring:</b>\n\n"
        "Masalan: <code>@kanalim</code> yoki havola <code>https://t.me/kanalim</code>\n\n"
        "⚠️ <i>Eslatma: Bot ushbu kanalda/guruhda Admin bo'lishi shart!</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Bekor qilish", callback_data="admin_channels")]])
    )

@dp.message(AdminStates.waiting_for_new_channel)
async def process_new_channel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    ch = message.text.strip()
    if add_channel(ch):
        await message.answer(f"✅ <b>'{html.escape(ch)}'</b> muvaffaqiyatli qo'shildi!", parse_mode="HTML")
    else:
        await message.answer(f"ℹ️ Bu kanal avvaldan mavjud edi.")
    await state.clear()
    await show_admin_panel(message, message.from_user.id)

@dp.callback_query(F.data == "admin_remove_channel")
async def cb_remove_channel_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    channels = get_channels()
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text=f"🗑 {ch}", callback_data=f"del_ch:{ch}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_channels")])

    await callback.message.edit_text(
        "O'chirmoqchi bo'lgan kanal ustiga bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(F.data.startswith("del_ch:"))
async def cb_delete_channel(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    channel = callback.data.split("del_ch:", 1)[1]
    remove_channel(channel)
    await callback.answer(f"'{channel}' o'chirildi!")
    await cb_admin_channels(callback)

# ==================== 2-ADMIN BOSHQARUVI ====================
@dp.callback_query(F.data == "admin_manage_second")
async def cb_manage_second_admin(callback: types.CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        await callback.answer("Faqat Bosh Admin uchun!", show_alert=True)
        return

    sec_admin = get_second_admin()
    text = (
        "👑 <b>2-ADMIN BOSHQARUVI</b>\n\n"
        f"Hozirgi 2-admin ID: <code>{sec_admin if sec_admin else 'Tayinlanmagan'}</code>\n\n"
        "<i>2-admin kanallarni qo'sha oladi, lekin Super adminni ko'ra olmaydi va o'zgartira olmaydi.</i>"
    )

    buttons = [
        [InlineKeyboardButton(text="➕ 2-Adminni tayinlash", callback_data="set_second_admin")]
    ]
    if sec_admin:
        buttons.append([InlineKeyboardButton(text="🗑 2-Adminni olib tashlash", callback_data="remove_second_admin")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_main")])

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "set_second_admin")
async def cb_set_second_admin_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_second_admin_id)
    await callback.message.edit_text(
        "Yangi 2-admin bo'ladigan shaxsning <b>Telegram ID raqamini</b> yuboring:\n"
        "(Masalan: <code>123456789</code>)",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Bekor qilish", callback_data="admin_manage_second")]])
    )

@dp.message(AdminStates.waiting_for_second_admin_id)
async def process_second_admin_id(message: types.Message, state: FSMContext):
    if not is_super_admin(message.from_user.id):
        return

    text_id = message.text.strip()
    if not text_id.isdigit():
        await message.answer("❌ Iltimos, faqat raqamlardan iborat Telegram ID yuboring.")
        return

    set_second_admin(int(text_id))
    await state.clear()
    await message.answer(f"✅ 2-Admin muvaffaqiyatli tayinlandi: <code>{text_id}</code>", parse_mode="HTML")
    await show_admin_panel(message, message.from_user.id)

@dp.callback_query(F.data == "remove_second_admin")
async def cb_remove_second_admin(callback: types.CallbackQuery):
    if not is_super_admin(callback.from_user.id):
        return
    remove_second_admin()
    await callback.answer("2-Admin olib tashlandi!", show_alert=True)
    await cb_manage_second_admin(callback)

# ==================== FOYDALANUVCHILAR ====================
@dp.message(Command("users"))
async def users_command_handler(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    total = get_users_count()
    recent = get_users_list(20)

    text = f"👥 <b>Jami foydalanuvchilar:</b> {total} nafar\n\n<b>Oxirgi a'zolar:</b>\n"
    for idx, u in enumerate(reversed(recent), 1):
        uname = f"@{u['username']}" if u['username'] else "yo'q"
        text += f"{idx}. {html.escape(u['name'])} (ID: <code>{u['id']}</code>, {uname})\n"

    await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    total = get_users_count()
    recent = get_users_list(15)

    text = f"👥 <b>Foydalanuvchilar statistikasi</b>\n\nJami soni: <b>{total}</b> nafar\n\n<b>Oxirgi qo'shilganlar:</b>\n"
    for idx, u in enumerate(reversed(recent), 1):
        uname = f"@{u['username']}" if u['username'] else "yo'q"
        text += f"{idx}. {html.escape(u['name'])} (ID: <code>{u['id']}</code>, {uname})\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_main")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

# ==================== QIDIRUV TIZIMI ====================
@dp.message(F.text)
async def search_handler(message: types.Message):
    query = message.text.strip()
    if query.startswith("/"):
        return

    user = message.from_user
    register_user(user.id, user.first_name, user.username)

    is_subbed, unsubbed = await check_user_subscriptions(message.bot, user.id)
    if not is_subbed:
        await message.answer(
            "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>\n"
            "A'zo bo'lgach, '✅ Obunani tekshirish' tugmasini bosing.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(unsubbed)
        )
        return

    active_b = get_active_book()
    if not active_b or not os.path.exists(active_b.get("path", "")):
        await message.answer("⚠️ Hozircha botda faol kitob mavjud emas. Iltimos, avval PDF kitob yuklang.")
        return

    book_path = active_b["path"]
    book_name = active_b["name"]

    wait_msg = await message.answer(f"🔍 <b>'{html.escape(query)}'</b> so'zi kitob bo'yicha qidirilmoqda...", parse_mode="HTML")

    try:
        res = await asyncio.to_thread(search_word_in_pdf, book_path, query, 6)
    except Exception as e:
        logger.exception("Qidiruvda xatolik:")
        await wait_msg.edit_text("⚠️ Qidiruv jarayonida xatolik yuz berdi.")
        return

    total = res["total"]
    results = res["results"]
    matched_query = res.get("matched_query", query)
    definition = res.get("definition")

    if total == 0:
        msg = f"❌ <b>'{html.escape(query)}'</b> so'zi (va shakllari) 📚 <b>\"{html.escape(book_name)}\"</b> kitobidan topilmadi.\n"
        if definition:
            msg += (
                f"\n💡 <b>So'zning umumiy ma'nosi (Izoh):</b>\n"
                f"🇺🇿 {html.escape(definition['meaning_uz'])}\n"
                f"🇬🇧 <i>{html.escape(definition['meaning_en'])}</i>\n\n"
            )
        msg += "So'zni to'g'ri yozganingizni tekshirib, qaytadan urinib ko'ring."
        await wait_msg.edit_text(msg, parse_mode="HTML")
        return

    msg_text = f"📚 <b>Kitob:</b> \"{html.escape(book_name)}\"\n"
    if matched_query.lower() != query.lower():
        msg_text += (
            f"✅ <b>'{html.escape(query)}'</b> so'zi bo'yicha uning <b>'{html.escape(matched_query)}'</b> shakli "
            f"ushbu kitobda jami <b>{total}</b> marta uchradi.\n"
        )
    else:
        msg_text += f"✅ <b>'{html.escape(query)}'</b> so'zi ushbu kitobda jami <b>{total}</b> marta uchradi.\n"

    if definition:
        msg_text += (
            f"\n💡 <b>So'zning ma'nosi (Izoh):</b>\n"
            f"🇺🇿 {html.escape(definition['meaning_uz'])}\n"
            f"🇬🇧 <i>{html.escape(definition['meaning_en'])}</i>\n"
        )

    msg_text += f"\n📖 <b>Kitobdagi izohi va mazmuni:</b>\n\n"

    for item in results:
        p = item["page"]
        sentence = html.escape(item["sentence"])
        msg_text += f"📄 <b>\"{html.escape(book_name)}\"</b> ({p}-sahifa):\n<blockquote>\"{sentence}\"</blockquote>\n\n"

    if len(msg_text) > 4000:
        msg_text = msg_text[:3990] + "...\n\n<i>(Natijalar ko'pligi sababli dastlabkilari ko'rsatildi)</i>"

    try:
        await wait_msg.edit_text(msg_text, parse_mode="HTML")
    except Exception as e:
        clean_text = msg_text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<blockquote>", "").replace("</blockquote>", "")
        await wait_msg.edit_text(clean_text, parse_mode=None)

async def keep_alive_ping():
    await asyncio.sleep(60)
    if not APP_URL:
        return
    import aiohttp
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(f"{APP_URL}/health") as resp:
                    logger.info(f"Keep-alive ping: {resp.status}")
            except Exception as e:
                logger.warning(f"Ping warning: {e}")
            await asyncio.sleep(600)

def ensure_books_exist():
    active_b = get_active_book()
    if active_b:
        path = active_b.get("path", DEFAULT_BOOK_PATH)
        url = active_b.get("url", "https://files.catbox.moe/9vv502.pdf")
        if not os.path.exists(path) and url:
            print(f"📥 Faol kitob yuklab olinmoqda ({url})...")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as f:
                    f.write(resp.read())
                print(f"✅ Kitob muvaffaqiyatli saqlandi! ({get_total_pages(path)} sahifa)")
            except Exception as e:
                print(f"⚠️ Kitob yuklashda xatolik: {e}")

async def main():
    if not TOKEN:
        print("XATOLIK: BOT_TOKEN topilmadi!")
        return

    os.makedirs("books", exist_ok=True)
    ensure_books_exist()

    app = setup_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🚀 Web server {PORT}-portda ishga tushdi.")

    bot = Bot(token=TOKEN)
    asyncio.create_task(keep_alive_ping())

    print("🤖 Telegram bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
