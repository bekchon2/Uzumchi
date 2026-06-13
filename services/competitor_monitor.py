"""
Raqib narx monitoring servisi.
Uzum ochiq katalog API orqali mahsulot narxlarini kuzatadi.
"""
import asyncio
import logging
import ssl
import aiohttp

logger = logging.getLogger(__name__)

# Windows SSL muammosini hal qilish
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Sinab ko'riladigan URL lar (Uzum API tez-tez o'zgaradi)
SEARCH_URLS = [
    "https://api.uzum.uz/api/v2/search/products",
    "https://api.uzum.uz/api/main/search/product",
    "https://api.uzum.uz/api/v1/search/products",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8,uz;q=0.7",
    "Origin": "https://uzum.uz",
    "Referer": "https://uzum.uz/",
}


async def search_products_by_name(query: str, limit: int = 20) -> list[dict]:
    """
    Uzum katalogidan mahsulot nomi bo'yicha qidirish.
    Bir nechta endpoint ni sinab ko'radi.
    """
    await asyncio.sleep(0.5)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
        headers=HEADERS
    ) as session:
        # 1. v2 search
        for url in SEARCH_URLS:
            try:
                params = {"query": query, "size": limit, "page": 0}
                async with session.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Turli response formatlar
                        products = (
                            data.get("payload", {}).get("products", [])
                            or data.get("products", [])
                            or data.get("items", [])
                            or (data if isinstance(data, list) else [])
                        )
                        if products:
                            logger.info(f"Catalog search OK: {url} → {len(products)} products")
                            return products
                    else:
                        logger.warning(f"Catalog search {url} → HTTP {resp.status}")
            except Exception as e:
                logger.debug(f"Search URL {url} failed: {e}")
                continue

    logger.warning(f"All catalog search URLs failed for query: '{query}'")
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
            # Narx olish — turli formatlar
            price = None
            sku_list = p.get("skuList", []) or p.get("skus", [])
            if sku_list:
                sku = sku_list[0]
                price = (
                    sku.get("purchasePrice")
                    or sku.get("sellPrice")
                    or sku.get("price")
                )
            if price is None:
                price = (
                    p.get("minSellPrice")
                    or p.get("price")
                    or p.get("sellPrice")
                    or 0
                )

            title = p.get("title") or p.get("name") or "—"
            shop_info = p.get("shop") or p.get("seller") or {}
            shop_name = (
                shop_info.get("name") or shop_info.get("shopName")
                if isinstance(shop_info, dict) else str(shop_info)
            ) or "—"
            rating = float(p.get("rating") or p.get("reviewRating") or 0)

            if float(price) > 0:
                result.append({
                    "title": str(title)[:60],
                    "price": float(price),
                    "shop": str(shop_name)[:40],
                    "rating": rating,
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

    sorted_comps = sorted(competitors, key=lambda x: x["price"])
    cheaper = [c for c in sorted_comps if c["price"] < my_price]
    more_expensive = [c for c in sorted_comps if c["price"] > my_price * 1.05]
    min_price = sorted_comps[0]["price"]
    max_price = sorted_comps[-1]["price"]
    avg_price = sum(c["price"] for c in sorted_comps) / len(sorted_comps)

    if lang == "uz":
        lines = [
            f"🔍 <b>Raqib narx tahlili</b>",
            f"📦 Mahsulot: <b>{my_product_name[:40]}</b>",
            f"💰 Mening narxim: <b>{my_price:,.0f} so'm</b>" if my_price > 0 else "💰 Narx: <i>topilmadi</i>",
            f"",
            f"📊 Bozor tahlili ({len(sorted_comps)} raqib):",
            f"  🟢 Eng arzon: {min_price:,.0f} so'm",
            f"  🟡 O'rtacha: {avg_price:,.0f} so'm",
            f"  🔴 Eng qimmat: {max_price:,.0f} so'm",
        ]
        if my_price > 0:
            if my_price <= min_price * 1.05:
                lines.append("\n✅ Siz eng arzon yoki birinchilar qatorida!")
            elif my_price > avg_price * 1.1:
                lines.append(f"\n⚠️ Narxingiz o'rtachadan {((my_price/avg_price)-1)*100:.0f}% yuqori")
            else:
                lines.append("\n🟡 Narxingiz raqobatbardosh")
            if cheaper:
                lines.append(f"💡 Sizdan arzon: {len(cheaper)} ta")
            if more_expensive:
                lines.append(f"📈 Sizdan qimmat: {len(more_expensive)} ta")

        lines.append("\n<b>Top 5 raqib:</b>")
        for i, c in enumerate(sorted_comps[:5], 1):
            icon = "🟢" if (my_price > 0 and c["price"] < my_price) else ("🟡" if (my_price > 0 and c["price"] <= my_price * 1.05) else "🔴")
            lines.append(f"{i}. {icon} {c['shop']}: {c['price']:,.0f} so'm ⭐{c['rating']:.1f}")
    else:
        lines = [
            f"🔍 <b>Анализ цен конкурентов</b>",
            f"📦 Товар: <b>{my_product_name[:40]}</b>",
            f"💰 Моя цена: <b>{my_price:,.0f} сум</b>" if my_price > 0 else "💰 Цена: <i>не найдена</i>",
            f"",
            f"📊 Анализ рынка ({len(sorted_comps)} конк.):",
            f"  🟢 Мин: {min_price:,.0f} сум",
            f"  🟡 Среднее: {avg_price:,.0f} сум",
            f"  🔴 Макс: {max_price:,.0f} сум",
        ]
        if my_price > 0:
            if my_price <= min_price * 1.05:
                lines.append("\n✅ Вы самый дешёвый или в топе!")
            elif my_price > avg_price * 1.1:
                lines.append(f"\n⚠️ Цена выше среднего на {((my_price/avg_price)-1)*100:.0f}%")
            else:
                lines.append("\n🟡 Цена конкурентоспособна")
            if cheaper:
                lines.append(f"💡 Дешевле вас: {len(cheaper)} шт.")
            if more_expensive:
                lines.append(f"📈 Дороже вас: {len(more_expensive)} шт.")

        lines.append("\n<b>Топ-5 конкурентов:</b>")
        for i, c in enumerate(sorted_comps[:5], 1):
            icon = "🟢" if (my_price > 0 and c["price"] < my_price) else ("🟡" if (my_price > 0 and c["price"] <= my_price * 1.05) else "🔴")
            lines.append(f"{i}. {icon} {c['shop']}: {c['price']:,.0f} сум ⭐{c['rating']:.1f}")

    return "\n".join(lines)
