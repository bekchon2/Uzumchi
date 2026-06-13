"""
Telegram tugmalar (ReplyKeyboard va InlineKeyboard).
"""
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from locales.i18n import t


def lang_keyboard() -> InlineKeyboardMarkup:
    """Til tanlash tugmalari."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="lang_ru")
    builder.button(text="🇺🇿 O'zbek", callback_data="lang_uz")
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Asosiy menyu tugmalari."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("btn_products", lang))
    builder.button(text=t("btn_orders", lang))
    builder.button(text=t("btn_storage", lang))
    builder.button(text=t("btn_report", lang))
    builder.button(text=t("btn_weekly", lang))
    builder.button(text=t("btn_monthly", lang))
    builder.button(text=t("btn_returns", lang))
    builder.button(text=t("btn_competitor", lang))
    builder.button(text=t("btn_ai", lang))
    builder.button(text=t("btn_settings", lang))
    builder.adjust(2, 2, 2, 2, 1, 1)
    return builder.as_markup(resize_keyboard=True)


def back_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Faqat 'Orqaga' inline tugmasi — edit_text bilan ishlaydi."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_back", lang), callback_data="go_back")
    return builder.as_markup()


def back_refresh_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Orqaga + Yangilash inline tugmalari — edit_text bilan ishlaydi."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_refresh", lang), callback_data="go_refresh")
    builder.button(text=t("btn_back", lang), callback_data="go_back")
    builder.adjust(2)
    return builder.as_markup()


def settings_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Sozlamalar inline tugmalari."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_change_key", lang), callback_data="settings_change_key")
    builder.button(text=t("btn_change_lang", lang), callback_data="settings_change_lang")
    builder.button(text=t("btn_switch_shop", lang), callback_data="settings_switch_shop")
    builder.adjust(1)
    return builder.as_markup()


def shops_keyboard(shops: list[dict], lang: str = "ru") -> InlineKeyboardMarkup:
    """Multi-shop: do'konlar ro'yxati."""
    builder = InlineKeyboardBuilder()
    for shop in shops:
        shop_id = shop.get("id", 0)
        shop_name = shop.get("name", f"Do'kon {shop_id}")
        builder.button(
            text=f"🏪 {shop_name}",
            callback_data=f"shop_{shop_id}_{shop_name[:20]}"
        )
    builder.button(text=t("btn_back", lang), callback_data="shop_back")
    builder.adjust(1)
    return builder.as_markup()


def competitor_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Raqib narx monitoring tugmalari."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔗 " + ("URL qo'shish" if lang == "uz" else "Добавить URL"),
        callback_data="competitor_search"
    )
    builder.button(
        text="📋 " + ("Kuzatilayotganlar" if lang == "uz" else "Отслеживаемые"),
        callback_data="competitor_list"
    )
    builder.button(text=t("btn_back", lang), callback_data="competitor_back")
    builder.adjust(1)
    return builder.as_markup()


def ai_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """AI maslahatchi tugmalari."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_ai_sales", lang), callback_data="ai_sales")
    builder.button(text=t("btn_ai_storage", lang), callback_data="ai_storage")
    builder.button(text=t("btn_ai_question", lang), callback_data="ai_question")
    builder.button(text=t("btn_back", lang), callback_data="ai_back")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Bekor qilish tugmasi (FSM uchun)."""
    builder = ReplyKeyboardBuilder()
    cancel_text = "❌ Bekor qilish" if lang == "uz" else "❌ Отмена"
    builder.button(text=cancel_text)
    return builder.as_markup(resize_keyboard=True)


def products_nav_keyboard(page: int, total_pages: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Mahsulotlar paginatsiyasi — faqat sahifa o'tish."""
    builder = InlineKeyboardBuilder()
    row = []
    if page > 1:
        builder.button(text="⬅️", callback_data=f"products_page_{page - 1}")
    builder.button(text=f"{page}/{total_pages}", callback_data="products_noop")
    if page < total_pages:
        builder.button(text="➡️", callback_data=f"products_page_{page + 1}")
    # Nav tugmalar soni
    nav_count = (1 if page > 1 else 0) + 1 + (1 if page < total_pages else 0)
    builder.adjust(nav_count)
    return builder.as_markup()
