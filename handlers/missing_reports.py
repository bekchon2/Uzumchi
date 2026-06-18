"""
handlers/missing_reports.py
===========================
📦 Yo'qolgan tovarlar — to'liq FSM forma + ZIP generatsiya.

Flow:
  1. Tugma → real yo'qolgan tovarlar API dan olinadi
  2. Ro'yxat + "Hisobotni shakllantirish" tugmasi
  3. Agar avval saqlangan ma'lumotlar bo'lsa → "Ishlatish / Qayta kiritish"
  4. Yo'q bo'lsa → birma-bir 11 ta maydon so'raladi
  5. Tasdiqlash → ZIP (xlsx + docx) → foydalanuvchiga yuboriladi
"""
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from database import get_user, get_missing_report_form, save_missing_report_form
from services.missing_service import find_missing_products, format_missing_list
from utils.doc_generator import create_zip
from utils.keyboards import main_menu_keyboard
from locales.i18n import t

logger = logging.getLogger(__name__)
router = Router()



# ─── FSM States ───────────────────────────────────────────────────────────────

class MissingForm(StatesGroup):
    report_date     = State()
    director_name   = State()
    org_name        = State()
    reg_number      = State()
    inn             = State()
    address         = State()
    contract_number = State()
    contract_date   = State()
    bank_name       = State()
    account_number  = State()
    bank_mfo        = State()
    confirm         = State()


# Maydon tartib va meta
FIELDS = [
    ("report_date",     "📅 Hisobot sanasi",        "Дата отчёта",         "2026-06-18"),
    ("director_name",   "👤 Rahbarning F.I.Sh.",    "Ф.И.О. руководителя","YAKUBOVA DILRABO KAMILJONOVNA"),
    ("org_name",        "🏢 Tashkilot nomi",        "Наименование орг.",   "ИП YAKUBOVA DILRABO KAMILJONOVNA"),
    ("reg_number",      "🗂 ЯТТ / Reg. raqam",      "Рег. номер (ЯТТ)",   "6691547"),
    ("inn",             "🔢 INN / ЖШШИР",           "ИНН / ЖШШИР",        "41507933180159"),
    ("address",         "📍 Manzil",                "Юридический адрес",   "Viloyat, tuman, ko'cha, uy"),
    ("contract_number", "📝 Shartnoma raqami",       "Номер договора",      "0432955н"),
    ("contract_date",   "📆 Shartnoma sanasi",       "Дата договора",       "2026-05-15"),
    ("bank_name",       "🏦 Bank nomi",             "Название банка",      "Kapitalbank"),
    ("account_number",  "💳 Hisob raqami",          "Расчётный счёт",      "20218000000074682298"),
    ("bank_mfo",        "🏷 Bank MFO",              "МФО банка",           "01158"),
]

FIELD_KEYS = [f[0] for f in FIELDS]
STATE_MAP  = {
    "report_date":     MissingForm.report_date,
    "director_name":   MissingForm.director_name,
    "org_name":        MissingForm.org_name,
    "reg_number":      MissingForm.reg_number,
    "inn":             MissingForm.inn,
    "address":         MissingForm.address,
    "contract_number": MissingForm.contract_number,
    "contract_date":   MissingForm.contract_date,
    "bank_name":       MissingForm.bank_name,
    "account_number":  MissingForm.account_number,
    "bank_mfo":        MissingForm.bank_mfo,
}



# ─── Klaviaturalar ────────────────────────────────────────────────────────────

def _field_keyboard(lang: str, has_saved: bool):
    """Har bir maydon uchun klaviatura."""
    builder = ReplyKeyboardBuilder()
    if has_saved:
        skip = "↩️ Saqlanganini qoldirish" if lang == "uz" else "↩️ Оставить сохранённое"
        builder.button(text=skip)
    cancel = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    builder.button(text=cancel)
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def _confirm_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    ok  = "✅ Tasdiqlash va ZIP olish" if lang == "uz" else "✅ Подтвердить и получить ZIP"
    redo = "✏️ Qayta kiritish"          if lang == "uz" else "✏️ Перезаполнить"
    builder.button(text=ok,   callback_data="missing_confirm_yes")
    builder.button(text=redo, callback_data="missing_confirm_redo")
    builder.adjust(1)
    return builder.as_markup()


def _use_saved_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    yes = "✅ Ha, shu ma'lumotlar bilan" if lang == "uz" else "✅ Да, использовать сохранённые"
    no  = "✏️ Yo'q, qayta kiritaman"    if lang == "uz" else "✏️ Нет, заполнить заново"
    builder.button(text=yes, callback_data="missing_use_saved_yes")
    builder.button(text=no,  callback_data="missing_use_saved_no")
    builder.adjust(1)
    return builder.as_markup()


def _missing_list_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    build = "📋 Hisobotni shakllantirish" if lang == "uz" else "📋 Сформировать отчёт"
    ref   = "🔄 Yangilash"               if lang == "uz" else "🔄 Обновить"
    builder.button(text=build, callback_data="missing_start_form")
    builder.button(text=ref,   callback_data="missing_refresh")
    builder.adjust(1)
    return builder.as_markup()



# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────

def _saved_summary(saved: dict, lang: str) -> str:
    """Saqlangan ma'lumotlarni ko'rsatish matni."""
    lines = []
    if lang == "uz":
        lines.append("💾 <b>Saqlangan ma'lumotlar:</b>")
    else:
        lines.append("💾 <b>Сохранённые данные:</b>")
    for key, lbl_uz, lbl_ru, _ in FIELDS:
        val = saved.get(key, "") or "—"
        lbl = lbl_uz if lang == "uz" else lbl_ru
        lines.append(f"  <b>{lbl}:</b> {val}")
    return "\n".join(lines)


def _form_summary(form: dict, lang: str) -> str:
    """To'ldirilgan forma xulosasi."""
    lines = []
    if lang == "uz":
        lines.append("📋 <b>To'ldirilgan ma'lumotlar:</b>")
    else:
        lines.append("📋 <b>Заполненные данные:</b>")
    for key, lbl_uz, lbl_ru, _ in FIELDS:
        val = form.get(key, "") or "—"
        lbl = lbl_uz if lang == "uz" else lbl_ru
        lines.append(f"  ✅ <b>{lbl}:</b> {val}")
    return "\n".join(lines)


async def _ask_field(message_or_callback, state: FSMContext,
                     field_idx: int, lang: str, saved: dict | None):
    """Keyingi maydonni so'rash."""
    key, lbl_uz, lbl_ru, example = FIELDS[field_idx]
    lbl     = lbl_uz if lang == "uz" else lbl_ru
    saved_v = (saved or {}).get(key, "")

    if lang == "uz":
        text = f"<b>{field_idx + 1}/{len(FIELDS)}. {lbl}:</b>"
        if saved_v:
            text += f"\n💾 Avvalgi: <code>{saved_v}</code>"
        text += f"\n📌 Namuna: <i>{example}</i>"
    else:
        text = f"<b>{field_idx + 1}/{len(FIELDS)}. {lbl}:</b>"
        if saved_v:
            text += f"\n💾 Предыдущее: <code>{saved_v}</code>"
        text += f"\n📌 Пример: <i>{example}</i>"

    kb = _field_keyboard(lang, bool(saved_v))
    await state.set_state(STATE_MAP[key])

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_callback.message.answer(text, reply_markup=kb, parse_mode="HTML")



# ─── Asosiy handler: tugma bosilganda ─────────────────────────────────────────

@router.message(F.text.in_(["📦 Yo'qolgan tovarlar", "📦 Потерянные товары"]))
async def cmd_missing(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if not user or not user.get("api_key"):
        await message.answer("⚠️ Avval /start bilan botni sozlang.")
        return
    lang     = user.get("lang", "ru")
    shop_id  = user.get("shop_id", 0)
    shop_name = user.get("shop_name", "—")

    loading = "⏳ Yo'qolgan tovarlar hisoblanmoqda..." if lang == "uz" \
              else "⏳ Рассчитываю потерянные товары..."
    msg = await message.answer(loading)

    try:
        items = await find_missing_products(user["api_key"], shop_id)
    except Exception as e:
        logger.error(f"find_missing_products: {e}")
        items = []

    # Natijani state ga saqlaymiz (forma uchun kerak)
    await state.update_data(
        missing_items=[vars(i) for i in items],
        lang=lang,
        shop_name=shop_name,
    )

    text = format_missing_list(items, lang, shop_name)
    await msg.edit_text(text, parse_mode="HTML",
                        reply_markup=_missing_list_keyboard(lang))


@router.callback_query(F.data == "missing_refresh")
async def missing_refresh(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("⚠️ /start")
        return
    lang      = user.get("lang", "ru")
    shop_id   = user.get("shop_id", 0)
    shop_name = user.get("shop_name", "—")

    await callback.answer(
        "🔄 Yangilanmoqda..." if lang == "uz" else "🔄 Обновляю..."
    )
    try:
        items = await find_missing_products(user["api_key"], shop_id)
    except Exception as e:
        items = []
    await state.update_data(
        missing_items=[vars(i) for i in items],
        lang=lang, shop_name=shop_name,
    )
    text = format_missing_list(items, lang, shop_name)
    await callback.message.edit_text(text, parse_mode="HTML",
                                     reply_markup=_missing_list_keyboard(lang))



# ─── Forma boshlash ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "missing_start_form")
async def missing_start_form(callback: CallbackQuery, state: FSMContext):
    user  = await get_user(callback.from_user.id)
    lang  = user.get("lang", "ru") if user else "ru"
    saved = await get_missing_report_form(callback.from_user.id)

    data = await state.get_data()
    if "missing_items" not in data:
        await state.update_data(lang=lang)

    if saved and any(saved.get(k) for k in FIELD_KEYS):
        # Saqlangan ma'lumotlar bor — foydalanuvchiga ko'rsatamiz
        text = _saved_summary(saved, lang)
        q = ("\n\n❓ Shu ma'lumotlardan foydalanishni xohlaysizmi?"
             if lang == "uz" else
             "\n\n❓ Использовать эти сохранённые данные?")
        await callback.message.answer(
            text + q, parse_mode="HTML",
            reply_markup=_use_saved_keyboard(lang)
        )
    else:
        # Birinchi marta — to'g'ridan so'rash
        await state.update_data(form={}, field_idx=0, saved=None)
        await callback.message.answer(
            "📝 Ma'lumotlarni birma-bir kiritamiz:"
            if lang == "uz" else
            "📝 Заполняем данные по одному:",
            parse_mode="HTML"
        )
        await _ask_field(callback, state, 0, lang, None)
    await callback.answer()


@router.callback_query(F.data == "missing_use_saved_yes")
async def use_saved_yes(callback: CallbackQuery, state: FSMContext):
    """Saqlangan ma'lumotlar bilan davom etish → to'g'ri confirm ga o'tish."""
    user  = await get_user(callback.from_user.id)
    lang  = user.get("lang", "ru") if user else "ru"
    saved = await get_missing_report_form(callback.from_user.id)
    form  = {k: (saved.get(k) or "") for k in FIELD_KEYS}

    await state.update_data(form=form, field_idx=len(FIELDS))
    await _show_confirm(callback.message, state, lang, form)
    await callback.answer()


@router.callback_query(F.data == "missing_use_saved_no")
async def use_saved_no(callback: CallbackQuery, state: FSMContext):
    """Qayta to'ldirish."""
    user  = await get_user(callback.from_user.id)
    lang  = user.get("lang", "ru") if user else "ru"
    saved = await get_missing_report_form(callback.from_user.id)
    await state.update_data(form={}, field_idx=0, saved=saved)
    await callback.message.answer(
        "📝 Yangi ma'lumotlarni kiritamiz:" if lang == "uz"
        else "📝 Вводим новые данные:",
        parse_mode="HTML"
    )
    await _ask_field(callback, state, 0, lang, saved)
    await callback.answer()



# ─── Universal maydon handler ─────────────────────────────────────────────────

async def _process_field(message: Message, state: FSMContext, field_key: str):
    """Har bir maydon uchun umumiy qayta ishlash."""
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    form  = data.get("form", {})
    saved = data.get("saved")
    idx   = data.get("field_idx", 0)

    cancel_txt = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    skip_txt   = "↩️ Saqlanganini qoldirish" if lang == "uz" else "↩️ Оставить сохранённое"

    if message.text == cancel_txt:
        await state.clear()
        user = await get_user(message.from_user.id)
        shop_name = (user or {}).get("shop_name", "—")
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang),
            parse_mode="HTML"
        )
        return

    if message.text == skip_txt:
        # Saqlangan qiymatni qoldirish
        saved_val = (saved or {}).get(field_key, "")
        if saved_val:
            form[field_key] = saved_val
        else:
            await message.answer(
                "⚠️ Saqlangan qiymat yo'q." if lang == "uz"
                else "⚠️ Нет сохранённого значения."
            )
            return
    else:
        form[field_key] = (message.text or "").strip()

    next_idx = idx + 1
    await state.update_data(form=form, field_idx=next_idx)

    if next_idx < len(FIELDS):
        await _ask_field(message, state, next_idx, lang, saved)
    else:
        await _show_confirm(message, state, lang, form)


# 11 ta alohida handler — har biri o'z STATE da ishlaydi

@router.message(MissingForm.report_date)
async def field_report_date(msg: Message, state: FSMContext):
    await _process_field(msg, state, "report_date")

@router.message(MissingForm.director_name)
async def field_director_name(msg: Message, state: FSMContext):
    await _process_field(msg, state, "director_name")

@router.message(MissingForm.org_name)
async def field_org_name(msg: Message, state: FSMContext):
    await _process_field(msg, state, "org_name")

@router.message(MissingForm.reg_number)
async def field_reg_number(msg: Message, state: FSMContext):
    await _process_field(msg, state, "reg_number")

@router.message(MissingForm.inn)
async def field_inn(msg: Message, state: FSMContext):
    await _process_field(msg, state, "inn")

@router.message(MissingForm.address)
async def field_address(msg: Message, state: FSMContext):
    await _process_field(msg, state, "address")

@router.message(MissingForm.contract_number)
async def field_contract_number(msg: Message, state: FSMContext):
    await _process_field(msg, state, "contract_number")

@router.message(MissingForm.contract_date)
async def field_contract_date(msg: Message, state: FSMContext):
    await _process_field(msg, state, "contract_date")

@router.message(MissingForm.bank_name)
async def field_bank_name(msg: Message, state: FSMContext):
    await _process_field(msg, state, "bank_name")

@router.message(MissingForm.account_number)
async def field_account_number(msg: Message, state: FSMContext):
    await _process_field(msg, state, "account_number")

@router.message(MissingForm.bank_mfo)
async def field_bank_mfo(msg: Message, state: FSMContext):
    await _process_field(msg, state, "bank_mfo")



# ─── Tasdiqlash sahifasi ──────────────────────────────────────────────────────

async def _show_confirm(message_or_obj, state: FSMContext, lang: str, form: dict):
    """Barcha ma'lumotlarni ko'rsatib, tasdiqlashni so'rash."""
    text = _form_summary(form, lang)
    q = ("\n\n❓ Ma'lumotlar to'g'rimi? ZIP fayl yaratilsinmi?"
         if lang == "uz" else
         "\n\n❓ Данные верны? Создать ZIP-файл?")
    await state.set_state(MissingForm.confirm)

    if isinstance(message_or_obj, Message):
        await message_or_obj.answer(
            text + q,
            reply_markup=_confirm_keyboard(lang),
            parse_mode="HTML"
        )
    else:
        await message_or_obj.answer(
            text + q,
            reply_markup=_confirm_keyboard(lang),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "missing_confirm_redo")
async def confirm_redo(callback: CallbackQuery, state: FSMContext):
    """Qayta kiritish — birinchi maydondan boshlaymiz."""
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    saved = await get_missing_report_form(callback.from_user.id)
    await state.update_data(form={}, field_idx=0, saved=saved)
    await callback.message.answer(
        "🔄 Qayta to'ldirish boshlanmoqda..." if lang == "uz"
        else "🔄 Начинаю заново...",
        parse_mode="HTML"
    )
    await _ask_field(callback, state, 0, lang, saved)
    await callback.answer()


@router.callback_query(F.data == "missing_confirm_yes")
async def confirm_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Tasdiqlash → ZIP yaratish → yuborish."""
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    form  = data.get("form", {})
    raw_items = data.get("missing_items", [])

    # MissingItem-ga o'xshash ob'ektlar yaratamiz
    from services.missing_service import MissingItem
    items = [MissingItem(**d) for d in raw_items]

    await callback.answer(
        "⏳ ZIP tayyorlanmoqda..." if lang == "uz"
        else "⏳ Формирую ZIP..."
    )
    loading = await callback.message.answer(
        "⚙️ Hujjatlar generatsiya qilinmoqda, biroz kuting..."
        if lang == "uz" else
        "⚙️ Генерирую документы, подождите немного..."
    )

    try:
        # Sana bo'sh bo'lsa bugungi kun
        if not form.get("report_date"):
            form["report_date"] = datetime.now().strftime("%Y-%m-%d")

        zip_buf  = create_zip(form, items)
        date_str = form["report_date"].replace("-", "")
        fname    = f"yoqolgan-tovarlar-{date_str}.zip"

        total_comp = sum(i.compensation for i in items)
        total_qty  = sum(i.missing_qty  for i in items)

        if lang == "uz":
            caption = (
                f"📦 <b>Yo'qolgan tovarlar hisoboti</b>\n\n"
                f"📊 Yo'qolgan: <b>{total_qty} dona</b>\n"
                f"💰 Kompensatsiya: <b>{total_comp:,.0f} so'm</b>\n\n"
                f"📄 <code>Доп-соглашение.docx</code>\n"
                f"📊 <code>отчет-потерянных-товаров.xlsx</code>\n\n"
                "💡 Shu fayllarni Uzum support ga yuboring."
            )
        else:
            caption = (
                f"📦 <b>Отчёт по потерянным товарам</b>\n\n"
                f"📊 Потеряно: <b>{total_qty} шт.</b>\n"
                f"💰 Компенсация: <b>{total_comp:,.0f} сум</b>\n\n"
                f"📄 <code>Доп-соглашение.docx</code>\n"
                f"📊 <code>отчет-потерянных-товаров.xlsx</code>\n\n"
                "💡 Отправьте эти файлы в поддержку Uzum."
            )

        await bot.send_document(
            chat_id=callback.from_user.id,
            document=BufferedInputFile(zip_buf.read(), filename=fname),
            caption=caption,
            parse_mode="HTML"
        )

        # Saqlash
        await save_missing_report_form(callback.from_user.id, form)
        await loading.delete()

        user = await get_user(callback.from_user.id)
        shop_name = (user or {}).get("shop_name", "—")
        await callback.message.answer(
            "✅ Hujjatlar yuborildi! Ma'lumotlar saqlandi.\n"
            "Keyingi safar tezroq bo'ladi 😊"
            if lang == "uz" else
            "✅ Документы отправлены! Данные сохранены.\n"
            "В следующий раз будет быстрее 😊",
            reply_markup=main_menu_keyboard(lang)
        )
        await state.clear()

    except Exception as e:
        logger.error(f"ZIP generation error: {e}", exc_info=True)
        await loading.edit_text(
            f"❌ Xatolik yuz berdi: <code>{str(e)[:200]}</code>"
            if lang == "uz" else
            f"❌ Ошибка: <code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )
