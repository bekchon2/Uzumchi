"""
handlers/missing_reports.py — Yo'qolgan tovarlar hisoboti.
Tugma: 📦 Yo'qolgan tovarlar / 📦 Потерянные товары
"""
import io
import logging
import os
import zipfile
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_user
from locales.i18n import t

logger = logging.getLogger(__name__)
router = Router()

# Fayllar joylashuvi
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES_DIR = os.path.join(BASE_DIR, "files")
DOC_FILE = os.path.join(FILES_DIR, "Доп-соглашение-422955.docx")
EXCEL_FILE = os.path.join(FILES_DIR, "отчет-потерянных-товаров-excel-1781781342893.xlsx")


# ─── Keyboard ─────────────────────────────────────────────────────────────────

def missing_keyboard(lang: str = "ru"):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📥 " + ("ZIP yuklab olish" if lang == "uz" else "Скачать ZIP"),
        callback_data="missing_download_zip"
    )
    builder.button(
        text=t("btn_back", lang),
        callback_data="missing_back"
    )
    builder.adjust(1)
    return builder.as_markup()


# ─── ZIP yaratish ─────────────────────────────────────────────────────────────

def create_compensation_zip() -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(DOC_FILE):
            zf.write(DOC_FILE, "Доп-соглашение-422955.docx")
            logger.info("ZIP: docx qo'shildi")
        else:
            logger.warning(f"Fayl topilmadi: {DOC_FILE}")

        if os.path.exists(EXCEL_FILE):
            zf.write(EXCEL_FILE, "отчет-потерянных-товаров.xlsx")
            logger.info("ZIP: xlsx qo'shildi")
        else:
            logger.warning(f"Fayl topilmadi: {EXCEL_FILE}")
    buf.seek(0)
    return buf


# ─── Ma'lumot matni ───────────────────────────────────────────────────────────

def missing_text(lang: str) -> str:
    return t("missing_title", lang) + "\n\n" + t("missing_body", lang)


# ─── Handlerlar ───────────────────────────────────────────────────────────────

@router.message(F.text.in_(["📦 Yo'qolgan tovarlar", "📦 Потерянные товары"]))
async def cmd_missing(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user.get("api_key"):
        await message.answer("⚠️ Avval /start bilan botni sozlang.")
        return
    lang = user.get("lang", "ru")
    await message.answer(
        missing_text(lang),
        reply_markup=missing_keyboard(lang),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "missing_download_zip")
async def download_zip(callback: CallbackQuery, bot: Bot):
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"

    await callback.answer(
        "⏳ " + ("ZIP tayyorlanmoqda..." if lang == "uz" else "Готовлю ZIP..."),
        show_alert=False
    )

    loading = await callback.message.answer(
        "⏳ " + ("Hujjatlar yuklanmoqda..." if lang == "uz" else "Загружаю документы...")
    )

    try:
        zip_buf = create_compensation_zip()
        fname = f"yoqolgan-tovarlar-{datetime.now().strftime('%Y%m%d')}.zip"

        await bot.send_document(
            chat_id=callback.from_user.id,
            document=BufferedInputFile(zip_buf.read(), filename=fname),
            caption=t("missing_zip_caption", lang),
            parse_mode="HTML"
        )
        await loading.delete()

    except Exception as e:
        logger.error(f"ZIP yuborishda xatolik: {e}")
        await loading.edit_text(f"❌ Xatolik: {str(e)[:150]}")


@router.callback_query(F.data == "missing_back")
async def missing_back(callback: CallbackQuery):
    from utils.keyboards import main_menu_keyboard
    user = await get_user(callback.from_user.id)
    lang = user.get("lang", "ru") if user else "ru"
    shop_name = user.get("shop_name", "—") if user else "—"
    await callback.message.answer(
        t("main_menu", lang, shop_name=shop_name),
        reply_markup=main_menu_keyboard(lang),
        parse_mode="HTML"
    )
    await callback.answer()
