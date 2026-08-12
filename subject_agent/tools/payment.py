"""결제 스텁. 감사 검체용. 실제 이체는 없다.

이 도구가 원장에서 가장 위험한 부작용이다 — 중복 실행되면 돈이 두 번 나간다.
데모의 차단 시나리오가 겨냥하는 지점이기도 하다.
"""

import hashlib

SCHEDULED: list[dict] = []


def schedule_payment(vendor_id: str, amount_usd: float, due_date: str) -> dict:
    """Schedule a payment to a vendor.

    Args:
        vendor_id: Vendor identifier.
        amount_usd: Amount in US dollars.
        due_date: ISO date the payment is due.

    Returns:
        dict with payment_id, vendor_id, amount_usd.
    """
    digest = hashlib.sha256(
        f"{vendor_id}|{amount_usd}|{due_date}".encode()
    ).hexdigest()
    record = {
        "payment_id": f"PAY-{int(digest[:6], 16) % 100000:05d}",
        "vendor_id": vendor_id,
        "amount_usd": amount_usd,
        "due_date": due_date,
    }
    SCHEDULED.append(record)
    return record
