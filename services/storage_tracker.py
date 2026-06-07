"""
Omborxona kunlarini hisoblash va ogohlantirishlar.

Uzum 60 kun bepul saqlash beradi.
Faqat invoiceStatus.value == "ACCEPTED" nakładnoylar hisobga olinadi.
dateAccepted — Unix milliseconds.
"""
import datetime
import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

FREE_DAYS = 60  # Uzum bepul saqlash muddati

# Ogohlantirish chegaralari
WARN_DAYS = 53   # ⚠️
ALERT_DAYS = 57  # 🚨
PAID_DAYS = 60   # 💸 Pullik saqlash boshlanadi


class StorageItem(NamedTuple):
    invoice_id: int
    invoice_number: int | str
    date_accepted_ms: int
    days_stored: int
    total_accepted: int
    status: str


def calc_days_stored(date_accepted_ms: int) -> int:
    """Unix milliseconds dan hozirgi kungacha necha kun."""
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    diff_ms = now_ms - date_accepted_ms
    if diff_ms < 0:
        return 0
    return diff_ms // (1000 * 60 * 60 * 24)


def parse_invoices(invoices: list[dict]) -> list[StorageItem]:
    """
    Invoice ro'yxatidan faqat ACCEPTED statuslilarini olib,
    saqlash kunlarini hisoblaydi.
    """
    result = []
    for inv in invoices:
        status_obj = inv.get("invoiceStatus", {})
        status = status_obj.get("value", "") if isinstance(status_obj, dict) else str(status_obj)

        if status != "ACCEPTED":
            continue

        date_accepted = inv.get("dateAccepted")
        if not date_accepted:
            continue

        try:
            days = calc_days_stored(int(date_accepted))
        except (ValueError, TypeError):
            continue

        result.append(
            StorageItem(
                invoice_id=inv.get("id", 0),
                invoice_number=inv.get("invoiceNumber", "—"),
                date_accepted_ms=int(date_accepted),
                days_stored=days,
                total_accepted=inv.get("totalAccepted", 0),
                status=status,
            )
        )
    return result


def get_storage_alerts(items: list[StorageItem]) -> dict:
    """
    Ogohlantirishlar bo'yicha guruhlash.
    Returns:
        {
            "paid":  [StorageItem, ...],   # ≥60 kun 💸
            "alert": [StorageItem, ...],   # >57 kun 🚨
            "warn":  [StorageItem, ...],   # >53 kun ⚠️
            "ok":    [StorageItem, ...],   # boshqalar
        }
    """
    paid, alert, warn, ok = [], [], [], []
    for item in items:
        if item.days_stored >= PAID_DAYS:
            paid.append(item)
        elif item.days_stored > ALERT_DAYS:
            alert.append(item)
        elif item.days_stored > WARN_DAYS:
            warn.append(item)
        else:
            ok.append(item)
    return {"paid": paid, "alert": alert, "warn": warn, "ok": ok}


def format_storage_report(items: list[StorageItem], lang: str = "ru") -> str:
    """Omborxona holati uchun matn hisobot."""
    if not items:
        if lang == "uz":
            return "🏭 Omborda qabul qilingan nakładnoy yo'q."
        return "🏭 В складе нет принятых накладных."

    alerts = get_storage_alerts(items)

    lines = []
    if lang == "uz":
        lines.append("🏭 <b>Ombor holati:</b>")
    else:
        lines.append("🏭 <b>Состояние склада:</b>")

    def fmt_item(item: StorageItem, icon: str) -> str:
        days_left = max(0, FREE_DAYS - item.days_stored)
        if lang == "uz":
            return (
                f"{icon} Nakładnoy #{item.invoice_number}\n"
                f"   📦 Miqdor: {item.total_accepted} dona\n"
                f"   🗓 Saqlangan: {item.days_stored} kun\n"
                f"   ⏳ Qolgan bepul: {days_left} kun"
            )
        return (
            f"{icon} Накладная #{item.invoice_number}\n"
            f"   📦 Кол-во: {item.total_accepted} шт.\n"
            f"   🗓 Хранится: {item.days_stored} дн.\n"
            f"   ⏳ Бесплатно осталось: {days_left} дн."
        )

    for item in alerts["paid"]:
        lines.append(fmt_item(item, "💸"))
    for item in alerts["alert"]:
        lines.append(fmt_item(item, "🚨"))
    for item in alerts["warn"]:
        lines.append(fmt_item(item, "⚠️"))
    for item in alerts["ok"]:
        lines.append(fmt_item(item, "✅"))

    if lang == "uz":
        lines.append(f"\n📊 Jami nakładnoylar: {len(items)} ta")
    else:
        lines.append(f"\n📊 Всего накладных: {len(items)}")

    return "\n\n".join(lines)
