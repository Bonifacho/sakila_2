"""Rutas REST del catálogo documental en MongoDB (Parte E)."""
from flask import Blueprint, request
from config import Config
from app.errors import success
from app.services import catalog_service
from app.validators import (
    SMALLINT_MAX,
    parse_float,
    parse_int,
    parse_pagination,
    parse_str_filter,
)

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/catalog")
def list_catalog():
    category = parse_str_filter(request.args.get("category"), "category", 60)
    actor = parse_str_filter(request.args.get("actor"), "actor", 100)
    raw_rate = request.args.get("max_rate")
    max_rate = parse_float(raw_rate, "max_rate", 0.0, 999.99) if raw_rate is not None else None
    page, page_size = parse_pagination(request.args, default_size=20, max_size=Config.MAX_PAGE_SIZE)

    data = catalog_service.search_catalog(
        category=category,
        actor=actor,
        max_rate=max_rate,
        page=page,
        page_size=page_size,
    )
    return success(data, 200)


@bp.get("/catalog/<int:film_id>")
def get_catalog_item(film_id):
    valid_id = parse_int(film_id, "film_id", 1, SMALLINT_MAX)
    doc = catalog_service.get_catalog_film(valid_id)
    return success(doc, 200)


@bp.post("/catalog/sync/<int:film_id>")
def sync_catalog_item(film_id):
    valid_id = parse_int(film_id, "film_id", 1, SMALLINT_MAX)
    doc = catalog_service.sync_film(valid_id)
    return success({"synced": True, "film": doc}, 200)

