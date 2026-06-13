"""
Uzum Seller OpenAPI wrapper.
Base URL: https://api-seller.uzum.uz/api/seller-openapi
Auth: Authorization: <api_key>  ← Bearer prefikssiz!
"""
import asyncio
import logging
import datetime
import ssl
import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://api-seller.uzum.uz/api/seller-openapi"

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class UzumAPIError(Exception):
    pass

class UzumAuthError(UzumAPIError):
    pass

class UzumRateLimitError(UzumAPIError):
    pass


async def _get(endpoint: str, api_key: str, params: dict = None, retry: int = 2):
    url = BASE_URL + endpoint
    headers = {"Authorization": api_key}
    await asyncio.sleep(0.3)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT)) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            logger.info(f"GET {endpoint} → {resp.status}")
            if resp.status == 200:
                return await resp.json()
            elif resp.status in (401, 403):
                raise UzumAuthError(f"Auth error {resp.status}: {endpoint}")
            elif resp.status == 429:
                if retry > 0:
                    await asyncio.sleep(2)
                    return await _get(endpoint, api_key, params, retry - 1)
                raise UzumRateLimitError("Rate limit exceeded")
            else:
                text = await resp.text()
                raise UzumAPIError(f"HTTP {resp.status}: {text[:300]}")


async def _post(endpoint: str, api_key: str, payload: dict = None, retry: int = 2):
    url = BASE_URL + endpoint
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    await asyncio.sleep(0.3)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT)) as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 429:
                if retry > 0:
                    await asyncio.sleep(2)
                    return await _post(endpoint, api_key, payload, retry - 1)
                raise UzumRateLimitError("Rate limit exceeded")
            else:
                text = await resp.text()
                raise UzumAPIError(f"HTTP {resp.status}: {text[:200]}")


# ─── Shops ────────────────────────────────────────────────────────────────────

async def get_shops(api_key: str) -> list[dict]:
    data = await _get("/v1/shops", api_key)
    if isinstance(data, list):
        return data
    return data.get("shops", [])


# ─── Products ─────────────────────────────────────────────────────────────────

async def get_products(api_key: str, shop_id: int) -> list[dict]:
    """
    Mahsulotlar ro'yxati — barcha SKU lari bilan.
    GET /v1/product/shop/{shopId}
    """
    params = {"size": 100, "page": 0}
    try:
        data = await _get(f"/v1/product/shop/{shop_id}", api_key, params)
    except UzumAPIError:
        data = await _get(f"/v1/product/shop/{shop_id}", api_key)

    if isinstance(data, list):
        return data
    return (
        data.get("productList")
        or data.get("products")
        or data.get("payload", {}).get("products", [])
        or []
    )


def calc_total_qty(product: dict) -> int:
    """Mahsulotning BARCHA SKU lari bo'yicha jami qoldiq."""
    total = 0
    for sku in product.get("skuList", []):
        total += int(sku.get("quantityActive") or 0)
    return total


def format_product_skus(product: dict, lang: str = "ru") -> str:
    """
    Mahsulotni barcha SKU variantlari bilan chiroyli ko'rsatish.
    Agar 1 ta SKU bo'lsa oddiy, ko'p bo'lsa har birini ko'rsatadi.
    """
    name = product.get("title") or product.get("name") or "—"
    skus = product.get("skuList", [])
    if not skus:
        return f"• {name[:50]}"

    total_qty = sum(int(s.get("quantityActive") or 0) for s in skus)

    from utils.helpers import stock_icon, safe_float, safe_int, short_name
    icon = stock_icon(total_qty)

    if len(skus) == 1:
        sku = skus[0]
        qty = safe_int(sku.get("quantityActive"))
        price = safe_float(sku.get("price") or sku.get("purchasePrice"))
        avg = safe_float(sku.get("avgdsales"))
        days = safe_int(sku.get("forecastOutOfStock", 9999))
        days_str = str(days) if days < 9999 else "∞"
        if lang == "uz":
            return (
                f"{icon} <b>{short_name(name, 45)}</b>\n"
                f"   📊 Qoldiq: <b>{qty}</b> dona | 💰 {price:,.0f} so'm\n"
                f"   📈 Kunlik: {avg:.1f} | ⏳ {days_str} kun"
            )
        return (
            f"{icon} <b>{short_name(name, 45)}</b>\n"
            f"   📊 Остаток: <b>{qty}</b> шт. | 💰 {price:,.0f} сум\n"
            f"   📈 В день: {avg:.1f} | ⏳ {days_str} дн."
        )
    else:
        # Ko'p SKU — har birini alohida ko'rsatish
        lines = [f"{icon} <b>{short_name(name, 45)}</b> (jami: {total_qty} dona)" if lang == "uz"
                 else f"{icon} <b>{short_name(name, 45)}</b> (всего: {total_qty} шт.)"]
        for sku in skus:
            qty = int(sku.get("quantityActive") or 0)
            price = float(sku.get("price") or sku.get("purchasePrice") or 0)
            # SKU xususiyatlarini olish
            char_values = []
            for cv in (sku.get("characteristics") or sku.get("charValues") or []):
                if isinstance(cv, dict):
                    val = cv.get("value") or cv.get("name") or ""
                    if val:
                        char_values.append(str(val))
            sku_name = " / ".join(char_values) if char_values else f"SKU {sku.get('id', '?')}"
            sku_icon = stock_icon(qty)
            lines.append(f"   {sku_icon} {sku_name}: <b>{qty}</b> шт. | {price:,.0f} сум" if lang == "ru"
                         else f"   {sku_icon} {sku_name}: <b>{qty}</b> dona | {price:,.0f} so'm")
        return "\n".join(lines)


# ─── Orders ───────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(datetime.datetime.now().timestamp() * 1000)


def _days_ago_ms(days: int) -> int:
    dt = datetime.datetime.now() - datetime.timedelta(days=days)
    return int(dt.timestamp() * 1000)


async def get_finance_orders(
    api_key: str,
    date_from: int = None,
    date_to: int = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """GET /v1/finance/orders"""
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()
    params = {"dateFrom": date_from, "dateTo": date_to, "limit": limit, "offset": offset}
    return await _get("/v1/finance/orders", api_key, params)


async def get_fbs_orders(
    api_key: str,
    date_from: int = None,
    date_to: int = None,
) -> list[dict]:
    """
    Buyurtmalar. Bir nechta endpoint sinab ko'riladi:
    1. /v2/fbs/orders (FBS)
    2. /v1/finance/orders (Finance)
    3. /v1/order (umumiy)
    """
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()

    # 1. FBS v2
    try:
        params = {"dateFrom": date_from, "dateTo": date_to, "limit": 100, "offset": 0}
        data = await _get("/v2/fbs/orders", api_key, params)
        orders = (
            data.get("payload", {}).get("orders", [])
            or data.get("orders", [])
            or (data if isinstance(data, list) else [])
        )
        if orders or isinstance(orders, list):
            logger.info(f"FBS v2 orders: {len(orders)}")
            return orders
    except (UzumAuthError, UzumAPIError) as e:
        logger.warning(f"FBS v2 failed: {e}")

    # 2. Finance orders
    try:
        fin = await get_finance_orders(api_key, date_from, date_to)
        items = fin.get("orderItems", []) or []
        logger.info(f"Finance orders: {len(items)}")
        return items
    except Exception as e:
        logger.warning(f"Finance orders failed: {e}")

    # 3. Umumiy order endpoint
    try:
        params = {"dateFrom": date_from, "dateTo": date_to, "limit": 100}
        data = await _get("/v1/order", api_key, params)
        orders = (
            data.get("orders", [])
            or data.get("orderList", [])
            or (data if isinstance(data, list) else [])
        )
        logger.info(f"v1/order: {len(orders)}")
        return orders
    except Exception as e:
        logger.warning(f"v1/order failed: {e}")

    return []


async def get_fbs_orders_period(api_key: str, days: int = 7) -> list[dict]:
    return await get_fbs_orders(
        api_key,
        date_from=_days_ago_ms(days),
        date_to=_now_ms(),
    )


# ─── Invoices ─────────────────────────────────────────────────────────────────

async def get_invoices(api_key: str, shop_id: int) -> list[dict]:
    try:
        data = await _get(f"/v1/shop/{shop_id}/invoice", api_key)
        if isinstance(data, list):
            return data
        return data.get("invoices") or data.get("payload", []) or []
    except UzumAPIError as e:
        logger.warning(f"get_invoices error: {e}")
        return []


# ─── Returns ──────────────────────────────────────────────────────────────────

async def get_returns(api_key: str, date_from: int = None, date_to: int = None) -> list[dict]:
    """
    Qaytarmalar. Bir nechta endpoint sinab ko'riladi.
    """
    if date_from is None:
        date_from = _days_ago_ms(30)
    if date_to is None:
        date_to = _now_ms()

    params = {"dateFrom": date_from, "dateTo": date_to}

    # 1. /v1/return
    try:
        data = await _get("/v1/return", api_key, params)
        items = (
            data.get("payload", [])
            or data.get("returns", [])
            or data.get("content", [])
            or (data if isinstance(data, list) else [])
        )
        logger.info(f"Returns /v1/return: {len(items)} items, raw keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
        if items:
            return items
    except Exception as e:
        logger.warning(f"get_returns /v1/return error: {e}")

    # 2. /v2/return
    try:
        data = await _get("/v2/return", api_key, params)
        items = (
            data.get("payload", [])
            or data.get("returns", [])
            or (data if isinstance(data, list) else [])
        )
        logger.info(f"Returns /v2/return: {len(items)}")
        return items
    except Exception as e:
        logger.warning(f"get_returns /v2/return error: {e}")

    return []


async def get_today_returns(api_key: str) -> list[dict]:
    return await get_returns(api_key, date_from=_days_ago_ms(1))


# ─── Finance expenses ─────────────────────────────────────────────────────────

async def get_expenses(api_key: str, date_from: int = None, date_to: int = None) -> dict | None:
    if date_from is None:
        date_from = _days_ago_ms(30)
    if date_to is None:
        date_to = _now_ms()
    params = {"dateFrom": date_from, "dateTo": date_to}
    try:
        return await _get("/v1/finance/expenses", api_key, params)
    except UzumAuthError:
        return None
    except Exception:
        return None


# ─── Price update ─────────────────────────────────────────────────────────────

async def send_price_data(api_key: str, shop_id: int, price_data: list[dict]) -> dict:
    return await _post(f"/v1/product/{shop_id}/sendPriceData", api_key, {"priceData": price_data})


# ─── Helper: orders summary ───────────────────────────────────────────────────

def summarize_orders(orders: list[dict]) -> dict:
    total = len(orders)
    delivered = sum(1 for o in orders if o.get("status") == "DELIVERED")
    cancelled = sum(1 for o in orders if o.get("status") == "CANCELLED")
    processing = sum(1 for o in orders if o.get("status") == "PROCESSING")
    shipped = sum(1 for o in orders if o.get("status") == "SHIPPED")
    revenue = sum(
        float(o.get("finalPrice", 0) or 0) for o in orders if o.get("status") == "DELIVERED"
    )
    return {
        "total": total,
        "delivered": delivered,
        "cancelled": cancelled,
        "processing": processing,
        "shipped": shipped,
        "revenue": revenue,
    }
