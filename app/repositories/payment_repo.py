"""Repositorio de reportes de pagos (tabla de volumen payment_big)."""


def payments_by_day(cur, day_start, day_end, limit, offset):
    # Condición SARGABLE (rango sobre la columna, sin funciones) y columnas explícitas.
    cur.execute(
        "SELECT payment_id, customer_id, staff_id, rental_id, amount, payment_date "
        "FROM payment_big "
        "WHERE payment_date >= %s AND payment_date < %s "
        "ORDER BY payment_date, payment_id "
        "LIMIT %s OFFSET %s",
        (day_start, day_end, limit, offset),
    )
    return cur.fetchall()
