"""Servicio de Catálogo Documental y Sincronización Híbrida (Parte E).

Responsabilidades:
- Servir consultas de lectura rápida desde MongoDB (Modelo de Consulta CQRS).
- Ejecutar `sync_film(film_id)` leyendo la Fuente de Verdad desde MySQL y
  actualizando el documento correspondiente en MongoDB.
"""
import logging
from app.db import get_connection
from app.errors import NotFoundError
from app.repositories import catalog_repo

logger = logging.getLogger(__name__)


def search_catalog(category=None, actor=None, max_rate=None, page=1, page_size=20):
    """Busca películas en la colección MongoDB con filtros opcionales y paginación."""
    total, items = catalog_repo.find_films_in_mongo(
        category=category,
        actor=actor,
        max_rate=max_rate,
        page=page,
        page_size=page_size,
    )
    return {
        "filters": {
            "category": category,
            "actor": actor,
            "max_rate": max_rate,
        },
        "page": page,
        "page_size": page_size,
        "total": total,
        "count": len(items),
        "items": items,
    }


def get_catalog_film(film_id: int):
    """Obtiene una película por su ID directamente desde el catálogo de MongoDB."""
    doc = catalog_repo.get_film_from_mongo(film_id)
    if not doc:
        raise NotFoundError(f"Película {film_id} no encontrada en el catálogo documental")
    return doc


def sync_film(film_id: int) -> dict:
    """Sincroniza una película específica desde MySQL (Fuente de Verdad) hacia MongoDB.

    1. Abre conexión del pool hacia MySQL.
    2. Extrae los datos actuales de `film`, `language`, `category` y `actor`.
    3. Reemplaza el documento `_id = film_id` en `sakila_catalog.films`.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            doc = catalog_repo.fetch_film_from_mysql(cur, film_id)
            if doc is None:
                raise NotFoundError(f"La película film_id={film_id} no existe en MySQL")
        finally:
            cur.close()

    catalog_repo.upsert_film_in_mongo(doc)
    logger.info(
        "Sincronización exitosa: film_id=%s (%s) -> rental_rate=%s en MongoDB",
        film_id,
        doc["title"],
        doc["rental_rate"],
    )
    return doc

