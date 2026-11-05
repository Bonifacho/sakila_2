"""Repositorio de alquileres y pagos. SQL parametrizado; sin commit."""

_RENTAL_COLUMNS = "rental_id, rental_date, inventory_id, customer_id, return_date, staff_id"


def insert_rental(cur, inventory_id, customer_id, staff_id):
    cur.execute(
        "INSERT INTO rental (rental_date, inventory_id, customer_id, staff_id) "
        "VALUES (NOW(), %s, %s, %s)",
        (inventory_id, customer_id, staff_id),
    )
    return cur.lastrowid


def insert_payment(cur, customer_id, staff_id, rental_id, amount):
    cur.execute(
        "INSERT INTO payment (customer_id, staff_id, rental_id, amount, payment_date) "
        "VALUES (%s, %s, %s, %s, NOW())",
        (customer_id, staff_id, rental_id, amount),
    )
    return cur.lastrowid


def get_rental(cur, rental_id):
    cur.execute(f"SELECT {_RENTAL_COLUMNS} FROM rental WHERE rental_id = %s", (rental_id,))
    return cur.fetchone()


def mark_returned(cur, rental_id):
    cur.execute(
        "UPDATE rental SET return_date = NOW() WHERE rental_id = %s AND return_date IS NULL",
        (rental_id,),
    )
    return cur.rowcount
