"""메일 스텁. 감사 검체용. 실제로 나가는 메일은 없다.

erp.py 와 같은 원칙: 난수도 시계도 쓰지 않는다(R3). 식별자는 인자에서 파생한다.
"""

import hashlib

SENT: list[dict] = []


def send(to: str, subject: str, body: str) -> dict:
    """Send an email to a vendor contact.

    Args:
        to: Recipient address.
        subject: Subject line.
        body: Message body.

    Returns:
        dict with message_id and to.
    """
    digest = hashlib.sha256(f"{to}|{subject}|{body}".encode()).hexdigest()
    record = {"message_id": f"MSG-{digest[:6].upper()}", "to": to, "subject": subject}
    SENT.append(record)
    return record
