"""
services/missing_service.py
===========================
Yo'qolgan (missing) FBO tovarlarni aniqlash.

Hisoblash mantiqi (to'g'ri versiya):
  Uzum API da LOST statusli FBO postinglar mavjud bo'lsa → ulardan olamiz.
  Bo'lmasa → product SKU larida quantityDefect/quantityLost fieldlarini ko'ramiz.
  Bo'lmasa → invoice vs current stock taqqoslaymiz.

Real test ma'lumoti:
  seller.uzum.plus saytida: missingCount=2, returnAmount=29848 so'm
  Demak: 1 ta tovar (paraşüt), 2 dona, narxi 14924 so'm/dona
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from services.uzum_api import _get, _post, get_products, get_invoices, UzumAPIError, UzumAuthError

logger = logging.getLogger(__name__)


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class MissingItem:
    name: str
    sku_code: str
    barcode: str
    missing_qty: int
    purchase_price: float
    compensation: float


# ─── Usul 1: LOST statusli FBO postinglardan ─────────────────────────────────

async def _get_lost_fbo_postings(api_key: str, shop_id: int, days: int = 180) -> list[dict]:
    """
    LOST / MISSING statusli FBO buyurtmalarni Uzum API dan oladi.
    Bir nechta endpoint varianti sinab ko'riladi.
    """
    date_to   = datetime.now()
    date_from = date_to - timedelta(days=days)

    # milliseconds
    date_from_ms = int(date_from.timestamp() * 1000)
    date_to_ms   = int(date_to.timestamp() * 1000)

    # ISO format
    date_from_iso = date_from.strftime("%Y-%m-%dT00:00:00.000Z")
    date_to_iso   = date_to.strftime("%Y-%m-%dT23:59:59.000Z")

    # Sinab ko'riladigan endpointlar va payload variantlari
    attempts = [
        # Variant 1: POST /v1/posting/fbo/list
        {
            "method": "POST",
            "endpoint": "/v1/posting/fbo/list",
            "payload": {
                "filter": {"status": "LOST", "since": date_from_iso, "to": date_to_iso},
                "limit": 100, "offset": 0,
            },
            "extractor": lambda d: d.get("result", d.get("postings", d.get("items", [])))
        },
        # Variant 2: POST bilan "missing" status
        {
            "method": "POST",
            "endpoint": "/v1/posting/fbo/list",
            "payload": {
                "filter": {"status": "MISSING", "since": date_from_iso, "to": date_to_iso},
                "limit": 100, "offset": 0,
            },
            "extractor": lambda d: d.get("result", d.get("postings", d.get("items", [])))
        },
        # Variant 3: GET /v1/posting/fbo bilan params
        {
            "method": "GET",
            "endpoint": f"/v1/shop/{shop_id}/posting/fbo",
            "params": {"status": "LOST", "dateFrom": date_from_ms, "dateTo": date_to_ms, "limit": 100},
            "extractor": lambda d: d.get("postings", d.get("result", d if isinstance(d, list) else []))
        },
        # Variant 4: /v2/fbo/orders LOST status
        {
            "method": "GET",
            "endpoint": "/v2/fbo/orders",
            "params": {"status": "LOST", "dateFrom": date_from_ms, "dateTo": date_to_ms, "limit": 100},
            "extractor": lambda d: d.get("payload", {}).get("orders", d.get("orders", d if isinstance(d, list) else []))
        },
    ]

    for attempt in attempts:
        endpoint = attempt["endpoint"]
        try:
            if attempt["method"] == "POST":
                data = await _post(endpoint, api_key, attempt["payload"])
            else:
                data = await _get(endpoint, api_key, attempt.get("params"))

            postings = attempt["extractor"](data)
            if postings and isinstance(postings, list):
                logger.info(f"[MISSING] ✅ {endpoint}: {len(postings)} ta LOST posting")
                return postings
            else:
                logger.info(f"[MISSING] {endpoint}: bo'sh javob")

        except UzumAuthError:
            logger.warning(f"[MISSING] {endpoint}: 403 ruxsat yo'q")
        except UzumAPIError as e:
            logger.warning(f"[MISSING] {endpoint}: API xato: {e}")
        except Exception as e:
            logger.warning(f"[MISSING] {endpoint}: {e}")

    return []


def _parse_postings_to_items(postings: list[dict]) -> list[MissingItem]:
    """LOST postinglardan MissingItem ro'yxatini tuzadi."""
    product_map: dict[str, dict] = {}

    for posting in postings:
        products = posting.get("products", posting.get("items", []))
        for p in products:
            name     = p.get("name", p.get("title", "Noma'lum"))
            sku_code = str(p.get("offer_id", p.get("sku", p.get("skuId", "-"))))
            barcode  = str(p.get("barcode", "-"))
            qty      = int(p.get("quantity", 1))
            price    = float(p.get("price", p.get("purchasePrice", 0)))

            key = sku_code if sku_code != "-" else name[:40]
            if key not in product_map:
                product_map[key] = {
                    "name": name, "sku_code": sku_code,
                    "barcode": barcode, "qty": 0, "price": price,
                }
            product_map[key]["qty"] += qty
            if price > 0:
                product_map[key]["price"] = price

    result = []
    for v in product_map.values():
        comp = v["qty"] * v["price"]
        result.append(MissingItem(
            name=v["name"],
            sku_code=v["sku_code"],
            barcode=v["barcode"],
            missing_qty=v["qty"],
            purchase_price=v["price"],
            compensation=comp,
        ))

    return sorted(result, key=lambda x: x.compensation, reverse=True)


# ─── Usul 2: Product SKU fieldlaridan ────────────────────────────────────────

async def _get_missing_from_products(api_key: str, shop_id: int) -> list[MissingItem]:
    """
    Product SKU larida quantityLost / quantityDefect / quantityMissing
    fieldlari orqali yo'qolgan tovarlarni topadi.
    """
    try:
        products = await get_products(api_key, shop_id)
    except Exception as e:
        logger.warning(f"[MISSING] get_products xato: {e}")
        return []

    results = []
    for product in products:
        name = product.get("title") or product.get("name") or "—"
        for sku in product.get("skuList", []):
            sku_id   = str(sku.get("skuId") or sku.get("id") or "")
            sku_code = str(sku.get("sellerItemCode") or sku_id)
            barcode  = str(sku.get("barcode") or sku.get("skuBarcode") or "—")
            price    = float(sku.get("purchasePrice") or sku.get("costPrice") or sku.get("price") or 0)

            # Yo'qolgan miqdor — turli field nomlarini tekshiramiz
            missing = int(
                sku.get("quantityLost") or
                sku.get("quantityDefect") or
                sku.get("quantityMissing") or
                sku.get("lostQuantity") or
                sku.get("defectQuantity") or 0
            )

            if missing > 0:
                results.append(MissingItem(
                    name=name,
                    sku_code=sku_code,
                    barcode=barcode,
                    missing_qty=missing,
                    purchase_price=price,
                    compensation=missing * price,
                ))
                logger.info(f"[MISSING] SKU field: {name[:40]} | qty={missing}")

    return results


# ─── Usul 3: Invoice vs stock taqqoslash ─────────────────────────────────────

async def _get_missing_from_invoice(api_key: str, shop_id: int) -> list[MissingItem]:
    """
    Qabul qilingan nakladnoylar vs hozirgi stock taqqoslab yo'qolganlarni topadi.
    received - (current + sold - returned) = missing
    """
    try:
        products = await get_products(api_key, shop_id)
        invoices = await get_invoices(api_key, shop_id)
    except Exception as e:
        logger.warning(f"[MISSING] invoice usul xato: {e}")
        return []

    # Faqat ACCEPTED nakladnoylar
    accepted = [inv for inv in invoices if _invoice_accepted(inv)]
    if not accepted:
        logger.info("[MISSING] Invoice usul: ACCEPTED nakladnoy topilmadi")
        return []

    # Per-SKU qabul qilingan miqdor
    received_map: dict[str, int] = {}
    for inv in accepted:
        # Invoice ichidagi tovarlar — turli field variantlari
        items = (inv.get("items") or inv.get("invoiceItems") or
                 inv.get("skuList") or [])
        total_accepted = int(inv.get("totalAccepted") or inv.get("acceptedQuantity") or 0)

        for item in items:
            sku_id = str(
                item.get("skuId") or item.get("sku_id") or
                item.get("productSku") or item.get("id") or ""
            )
            qty = int(
                item.get("acceptedQuantity") or item.get("accepted") or
                item.get("quantity") or item.get("qty") or 0
            )
            if sku_id and qty:
                received_map[sku_id] = received_map.get(sku_id, 0) + qty

    if not received_map:
        logger.info("[MISSING] Invoice usul: per-SKU ma'lumot yo'q")
        return []

    results = []
    for product in products:
        name = product.get("title") or product.get("name") or "—"
        for sku in product.get("skuList", []):
            sku_id   = str(sku.get("skuId") or sku.get("id") or "")
            sku_code = str(sku.get("sellerItemCode") or sku_id)
            barcode  = str(sku.get("barcode") or "—")
            price    = float(sku.get("purchasePrice") or sku.get("price") or 0)

            received = received_map.get(sku_id, 0)
            if received == 0:
                continue

            current  = int(sku.get("quantityActive") or 0)
            sold     = int(sku.get("quantitySold") or 0)
            returned = int(sku.get("quantityReturned") or 0)

            missing = received - current - sold + returned
            if missing > 0:
                results.append(MissingItem(
                    name=name,
                    sku_code=sku_code,
                    barcode=barcode,
                    missing_qty=missing,
                    purchase_price=price,
                    compensation=missing * price,
                ))
                logger.info(
                    f"[MISSING] Invoice: {name[:40]} | "
                    f"received={received} current={current} sold={sold} "
                    f"returned={returned} → MISSING={missing}"
                )

    return results


# ─── Asosiy funksiya ──────────────────────────────────────────────────────────

async def find_missing_products(api_key: str, shop_id: int) -> list[MissingItem]:
    """
    Yo'qolgan FBO tovarlarni 3 usulda izlaydi (ketma-ket fallback):
      1. LOST statusli FBO postinglar (eng ishonchli)
      2. Product SKU fieldlari (quantityLost va h.k.)
      3. Invoice vs stock taqqoslash

    Qaytadi: [MissingItem, ...]
    """
    # Usul 1: LOST postinglar
    logger.info("[MISSING] Usul 1: LOST postinglar...")
    postings = await _get_lost_fbo_postings(api_key, shop_id, days=180)
    if postings:
        items = _parse_postings_to_items(postings)
        if items:
            logger.info(f"[MISSING] Usul 1 muvaffaqiyatli: {len(items)} ta tovar")
            return items

    # Usul 2: Product SKU fieldlari
    logger.info("[MISSING] Usul 2: Product SKU fieldlari...")
    items = await _get_missing_from_products(api_key, shop_id)
    if items:
        logger.info(f"[MISSING] Usul 2 muvaffaqiyatli: {len(items)} ta tovar")
        return items

    # Usul 3: Invoice vs stock
    logger.info("[MISSING] Usul 3: Invoice vs stock...")
    items = await _get_missing_from_invoice(api_key, shop_id)
    if items:
        logger.info(f"[MISSING] Usul 3 muvaffaqiyatli: {len(items)} ta tovar")
        return items

    logger.info("[MISSING] Hech qaysi usul natija bermadi - yo'qolgan tovar topilmadi")
    return []


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _invoice_accepted(inv: dict) -> bool:
    status_obj = inv.get("invoiceStatus", {})
    if isinstance(status_obj, dict):
        val = status_obj.get("value", "")
    else:
        val = str(status_obj)
    return val.upper() == "ACCEPTED"


def format_missing_list(items: list[MissingItem], lang: str, shop_name: str) -> str:
    """Bot xabar matni uchun yo'qolgan tovarlar ro'yxati."""
    if not items:
        if lang == "uz":
            return (
                f"✅ <b>Yo'qolgan tovarlar topilmadi</b>\n"
                f"Do'kon: <b>{shop_name}</b>\n\n"
                "Barcha tovarlar hisobida — kompensatsiya talab qilish shart emas."
            )
        return (
            f"✅ <b>Потерянных товаров не обнаружено</b>\n"
            f"Магазин: <b>{shop_name}</b>\n\n"
            "Все товары в наличии — требовать компенсацию не нужно."
        )

    total_qty = sum(i.missing_qty for i in items)
    total_sum = sum(i.compensation for i in items)

    lines = []
    if lang == "uz":
        lines.append(f"📦 <b>Yo'qolgan tovarlar hisoboti</b>")
        lines.append(f"🏪 Do'kon: <b>{shop_name}</b>  |  Ombor: <b>FBO</b>\n")
        lines.append("🔍 <b>Yo'qolgan tovarlar:</b>")
    else:
        lines.append(f"📦 <b>Отчёт по потерянным товарам</b>")
        lines.append(f"🏪 Магазин: <b>{shop_name}</b>  |  Склад: <b>FBO</b>\n")
        lines.append("🔍 <b>Потерянные товары:</b>")

    for i, item in enumerate(items, 1):
        title = item.name[:50] + ("…" if len(item.name) > 50 else "")
        if lang == "uz":
            lines.append(
                f"{i}. <b>{title}</b>\n"
                f"   🔖 SKU: <code>{item.sku_code}</code>\n"
                f"   🔢 Yo'qolgan: <b>{item.missing_qty} dona</b>\n"
                f"   💰 Kompensatsiya: <b>{item.compensation:,.0f} so'm</b>"
            )
        else:
            lines.append(
                f"{i}. <b>{title}</b>\n"
                f"   🔖 SKU: <code>{item.sku_code}</code>\n"
                f"   🔢 Потеряно: <b>{item.missing_qty} шт.</b>\n"
                f"   💰 Компенсация: <b>{item.compensation:,.0f} сум</b>"
            )

    lines.append("─" * 30)
    if lang == "uz":
        lines.append(f"📊 <b>Jami:</b> {total_qty} dona")
        lines.append(f"💵 <b>Umumiy kompensatsiya: {total_sum:,.0f} so'm</b>")
    else:
        lines.append(f"📊 <b>Итого:</b> {total_qty} шт.")
        lines.append(f"💵 <b>Общая компенсация: {total_sum:,.0f} сум</b>")

    return "\n".join(lines)
