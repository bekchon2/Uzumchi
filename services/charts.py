"""
Matplotlib asosida grafiklar yaratish.
Rasmlar BytesIO da qaytariladi — Telegram ga yuborish uchun.
"""
import io
import logging
import datetime
import matplotlib
matplotlib.use("Agg")  # GUI kerak emas
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

COLORS = {
    "blue":  "#4A90D9",
    "green": "#27AE60",
    "red":   "#E74C3C",
    "orange":"#F39C12",
    "gray":  "#95A5A6",
    "bg":    "#1E1E2E",
    "text":  "#FFFFFF",
}


def _setup_dark_style():
    plt.rcParams.update({
        "figure.facecolor": COLORS["bg"],
        "axes.facecolor":   COLORS["bg"],
        "axes.edgecolor":   COLORS["gray"],
        "axes.labelcolor":  COLORS["text"],
        "xtick.color":      COLORS["text"],
        "ytick.color":      COLORS["text"],
        "text.color":       COLORS["text"],
        "grid.color":       "#2E2E4E",
        "grid.linestyle":   "--",
        "grid.alpha":       0.5,
        "font.size":        10,
    })


def weekly_sales_chart(daily_data: list[dict], lang: str = "ru") -> io.BytesIO:
    """
    7 kunlik bar chart.
    daily_data: [{"date": "2026-06-01", "orders": 5, "revenue": 150000}, ...]
    """
    _setup_dark_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    fig.suptitle(
        "📊 Haftalik sotuv" if lang == "uz" else "📊 Еженедельные продажи",
        color=COLORS["text"], fontsize=14, fontweight="bold"
    )

    dates = [d["date"] for d in daily_data]
    orders = [d.get("orders", 0) for d in daily_data]
    revenues = [d.get("revenue", 0) / 1000 for d in daily_data]  # ming so'mda

    # Buyurtmalar
    bars1 = ax1.bar(dates, orders, color=COLORS["blue"], alpha=0.85, width=0.6)
    ax1.set_ylabel("Buyurtmalar" if lang == "uz" else "Заказы", color=COLORS["text"])
    ax1.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax1.grid(axis="y")
    for bar, val in zip(bars1, orders):
        if val > 0:
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.1,
                str(val),
                ha="center", va="bottom", color=COLORS["text"], fontsize=9
            )

    # Tushum
    bars2 = ax2.bar(dates, revenues, color=COLORS["green"], alpha=0.85, width=0.6)
    ylabel = "Tushum (ming so'm)" if lang == "uz" else "Выручка (тыс. сум)"
    ax2.set_ylabel(ylabel, color=COLORS["text"])
    ax2.grid(axis="y")
    for bar, val in zip(bars2, revenues):
        if val > 0:
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.1,
                f"{val:.0f}",
                ha="center", va="bottom", color=COLORS["text"], fontsize=9
            )

    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf


def monthly_sales_chart(weekly_data: list[dict], lang: str = "ru") -> io.BytesIO:
    """
    4 haftalik bar chart.
    weekly_data: [{"week": "Hafta 1", "orders": 20, "revenue": 600000}, ...]
    """
    _setup_dark_style()
    fig, ax = plt.subplots(figsize=(9, 5))
    title = "📅 Oylik sotuv (haftalar bo'yicha)" if lang == "uz" else "📅 Месячные продажи (по неделям)"
    fig.suptitle(title, color=COLORS["text"], fontsize=13, fontweight="bold")

    weeks = [d["week"] for d in weekly_data]
    revenues = [d.get("revenue", 0) / 1000 for d in weekly_data]
    orders = [d.get("orders", 0) for d in weekly_data]

    x = range(len(weeks))
    width = 0.4

    bars_r = ax.bar([i - width/2 for i in x], revenues, width=width,
                    color=COLORS["green"], alpha=0.85, label="Tushum (ming so'm)" if lang == "uz" else "Выручка (тыс. сум)")
    bars_o = ax.bar([i + width/2 for i in x], orders, width=width,
                    color=COLORS["blue"], alpha=0.85, label="Buyurtmalar" if lang == "uz" else "Заказы")

    ax.set_xticks(list(x))
    ax.set_xticklabels(weeks)
    ax.legend(facecolor=COLORS["bg"], edgecolor=COLORS["gray"], labelcolor=COLORS["text"])
    ax.grid(axis="y")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf


def stock_pie_chart(products: list[dict], lang: str = "ru") -> io.BytesIO:
    """
    Mahsulot qoldiqlari bo'yicha pie chart.
    products: [{"name": "...", "qty": 10}, ...]
    """
    _setup_dark_style()
    fig, ax = plt.subplots(figsize=(8, 6))
    title = "📦 Mahsulot qoldiqlari" if lang == "uz" else "📦 Остатки товаров"
    fig.suptitle(title, color=COLORS["text"], fontsize=13, fontweight="bold")

    # Faqat top-10
    products_sorted = sorted(products, key=lambda p: p.get("qty", 0), reverse=True)[:10]
    names = [p["name"][:20] for p in products_sorted]
    qtys = [p.get("qty", 0) for p in products_sorted]

    if not qtys or sum(qtys) == 0:
        ax.text(0.5, 0.5, "Qoldiq yo'q" if lang == "uz" else "Нет остатков",
                ha="center", va="center", color=COLORS["text"], fontsize=14)
        ax.axis("off")
    else:
        palette = [COLORS["blue"], COLORS["green"], COLORS["orange"],
                   COLORS["red"], "#9B59B6", "#1ABC9C", "#E67E22",
                   "#3498DB", "#E91E63", "#00BCD4"]
        wedge_colors = palette[:len(qtys)]
        wedges, texts, autotexts = ax.pie(
            qtys, labels=names, autopct="%1.0f%%",
            colors=wedge_colors, startangle=140,
            textprops={"color": COLORS["text"], "fontsize": 8},
        )
        for at in autotexts:
            at.set_color(COLORS["bg"])
            at.set_fontsize(8)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf
