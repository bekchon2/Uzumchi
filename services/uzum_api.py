"""
Uzum Seller OpenAPI wrapper.
Base URL: https://api-seller.uzum.uz/api/seller-openapi
Auth: Authorization: <api_key>  ← Bearer prefikssiz!
"""
import asyncio
import logging
import datetime
import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://api-seller.uzum.uz/api/seller-openapi"


class UzumAPIError(Exception):
    pass


class UzumAuthError(UzumAPIError):
    pass


class UzumRateLimitError(UzumAPIError):
    pass


async def _get(endpoint: str, api_key: str, params: dict = None, retry: int = 2):
    url = BASE_URL + endpoint
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    await asyncio.sleep(0.3)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 401 or resp.status == 403:
                raise UzumAuthError(f"Auth error {resp.status}: {endpoint}")
            elif resp.status == 429:
                if retry > 0:
                    logger.warning("Rate limited (429), retrying in 2s...")
                    await asyncio.sleep(2)
                    return await _get(endpoint, api_key, params, retry - 1)
                raise UzumRateLimitError("Rate limit exceeded")
            else:
                text = await resp.text()
                raise UzumAPIError(f"HTTP {resp.status}: {text[:200]}")


async def _post(endpoint: str, api_key: str, payload: dict = None, retry: int = 2):
    url = BASE_URL + endpoint
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    await asyncio.sleep(0.3)
    async with aiohttp.ClientSession() as session:
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
    """Do'konlar ro'yxati → [{"id": 116973, "name": "JoyKid"}]"""
    data = await _get("/v1/shops", api_key)
    if isinstance(data, list):
        return data
    return data.get("shops", [])


# ─── Products ─────────────────────────────────────────────────────────────────

async def get_products(api_key: str, shop_id: int) -> list[dict]:
    """Mahsulotlar ro'yxati → productList"""
    data = await _get(f"/v1/product/shop/{shop_id}", api_key)
    return data.get("productList", [])


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
    """Moliyaviy buyurtmalar → {"orderItems": [], "totalElements": 0}"""
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()
    params = {
        "dateFrom": date_from,
        "dateTo": date_to,
        "limit": limit,
        "offset": offset,
    }
    return await _get("/v1/finance/orders", api_key, params)


async def get_fbs_orders(
    api_key: str,
    date_from: int = None,
    date_to: int = None,
) -> list[dict]:
    """FBS buyurtmalar → orders list"""
    if date_from is None:
        date_from = _days_ago_ms(1)
    if date_to is None:
        date_to = _now_ms()
    params = {"dateFrom": date_from, "dateTo": date_to}
    data = await _get("/v2/fbs/orders", api_key, params)
    return data.get("payload", {}).get("orders", [])


async def get_fbs_orders_period(api_key: str, days: int = 7) -> list[dict]:
    return await get_fbs_orders(
        api_key,
        date_from=_days_ago_ms(days),
        date_to=_now_ms(),
    )


# ─── Invoices ─────────────────────────────────────────────────────────────────

async def get_invoices(api_key: str, shop_id: int) -> list[dict]:
    """Nakładnoylar → [{"id":..., "dateAccepted":..., "invoiceStatus":...}]"""
    data = await _get(f"/v1/shop/{shop_id}/invoice", api_key)
    if isinstance(data, list):
        return data
    return data.get("invoices", [])


# ─── Returns ──────────────────────────────────────────────────────────────────

async def get_returns(api_key: str, date_from: int = None, date_to: int = None) -> list[dict]:
    """Qaytarmalar → payload list"""
    if date_from is None:
        date_from = _days_ago_ms(30)
    if date_to is None:
        date_to = _now_ms()
    params = {"dateFrom": date_from, "dateTo": date_to}
    data = await _get("/v1/return", api_key, params)
    return data.get("payload", [])


async def get_today_returns(api_key: str) -> list[dict]:
    return await get_returns(api_key, date_from=_days_ago_ms(1))


# ─── Finance expenses ─────────────────────────────────────────────────────────

async def get_expenses(
    api_key: str, date_from: int = None, date_to: int = None
) -> dict | None:
    """Xarajatlar (403 qaytarishi mumkin)"""
    if date_from is None:
        date_from = _days_ago_ms(30)
    if date_to is None:
        date_to = _now_ms()
    params = {"dateFrom": date_from, "dateTo": date_to}
    try:
        return await _get("/v1/finance/expenses", api_key, params)
    except UzumAuthError:
        logger.warning("Expenses endpoint: access denied (403)")
        return None


# ─── Price update ─────────────────────────────────────────────────────────────

async def send_price_data(api_key: str, shop_id: int, price_data: list[dict]) -> dict:
    """Narx o'zgartirish"""
    return await _post(
        f"/v1/product/{shop_id}/sendPriceData", api_key, {"priceData": price_data}
    )


# ─── Helper: orders summary ───────────────────────────────────────────────────

def summarize_orders(orders: list[dict]) -> dict:
    """FBS orders dan qisqa statistika chiqarish."""
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
