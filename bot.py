import os
import sys
import html
import asyncio
import logging

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
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)

from pdf_searcher import search_word_in_pdf, get_total_pages
from web_server import setup_web_app
from data_manager import (
    SUPER_ADMIN_ID, is_super_admin, is_admin,
    get_second_admin, set_second_admin, remove_second_admin,
    get_channels, add_channel, remove_channel,
    register_user, get_users_count, get_users_list
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "8329325372:AAFo02n3AKlZntAD_JMvTcPrIgefwXvgQ-Y").strip()
APP_URL = os.getenv("APP_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", 8080))
BOOK_PATH = os.getenv("BOOK_PATH", "books/book.pdf")
ADMIN_PASSWORD = "12@$"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()

class AdminStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_new_channel = State()
    waiting_for_second_admin_id = State()

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
            # Agar bot kanalda admin bo'lmasa, tekshirish o'tkazib yuboriladi
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

    book_exists = os.path.exists(BOOK_PATH)
    total_pages = get_total_pages(BOOK_PATH) if book_exists else 0

    text = (
        "👋 <b>Assalomu alaykum! Kitob qidiruv botiga xush kelibsiz.</b>\n\n"
        "🔍 Ushbu bot orqali kitob ichidan istalgan so'z yoki iborani qidirishingiz mumkin.\n"
        "Bot qidirilgan so'zning qomusiy ma'nosini va kitobdagi to'liq mazmunli izohini chiqarib beradi!\n\n"
    )

    if book_exists:
        text += f"📚 <b>Mavjud kitob:</b> yuklangan ({total_pages} sahifa)\n"
        text += "💡 <i>Qidirish uchun shunchaki biror so'z yozib yuboring.</i>"
    else:
        text += "⚠️ Hozircha kitob yuklanmagan.\nAdmin botga PDF formatdagi kitob faylini yuborishi kerak."

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
    """Admin panel menyusini chiqarish."""
    is_super = is_super_admin(user_id)
    channels_count = len(get_channels())
    users_count = get_users_count()

    text = (
        "⚙️ <b>ADMIN PANEL</b>\n\n"
        f"👤 <b>Darajangiz:</b> {'👑 Bosh Admin (Super)' if is_super else '👮‍♂️ Yordamchi Admin'}\n"
        f"📢 <b>Majburiy kanallar soni:</b> {channels_count}\n"
        f"👥 <b>Jami foydalanuvchilar:</b> {users_count}\n"
    )

    buttons = [
        [InlineKeyboardButton(text="📢 Majburiy obuna kanallari", callback_data="admin_channels")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar ro'yxati", callback_data="admin_users")]
    ]

    # Faqat 1-Super Admin ko'radi va o'zgartira oladi (2-admin ko'rmaydi!)
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

# --- Majburiy obunalar bo'limi ---
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

# --- 2-Adminni boshqarish (Faqat Super Admin uchun) ---
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

# --- Foydalanuvchilar buyrug'i (/users va panel orqali) ---
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

# --- Kitob fayli va admin yuklashi ---
@dp.message(Command("kitob"))
async def send_book_file(message: types.Message):
    if not os.path.exists(BOOK_PATH):
        await message.answer("⚠️ Kitob fayli hali yuklanmagan.")
        return
    await message.answer("📚 Kitob yuklanmoqda, iltimos kuting...")
    doc = FSInputFile(BOOK_PATH, filename="kitob.pdf")
    await message.answer_document(doc, caption="📖 Mana, kitobning to'liq elektron nusxasi.")

@dp.message(F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    doc = message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await message.answer("Iltimos, faqat PDF formatdagi fayl yuboring.")
        return

    os.makedirs(os.path.dirname(BOOK_PATH), exist_ok=True)
    wait_msg = await message.answer("⏳ Kitob serverga saqlanmoqda...")

    file = await message.bot.get_file(doc.file_id)
    await message.bot.download_file(file.file_path, BOOK_PATH)

    pages = get_total_pages(BOOK_PATH)
    await wait_msg.edit_text(
        f"✅ Yangi kitob muvaffaqiyatli yuklandi!\n"
        f"📄 Jami sahifalar soni: {pages}\n"
        f"Endi botdan yangi kitob bo'yicha qidirishingiz mumkin."
    )

@dp.callback_query(F.data == "download_book")
async def cb_download(callback: types.CallbackQuery):
    if os.path.exists(BOOK_PATH):
        doc = FSInputFile(BOOK_PATH, filename="kitob.pdf")
        await callback.message.answer_document(doc, caption="📖 Kitobning to'liq PDF nusxasi.")
    else:
        await callback.answer("Kitob fayli topilmadi.", show_alert=True)
    await callback.answer()

# --- Qidiruv tizimi ---
@dp.message(F.text)
async def search_handler(message: types.Message):
    query = message.text.strip()
    if query.startswith("/"):
        return

    user = message.from_user
    register_user(user.id, user.first_name, user.username)

    # Obunani tekshirish
    is_subbed, unsubbed = await check_user_subscriptions(message.bot, user.id)
    if not is_subbed:
        await message.answer(
            "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>\n"
            "A'zo bo'lgach, '✅ Obunani tekshirish' tugmasini bosing.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(unsubbed)
        )
        return

    if not os.path.exists(BOOK_PATH):
        await message.answer("⚠️ Hozircha botda kitob mavjud emas. Iltimos, avval PDF kitob yuklang.")
        return

    wait_msg = await message.answer(f"🔍 <b>'{html.escape(query)}'</b> so'zi kitob bo'yicha qidirilmoqda...", parse_mode="HTML")

    try:
        res = await asyncio.to_thread(search_word_in_pdf, BOOK_PATH, query, 6)
    except Exception as e:
        logger.exception("Qidiruvda xatolik:")
        await wait_msg.edit_text("⚠️ Qidiruv jarayonida xatolik yuz berdi.")
        return

    total = res["total"]
    results = res["results"]
    matched_query = res.get("matched_query", query)
    definition = res.get("definition")

    if total == 0:
        msg = f"❌ <b>'{html.escape(query)}'</b> so'zi (va uning boshqa zamon/shakllari) kitobdan topilmadi.\n"
        if definition:
            msg += (
                f"\n💡 <b>So'zning umumiy ma'nosi (Izoh):</b>\n"
                f"🇺🇿 {html.escape(definition['meaning_uz'])}\n"
                f"🇬🇧 <i>{html.escape(definition['meaning_en'])}</i>\n\n"
            )
        msg += "So'zni to'g'ri yozganingizni tekshirib, qaytadan urinib ko'ring."
        await wait_msg.edit_text(msg, parse_mode="HTML")
        return

    if matched_query.lower() != query.lower():
        msg_text = (
            f"✅ <b>'{html.escape(query)}'</b> so'zi bo'yicha uning <b>'{html.escape(matched_query)}'</b> shakli "
            f"kitobda jami <b>{total}</b> marta uchradi.\n"
        )
    else:
        msg_text = f"✅ <b>'{html.escape(query)}'</b> so'zi kitobda jami <b>{total}</b> marta uchradi.\n"

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
        msg_text += f"📄 <b>{p}-sahifadagi izohi:</b>\n<blockquote>\"{sentence}\"</blockquote>\n\n"

    buttons = [[InlineKeyboardButton(text="📥 Butun kitobni yuklab olish", callback_data="download_book")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if len(msg_text) > 4000:
        msg_text = msg_text[:3990] + "...\n\n<i>(Natijalar ko'pligi sababli dastlabkilari ko'rsatildi)</i>"

    try:
        await wait_msg.edit_text(msg_text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logger.warning(f"HTML parse xatoligi: {e}")
        clean_text = msg_text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<blockquote>", "").replace("</blockquote>", "")
        await wait_msg.edit_text(clean_text, parse_mode=None, reply_markup=keyboard)

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

async def main():
    if not TOKEN:
        print("XATOLIK: BOT_TOKEN topilmadi!")
        return

    os.makedirs(os.path.dirname(BOOK_PATH), exist_ok=True)

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
