from datetime import datetime
import db

def calc_slot(new_expiry: datetime) -> int:
    """
    FEFO(First Expired First Out) 기반 슬롯 번호 계산.
    유통기한이 짧을수록 앞 번호.

    예) 저장된 식품 유통기한: [2025.03.01, 2025.05.10]
        새 식품 유통기한: 2025.04.15
        → 슬롯 2 반환 (2025.03.01 다음)
    """
    items = db.get_stored_items_by_expiry()  # 유통기한 오름차순
    slot  = 1
    for item in items:
        item_expiry = datetime.strptime(item["expired_date"], "%Y-%m-%d")
        if new_expiry > item_expiry:
            slot += 1
        else:
            break
    return slot
