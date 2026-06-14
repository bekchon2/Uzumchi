"""
Raqib narx monitoring.
Foydalanuvchi Uzum tovar sahifa URL sini beradi.
Bot tovar nomini HTML dan avtomatik oladi, narxni API dan oladi.
"""
import asyncio
import logging
import ssl
import re
import json
import aiohttp

logger = logging.getLogger(__name__)

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://uzum.uz/",
    "Origin": "https://uzum.uz",
    "x-iid": "00000000-0000-0000-0000-000000000001",
}

HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def extract_product_id_from_url(url: str) -> str | None:
    """
    Uzum URL dan product ID ajratish.
    https://uzum.uz/ru/product/tovar-nomi-2855035?skuId=...  → "2855035"
    """
    url = url.strip()
    match = re.search(r'/product/[^/?#]+-(\d{4,})', url)
    if match:
        return match.group(1)
    match = re.search(r'/product/(\d{4,})', url)
    if match:
        return match.group(1)
    match = re.search(r'(\d{6,})', url)
    if match:
        return match.group(1)
    return None


def _extract_prices(payload: dict) -> list[float]:
    """Payload dan barcha narxlarni olish."""
    prices = []
    for sku in (payload.get("skuList") or payload.get("skus") or []):
        for key in ["purchasePrice", "sellPrice", "price", "minSellPrice",
                    "salePrice", "currentPrice", "fullPrice", "cost"]:
            val = sku.get(key)
            if val:
                try:
                    v = float(val)
                    if v > 100:
                        prices.append(v)
                        break
                except Exception:
                    pass
    for key in ["minSellPrice", "price", "sellPrice", "currentPrice",
                "minPrice", "maxPrice", "salePrice"]:
        val = payload.get(key)
        if val:
            try:
                v = float(val)
                if v > 100:
                    prices.append(v)
            except Exception:
                pass
    return list(set(prices))


def _accumulate_price(value, prices: list[float]) -> None:
    """Coerce `value` to float and append it only when it exceeds the threshold (>100)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    if v > 100:
        prices.append(v)


def get_price_from_html(html: str) -> tuple[float, float] | None:
    """
    Extract (min_price, max_price) from a Uzum product page's HTML.

    Sources:
      1) JSON-LD <script type="application/ld+json"> offers: price / lowPrice / highPrice
      2) Embedded state JSON keys: sellPrice / purchasePrice / minSellPrice / price / fullPrice

    Returns None when no plausible price (> 100) is found.
    """
    if not html:
        return None

    prices: list[float] = []

    # 1) JSON-LD offers
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        for node in (data if isinstance(data, list) else [data]):
            offers = node.get("offers") if isinstance(node, dict) else None
            if offers is None:
                continue
            for off in (offers if isinstance(offers, list) else [offers]):
                if not isinstance(off, dict):
                    continue
                for key in ("price", "lowPrice", "highPrice"):
                    _accumulate_price(off.get(key), prices)

    # 2) Embedded state JSON keys (regex over raw HTML — robust to bundling)
    for key in ("sellPrice", "purchasePrice", "minSellPrice", "price", "fullPrice"):
        for m in re.findall(rf'"{key}"\s*:\s*"?(\d[\d.]*)"?', html):
            _accumulate_price(m, prices)

    if not prices:
        return None
    return (min(prices), max(prices))


async def _fetch_product_html(url: str) -> str | None:
    """Single GET of the product page; returns HTML text or None on error/non-200."""
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
            headers=HTML_HEADERS,
        ) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning(f"[COMP] HTML {url} → {resp.status}")
                    return None
                return await resp.text()
    except Exception as e:
        logger.warning(f"[COMP] HTML fetch error: {e}")
        return None


def _title_from_html(html: str) -> str | None:
    """Pure title parse: og:title → <title> → JSON-LD name."""
    if not html:
        return None

    # 1. og:title meta tag
    match = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    if match:
        title = match.group(1).strip()
        logger.info(f"[COMP] og:title: {title[:50]}")
        return title

    # 2. <title> tegi
    match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        title = re.sub(r'\s*[|–-]\s*Uzum.*$', '', title, flags=re.IGNORECASE).strip()
        if title and len(title) > 5:
            logger.info(f"[COMP] title tag: {title[:50]}")
            return title

    # 3. JSON-LD name
    match = re.search(r'"name"\s*:\s*"([^"]{5,})"', html)
    if match:
        title = match.group(1).strip()
        logger.info(f"[COMP] JSON-LD name: {title[:50]}")
        return title

    return None


async def get_product_title_from_html(url: str) -> str | None:
    """Uzum tovar sahifasi HTML dan tovar nomini olish (thin wrapper)."""
    html = await _fetch_product_html(url)
    return _title_from_html(html) if html else None


async def _get_product_from_api(product_id: str) -> dict | None:
    """API dan tovar ma'lumotlarini olish."""
    api_endpoints = [
        f"https://api.uzum.uz/api/product/{product_id}",
        f"https://api.uzum.uz/api/v2/product/{product_id}",
        f"https://api.uzum.uz/api/product/{product_id}?lang=ru",
    ]
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT),
        headers=API_HEADERS
    ) as session:
        for api_url in api_endpoints:
            try:
                await asyncio.sleep(0.5)
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    logger.info(f"[COMP] {api_url} → {resp.status}")
                    if resp.status != 200:
                        continue
                    try:
                        data = await resp.json()
                    except Exception:
                        data = await resp.json(content_type=None)

                    raw_payload = data.get("payload")
                    if raw_payload is None:
                        logger.warning("[COMP] payload=null: tovar yashirilgan")
                        continue
                    payload = raw_payload if isinstance(raw_payload, dict) else data
                    if not isinstance(payload, dict) or not payload:
                        continue

                    prices = _extract_prices(payload)
                    if not prices:
                        logger.warning(f"[COMP] Narx topilmadi: {list(payload.keys())[:10]}")
                        continue

                    min_p, max_p = min(prices), max(prices)
                    title = (payload.get("title") or payload.get("name")
                             or payload.get("productName") or "—")
                    shop = payload.get("shop") or payload.get("seller") or {}
                    shop_name = (
                        shop.get("name") or shop.get("shopName")
                        if isinstance(shop, dict) else str(shop)
                    ) or "—"
                    rating = float(payload.get("rating") or payload.get("avgRating") or 0)
                    reviews = int(payload.get("reviewCount") or payload.get("totalReviews") or 0)

                    return {
                        "title": str(title)[:60],
                        "price": (min_p + max_p) / 2,
                        "min_price": min_p,
                        "max_price": max_p,
                        "shop": shop_name,
                        "rating": rating,
                        "reviews": reviews,
                        "product_id": product_id,
                        "url": "",
                    }
            except asyncio.TimeoutError:
                logger.warning(f"[COMP] Timeout: {api_url}")
            except Exception as e:
                logger.warning(f"[COMP] {api_url}: {e}")
    return None


async def get_product_info_by_url(uzum_url: str) -> dict | None:
    """
    Uzum tovar URL dan ma'lumot olish:
    1. HTML sahifadan nom va narx (bir marta GET)
    2. API dan narx (mavjud bo'lsa ustun)

    price_source: "api" | "html" | "none". Hech qachon handlerga xato ko'tarmaydi.
    """
    product_id = extract_product_id_from_url(uzum_url)
    if not product_id:
        logger.warning(f"[COMP] URL dan ID ajratilmadi: {uzum_url}")
        return None

    logger.info(f"[COMP] Product ID: {product_id}")

    # Fetch the product-page HTML once; derive both title and price from it.
    html = await _fetch_product_html(uzum_url)
    title_from_html = _title_from_html(html) if html else None
    html_prices = get_price_from_html(html) if html else None

    api_data = await _get_product_from_api(product_id)

    if api_data:
        if title_from_html and (not api_data.get("title") or api_data.get("title") == "—"):
            api_data["title"] = title_from_html
        api_min = api_data.get("min_price") or 0
        if api_min > 0:
            # API gave a usable price -> keep it, do not overwrite with HTML.
            api_data["price_source"] = "api"
            api_data.setdefault("html_only", False)
        elif html_prices:
            # API price missing -> fall back to HTML price.
            lo, hi = html_prices
            api_data.update(
                min_price=lo, max_price=hi, price=(lo + hi) / 2,
                price_source="html", html_only=False,
            )
        else:
            api_data["price_source"] = "none"
            api_data["html_only"] = True
            api_data.setdefault("min_price", 0)
            api_data.setdefault("max_price", 0)
        api_data["url"] = uzum_url
        return api_data

    # API failed entirely -> HTML primary (title and/or price).
    if title_from_html or html_prices:
        lo, hi = html_prices if html_prices else (0.0, 0.0)
        return {
            "title": (title_from_html or "Tovar")[:60],
            "price": (lo + hi) / 2,
            "min_price": lo,
            "max_price": hi,
            "shop": "—",
            "rating": 0,
            "reviews": 0,
            "product_id": product_id,
            "url": uzum_url,
            "price_source": "html" if html_prices else "none",
            "html_only": html_prices is None,
        }

    return None


async def check_saved_urls(
    api_key: str,
    my_products: list[dict],
    saved_urls: list[dict],
    lang: str = "ru"
) -> str:
    if not saved_urls:
        if lang == "uz":
            return "📋 Kuzatilayotgan tovarlar yo'q.\n\n🔗 «URL qo'shish» tugmasini bosing."
        return "📋 Нет отслеживаемых товаров.\n\n🔗 Нажмите «Добавить URL»."

    header = "🔍 <b>Narx monitoringi</b>\n\n" if lang == "uz" else "🔍 <b>Мониторинг цен</b>\n\n"
    lines = [header]

    for item in saved_urls:
        product_name = item.get("product_name") or "—"
        uzum_url = item.get("uzum_url") or ""

        my_price = 0.0
        for p in my_products:
            p_title = (p.get("title") or p.get("name") or "").lower()
            pn_lower = product_name.lower()
            p_words = set(p_title.split())
            n_words = set(pn_lower.split())
            if (pn_lower in p_title) or (p_title in pn_lower) or (p_words & n_words):
                for sku in p.get("skuList", [])[:1]:
                    my_price = float(sku.get("price") or sku.get("purchasePrice") or 0)
                break

        info = await get_product_info_by_url(uzum_url)
        await asyncio.sleep(0.5)

        if info:
            market_min = info.get("min_price") or info.get("price") or 0
            rating = info.get("rating", 0)
            reviews = info.get("reviews", 0)
            shop = info.get("shop", "—")

            if my_price > 0 and market_min > 0:
                pct = ((my_price - market_min) / market_min) * 100
                icon = "🟡" if abs(pct) < 3 else ("🟢" if my_price < market_min else "🔴")
                diff_str = f" ({pct:+.0f}%)"
            else:
                icon, diff_str = "⚪", ""

            stars = f" ⭐{rating:.1f}" if rating > 0 else ""
            rev_str = f" ({reviews} отз.)" if reviews > 0 else ""

            if lang == "uz":
                lines.append(
                    f"{icon} <b>{product_name[:30]}</b>\n"
                    f"   💰 Mening: {my_price:,.0f} | Bozor: {market_min:,.0f}{diff_str}\n"
                    f"   🏪 {shop}{stars}{rev_str}"
                )
            else:
                lines.append(
                    f"{icon} <b>{product_name[:30]}</b>\n"
                    f"   💰 Моя: {my_price:,.0f} | Рынок: {market_min:,.0f}{diff_str}\n"
                    f"   🏪 {shop}{stars}{rev_str}"
                )
        else:
            no_data = "Ma'lumot olinmadi" if lang == "uz" else "Данные не получены"
            lines.append(f"❓ <b>{product_name[:30]}</b>\n   {no_data}")
        lines.append("")

    return "\n".join(lines).strip()


def format_single_product_report(
    product_name: str,
    my_price: float,
    info: dict,
    lang: str = "ru"
) -> str:
    market_min = info.get("min_price", 0) or info.get("price", 0)
    market_max = info.get("max_price", 0) or market_min
    rating = info.get("rating", 0)
    reviews = info.get("reviews", 0)
    shop = info.get("shop", "—")
    title = info.get("title", product_name)
    html_only = info.get("html_only", False)

    if lang == "uz":
        lines = [f"✅ <b>Saqlandi: {product_name}</b>", "", f"📦 {title[:50]}"]
        if shop and shop != "—":
            lines.append(f"🏪 {shop}")
        if rating > 0:
            lines.append(f"⭐ {rating:.1f} ({reviews} sharh)")
        if market_min > 0:
            lines += ["", "💰 <b>Narxlar:</b>", f"   Min: {market_min:,.0f} so'm"]
            if market_max > market_min:
                lines.append(f"   Max: {market_max:,.0f} so'm")
            if my_price > 0:
                lines.append(f"   Mening: {my_price:,.0f} so'm")
                pct = ((my_price - market_min) / market_min) * 100
                if pct < -3:
                    lines.append(f"\n✅ Narxingiz bozordan {abs(pct):.0f}% arzon!")
                elif pct > 10:
                    lines.append(f"\n⚠️ Narxingiz bozordan {pct:.0f}% qimmat")
                else:
                    lines.append("\n🟡 Narxingiz bozor bilan teng")
        elif html_only:
            lines.append("\nℹ️ Narx ma'lumoti olinmadi (tovar yashirin bo'lishi mumkin)")
        lines.append("\n📋 «Kuzatilayotganlar» tugmasi orqali tekshiring")
    else:
        lines = [f"✅ <b>Сохранено: {product_name}</b>", "", f"📦 {title[:50]}"]
        if shop and shop != "—":
            lines.append(f"🏪 {shop}")
        if rating > 0:
            lines.append(f"⭐ {rating:.1f} ({reviews} отз.)")
        if market_min > 0:
            lines += ["", "💰 <b>Цены:</b>", f"   Мин: {market_min:,.0f} сум"]
            if market_max > market_min:
                lines.append(f"   Макс: {market_max:,.0f} сум")
            if my_price > 0:
                lines.append(f"   Моя: {my_price:,.0f} сум")
                pct = ((my_price - market_min) / market_min) * 100
                if pct < -3:
                    lines.append(f"\n✅ Ваша цена на {abs(pct):.0f}% ниже рынка!")
                elif pct > 10:
                    lines.append(f"\n⚠️ Ваша цена на {pct:.0f}% выше рынка")
                else:
                    lines.append("\n🟡 Ваша цена на уровне рынка")
        elif html_only:
            lines.append("\nℹ️ Цена не получена (товар может быть скрыт)")
        lines.append("\n📋 Проверяйте через кнопку «Отслеживаемые»")

    return "\n".join(lines)
