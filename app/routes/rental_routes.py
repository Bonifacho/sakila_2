"""Rutas HTTP de alquileres. Solo traducen HTTP <-> servicio; sin SQL ni lógica de negocio."""
from flask import Blueprint, request

from app.errors import ValidationError, success
from app.services import rental_service
from app.validators import INT_MAX, parse_checkout, parse_int

bp = Blueprint("rentals", __name__, url_prefix="/api")


@bp.post("/checkout")
def checkout():
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("Se esperaba un cuerpo JSON (Content-Type: application/json)")
    data = parse_checkout(payload)
    result = rental_service.checkout(**data)
    return success(result, 201)


@bp.get("/rentals/<rental_id>")
def get_rental(rental_id):
    rid = parse_int(rental_id, "rental_id", 1, INT_MAX)
    return success(rental_service.get_rental(rid))


@bp.patch("/rentals/<rental_id>/return")
def return_rental(rental_id):
    rid = parse_int(rental_id, "rental_id", 1, INT_MAX)
    return success(rental_service.return_rental(rid))

