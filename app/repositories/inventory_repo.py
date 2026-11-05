"""Repositorio: SQL puro y 100 % parametrizado. No hace commit: eso lo decide el servicio."""


def customer_exists(cur, customer_id):
    cur.execute("SELECT 1 FROM customer WHERE customer_id = %s", (customer_id,))
    return cur.fetchone() is not None


def staff_exists(cur, staff_id):
    cur.execute("SELECT 1 FROM staff WHERE staff_id = %s", (staff_id,))
    return cur.fetchone() is not None


def get_inventory_rate(cur, inventory_id):
    """Tarifa de la película asociada a la copia (fuente de verdad: MySQL)."""
    cur.execute(
        "SELECT f.rental_rate FROM inventory i "
        "JOIN film f ON f.film_id = i.film_id WHERE i.inventory_id = %s",
        (inventory_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def is_in_stock(cur, inventory_id):
    cur.execute("SELECT inventory_in_stock(%s)", (inventory_id,))
    return bool(cur.fetchone()[0])

