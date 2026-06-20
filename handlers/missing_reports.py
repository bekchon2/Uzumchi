"""
handlers/missing_reports.py
===========================
Yo'qolgan tovarlar — qo'lda kiritish + ZIP generatsiya.

Flow:
  1. "📦 Yo'qolgan tovarlar" tugmasi
  2. Avvalgi saqlangan firma ma'lumotlari bormi? → Ha/Yo'q
  3. 11 ta firma maydoni (yoki saqlanganlari ishlatiladi)
  4. Tovarlarni qo'lda kiritish:
     - Tovar nomi → miqdor → narx → yana tovar? → Yo'q
  5. Tasdiqlash → ZIP (xlsx + docx) → yuboriladi
"""
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from database import get_user, get_missing_report_form, save_missing_report_form
from utils.doc_generator import create_zip
from utils.keyboards import main_menu_keyboard
from locales.i18n import t
from services.missing_service import MissingItem, format_missing_list

logger = logging.getLogger(__name__)
router = Router()


# ─── FSM States ───────────────────────────────────────────────────────────────

class MissingForm(StatesGroup):
    # Firma ma'lumotlari (11 ta)
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
    # Tovar kiritish
    item_name       = State()
    item_qty        = State()
    item_price      = State()
    # Tasdiqlash
    confirm         = State()


# Firma maydonlari
FIELDS = [
    ("report_date",     "📅 Hisobot sanasi",        "Дата отчёта",              "2026-06-19"),
    ("director_name",   "👤 Rahbarning F.I.Sh.",    "Ф.И.О. руководителя",     "YAKUBOVA DILRABO KAMILJONOVNA"),
    ("org_name",        "🏢 Tashkilot nomi",        "Наименование орг.",        "ИП YAKUBOVA DILRABO KAMILJONOVNA"),
    ("reg_number",      "🗂 ЯТТ / Reg. raqam",      "Рег. номер (ЯТТ)",        "6691547"),
    ("inn",             "🔢 INN / ЖШШИР",           "ИНН / ЖШШИР",             "41507933180159"),
    ("address",         "📍 Manzil",                "Юридический адрес",        "Viloyat, tuman, ko'cha, uy"),
    ("contract_number", "📝 Shartnoma raqami",       "Номер договора",           "0432955н"),
    ("contract_date",   "📆 Shartnoma sanasi",       "Дата договора",            "2026-05-15"),
    ("bank_name",       "🏦 Bank nomi",             "Название банка",           "Kapitalbank"),
    ("account_number",  "💳 Hisob raqami",          "Расчётный счёт",           "20218000000074682298"),
    ("bank_mfo",        "🏷 Bank MFO",              "МФО банка",                "01158"),
]

FIELD_KEYS = [f[0] for f in FIELDS]

STATE_MAP = {
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

def _cancel_kb(lang: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Bekor qilish" if lang == "uz" else "❌ Отмена")
    return builder.as_markup(resize_keyboard=True)


def _field_kb(lang: str, has_saved: bool):
    builder = ReplyKeyboardBuilder()
    if has_saved:
        builder.button(text="↩️ Saqlanganini qoldirish" if lang == "uz" else "↩️ Оставить сохранённое")
    builder.button(text="❌ Bekor qilish" if lang == "uz" else "❌ Отмена")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def _use_saved_kb(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Ha, shu ma'lumotlar" if lang == "uz" else "✅ Да, использовать",
        callback_data="missing_use_saved_yes"
    )
    builder.button(
        text="✏️ Qayta kiritaman" if lang == "uz" else "✏️ Заполнить заново",
        callback_data="missing_use_saved_no"
    )
    builder.adjust(1)
    return builder.as_markup()


def _more_items_kb(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Yana tovar qo'shish" if lang == "uz" else "➕ Добавить ещё товар",
        callback_data="missing_add_more"
    )
    builder.button(
        text="✅ Tayyor, hujjat tayyorla" if lang == "uz" else "✅ Готово, сформировать",
        callback_data="missing_items_done"
    )
    builder.adjust(1)
    return builder.as_markup()


def _confirm_kb(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Tasdiqlash va ZIP olish" if lang == "uz" else "✅ Подтвердить и получить ZIP",
        callback_data="missing_confirm_yes"
    )
    builder.button(
        text="✏️ Tovarlarni qayta kiritish" if lang == "uz" else "✏️ Переввести товары",
        callback_data="missing_redo_items"
    )
    builder.button(
        text="🔄 Firma ma'lumotlarini o'zgartirish" if lang == "uz" else "🔄 Изменить данные фирмы",
        callback_data="missing_redo_form"
    )
    builder.adjust(1)
    return builder.as_markup()


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────

def _saved_summary(saved: dict, lang: str) -> str:
    lines = ["💾 <b>Saqlangan ma'lumotlar:</b>" if lang == "uz" else "💾 <b>Сохранённые данные:</b>"]
    for key, lbl_uz, lbl_ru, _ in FIELDS:
        val = saved.get(key) or "—"
        lbl = lbl_uz if lang == "uz" else lbl_ru
        lines.append(f"  <b>{lbl}:</b> {val}")
    return "\n".join(lines)


def _items_summary(items: list[dict], lang: str) -> str:
    if not items:
        return "—"
    lines = []
    total_comp = 0.0
    for i, item in enumerate(items, 1):
        comp = item["qty"] * item["price"]
        total_comp += comp
        if lang == "uz":
            lines.append(
                f"{i}. <b>{item['name'][:50]}</b>\n"
                f"   {item['qty']} dona × {item['price']:,.0f} = <b>{comp:,.0f} so'm</b>"
            )
        else:
            lines.append(
                f"{i}. <b>{item['name'][:50]}</b>\n"
                f"   {item['qty']} шт. × {item['price']:,.0f} = <b>{comp:,.0f} сум</b>"
            )
    sep = "─" * 28
    total_lbl = f"💰 Jami: <b>{total_comp:,.0f} so'm</b>" if lang == "uz" \
                else f"💰 Итого: <b>{total_comp:,.0f} сум</b>"
    return "\n".join(lines) + f"\n{sep}\n{total_lbl}"


async def _ask_field(target, state: FSMContext, idx: int, lang: str, saved: dict | None):
    key, lbl_uz, lbl_ru, example = FIELDS[idx]
    lbl = lbl_uz if lang == "uz" else lbl_ru
    saved_v = (saved or {}).get(key, "")

    text = f"<b>{idx + 1}/{len(FIELDS)}. {lbl}:</b>"
    if saved_v:
        text += f"\n💾 {'Avvalgi' if lang == 'uz' else 'Предыдущее'}: <code>{saved_v}</code>"
    text += f"\n📌 {'Namuna' if lang == 'uz' else 'Пример'}: <i>{example}</i>"

    await state.set_state(STATE_MAP[key])
    kb = _field_kb(lang, bool(saved_v))

    msg = target if isinstance(target, Message) else target.message
    await msg.answer(text, reply_markup=kb, parse_mode="HTML")


async def _start_item_entry(target, state: FSMContext, lang: str):
    """Tovar kiritishni boshlash."""
    await state.set_state(MissingForm.item_name)
    text = (
        "📦 <b>Yo'qolgan tovarni kiriting</b>\n\n"
        "Tovar nomini yozing:\n"
        "<i>Masalan: Детский игрушечный парашют...</i>"
        if lang == "uz" else
        "📦 <b>Введите потерянный товар</b>\n\n"
        "Напишите название товара:\n"
        "<i>Например: Детский игрушечный парашют...</i>"
    )
    msg = target if isinstance(target, Message) else target.message
    await msg.answer(text, reply_markup=_cancel_kb(lang), parse_mode="HTML")


async def _go_to_confirm(target, state: FSMContext, lang: str, form: dict, items: list):
    """Tasdiqlash sahifasini ko'rsatish."""
    await state.set_state(MissingForm.confirm)

    items_text = _items_summary(items, lang)
    total_qty  = sum(i["qty"] for i in items)
    total_comp = sum(i["qty"] * i["price"] for i in items)

    if lang == "uz":
        text = (
            f"📋 <b>Tasdiqlash</b>\n\n"
            f"🏢 <b>Firma:</b> {form.get('org_name', '—')}\n"
            f"📅 <b>Sana:</b> {form.get('report_date', '—')}\n"
            f"📝 <b>Shartnoma:</b> №{form.get('contract_number', '—')}\n\n"
            f"📦 <b>Yo'qolgan tovarlar:</b>\n{items_text}\n\n"
            f"📊 Jami: <b>{total_qty} dona</b>\n"
            f"💰 Kompensatsiya: <b>{total_comp:,.0f} so'm</b>\n\n"
            f"❓ Ma'lumotlar to'g'rimi?"
        )
    else:
        text = (
            f"📋 <b>Подтверждение</b>\n\n"
            f"🏢 <b>Фирма:</b> {form.get('org_name', '—')}\n"
            f"📅 <b>Дата:</b> {form.get('report_date', '—')}\n"
            f"📝 <b>Договор:</b> №{form.get('contract_number', '—')}\n\n"
            f"📦 <b>Потерянные товары:</b>\n{items_text}\n\n"
            f"📊 Итого: <b>{total_qty} шт.</b>\n"
            f"💰 Компенсация: <b>{total_comp:,.0f} сум</b>\n\n"
            f"❓ Данные верны?"
        )

    msg = target if isinstance(target, Message) else target.message
    await msg.answer(text, reply_markup=_confirm_kb(lang), parse_mode="HTML")


# ─── Asosiy kirish nuqtasi ────────────────────────────────────────────────────

@router.message(F.text.in_(["📦 Yo'qolgan tovarlar", "📦 Потерянные товары"]))
async def cmd_missing(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("⚠️ Avval /start bilan botni sozlang.")
        return

    lang      = user.get("lang", "ru")
    shop_name = user.get("shop_name", "JoyKid")
    saved     = await get_missing_report_form(message.from_user.id)

    await state.update_data(lang=lang, shop_name=shop_name, items=[])

    if saved and any(saved.get(k) for k in FIELD_KEYS):
        text = _saved_summary(saved, lang)
        q = ("\n\n❓ Shu ma'lumotlardan foydalanasizmi?" if lang == "uz"
             else "\n\n❓ Использовать эти сохранённые данные?")
        await message.answer(text + q, reply_markup=_use_saved_kb(lang), parse_mode="HTML")
    else:
        intro = (
            "📝 <b>Yo'qolgan tovarlar hujjati</b>\n\n"
            "Avval firma ma'lumotlarini kiritamiz (11 ta maydon).\n"
            "Keyingi safar qayta kiritish shart emas — saqlanadi. 💾"
            if lang == "uz" else
            "📝 <b>Документ по потерянным товарам</b>\n\n"
            "Сначала введём данные фирмы (11 полей).\n"
            "В следующий раз вводить заново не нужно — сохранится. 💾"
        )
        await message.answer(intro, parse_mode="HTML")
        await state.update_data(form={}, field_idx=0, saved=None)
        await _ask_field(message, state, 0, lang, None)


# ─── Saqlangan ma'lumotlar ────────────────────────────────────────────────────

@router.callback_query(F.data == "missing_use_saved_yes")
async def use_saved_yes(call: CallbackQuery, state: FSMContext):
    user  = await get_user(call.from_user.id)
    lang  = user.get("lang", "ru") if user else "ru"
    saved = await get_missing_report_form(call.from_user.id)
    form  = {k: (saved.get(k) or "") for k in FIELD_KEYS}

    await state.update_data(form=form, field_idx=len(FIELDS))
    await call.answer()
    await _start_item_entry(call, state, lang)


@router.callback_query(F.data == "missing_use_saved_no")
async def use_saved_no(call: CallbackQuery, state: FSMContext):
    user  = await get_user(call.from_user.id)
    lang  = user.get("lang", "ru") if user else "ru"
    saved = await get_missing_report_form(call.from_user.id)

    await state.update_data(form={}, field_idx=0, saved=saved)
    await call.answer()
    await _ask_field(call, state, 0, lang, saved)


# ─── Firma maydonlari ─────────────────────────────────────────────────────────

async def _process_field(message: Message, state: FSMContext, field_key: str):
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    form  = data.get("form", {})
    saved = data.get("saved")
    idx   = data.get("field_idx", 0)

    cancel = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    skip   = "↩️ Saqlanganini qoldirish" if lang == "uz" else "↩️ Оставить сохранённое"

    if message.text == cancel:
        await state.clear()
        user = await get_user(message.from_user.id)
        shop_name = (user or {}).get("shop_name", "—")
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
        )
        return

    if message.text == skip:
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
        # Firma ma'lumotlari tugadi → tovar kiritishga o'tish
        await _start_item_entry(message, state, lang)


@router.message(MissingForm.report_date)
async def f_report_date(msg: Message, state: FSMContext):
    await _process_field(msg, state, "report_date")

@router.message(MissingForm.director_name)
async def f_director_name(msg: Message, state: FSMContext):
    await _process_field(msg, state, "director_name")

@router.message(MissingForm.org_name)
async def f_org_name(msg: Message, state: FSMContext):
    await _process_field(msg, state, "org_name")

@router.message(MissingForm.reg_number)
async def f_reg_number(msg: Message, state: FSMContext):
    await _process_field(msg, state, "reg_number")

@router.message(MissingForm.inn)
async def f_inn(msg: Message, state: FSMContext):
    await _process_field(msg, state, "inn")

@router.message(MissingForm.address)
async def f_address(msg: Message, state: FSMContext):
    await _process_field(msg, state, "address")

@router.message(MissingForm.contract_number)
async def f_contract_number(msg: Message, state: FSMContext):
    await _process_field(msg, state, "contract_number")

@router.message(MissingForm.contract_date)
async def f_contract_date(msg: Message, state: FSMContext):
    await _process_field(msg, state, "contract_date")

@router.message(MissingForm.bank_name)
async def f_bank_name(msg: Message, state: FSMContext):
    await _process_field(msg, state, "bank_name")

@router.message(MissingForm.account_number)
async def f_account_number(msg: Message, state: FSMContext):
    await _process_field(msg, state, "account_number")

@router.message(MissingForm.bank_mfo)
async def f_bank_mfo(msg: Message, state: FSMContext):
    await _process_field(msg, state, "bank_mfo")


# ─── Tovar kiritish ───────────────────────────────────────────────────────────

@router.message(MissingForm.item_name)
async def f_item_name(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")

    cancel = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    if message.text == cancel:
        await state.clear()
        user = await get_user(message.from_user.id)
        shop_name = (user or {}).get("shop_name", "—")
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
        )
        return

    await state.update_data(current_item_name=message.text.strip())
    await state.set_state(MissingForm.item_qty)

    text = (
        f"✅ Tovar: <b>{message.text.strip()[:50]}</b>\n\n"
        f"🔢 Yo'qolgan soni (faqat raqam):\n<i>Masalan: 2</i>"
        if lang == "uz" else
        f"✅ Товар: <b>{message.text.strip()[:50]}</b>\n\n"
        f"🔢 Количество потерянных (только цифра):\n<i>Например: 2</i>"
    )
    await message.answer(text, reply_markup=_cancel_kb(lang), parse_mode="HTML")


@router.message(MissingForm.item_qty)
async def f_item_qty(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")

    cancel = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    if message.text == cancel:
        await state.clear()
        user = await get_user(message.from_user.id)
        shop_name = (user or {}).get("shop_name", "—")
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
        )
        return

    try:
        qty = int(message.text.strip().replace(" ", ""))
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ Faqat musbat son kiriting. Masalan: <code>2</code>"
            if lang == "uz" else
            "⚠️ Введите только положительное число. Например: <code>2</code>",
            parse_mode="HTML"
        )
        return

    await state.update_data(current_item_qty=qty)
    await state.set_state(MissingForm.item_price)

    text = (
        f"💰 Tovar tannarxi (so'mda, faqat raqam):\n"
        f"<i>Masalan: 14924</i>\n\n"
        f"💡 Tannarxingizni bilmasangiz, Uzum kabinetdagi sotish narxini kiriting"
        if lang == "uz" else
        f"💰 Себестоимость товара (в сумах, только цифра):\n"
        f"<i>Например: 14924</i>\n\n"
        f"💡 Если не знаете себестоимость, введите цену продажи из кабинета Uzum"
    )
    await message.answer(text, reply_markup=_cancel_kb(lang), parse_mode="HTML")


@router.message(MissingForm.item_price)
async def f_item_price(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")

    cancel = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    if message.text == cancel:
        await state.clear()
        user = await get_user(message.from_user.id)
        shop_name = (user or {}).get("shop_name", "—")
        await message.answer(
            t("main_menu", lang, shop_name=shop_name),
            reply_markup=main_menu_keyboard(lang), parse_mode="HTML"
        )
        return

    try:
        price = float(message.text.strip().replace(" ", "").replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ Faqat musbat son kiriting. Masalan: <code>14924</code>"
            if lang == "uz" else
            "⚠️ Введите только положительное число. Например: <code>14924</code>",
            parse_mode="HTML"
        )
        return

    # Tovarni ro'yxatga qo'shamiz
    items = data.get("items", [])
    name  = data.get("current_item_name", "—")
    qty   = data.get("current_item_qty", 1)
    comp  = qty * price

    items.append({"name": name, "qty": qty, "price": price})
    await state.update_data(items=items)

    # Qo'shilgan tovarni ko'rsatamiz
    if lang == "uz":
        text = (
            f"✅ <b>Qo'shildi:</b>\n"
            f"📦 {name[:50]}\n"
            f"🔢 {qty} dona × {price:,.0f} = <b>{comp:,.0f} so'm</b>\n\n"
            f"Jami tovarlar: <b>{len(items)} ta</b>\n\n"
            f"Yana tovar qo'shish yoki tayyor?"
        )
    else:
        text = (
            f"✅ <b>Добавлено:</b>\n"
            f"📦 {name[:50]}\n"
            f"🔢 {qty} шт. × {price:,.0f} = <b>{comp:,.0f} сум</b>\n\n"
            f"Всего товаров: <b>{len(items)} шт.</b>\n\n"
            f"Добавить ещё или готово?"
        )

    await message.answer(text, reply_markup=_more_items_kb(lang), parse_mode="HTML")


# ─── Yana tovar / Tayyor ──────────────────────────────────────────────────────

@router.callback_query(F.data == "missing_add_more")
async def add_more_items(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await call.answer()
    await _start_item_entry(call, state, lang)


@router.callback_query(F.data == "missing_items_done")
async def items_done(call: CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    items = data.get("items", [])
    form  = data.get("form", {})

    if not items:
        await call.answer(
            "⚠️ Kamida 1 ta tovar kiriting!" if lang == "uz"
            else "⚠️ Введите хотя бы 1 товар!",
            show_alert=True
        )
        return

    await call.answer()
    await _go_to_confirm(call, state, lang, form, items)


# ─── Tasdiqlash ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "missing_redo_items")
async def redo_items(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.update_data(items=[])
    await call.answer()
    await _start_item_entry(call, state, lang)


@router.callback_query(F.data == "missing_redo_form")
async def redo_form(call: CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    saved = await get_missing_report_form(call.from_user.id)
    await state.update_data(form={}, field_idx=0, saved=saved)
    await call.answer()
    await _ask_field(call, state, 0, lang, saved)


@router.callback_query(F.data == "missing_confirm_yes")
async def confirm_yes(call: CallbackQuery, state: FSMContext, bot: Bot):
    data  = await state.get_data()
    lang  = data.get("lang", "ru")
    form  = data.get("form", {})
    items_raw = data.get("items", [])

    if not items_raw:
        await call.answer(
            "⚠️ Tovarlar kiritilmagan!" if lang == "uz" else "⚠️ Товары не введены!",
            show_alert=True
        )
        return

    # dict → MissingItem
    missing_items = [
        MissingItem(
            name=i["name"],
            sku_code="—",
            barcode="—",
            missing_qty=i["qty"],
            purchase_price=i["price"],
            compensation=i["qty"] * i["price"],
        )
        for i in items_raw
    ]

    await call.answer(
        "⏳ ZIP tayyorlanmoqda..." if lang == "uz" else "⏳ Формирую ZIP..."
    )
    loading = await call.message.answer(
        "⚙️ Hujjatlar generatsiya qilinmoqda..." if lang == "uz"
        else "⚙️ Генерирую документы, подождите..."
    )

    try:
        if not form.get("report_date"):
            form["report_date"] = datetime.now().strftime("%Y-%m-%d")

        zip_buf  = create_zip(form, missing_items)
        date_str = form["report_date"].replace("-", "")
        fname    = f"yoqolgan-tovarlar-{date_str}.zip"

        total_qty  = sum(i.missing_qty for i in missing_items)
        total_comp = sum(i.compensation for i in missing_items)

        if lang == "uz":
            caption = (
                f"📦 <b>Yo'qolgan tovarlar hujjati</b>\n\n"
                f"📊 Yo'qolgan: <b>{total_qty} dona</b>\n"
                f"💰 Kompensatsiya: <b>{total_comp:,.0f} so'm</b>\n\n"
                f"📄 <code>Доп-соглашение.docx</code>\n"
                f"📊 <code>отчет-потерянных-товаров.xlsx</code>\n\n"
                f"💡 Shu fayllarni Uzum support ga yuboring."
            )
        else:
            caption = (
                f"📦 <b>Документ по потерянным товарам</b>\n\n"
                f"📊 Потеряно: <b>{total_qty} шт.</b>\n"
                f"💰 Компенсация: <b>{total_comp:,.0f} сум</b>\n\n"
                f"📄 <code>Доп-соглашение.docx</code>\n"
                f"📊 <code>отчет-потерянных-товаров.xlsx</code>\n\n"
                f"💡 Отправьте эти файлы в поддержку Uzum."
            )

        await bot.send_document(
            chat_id=call.from_user.id,
            document=BufferedInputFile(zip_buf.read(), filename=fname),
            caption=caption,
            parse_mode="HTML"
        )

        await save_missing_report_form(call.from_user.id, form)
        await loading.delete()

        user = await get_user(call.from_user.id)
        shop_name = (user or {}).get("shop_name", "—")
        await call.message.answer(
            "✅ Hujjatlar yuborildi! Firma ma'lumotlari saqlandi.\n"
            "Keyingi safar tezroq bo'ladi 😊"
            if lang == "uz" else
            "✅ Документы отправлены! Данные фирмы сохранены.\n"
            "В следующий раз будет быстрее 😊",
            reply_markup=main_menu_keyboard(lang)
        )
        await state.clear()

    except Exception as e:
        logger.error(f"ZIP generation error: {e}", exc_info=True)
        await loading.edit_text(
            f"❌ Xatolik: <code>{str(e)[:200]}</code>"
            if lang == "uz" else
            f"❌ Ошибка: <code>{str(e)[:200]}</code>",
            parse_mode="HTML"
        )
