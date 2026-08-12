"""ERP 스텁. 감사 검체용이라 실제 ERP는 없다.

부작용은 프로세스 메모리의 append-only 리스트로 흉내낸다. P1에서 이 자리에
IdempotencyGuard(관문 ①)가 붙고, 실제 기록은 Firestore `effects`로 간다.
PO 번호는 인자에서 결정론적으로 파생한다 — 난수도 시계도 쓰지 않는다(R3).
"""

import hashlib

ISSUED_POS: list[dict] = []


def _po_number(vendor_id: str, amount_usd: float, line_item: str) -> str:
    digest = hashlib.sha256(
        f"{vendor_id}|{amount_usd}|{line_item}".encode()
    ).hexdigest()
    return f"PO-{int(digest[:8], 16) % 10000:04d}"


def create_po(vendor_id: str, amount_usd: float, line_item: str) -> dict:
    """Issue a purchase order to a vendor.

    Args:
        vendor_id: Vendor identifier, e.g. "acme-corp".
        amount_usd: Order total in US dollars.
        line_item: What is being ordered.

    Returns:
        dict with po_id, vendor_id, amount_usd, line_item.
    """
    record = {
        "po_id": _po_number(vendor_id, amount_usd, line_item),
        "vendor_id": vendor_id,
        "amount_usd": amount_usd,
        "line_item": line_item,
    }
    ISSUED_POS.append(record)
    return record
