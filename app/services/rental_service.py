"""Lógica de negocio de alquileres.

Checkout = una sola transacción: rental + payment, un único COMMIT y ROLLBACK ante
cualquier error. El monto lo calcula el servidor a partir de film.rental_rate.

NOTA (Parte C): esta versión todavía NO tiene control de concurrencia; la verificación
de stock y el INSERT no están protegidos con bloqueo (condición de carrera a demostrar).
"""
import logging

from app.db import get_connection
from app.errors import ConflictError, NotFoundError, UnavailableError
from app.repositories import inventory_repo, rental_repo

logger = logging.getLogger(__name__)


def _serialize_rental(row):
    return {
        "rental_id": row["rental_id"],
        "rental_date": row["rental_date"].isoformat() if row["rental_date"] else None,
        "inventory_id": row["inventory_id"],
        "customer_id": row["customer_id"],
        "return_date": row["return_date"].isoformat() if row["return_date"] else None,
        "staff_id": row["staff_id"],
    }


def checkout(customer_id, inventory_id, staff_id):
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            conn.start_transaction()

            if not inventory_repo.customer_exists(cur, customer_id):
                raise NotFoundError("El cliente no existe")
            if not inventory_repo.staff_exists(cur, staff_id):
                raise NotFoundError("El empleado no existe")
            amount = inventory_repo.get_inventory_rate(cur, inventory_id)
            if amount is None:
                raise NotFoundError("La copia de inventario no existe")
            if not inventory_repo.is_in_stock(cur, inventory_id):
                raise UnavailableError()

            rental_id = rental_repo.insert_rental(cur, inventory_id, customer_id, staff_id)
            payment_id = rental_repo.insert_payment(cur, customer_id, staff_id, rental_id, amount)

            conn.commit()  # ÚNICO commit: rental y payment se confirman juntos
        except Exception:
            conn.rollback()  # cualquier fallo deshace TODO (atomicidad)
            raise
        finally:
            cur.close()

    logger.info("Checkout OK rental_id=%s payment_id=%s amount=%s",
                rental_id, payment_id, amount)
    return {
        "rental_id": rental_id,
        "payment_id": payment_id,
        "customer_id": customer_id,
        "inventory_id": inventory_id,
        "staff_id": staff_id,
        "amount": str(amount),
    }


def get_rental(rental_id):
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            row = rental_repo.get_rental(cur, rental_id)
        finally:
            cur.close()
    if row is None:
        raise NotFoundError("El alquiler no existe")
    return _serialize_rental(row)


def return_rental(rental_id):
    """Reemplazo del borrado físico: registrar la devolución (return_date)."""
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
            if rental_repo.get_rental(cur, rental_id) is None:
                raise NotFoundError("El alquiler no existe")
            if rental_repo.mark_returned(cur, rental_id) == 0:
                raise ConflictError("El alquiler ya fue devuelto")
            row = rental_repo.get_rental(cur, rental_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    return _serialize_rental(row)
