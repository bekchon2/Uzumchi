"""
Yordamchi funksiyalar: vaqt, format, mahsulot ikonkalar.
"""
import datetime
import pytz

TASHKENT = pytz.timezone("Asia/Tashkent")


def now_tashkent() -> datetime.datetime:
    return datetime.datetime.now(TASHKENT)


def format_price(amount: float, lang: str = "ru") -> str:
    """Narxni chiroyli ko'rinishda chiqarish."""
    suffix = " so'm" if lang == "uz" else " сум"
    return f"{amount:,.0f}{suffix}"


def format_date(ts_ms: int) -> str:
    """Unix milliseconds → 'DD.MM.YYYY' string."""
    dt = datetime.datetime.fromtimestamp(ts_ms / 1000, tz=TASHKENT)
    return dt.strftime("%d.%m.%Y")


def format_datetime(ts_ms: int) -> str:
    """Unix milliseconds → 'DD.MM.YYYY HH:MM' string."""
    dt = datetime.datetime.fromtimestamp(ts_ms / 1000, tz=TASHKENT)
    return dt.strftime("%d.%m.%Y %H:%M")


def days_ago_ms(days: int) -> int:
    """N kun oldingi vaqt (Unix milliseconds)."""
    dt = datetime.datetime.now() - datetime.timedelta(days=days)
    return int(dt.timestamp() * 1000)


def now_ms() -> int:
    return int(datetime.datetime.now().timestamp() * 1000)


def stock_icon(qty: int) -> str:
    """Qoldiq miqdori bo'yicha ikonka."""
    if qty == 0:
        return "🚫"
    elif qty <= 5:
        return "⚠️"
    elif qty <= 15:
        return "🟡"
    else:
        return "🟢"


def forecast_days(qty: int, avg_daily: float) -> int:
    """Qoldiq tugashiga qancha kun qolganini hisoblash."""
    if avg_daily <= 0:
        return 9999
    return int(qty / avg_daily)


def short_name(name: str, max_len: int = 35) -> str:
    """Uzun nomni qisqartirish."""
    if len(name) <= max_len:
        return name
    return name[:max_len - 1] + "…"


def order_status_icon(status: str) -> str:
    """Buyurtma statusi ikonkasi."""
    return {
        "DELIVERED":  "✅",
        "CANCELLED":  "❌",
        "PROCESSING": "🔄",
        "SHIPPED":    "🚚",
        "CREATED":    "🆕",
        "PENDING":    "⏳",
    }.get(status.upper(), "❓")


def pct_change(old: float, new: float) -> str:
    """O'zgarish foizini ko'rsatish: +12% yoki -5%."""
    if old == 0:
        return "—"
    pct = (new - old) / old * 100
    icon = "📈" if pct >= 0 else "📉"
    return f"{icon} {pct:+.1f}%"


def chunk_list(lst: list, size: int) -> list[list]:
    """Ro'yxatni teng bo'laklarga ajratish."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def safe_float(val, default: float = 0.0) -> float:
    """Xavfsiz float konvertatsiya."""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_int(val, default: int = 0) -> int:
    """Xavfsiz int konvertatsiya."""
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default
