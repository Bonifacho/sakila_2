"""Lógica de reportes de pagos."""
from datetime import datetime, time, timedelta

from app.db import get_connection
from app.repositories import payment_repo


def daily_report(day, page, page_size):
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)
    offset = (page - 1) * page_size
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            rows = payment_repo.payments_by_day(cur, day_start, day_end, page_size, offset)
        finally:
            cur.close()
    items = [
        {
            "payment_id": r["payment_id"],
            "customer_id": r["customer_id"],
            "staff_id": r["staff_id"],
            "rental_id": r["rental_id"],
            "amount": str(r["amount"]),
            "payment_date": r["payment_date"].isoformat(),
        }
        for r in rows
    ]
    return {"day": day.isoformat(), "page": page, "page_size": page_size,
            "count": len(items), "items": items}
