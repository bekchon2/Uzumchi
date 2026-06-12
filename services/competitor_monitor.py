"""
Raqib narx monitoring servisi.
Uzum ochiq katalog API orqali mahsulot narxlarini kuzatadi.
"""
import asyncio
import logging
import ssl
import aiohttp
import datetime

logger = logging.getLogger(__name__)

CATALOG_BASE = "https://api.uzum.uz/api"

# Windows SSL muammosini hal qilish
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


async def search_products_by_name(query: str, limit: int = 20) -> list[dict]:
    """
    Uzum katalogidan mahsulot nomi bo'yicha qidirish.
    """
    url = f"{CATALOG_BASE}/v2/search/products"
    params = {
        "query": query,
        "limit": limit,
        "offset": 0,
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "x-iid": "uzumBot",
    }
    try:
        await asyncio.sleep(0.5)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT)) as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("payload", {}).get("products", [])
                else:
                    logger.warning(f"Catalog search HTTP {resp.status}")
                    return []
    except Exception as e:
        logger.error(f"Catalog search error: {e}")
        return []


async def get_product_prices(product_name: str, limit: int = 10) -> list[dict]:
    """
    Mahsulot nomi bo'yicha raqiblar narxlarini olish.
    Returns: [{"title": "...", "price": 99000, "shop": "...", "rating": 4.8}]
    """
    products = await search_products_by_name(product_name, limit=limit)
    result = []
    for p in products:
        try:
            # Narx olish
            sku_list = p.get("skuList", [])
            price = None
            if sku_list:
                price = sku_list[0].get("purchasePrice") or sku_list[0].get("price")
            if price is None:
                price = p.get("minSellPrice") or p.get("price") or 0

            title = p.get("title", p.get("name", "—"))
            shop_info = p.get("shop", {}) or {}
            shop_name = shop_info.get("name", "—") if isinstance(shop_info, dict) else "—"
            rating = p.get("rating", 0) or 0

            result.append({
                "title": title[:60],
                "price": float(price),
                "shop": shop_name,
                "rating": float(rating),
                "product_id": p.get("id"),
            })
        except Exception as e:
            logger.debug(f"Price parse error: {e}")
            continue
    return result


def format_competitor_report(
    my_product_name: str,
    my_price: float,
    competitors: list[dict],
    lang: str = "ru"
) -> str:
    """Raqib narxlari hisoboti."""
    if not competitors:
        if lang == "uz":
            return f"🔍 <b>{my_product_name}</b>\n\nRaqiblar topilmadi."
        return f"🔍 <b>{my_product_name}</b>\n\nКонкуренты не найдены."

    # Narx bo'yicha saralash
    sorted_comps = sorted(competitors, key=lambda x: x["price"])

    cheaper = [c for c in sorted_comps if c["price"] < my_price]
    same_range = [c for c in sorted_comps if abs(c["price"] - my_price) / max(my_price, 1) <= 0.05]
    more_expensive = [c for c in sorted_comps if c["price"] > my_price * 1.05]

    min_price = sorted_comps[0]["price"] if sorted_comps else 0
    max_price = sorted_comps[-1]["price"] if sorted_comps else 0
    avg_price = sum(c["price"] for c in sorted_comps) / len(sorted_comps)

    if lang == "uz":
        lines = [
            f"🔍 <b>Raqib narx tahlili</b>",
            f"📦 Mahsulot: <b>{my_product_name[:40]}</b>",
            f"💰 Mening narxim: <b>{my_price:,.0f} so'm</b>",
            f"",
            f"📊 Bozor tahlili ({len(sorted_comps)} raqib):",
            f"  🟢 Eng arzon: {min_price:,.0f} so'm",
            f"  🟡 O'rtacha: {avg_price:,.0f} so'm",
            f"  🔴 Eng qimmat: {max_price:,.0f} so'm",
            f"",
        ]
        if my_price <= min_price * 1.02:
            lines.append("✅ Siz eng arzon yoki birinchilar qatorida!")
        elif my_price > avg_price * 1.1:
            lines.append(f"⚠️ Narxingiz o'rtachadan {((my_price/avg_price)-1)*100:.0f}% yuqori")
        else:
            lines.append("🟡 Narxingiz raqobatbardosh")

        if cheaper:
            lines.append(f"\n💡 Sizdan arzon: {len(cheaper)} ta")
        if more_expensive:
            lines.append(f"📈 Sizdan qimmat: {len(more_expensive)} ta")

        lines.append("\n<b>Top 5 raqib:</b>")
        for i, c in enumerate(sorted_comps[:5], 1):
            icon = "🟢" if c["price"] < my_price else ("🟡" if c["price"] <= my_price * 1.05 else "🔴")
            lines.append(f"{i}. {icon} {c['shop']}: {c['price']:,.0f} so'm ⭐{c['rating']:.1f}")

    else:
        lines = [
            f"🔍 <b>Анализ цен конкурентов</b>",
            f"📦 Товар: <b>{my_product_name[:40]}</b>",
            f"💰 Моя цена: <b>{my_price:,.0f} сум</b>",
            f"",
            f"📊 Анализ рынка ({len(sorted_comps)} конк.):",
            f"  🟢 Мин: {min_price:,.0f} сум",
            f"  🟡 Среднее: {avg_price:,.0f} сум",
            f"  🔴 Макс: {max_price:,.0f} сум",
            f"",
        ]
        if my_price <= min_price * 1.02:
            lines.append("✅ Вы самый дешёвый или в топе!")
        elif my_price > avg_price * 1.1:
            lines.append(f"⚠️ Цена выше среднего на {((my_price/avg_price)-1)*100:.0f}%")
        else:
            lines.append("🟡 Цена конкурентоспособна")

        if cheaper:
            lines.append(f"\n💡 Дешевле вас: {len(cheaper)} шт.")
        if more_expensive:
            lines.append(f"📈 Дороже вас: {len(more_expensive)} шт.")

        lines.append("\n<b>Топ-5 конкурентов:</b>")
        for i, c in enumerate(sorted_comps[:5], 1):
            icon = "🟢" if c["price"] < my_price else ("🟡" if c["price"] <= my_price * 1.05 else "🔴")
            lines.append(f"{i}. {icon} {c['shop']}: {c['price']:,.0f} сум ⭐{c['rating']:.1f}")

    return "\n".join(lines)
