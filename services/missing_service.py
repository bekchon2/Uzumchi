"""
services/missing_service.py
===========================
Yo'qolgan (missing) FBO tovarlarni aniqlash.

Hisoblash mantigi:
  received  = nakladnoylarda qabul qilingan jami (barcha ACCEPTED invoicelar)
  current   = hozir omborda bor (quantityActive per SKU)
  sold      = sotilgan (quantitySold per SKU)
  returned  = qaytib kelgan (quantityReturned per SKU)

  missing = received − current − sold + returned
          = received − (current + sold − returned)

Agar invoice per-SKU ma'lumot bermasa:
  → received ni invoice jami (totalAccepted) dan taxminiy bo'lishtiramiz
  → Yoki faqat "current + sold" dan kelib chiqib "kutilgan" bilan taqqoslashni
    bo'sh nakladnoy bo'lganda skip qilamiz.
"""
import logging
from dataclasses import dataclass, field

from services.uzum_api import get_products, get_invoices, _get, UzumAPIError

logger = logging.getLogger(__name__)


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class MissingItem:
    name: str
    sku_code: str          # sellerItemCode yoki skuId
    barcode: str
    missing_qty: int
    purchase_price: float  # tannarxi (cost)
    compensation: float    # missing_qty × purchase_price


# ─── Invoice items (per-SKU breakdown) ────────────────────────────────────────

async def _get_invoice_items(api_key: str, shop_id: int, invoice_id: int) -> list[dict]:
    """
    Bitta nakladnoy ichidagi tovarlar (per-SKU).
    Endpoint: /v1/shop/{shop_id}/invoice/{invoice_id}/items
    """
    endpoints = [
        f"/v1/shop/{shop_id}/invoice/{invoice_id}/items",
        f"/v1/invoice/{invoice_id}/items",
        f"/v1/shop/{shop_id}/invoice/{invoice_id}",
    ]
    for ep in endpoints:
        try:
            data = await _get(ep, api_key)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                items = (data.get("items") or data.get("invoiceItems")
                         or data.get("skuList") or [])
                if items:
                    return items
        except UzumAPIError:
            pass
        except Exception as e:
            logger.debug(f"invoice items {ep}: {e}")
    return []


async def _build_received_map(api_key: str, shop_id: int,
                              invoices: list[dict]) -> dict[str, int]:
    """
    Har bir SKU uchun ombor tomonidan qabul qilingan jami miqdor.
    {sku_id_str → total_received_qty}
    """
    received: dict[str, int] = {}

    for inv in invoices:
        inv_id = inv.get("id")
        if not inv_id:
            continue
        items = await _get_invoice_items(api_key, shop_id, inv_id)
        for item in items:
            # turli field nomlari
            sku_id = str(
                item.get("skuId") or item.get("sku_id") or
                item.get("productSku") or item.get("id") or ""
            )
            qty = int(
                item.get("acceptedQuantity") or item.get("accepted") or
                item.get("quantity") or item.get("qty") or 0
            )
            if sku_id and qty:
                received[sku_id] = received.get(sku_id, 0) + qty

    return received


# ─── Main function ─────────────────────────────────────────────────────────────

async def find_missing_products(api_key: str, shop_id: int) -> list[MissingItem]:
    """
    Haqiqiy yo'qolgan FBO tovarlarni hisoblaydi.
    Qaytadi: [MissingItem, ...]  — bo'sh list = hech narsa yo'qolmagan.
    """
    # 1. Barcha produktlarni olish
    products = await get_products(api_key, shop_id)

    # 2. Qabul qilingan nakladnoylarni olish
    invoices = await get_invoices(api_key, shop_id)
    accepted_invoices = [
        inv for inv in invoices
        if _invoice_accepted(inv)
    ]
    logger.info(f"Invoices: jami={len(invoices)}, accepted={len(accepted_invoices)}")

    # 3. Per-SKU qabul qilingan miqdorlarni olish
    received_map = await _build_received_map(api_key, shop_id, accepted_invoices)
    logger.info(f"Received map: {len(received_map)} SKU")

    # 4. Har bir SKU uchun hisoblash
    results: list[MissingItem] = []

    for product in products:
        name = product.get("title") or product.get("name") or "—"
        for sku in product.get("skuList", []):
            sku_id = str(sku.get("skuId") or sku.get("id") or "")
            sku_code = str(sku.get("sellerItemCode") or sku_id)
            barcode = str(sku.get("barcode") or sku.get("skuBarcode") or "—")

            current  = int(sku.get("quantityActive") or 0)
            sold     = int(sku.get("quantitySold") or 0)
            returned = int(sku.get("quantityReturned") or 0)
            price    = float(sku.get("purchasePrice") or sku.get("price") or 0)

            received = received_map.get(sku_id, 0)

            if received > 0:
                # To'liq formula: received - current - sold + returned
                missing = received - current - sold + returned
            else:
                # Invoice per-SKU ma'lumot yo'q — alternativ usul
                # Uzum ba'zan quantityDefect yoki quantityLost fieldlarini beradi
                missing = int(
                    sku.get("quantityDefect") or
                    sku.get("quantityLost") or
                    sku.get("quantityMissing") or 0
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
                logger.info(
                    f"  ❗ {name[:40]} | SKU={sku_code} | "
                    f"received={received} current={current} sold={sold} "
                    f"returned={returned} → MISSING={missing}"
                )

    logger.info(f"Yo'qolgan tovarlar: {len(results)} ta")
    return results


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
        if lang == "uz":
            lines.append(
                f"{i}. <b>{item.name[:50]}</b>\n"
                f"   🔖 SKU: <code>{item.sku_code}</code>\n"
                f"   🔢 Yo'qolgan: <b>{item.missing_qty} dona</b>\n"
                f"   💰 Kompensatsiya: <b>{item.compensation:,.0f} so'm</b>"
            )
        else:
            lines.append(
                f"{i}. <b>{item.name[:50]}</b>\n"
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
