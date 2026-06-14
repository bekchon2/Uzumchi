"""
handlers/report_fallback.py — Mahsulot asosidagi zaxira hisobot (403 fallback).

Buyurtma/moliya endpointlari 403 qaytarganda (API kalitga «Buyurtmalar» ruxsati
berilmagan), kunlik/haftalik/oylik hisobotlar shu yerdagi sof (pure) funksiyalardan
foydalanib, `get_sales_stats_from_products` natijasini taxminiy hisobot sifatida
ko'rsatadi. Bu modul faqat i18n ga bog'liq — hech qanday I/O yoki holat yo'q.
"""
from locales.i18n import t


def product_stats_available(stats: dict) -> bool:
    """
    `get_sales_stats_from_products` natijasi zaxira hisobot uchun yaroqlimi?

    Rost (True) — `stats` bo'sh bo'lmagan dict bo'lib, `products_count > 0`.
    Bu 403 bo'lmagan mahsulot xatosini (bo'sh `{}`) va mahsulotsiz do'konni
    (`products_count == 0`) ajratadi — bunday hollarda fallback ishlamasligi kerak.
    """
    return bool(stats) and stats.get("products_count", 0) > 0


def build_product_fallback_report(product_stats: dict, lang: str) -> str:
    """
    Mahsulot statistikasidan taxminiy hisobot matnini tuzadi.

    `product_stats` — `get_sales_stats_from_products` qaytargan dict bo'lib,
    `total_sold, total_returned, total_revenue, products_count, low_stock_count,
    out_count` kalitlarini o'z ichiga oladi. Natija: taxminiy xulosa + lokalizatsiya
    qilingan (uz/ru) ogohlantirish izohi.
    """
    summary = t("report_fallback_summary", lang, **product_stats)
    note = t("report_fallback_note", lang)
    return f"{summary}\n\n{note}"
