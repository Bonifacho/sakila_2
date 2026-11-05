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


def lock_inventory_for_update(cur, inventory_id):
    """Bloqueo pesimista exclusivo (X-lock) sobre la fila de inventario para serializar reservas."""
    cur.execute(
        "SELECT inventory_id FROM inventory WHERE inventory_id = %s FOR UPDATE;",
        (inventory_id,),
    )
    row = cur.fetchone()
    return row is not None


def is_inventory_currently_rented(cur, inventory_id):
    """Comprueba si existe un alquiler activo no devuelto para este ejemplar físico.
    
    IMPORTANTE: Se utiliza 'FOR UPDATE' (Current Read / Locking Read) para que bajo
    el nivel de aislamiento REPEATABLE READ de InnoDB la consulta no lea un snapshot
    obsoleto, sino la versión más reciente confirmada por transacciones concurrentes.
    """
    cur.execute(
        "SELECT COUNT(*) FROM rental WHERE inventory_id = %s AND return_date IS NULL FOR UPDATE;",
        (inventory_id,),
    )
    count = cur.fetchone()[0]
    return count > 0

